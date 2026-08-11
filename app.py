import os
import requests
from fastapi import FastAPI, Request
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

DEVIN_API_KEY = os.environ["DEVIN_API_KEY"]
DEVIN_ORG_ID = os.environ["DEVIN_ORG_ID"]

DEVIN_BASE_URL = "https://api.devin.ai/v3"


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


@app.post("/github-webhook")
async def github_webhook(request: Request):
    payload = await request.json()

    action = payload.get("action")
    label = payload.get("label", {}).get("name")
    issue = payload.get("issue", {})
    repository = payload.get("repository", {})

    print(f"GitHub event received: action={action}, label={label}")

    # Only delegate issues when devin-ready is added.
    if action != "labeled" or label != "devin-ready":
        print("Ignoring event")
        return {
            "status": "ignored",
            "action": action,
            "label": label,
        }

    print(f"Starting Devin for issue #{issue.get('number')}")
    print(f"Title: {issue.get('title')}")

    try:
        session = create_devin_session(issue, repository)

        print("Devin session created")
        print("Session ID:", session.get("session_id"))
        print("Session URL:", session.get("url"))

        return {
            "status": "started",
            "issue_number": issue.get("number"),
            "session_id": session.get("session_id"),
            "session_url": session.get("url"),
        }

    except requests.RequestException as error:
        print("Failed to create Devin session:", error)

        return {
            "status": "error",
            "message": str(error),
        }