import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

app = FastAPI(
    title="Devin Issue Automation",
    description="Event-driven GitHub issue remediation powered by Devin.",
    version="1.0.0",
)

DEVIN_API_KEY = os.environ["DEVIN_API_KEY"]
DEVIN_ORG_ID = os.environ["DEVIN_ORG_ID"]
DEVIN_BASE_URL = "https://api.devin.ai/v3"

TASKS_FILE = Path("tasks.json")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_tasks() -> dict:
    """Load previously tracked remediation tasks from disk."""
    if not TASKS_FILE.exists():
        return {}

    with open(TASKS_FILE, "r") as file:
        data = json.load(file)

    return {
        int(issue_number): task
        for issue_number, task in data.items()
    }


def save_tasks() -> None:
    """Persist remediation task state to disk."""
    with open(TASKS_FILE, "w") as file:
        json.dump(tasks, file, indent=2)


tasks = load_tasks()


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def parse_timestamp(timestamp: str | None) -> datetime | None:
    if not timestamp:
        return None

    return datetime.fromisoformat(timestamp)


def format_duration(seconds: float | None) -> str | None:
    """Return duration."""
    if seconds is None:
        return None

    total_seconds = int(seconds)

    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}h {minutes}m {seconds}s"

    if minutes:
        return f"{minutes}m {seconds}s"

    return f"{seconds}s"


def calculate_time_to_pr(task: dict) -> float | None:
    """Calculate elapsed time from delegation to first observed pull request."""
    started_at = parse_timestamp(task.get("started_at"))
    completed_at = parse_timestamp(task.get("completed_at"))

    if not started_at or not completed_at:
        return None

    return (completed_at - started_at).total_seconds()


def enrich_task_metrics(task: dict) -> dict:
    result = task.copy()

    time_to_pr_seconds = calculate_time_to_pr(task)

    result["time_to_pr_seconds"] = time_to_pr_seconds
    result["time_to_pr"] = format_duration(time_to_pr_seconds)

    return result


# ---------------------------------------------------------------------------
# Devin API
# ---------------------------------------------------------------------------

