import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request

load_dotenv()

app = FastAPI()

DEVIN_API_KEY = os.environ["DEVIN_API_KEY"]
DEVIN_ORG_ID = os.environ["DEVIN_ORG_ID"]

DEVIN_BASE_URL = "https://api.devin.ai/v3"

TASKS_FILE = Path("tasks.json")


def load_tasks():
    if not TASKS_FILE.exists():
        return {}

    with open(TASKS_FILE, "r") as file:
        data = json.load(file)

    return {
        int(issue_number): task
        for issue_number, task in data.items()
    }


def save_tasks():
    with open(TASKS_FILE, "w") as file:
        json.dump(tasks, file, indent=2)


tasks = load_tasks()


def create_devin_session(issue: dict, repository: dict):
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
2. Implement the fix described in the issue.
3. Add or update tests as needed.
4. Run the relevant tests.
5. Create a pull request with your changes.
6. In the pull request, briefly explain what changed and how you verified it.

Do not make unrelated changes.
"""

    response = requests.post(
        f"{DEVIN_BASE_URL}/organizations/{DEVIN_ORG_ID}/sessions",
        headers={
            "Authorization": f"Bearer {DEVIN_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "prompt": prompt
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def get_devin_session(session_id: str):
    response = requests.get(
        f"{DEVIN_BASE_URL}/organizations/{DEVIN_ORG_ID}/sessions/{session_id}",
        headers={
            "Authorization": f"Bearer {DEVIN_API_KEY}",
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


@app.post("/github-webhook")
async def github_webhook(request: Request):
    payload = await request.json()

    action = payload.get("action")
    label = payload.get("label", {}).get("name")

    issue = payload.get("issue", {})
    repository = payload.get("repository", {})

    # Ignore anything that is not the devin-ready label being added.
    if action != "labeled" or label != "devin-ready":
        return {
            "status": "ignored",
            "action": action,
            "label": label,
        }

    issue_number = issue.get("number")

    # Prevent accidentally creating multiple Devin sessions
    # for the same issue.
    if issue_number in tasks:
        return {
            "status": "already_exists",
            "task": tasks[issue_number],
        }

    try:
        session = create_devin_session(issue, repository)

        tasks[issue_number] = {
            "issue_number": issue_number,
            "issue_title": issue.get("title"),
            "issue_url": issue.get("html_url"),
            "repo": repository.get("full_name"),
            "session_id": session.get("session_id"),
            "session_url": session.get("url"),
            "devin_status": session.get("status"),
            "outcome": "in_progress",
            "pull_requests": session.get("pull_requests", []),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        save_tasks()

        print(f"Started Devin for issue #{issue_number}")
        print(f"Session: {session.get('url')}")

        return {
            "status": "started",
            "task": tasks[issue_number],
        }

    except requests.RequestException as error:
        tasks[issue_number] = {
            "issue_number": issue_number,
            "issue_title": issue.get("title"),
            "issue_url": issue.get("html_url"),
            "repo": repository.get("full_name"),
            "devin_status": "failed_to_start",
            "outcome": "failed",
            "pull_requests": [],
            "error": str(error),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        save_tasks()

        return {
            "status": "error",
            "message": str(error),
        }


@app.get("/status")
def status():
    task_list = list(tasks.values())

    successful_tasks = sum(
        1
        for task in task_list
        if task.get("pull_requests")
    )

    failed_tasks = sum(
        1
        for task in task_list
        if task.get("outcome") == "failed"
    )

    active_tasks = sum(
        1
        for task in task_list
        if not task.get("pull_requests")
        and task.get("outcome") != "failed"
    )

    prs_created = sum(
        len(task.get("pull_requests", []))
        for task in task_list
    )

    success_rate = (
        round((successful_tasks / len(task_list)) * 100, 1)
        if task_list
        else 0
    )

    return {
        "summary": {
            "total_tasks": len(task_list),
            "successful_tasks": successful_tasks,
            "active_tasks": active_tasks,
            "failed_tasks": failed_tasks,
            "prs_created": prs_created,
            "success_rate_percent": success_rate,
        },
        "tasks": task_list,
    }


@app.get("/status/{issue_number}")
def issue_status(issue_number: int):
    task = tasks.get(issue_number)

    if not task:
        return {
            "status": "not_found",
            "issue_number": issue_number,
        }

    session_id = task.get("session_id")

    if not session_id:
        return task

    try:
        session = get_devin_session(session_id)

        task["devin_status"] = session.get("status")
        task["pull_requests"] = session.get("pull_requests", [])
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        if task["pull_requests"]:
            task["outcome"] = "pr_created"
        elif task["devin_status"] in ["new", "running"]:
            task["outcome"] = "in_progress"

        save_tasks()

    except requests.RequestException as error:
        task["status_check_error"] = str(error)
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

        save_tasks()

    return task


@app.get("/")
def root():
    return {
        "service": "Devin Issue Automation",
        "status": "running",
        "endpoints": {
            "webhook": "/github-webhook",
            "all_tasks": "/status",
            "single_task": "/status/{issue_number}",
        },
    }