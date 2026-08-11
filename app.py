from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/github-webhook")
async def github_webhook(request: Request):
    payload = await request.json()

    action = payload.get("action")
    label = payload.get("label", {}).get("name")
    issue = payload.get("issue", {})

    if action == "labeled" and label == "devin-ready":
        print("devin-ready issue received")
        print("Issue:", issue.get("number"))
        print("Title:", issue.get("title"))
        print("URL:", issue.get("html_url"))

        return {
            "status": "accepted",
            "issue_number": issue.get("number"),
            "title": issue.get("title"),
        }

    print(f"Ignored event: action={action}, label={label}")
    return {"status": "ignored"}