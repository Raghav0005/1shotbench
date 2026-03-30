import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response
from dotenv import load_dotenv
import json
from datetime import datetime, timezone
from pathlib import Path
load_dotenv()

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
KIMI_URL = "https://api.moonshot.ai/v1/chat/completions"
MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY")
GLM_URL = "https://api.z.ai/api/coding/paas/v4/chat/completions"
Z_AI_API_KEY = os.getenv("Z_AI_API_KEY")
CLAUDE_URL = "https://api.anthropic.com/v1/chat/completions"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
USAGE_LOG_PATH = Path("usage_logs/usage.jsonl")

app = FastAPI()


def make_auth_headers(req: Request, env_key: str | None):
    authorization = req.headers.get("Authorization")
    token = env_key
    if token:
        authorization = f"Bearer {token}"

    headers = {}
    if authorization:
        headers["Authorization"] = authorization
    return headers


def parse_usage(response_bytes: bytes):
    body = response_bytes.decode("utf-8", errors="ignore").strip()
    if not body:
        return None, None

    # Non-stream responses are plain JSON.
    if not body.startswith("data:"):
        try:
            parsed = json.loads(body)
            return parsed.get("model"), parsed.get("usage")
        except json.JSONDecodeError:
            return None, None

    # Streamed responses are SSE lines; usage often arrives in the final chunk.
    model = None
    usage = None
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if not data or data == "[DONE]":
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not model:
            model = chunk.get("model")
        choices = chunk.get("choices", [])
        if choices and choices[0].get("usage"):
            usage = choices[0]["usage"]
        elif chunk.get("usage"):
            usage = chunk["usage"]
    return model, usage


def log_usage(provider: str, request_model: str | None, status_code: int, response_bytes: bytes):
    response_model, usage = parse_usage(response_bytes)
    if not usage:
        return

    USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "request_model": request_model,
        "response_model": response_model,
        "status_code": status_code,
        "usage": usage,
    }
    with USAGE_LOG_PATH.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(event) + "\n")


async def forward_and_log(
    req: Request,
    payload: dict,
    provider: str,
    url: str,
    env_key: str | None,
):
    headers = make_auth_headers(req, env_key)

    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(url, json=payload, headers=headers)

    log_usage(
        provider=provider,
        request_model=payload.get("model"),
        status_code=response.status_code,
        response_bytes=response.content,
    )
    content_type = response.headers.get("content-type", "application/json")
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=content_type.split(";")[0],
    )


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
async def gemini_proxy(req: Request):
    payload = await req.json()
    payload = convert_tools_gemini(payload)
    return await forward_and_log(
        req=req,
        payload=payload,
        provider="gemini",
        url=GEMINI_URL,
        env_key=GEMINI_API_KEY,
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
async def minimax_proxy(req: Request):
    payload = await req.json()
    payload = normalize_messages_minimax(payload)
    return await forward_and_log(
        req=req,
        payload=payload,
        provider="minimax",
        url=MINIMAX_URL,
        env_key=MINIMAX_API_KEY,
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
    return await forward_and_log(
        req=req,
        payload=payload,
        provider="kimi",
        url=KIMI_URL,
        env_key=MOONSHOT_API_KEY,
    )


@app.post("/glm/chat/completions")
async def glm_proxy(req: Request):
    payload = await req.json()
    return await forward_and_log(
        req=req,
        payload=payload,
        provider="glm",
        url=GLM_URL,
        env_key=Z_AI_API_KEY,
    )


@app.post("/claude/chat/completions")
async def claude_proxy(req: Request):
    payload = await req.json()
    return await forward_and_log(
        req=req,
        payload=payload,
        provider="claude",
        url=CLAUDE_URL,
        env_key=ANTHROPIC_API_KEY,
    )