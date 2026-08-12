# Devin Issue Automation

An event-driven workflow that delegates GitHub engineering issues to Devin and tracks them through pull request creation.

## Overview

Engineers delegate an issue by adding a single GitHub label:

`devin-ready`

From there, the workflow automatically:

1. Receives the GitHub issue event.
2. Creates a Devin session with the repository and issue context.
3. Instructs Devin to investigate, implement, and test the change.
4. Creates a pull request for human review.
5. Tracks task progress and exposes lightweight observability metrics.

The engineer remains in the loop for code review, CI validation, and approval.

---

## Architecture

```text
GitHub Issue
     │
     │ Add "devin-ready"
     ▼
GitHub Webhook
     │
     ▼
FastAPI Automation Service
     │
     ├── Persist task state
     │
     └── Create Devin session
              │
              ▼
          Devin API
              │
              ▼
     Investigate repository
     Implement change
     Add / update tests
     Run relevant tests
              │
              ▼
        GitHub Pull Request
              │
              ▼
       Human Review + CI

FastAPI Service
     │
     └── /active
         /status
         /status/{issue_number}
              │
              ▼
       Observability / Metrics
```

### Event Flow

```text
devin-ready label
       ↓
 GitHub webhook
       ↓
 FastAPI service
       ↓
 Devin session
       ↓
 Implementation + tests
       ↓
 Pull request
       ↓
 Human review + CI
```

---

## Quick Start

### 1. Clone the repository

```bash
git clone <repository-url>
cd devin-issue-automation
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
DEVIN_API_KEY=your_devin_api_key
DEVIN_ORG_ID=your_devin_org_id
```

Do not commit `.env` to Git.

### 5. Start the FastAPI service

```bash
uvicorn app:app --port 8000
```

The service will be available locally at:

```text
http://localhost:8000
```

### 6. Expose the webhook

For local development, expose port `8000` using a tunneling service such as ngrok:

```bash
ngrok http 8000
```

Copy the generated HTTPS forwarding URL.

For example:

```text
https://<your-tunnel>.ngrok-free.app
```

The GitHub webhook endpoint will be:

```text
https://<your-tunnel>.ngrok-free.app/github-webhook
```

---

## GitHub Webhook Setup

In the GitHub repository that Devin will work against:

1. Go to **Settings → Webhooks**.
2. Select **Add webhook**.
3. Set the Payload URL to:

```text
https://<your-public-url>/github-webhook
```

4. Set the content type to:

```text
application/json
```

5. Subscribe to **Issues** events.
6. Save the webhook.

The automation ignores unrelated issue events and only starts when:

```text
action = labeled
label  = devin-ready
```

---

## Running an Issue

Create or select a GitHub issue with enough context for Devin to investigate.

When the issue is ready for automated remediation, add the label:

```text
devin-ready
```

No additional API call is required.

GitHub sends the webhook to the FastAPI service, which creates a Devin session using the issue and repository context.

Devin is instructed to:

1. Investigate the issue and relevant code.
2. Synchronize its working branch with the latest upstream default branch.
3. Implement the fix.
4. Add or update relevant tests.
5. Run the relevant tests.
6. Verify the branch is still up to date before creating the PR.
7. Create a pull request.
8. Document what changed and how it was verified.

The resulting pull request remains subject to the repository's existing CI and human review process.

---

## Observability

The service exposes lightweight endpoints for monitoring delegated work.

### Active Tasks

```bash
curl -s http://localhost:8000/active | python3 -m json.tool
```

Shows tasks that are currently in progress.

### Overall Status

```bash
curl -s http://localhost:8000/status | python3 -m json.tool
```

Provides aggregate metrics including:

- issues delegated
- active tasks
- failed tasks
- pull requests created
- PR creation rate
- average time to PR

### Individual Issue

```bash
curl -s http://localhost:8000/status/6 | python3 -m json.tool
```

Replace `6` with the GitHub issue number.

Task-level status includes information such as:

- issue number and title
- repository
- Devin session status
- direct Devin session URL
- outcome
- generated pull request
- start time
- completion time
- time to PR

Task state is persisted locally so both in-progress and completed work can continue to be reported.

---

## Success Definition

For this prototype, a remediation has produced an observable output when Devin creates a pull request.

PR creation alone does not necessarily mean the remediation is production-ready.

A production deployment should use a stronger success definition that also incorporates:

- relevant tests passing
- CI status
- human approval
- successful merge

This distinguishes **PR generation** from a fully validated engineering outcome.

---

## Example: Apache Superset

This workflow was tested against a fork of Apache Superset.

One example issue involved overly broad exception handling in the Rison filter parser.

After the issue was labeled `devin-ready`, Devin:

- investigated the existing implementation
- identified the relevant code and tests
- implemented the remediation
- added regression tests
- ran 17 unit tests successfully
- created a pull request for human review

The workflow moved a bounded remediation task from issue delegation to a reviewable change in minutes while preserving the repository's existing CI and human approval gates.

Multiple issues can also be delegated independently, allowing remediation tasks to run concurrently while the automation service tracks their status.

---

## Docker

### Build

```bash
docker build -t devin-issue-automation .
```

### Run

```bash
docker run --env-file .env -p 8000:8000 devin-issue-automation
```

The service will be available at:

```text
http://localhost:8000
```

---

## Design Principles

### Explicit Delegation

Only issues intentionally labeled `devin-ready` trigger the automation. Engineers decide which work is appropriate to delegate.

### Human in the Loop

Devin produces reviewable work rather than bypassing the engineering team's approval process.

### Observable

The service tracks delegated, active, completed, and failed work and exposes metrics for evaluating system effectiveness.

### Traceable

Each tracked task retains its issue information, Devin session, timestamps, outcome, and generated pull request.

### Compatible With Existing Workflows

The automation works within the existing GitHub pull request, CI, testing, and review process rather than replacing those quality gates.

---

## Business Impact

The goal of the workflow is not simply to generate more pull requests.

It is to reduce the engineering effort required to move appropriate, bounded issues from backlog to review.

Instead of manually implementing every remediation task, engineers can delegate selected work with a single label while retaining visibility and approval authority.

This allows engineering teams to spend less time on repetitive remediation work and more time on higher-value engineering decisions.
