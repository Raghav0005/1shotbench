import asyncio
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
GEMINI_DEBUG_LOG = Path("proxy_logs/gemini_debug.jsonl")
HTTP_TIMEOUT = httpx.Timeout(connect=30.0, read=600.0, write=120.0, pool=60.0)
FORWARD_MAX_ATTEMPTS = 5

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


def _message_roles_summary(messages: list | None) -> list[str]:
    if not isinstance(messages, list):
        return []
    return [(m.get("role") or "?") for m in messages[:40]]


def log_gemini_debug(payload: dict, status_code: int, response_bytes: bytes, note: str = "") -> None:
    if os.getenv("PROXY_GEMINI_DEBUG", "1").lower() in ("0", "false", "no"):
        return
    GEMINI_DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
    body = response_bytes.decode("utf-8", errors="replace")
    preview = body[:8000]
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": note,
        "model": payload.get("model"),
        "stream": payload.get("stream"),
        "message_roles": _message_roles_summary(payload.get("messages")),
        "message_count": len(payload.get("messages") or []),
        "status_code": status_code,
        "response_preview": preview,
        "response_len": len(response_bytes),
    }
    with GEMINI_DEBUG_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


async def forward_and_log(
    req: Request,
    payload: dict,
    provider: str,
    url: str,
    env_key: str | None,
    *,
    gemini_debug: bool = False,
):
    headers = make_auth_headers(req, env_key)
    response: httpx.Response | None = None
    last_error: str | None = None

    for attempt in range(FORWARD_MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.post(url, json=payload, headers=headers)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(min(2 ** attempt, 30.0))
            continue

        if response is None:
            continue

        if response.status_code == 429 and attempt < FORWARD_MAX_ATTEMPTS - 1:
            ra = response.headers.get("Retry-After")
            try:
                delay = float(ra) if ra else min(2 ** attempt, 60.0)
            except ValueError:
                delay = min(2 ** attempt, 60.0)
            await asyncio.sleep(delay)
            continue

        if response.status_code in (500, 502, 503, 504) and attempt < FORWARD_MAX_ATTEMPTS - 1:
            await asyncio.sleep(min(2 ** attempt, 30.0))
            continue

        break

    if response is None:
        err = last_error or "upstream request failed after retries"
        return Response(
            content=json.dumps({"error": {"message": err, "type": "proxy_error"}}),
            status_code=502,
            media_type="application/json",
        )

    if gemini_debug:
        log_gemini_debug(payload, response.status_code, response.content)

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


def ensure_sequential_tool_calls(payload: dict) -> dict:
    """Force sequential tool execution (OpenAI-compatible). Reduces parallel tool-call
    ordering bugs on several provider adapters (e.g. Anthropic, Kimi thinking + tools)."""
    payload["parallel_tool_calls"] = False
    return payload


def ensure_kimi_reasoning_content(payload: dict) -> dict:
    """Kimi K2.5 with thinking enabled requires full reasoning_content in history for tool
    turns; Codex often drops it. Moonshot recommends either preserving it or disabling
    thinking — we set thinking disabled in kimi_proxy for reliability."""
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return payload
    for msg in messages:
        role = (msg.get("role") or "").lower()
        if role != "assistant":
            continue
        if msg.get("tool_calls") and msg.get("reasoning_content") is None:
            msg["reasoning_content"] = ""
    return payload


def drop_orphan_tool_messages(messages: list) -> list:
    """Remove tool rows that do not belong to the nearest preceding assistant with
    tool_calls (walk backward over tool messages). Drops duplicates of the same
    tool_call_id for that turn. Prevents Anthropic errors where a tool's id is not in
    the *previous* assistant message's tool_calls."""
    if not isinstance(messages, list):
        return messages
    out: list = []
    for m in messages:
        role = (m.get("role") or "").lower()
        if role != "tool":
            out.append(m)
            continue
        tid = m.get("tool_call_id")
        if not isinstance(tid, str):
            continue
        j = len(out) - 1
        anchor_idx = None
        while j >= 0:
            prev = out[j]
            pr = (prev.get("role") or "").lower()
            if pr == "assistant":
                if prev.get("tool_calls"):
                    anchor_idx = j
                break
            if pr in ("user", "system"):
                break
            j -= 1
        if anchor_idx is None:
            continue
        anchor = out[anchor_idx]
        ids = [tc.get("id") for tc in (anchor.get("tool_calls") or []) if isinstance(tc, dict)]
        if tid not in ids:
            continue
        dup = False
        for k in range(anchor_idx + 1, len(out)):
            if (out[k].get("role") or "").lower() != "tool":
                break
            if out[k].get("tool_call_id") == tid:
                dup = True
                break
        if dup:
            continue
        out.append(m)
    return out


def normalize_tool_turns_openai(messages: list) -> list:
    """OpenAI-style chat: after assistant+tool_calls, each following tool message must
    reference a tool_call_id from that assistant, and providers often require **order**
    to match tool_calls[].id. Codex may emit tools in wrong order, duplicate ids, or
    orphan tool rows — Anthropic then errors (id not in previous tool_calls / missing
    responses); MiniMax errors (2013). We: keep only tools whose id is in this turn,
    reorder to match tool_calls order, then stub any missing ids."""
    if not isinstance(messages, list):
        return messages
    out: list = []
    i = 0
    while i < len(messages):
        m = messages[i]
        role = (m.get("role") or "").lower()
        tool_calls = m.get("tool_calls")
        if role != "assistant" or not tool_calls:
            out.append(m)
            i += 1
            continue
        out.append(m)
        needed: list[str] = []
        seen_tc: set[str] = set()
        for tc in tool_calls:
            if isinstance(tc, dict) and tc.get("id"):
                tid = tc["id"]
                if tid not in seen_tc:
                    seen_tc.add(tid)
                    needed.append(tid)
        i += 1
        by_id: dict[str, dict] = {}
        while i < len(messages) and (messages[i].get("role") or "").lower() == "tool":
            tm = messages[i]
            tid = tm.get("tool_call_id")
            if isinstance(tid, str) and tid in needed:
                by_id[tid] = tm
            # Drop tools with unknown ids (orphans break Anthropic / MiniMax)
            i += 1
        stub = "(Tool result not recorded by client.)"
        for tid in needed:
            if tid in by_id:
                out.append(by_id[tid])
            else:
                out.append({"role": "tool", "tool_call_id": tid, "content": stub})
    return out


def fix_messages_for_tools(messages: list) -> list:
    if not isinstance(messages, list):
        return messages
    return normalize_tool_turns_openai(drop_orphan_tool_messages(messages))


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
    if isinstance(payload.get("messages"), list):
        payload["messages"] = fix_messages_for_tools(payload["messages"])
    payload = ensure_sequential_tool_calls(payload)
    return await forward_and_log(
        req=req,
        payload=payload,
        provider="gemini",
        url=GEMINI_URL,
        env_key=GEMINI_API_KEY,
        gemini_debug=True,
    )

def _stringify_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def normalize_messages_minimax(payload):
    """Merge system/developer prompts; preserve full assistant/tool messages (tool_calls,
    tool_call_id). Previous version dropped tool_calls and broke MiniMax tool protocol
    (error 2013). See https://github.com/Kilo-Org/kilocode/issues/3967"""
    if "messages" not in payload:
        return payload

    system_parts: list[str] = []
    new_messages: list = []

    for m in payload["messages"]:
        role = m.get("role")
        if role in ("system", "developer"):
            system_parts.append(_stringify_content(m.get("content")))
            continue
        new_messages.append(dict(m))

    if system_parts:
        new_messages.insert(0, {
            "role": "system",
            "content": "\n\n".join(system_parts),
        })

    payload["messages"] = new_messages
    return payload

@app.post("/minimax/chat/completions")
async def minimax_proxy(req: Request):
    payload = await req.json()
    payload = normalize_messages_minimax(payload)
    if isinstance(payload.get("messages"), list):
        payload["messages"] = fix_messages_for_tools(payload["messages"])
    payload = ensure_sequential_tool_calls(payload)
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
    # Codex does not reliably preserve reasoning_content across tool turns; Kimi K2.5 then
    # errors. Moonshot: use thinking disabled OR preserve reasoning_content in full.
    # https://platform.moonshot.ai/docs/guide/kimi-k2-5-quickstart
    payload["thinking"] = {"type": "disabled"}
    payload = ensure_kimi_reasoning_content(payload)
    if isinstance(payload.get("messages"), list):
        payload["messages"] = fix_messages_for_tools(payload["messages"])
    payload = ensure_sequential_tool_calls(payload)
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
    if isinstance(payload.get("messages"), list):
        payload["messages"] = fix_messages_for_tools(payload["messages"])
    payload = ensure_sequential_tool_calls(payload)
    return await forward_and_log(
        req=req,
        payload=payload,
        provider="claude",
        url=CLAUDE_URL,
        env_key=ANTHROPIC_API_KEY,
    )