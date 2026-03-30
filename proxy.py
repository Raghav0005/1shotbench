import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response
from dotenv import load_dotenv
import json
load_dotenv()

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"
MINIMAX_API_KEY = os.environ["MINIMAX_API_KEY"]
KIMI_URL = "https://api.moonshot.ai/v1/chat/completions"
MOONSHOT_API_KEY = os.environ["MOONSHOT_API_KEY"]

app = FastAPI()
def convert_tools_gemini(payload):
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

@app.post("/gemini/chat/completions")
async def proxy(req: Request):
    payload = await req.json()
    payload = convert_tools_gemini(payload)

    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(
            GEMINI_URL,
            json=payload,
            headers={"Authorization": f"Bearer {GEMINI_API_KEY}"}
        )

    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type="application/json"
    )

def normalize_messages_minimax(payload):
    if "messages" not in payload:
        return payload

    system_parts = []
    new_messages = []

    for m in payload["messages"]:
        role = m.get("role")
        content = str(m.get("content", ""))

        # treat developer as system
        if role in ("system", "developer"):
            system_parts.append(content)
            continue

        new_messages.append({
            "role": role,
            "content": content
        })

    # prepend single system message if any existed
    if system_parts:
        new_messages.insert(0, {
            "role": "system",
            "content": "\n\n".join(system_parts)
        })

    payload["messages"] = new_messages
    return payload

@app.post("/minimax/chat/completions")
async def proxy(req: Request):
    payload = await req.json()
    payload = normalize_messages_minimax(payload)
    print(json.dumps(payload["messages"], indent=2))

    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(
            MINIMAX_URL,
            json=payload,
            headers={"Authorization": f"Bearer {MINIMAX_API_KEY}"}
        )
    print(r.content)

    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type="application/json"
    )

def convert_developer_role(payload):
    if "messages" not in payload:
        return payload

    for m in payload["messages"]:
        if m.get("role") == "developer":
            m["role"] = "system"

    return payload

@app.post("/kimi/chat/completions")
async def kimi_proxy(req: Request):
    payload = await req.json()

    payload = convert_developer_role(payload)
    print(json.dumps(payload["messages"], indent=2))
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(
            KIMI_URL,
            json=payload,
            headers={"Authorization": f"Bearer {MOONSHOT_API_KEY}"}
        )

    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type="application/json"
    )