def create_devin_session(issue: dict, repository: dict) -> dict:
    """Delegate a GitHub engineering issue to Devin."""
    issue_number = issue.get("number")
    issue_title = issue.get("title")
    issue_body = issue.get("body") or ""
    issue_url = issue.get("html_url")

    repo_name = repository.get("full_name")
    repo_url = repository.get("html_url")

    prompt = f"""
You are working on GitHub issue #{issue_number} in repository {repo_name}.

Repository:
{repo_url}

Issue:
{issue_url}

Title:
{issue_title}

Description:
{issue_body}

Please:

1. Investigate the issue and relevant code.
2. Before making changes, ensure your working branch is based on the latest
   upstream default branch. Fetch the latest upstream changes and safely
   rebase or otherwise synchronize the working branch as appropriate.
3. Implement the fix described in the issue.
4. Add or update tests as needed.
5. Run the relevant tests.
6. Before creating the pull request, verify the branch is still up to date
   with the upstream default branch. If upstream changed during the session,
   safely synchronize again and resolve any conflicts without discarding
   unrelated upstream changes.
7. Create a pull request with your changes.
8. In the pull request, briefly explain:
   - what changed
   - how the change was verified
   - what tests were run

Do not make unrelated changes.
Do not force-push or rewrite shared upstream history.
"""

    response = requests.post(
        f"{DEVIN_BASE_URL}/organizations/{DEVIN_ORG_ID}/sessions",
        headers={
            "Authorization": f"Bearer {DEVIN_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "prompt": prompt,
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def get_devin_session(session_id: str) -> dict:
    """
    Retrieve the current state of an existing Devin session.
    """
    response = requests.get(
        f"{DEVIN_BASE_URL}/organizations/{DEVIN_ORG_ID}/sessions/{session_id}",
        headers={
            "Authorization": f"Bearer {DEVIN_API_KEY}",
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


# ---------------------------------------------------------------------------
# GitHub webhook
# ---------------------------------------------------------------------------

@app.post("/github-webhook")
async def github_webhook(request: Request):
    """
    Delegate a GitHub issue to Devin when the `devin-ready` label is added.
    """
    payload = await request.json()

    action = payload.get("action")
    label = payload.get("label", {}).get("name")

    issue = payload.get("issue", {})
    repository = payload.get("repository", {})

    # The label acts as the explicit human-to-agent delegation boundary.
    if action != "labeled" or label != "devin-ready":
        return {
            "status": "ignored",
            "reason": "Event was not a devin-ready delegation.",
            "action": action,
            "label": label,
        }

    issue_number = issue.get("number")

    # Prevent accidental duplicate Devin sessions for the same issue.
    if issue_number in tasks:
        return {
            "status": "already_exists",
            "task": enrich_task_metrics(tasks[issue_number]),
        }

    now = datetime.now(timezone.utc).isoformat()

    try:
        session = create_devin_session(issue, repository)

        tasks[issue_number] = {
            "issue_number": issue_number,
            "issue_title": issue.get("title"),
            "issue_url": issue.get("html_url"),
            "repository": repository.get("full_name"),

            # Devin execution state
            "session_id": session.get("session_id"),
            "session_url": session.get("url"),
            "devin_status": session.get("status"),

            # Engineering workflow outcome
            "outcome": "in_progress",
            "pull_requests": session.get("pull_requests", []),

            # Timing
            "started_at": now,
            "completed_at": None,
            "updated_at": now,
        }

        save_tasks()

        print(
            f"Delegated issue #{issue_number} to Devin "
            f"({session.get('session_id')})"
        )

        return {
            "status": "started",
            "task": enrich_task_metrics(tasks[issue_number]),
        }

    except requests.RequestException as error:
        tasks[issue_number] = {
            "issue_number": issue_number,
            "issue_title": issue.get("title"),
            "issue_url": issue.get("html_url"),
            "repository": repository.get("full_name"),

            "devin_status": "failed_to_start",
            "outcome": "failed",
            "pull_requests": [],

            "error": str(error),

            "started_at": now,
            "completed_at": None,
            "updated_at": now,
        }

        save_tasks()

        return {
            "status": "error",
            "message": str(error),
        }



# ---------------------------------------------------------------------------
# Background status refresh
# ---------------------------------------------------------------------------

def refresh_task(issue_number: int, task: dict) -> None:
    """Refresh one tracked task from Devin and persist the latest state."""
    session_id = task.get("session_id")

    if not session_id:
        return

    try:
        session = get_devin_session(session_id)

        current_prs = session.get("pull_requests", [])

        task["devin_status"] = session.get("status")
        task["pull_requests"] = current_prs
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        # First PR is our observable prototype completion event.
        if current_prs:
            task["outcome"] = "pr_created"

            # Record completion only once so time-to-PR remains stable.
            if not task.get("completed_at"):
                task["completed_at"] = (
                    datetime.now(timezone.utc).isoformat()
                )

        elif task["devin_status"] in ["new", "running"]:
            task["outcome"] = "in_progress"

        save_tasks()

    except requests.RequestException as error:
        task["status_check_error"] = str(error)
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_tasks()


async def poll_active_devin_sessions() -> None:
    """Refresh active Devin sessions every 30 seconds."""
    while True:
        active_tasks = [
            (issue_number, task)
            for issue_number, task in tasks.items()
            if task.get("outcome") == "in_progress"
        ]

        for issue_number, task in active_tasks:
            refresh_task(issue_number, task)

        await asyncio.sleep(30)


@app.on_event("startup")
async def start_status_poller():
    """Start the lightweight background status poller."""
    asyncio.create_task(poll_active_devin_sessions())


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

@app.get("/active")
def active_tasks():
    """Return all remediation tasks that are currently in progress."""
    active = [
        task
        for task in tasks.values()
        if task.get("outcome") == "in_progress"
    ]

    return {
        "active_count": len(active),
        "active_tasks": [
            enrich_task_metrics(task)
            for task in active
        ],
    }


@app.get("/status")
def status():
    """
    Engineering-leader view of the automation.

    Answers:
    - How much work has been delegated?
    - How much produced reviewable PRs?
    - How much is still active or failed?
    - How quickly are PRs being produced?
    """
    task_list = list(tasks.values())

    total_tasks = len(task_list)

    tasks_with_prs = [
        task
        for task in task_list
        if task.get("pull_requests")
    ]

    failed_tasks = [
        task
        for task in task_list
        if task.get("outcome") == "failed"
    ]

    active_tasks = [
        task
        for task in task_list
        if not task.get("pull_requests")
        and task.get("outcome") != "failed"
    ]

    prs_created = sum(
        len(task.get("pull_requests", []))
        for task in task_list
    )

    pr_creation_rate = (
        round((len(tasks_with_prs) / total_tasks) * 100, 1)
        if total_tasks
        else 0
    )

    time_to_pr_values = [
        calculate_time_to_pr(task)
        for task in tasks_with_prs
    ]

    time_to_pr_values = [
        seconds
        for seconds in time_to_pr_values
        if seconds is not None
    ]

    average_time_to_pr_seconds = (
        round(sum(time_to_pr_values) / len(time_to_pr_values), 1)
        if time_to_pr_values
        else None
    )

    return {
        "summary": {
            # Scale / throughput
            "issues_delegated": total_tasks,
            "prs_created": prs_created,

            # Workflow health
            "active_tasks": len(active_tasks),
            "failed_tasks": len(failed_tasks),

            # Observable engineering output
            "pr_creation_rate_percent": pr_creation_rate,

            # Speed
            "average_time_to_pr": format_duration(
                average_time_to_pr_seconds
            ),
            "average_time_to_pr_seconds": average_time_to_pr_seconds,
        },

        "tasks": [
            enrich_task_metrics(task)
            for task in task_list
        ],

        "success_definition": {
            "prototype": (
                "A remediation is considered to have produced an "
                "observable output when Devin creates a pull request."
            ),
            "production": (
                "In production, success should additionally require "
                "CI/test validation and ideally human acceptance or merge."
            ),
        },
    }


@app.get("/status/{issue_number}")
def issue_status(issue_number: int):
    """
    Refresh and return the current state of a single remediation task.
    """
    task = tasks.get(issue_number)

    if not task:
        return {
            "status": "not_found",
            "issue_number": issue_number,
        }

    refresh_task(issue_number, task)

    return enrich_task_metrics(task)


# ---------------------------------------------------------------------------
# Service information
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "service": "Devin Issue Automation",
        "status": "running",
        "purpose": (
            "Automatically delegate approved GitHub engineering issues "
            "to Devin and expose measurable remediation outcomes."
        ),
        "endpoints": {
            "webhook": "POST /github-webhook",
            "all_tasks": "GET /status",
            "active_tasks": "GET /active",
            "single_task": "GET /status/{issue_number}",
        },
    }