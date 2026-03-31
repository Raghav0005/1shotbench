from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.schemas import TokenMetrics


SESSION_ID_PATTERN = re.compile(r"codex resume ([0-9a-f-]{20,})", re.IGNORECASE)
TOKEN_USAGE_PATTERN = re.compile(
    r"Token usage:\s*total=(\d+)\s*input=(\d+)\s*output=(\d+)\s*\(reasoning\s*(\d+)\)",
    re.IGNORECASE,
)
CCUSAGE_ROW_PATTERN = re.compile(
    r"│\s*[^│]*│\s*[^│]*│\s*[^│]*│\s*[^│]*│\s*([\d,]+)\s*│\s*([\d,]+)\s*│\s*([\d,]+)\s*│\s*([\d,]+)\s*│\s*([\d,]+)\s*│\s*\$?([\d.,]+)\s*│"
)


def parse_iso_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def extract_session_id(output: str) -> str | None:
    match = SESSION_ID_PATTERN.search(output)
    return match.group(1) if match else None


def extract_inline_token_usage(output: str) -> TokenMetrics | None:
    match = TOKEN_USAGE_PATTERN.search(output)
    if not match:
        return None
    total, input_t, output_t, reasoning_t = (int(part) for part in match.groups())
    return TokenMetrics(
        input_tokens=input_t,
        output_tokens=output_t,
        reasoning_tokens=reasoning_t,
        total_tokens=total,
        requests=1,
    )


def _usage_value(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, int):
            return value
    return 0


def _nested_usage_value(usage: dict[str, Any], path: tuple[str, ...]) -> int:
    current: Any = usage
    for key in path:
        if not isinstance(current, dict):
            return 0
        current = current.get(key)
    return current if isinstance(current, int) else 0


def get_non_gpt_metrics(
    usage_log_path: Path,
    provider: str | None,
    model_name: str,
    started_at: str,
    ended_at: str,
) -> TokenMetrics:
    metrics = TokenMetrics()
    if not provider or not usage_log_path.exists():
        return metrics

    window_start = parse_iso_time(started_at)
    window_end = parse_iso_time(ended_at)

    with usage_log_path.open("r", encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_provider = event.get("provider")
            event_model = event.get("response_model") or event.get("request_model") or ""
            if event_provider != provider:
                continue
            if model_name and model_name not in event_model:
                continue

            timestamp = event.get("timestamp")
            if not isinstance(timestamp, str):
                continue
            try:
                event_time = parse_iso_time(timestamp)
            except ValueError:
                continue
            if not (window_start <= event_time <= window_end):
                continue

            usage = event.get("usage") or {}
            input_tokens = _usage_value(
                usage,
                "prompt_tokens",
                "input_tokens",
            )
            output_tokens = _usage_value(
                usage,
                "completion_tokens",
                "output_tokens",
            )
            reasoning_tokens = _usage_value(
                usage,
                "reasoning_tokens",
                "reasoning_output_tokens",
            )
            if reasoning_tokens == 0:
                reasoning_tokens = _nested_usage_value(
                    usage,
                    ("completion_tokens_details", "reasoning_tokens"),
                )
            cache_read_tokens = _usage_value(
                usage,
                "cache_read_tokens",
                "cached_input_tokens",
            )
            if cache_read_tokens == 0:
                cache_read_tokens = _nested_usage_value(
                    usage,
                    ("prompt_tokens_details", "cached_tokens"),
                )
            metrics.input_tokens += input_tokens
            metrics.output_tokens += output_tokens
            metrics.reasoning_tokens += reasoning_tokens
            metrics.cache_read_tokens += cache_read_tokens
            total_tokens = _usage_value(usage, "total_tokens")
            if total_tokens:
                metrics.total_tokens += total_tokens
            else:
                metrics.total_tokens += input_tokens + output_tokens
            metrics.requests += 1
    return metrics


def _parse_number(value: str) -> int:
    return int(value.replace(",", "").strip())


def _parse_money(value: str) -> float:
    cleaned = value.replace("$", "").strip()
    return float(cleaned) if cleaned else 0.0


def get_gpt_metrics_from_ccusage(workspace_path: Path) -> TokenMetrics:
    """
    Fallback parser. It expects the session table format printed by ccusage.
    We take the latest non-total row.
    """
    cmd = ["npx", "@ccusage/codex@latest", "session"]
    if not shutil.which("npx"):
        cmd = ["conda", "run", "-n", "cdx"] + cmd
    proc = subprocess.run(cmd, cwd=str(workspace_path), capture_output=True, text=True, check=False)
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    rows = []
    for match in CCUSAGE_ROW_PATTERN.finditer(output):
        input_t, output_t, reasoning_t, cache_t, total_t, cost = match.groups()
        try:
            rows.append(
                TokenMetrics(
                    input_tokens=_parse_number(input_t),
                    output_tokens=_parse_number(output_t),
                    reasoning_tokens=_parse_number(reasoning_t),
                    cache_read_tokens=_parse_number(cache_t),
                    total_tokens=_parse_number(total_t),
                    cost_usd=_parse_money(cost),
                    requests=1,
                )
            )
        except ValueError:
            continue
    return rows[-1] if rows else TokenMetrics()
