import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ["DEVIN_API_KEY"]
org_id = os.environ["DEVIN_ORG_ID"]

url = f"https://api.devin.ai/v3/organizations/{org_id}/sessions"

response = requests.post(
    url,
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    json={
        "prompt": "This is an API connectivity test."
    },
)

print("Status:", response.status_code)
print(response.text)