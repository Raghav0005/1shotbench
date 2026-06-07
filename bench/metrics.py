from __future__ import annotations

import re

from bench.schemas import TokenMetrics


TOKEN_USAGE_PATTERN = re.compile(
    r"Token usage:\s*total=(\d+)\s*input=(\d+)\s*output=(\d+)(?:\s*\(reasoning\s*(\d+)\))?",
    re.IGNORECASE,
)


def extract_inline_token_usage(output: str) -> TokenMetrics | None:
    match = TOKEN_USAGE_PATTERN.search(output)
    if not match:
        return None
    total = int(match.group(1))
    input_t = int(match.group(2))
    output_t = int(match.group(3))
    reasoning_t = int(match.group(4) or 0)
    return TokenMetrics(
        input_tokens=input_t,
        output_tokens=output_t,
        reasoning_tokens=reasoning_t,
        prompt_tokens=input_t,
        total_tokens=total,
        requests=1,
    )
