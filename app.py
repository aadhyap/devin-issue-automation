import os
from datetime import datetime, timezone

import requests
from fastapi import FastAPI, Request
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

DEVIN_API_KEY = os.environ["DEVIN_API_KEY"]
DEVIN_ORG_ID = os.environ["DEVIN_ORG_ID"]

DEVIN_BASE_URL = "https://api.devin.ai/v3"

tasks = {}


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
        json={"prompt": prompt},
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

    if action != "labeled" or label != "devin-ready":
        return {
            "status": "ignored",
            "action": action,
            "label": label,
        }

    issue_number = issue.get("number")

    try:
        session = create_devin_session(issue, repository)

        tasks[issue_number] = {
            "issue_number": issue_number,
            "issue_title": issue.get("title"),
            "issue_url": issue.get("html_url"),
            "repo": repository.get("full_name"),
            "session_id": session.get("session_id"),
            "session_url": session.get("url"),
            "status": session.get("status"),
            "pull_requests": session.get("pull_requests", []),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

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
            "status": "failed_to_start",
            "error": str(error),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "status": "error",
            "message": str(error),
        }


@app.get("/status")
def status():
    return {
        "total_tasks": len(tasks),
        "tasks": list(tasks.values()),
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

    if session_id:
        try:
            session = get_devin_session(session_id)

            task["status"] = session.get("status")
            task["pull_requests"] = session.get("pull_requests", [])
            task["updated_at"] = datetime.now(timezone.utc).isoformat()

        except requests.RequestException as error:
            task["status_check_error"] = str(error)

    return task