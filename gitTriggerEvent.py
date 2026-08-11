from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/github-webhook")
async def github_webhook(request: Request):
    payload = await request.json()
    print(payload)
    return {"status": "received"}