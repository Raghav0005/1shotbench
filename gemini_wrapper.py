import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
API_KEY = os.environ["GEMINI_API_KEY"]

app = FastAPI()
def convert_tools(payload):
    if "tools" not in payload:
        return payload

    clean = []

    for t in payload["tools"]:
        fn = t.get("function", {})

        clean.append({
            "type": "function",
            "function": {
                "name": fn.get("name") or t.get("name"),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {})
            }
        })

    payload["tools"] = clean
    return payload

@app.post("/chat/completions")
async def proxy(req: Request):
    payload = await req.json()
    payload = convert_tools(payload)

    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(
            GEMINI_URL,
            json=payload,
            headers={"Authorization": f"Bearer {API_KEY}"}
        )

    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type="application/json"
    )