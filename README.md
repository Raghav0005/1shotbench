## Proxy Server

Run the proxy for non-GPT provider request shaping and usage logging:

`uvicorn proxy:app --port 4000 > proxy.txt 2>&1`

Token usage logs are written to:

`usage_logs/usage.jsonl`

Each line stores `timestamp`, `provider`, `request_model`, `response_model`, `status_code`, and token usage fields.

### Tool calling and provider quirks

The proxy applies request tweaks before forwarding:

- **Claude / Gemini / Kimi / MiniMax**: `parallel_tool_calls` is set to `false` where supported.
- **Claude / Gemini / Kimi / MiniMax (tool turns)**: after each `assistant` message with `tool_calls`, the proxy **reorders** `tool` messages to match `tool_calls[].id` order, **drops** tool rows whose `tool_call_id` is not in that turn (orphans confuse Anthropic/MiniMax), and **inserts stubs** only for ids that are still missing. This fixes Anthropic errors like `tool_call_id ... not found in tool_calls of previous message` and MiniMax **2013** (`tool call result does not follow tool call`).
- **Kimi (Moonshot)**: requests set **`"thinking": {"type": "disabled"}`** per the [Kimi K2.5 docs](https://platform.moonshot.ai/docs/guide/kimi-k2-5-quickstart). With thinking enabled, the API requires **`reasoning_content` preserved across tool steps**; Codex often drops it. Disabling thinking avoids that (tradeoff: less chain-of-thought from Kimi). Assistant messages still get `reasoning_content: ""` when present with tools as a fallback.
- **MiniMax**: an earlier version merged every message to `{role, content}` only, which **stripped `tool_calls` and `tool_call_id`** and broke tool protocol (`tool id ... (2013)`). Non-system messages are now copied in full (system/developer merged into one system message). See [kilocode#3967](https://github.com/Kilo-Org/kilocode/issues/3967).

Codex may still print `deprecated: ... wire_api = "responses"` — that is a Codex migration notice; this repo still uses `wire_api = "chat"` with `/chat/completions` on the proxy until a Responses-compatible proxy path exists.

**Gemini with empty stdout**: if the proxy logs `200` but the GUI shows no text, check Codex `stderr` and whether the model returned only tool/reasoning chunks; not always a proxy 4xx.

Restart **`uvicorn proxy:app`** after changing `proxy.py`.

### Retries, timeouts, and Gemini debug logs

- Upstream HTTP uses a **600s read timeout** and **retries** (connection/read errors, **429**, **500/502/503/504**) with exponential backoff so transient **ReadError** / rate limits / MiniMax 5xx are less likely to kill runs.
- **Gemini** (when `PROXY_GEMINI_DEBUG` is not `0`): append-only JSON lines to **`proxy_logs/gemini_debug.jsonl`** with `stream`, message role summary, HTTP status, and a **response preview** (first 8k chars) for debugging empty Codex output.

### Benchmark fairness (Kimi thinking)

Kimi runs with **`thinking: {"type": "disabled"}`** so Codex can complete tool loops without Moonshot’s **`reasoning_content` history** requirement. That is **not** the same as default **Kimi K2.5 with thinking on** (different latency, token mix, and behavior). For fair cross-model tables, either:

- label runs as **“Kimi (thinking off)”**, or  
- run a **separate** benchmark track if you later wire a client that preserves full `reasoning_content` (often impractical with Codex today).

## Benchmark Runner (CLI)

Run one prompt against multiple model workspaces:

`python -m bench.cli --prompt "Your task prompt" --models gpt gemini minimax kimi glm`

Useful options:

- `--mode sequential|parallel`
- `--max-concurrency 2`
- `--timeout-seconds 1800`
- `--retries 1`
- `--warmup`
- `--label e2e-bench-1`

Artifacts are written to:

`runs/<run_id>/`

Each run includes per-model logs/result JSON plus `summary.json`, `summary.csv`, and `summary.md`.

## Benchmark GUI

Start the GUI server:

`uvicorn bench.web:app --port 4010`

Open:

`http://127.0.0.1:4010`

GUI features:

- pick models and run mode (parallel/sequential)
- live side-by-side stdout/stderr streaming
- final comparison table (duration + normalized token/cost metrics)
- recent run history

## Notes on Metrics

- Non-GPT models: metrics are aggregated from `usage_logs/usage.jsonl` in the run time window.
- GPT models: metrics are parsed from inline `Token usage:` output when available; fallback is `npx @ccusage/codex@latest session` (use `conda activate cdx` if `npx` lives in that env).