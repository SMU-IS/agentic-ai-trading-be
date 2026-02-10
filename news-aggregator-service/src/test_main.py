# test_api.py - run this first!
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("PPLX_API_KEY")
if not api_key:
    print("❌ Set PPLX_API_KEY in .env")
    exit(1)

headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
data = {
    "model": "sonar",
    "messages": [{"role": "user", "content": "Say 'API works!'"}]
}

response = httpx.post("https://api.perplexity.ai/chat/completions", headers=headers, json=data)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    print("✅ API KEY WORKS!")
else:
    print(f"❌ Error: {response.text}")
