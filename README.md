# devin-issue-automation
Event-driven Automation that delegates engineering issues to Devin.

## What it does

1. A GitHub issue is created and reviewed.
2. An engineer adds the `devin-ready` label.
3. GitHub sends a webhook to this service.
4. The service creates a Devin session through the Devin API.
5. Devin investigates the issue, edits the repository, runs tests, and opens a pull request.
6. The service exposes task status through `/status`.

## Architecture

GitHub Issue
→ `devin-ready`
→ GitHub Webhook
→ FastAPI service
→ Devin API
→ Devin session
→ Pull Request

## Example

This project was tested against a fork of Apache Superset

Issue:
Narrow overly broad exception handling in Rison filter parsing.

Devin:
- inspected the existing implementation
- narrowed exception handling to the Rison parser error
- added tests
- ran 17 unit tests
- created a pull request

## Observability

`GET /status`

Returns:
- total tasks
- active tasks
- successful tasks
- failed tasks
- pull requests created
- success rate

`GET /status/{issue_number}`

Returns the latest Devin session status and pull request information for a specific issue.

## Setup

Create a `.env` file:

DEVIN_API_KEY=...
DEVIN_ORG_ID=...

Install dependencies:

pip install -r requirements.txt

Run locally:

uvicorn app:app --port 8000

## Docker

Build:

docker build -t devin-issue-automation .

Run:

docker run --env-file .env -p 8000:8000 devin-issue-automation

## GitHub Webhook

Configure a repository webhook to:

POST /github-webhook

Subscribe to `Issues` events.

The automation only starts when:
- action = `labeled`
- label = `devin-ready`
