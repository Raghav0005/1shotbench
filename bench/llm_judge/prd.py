from __future__ import annotations

import re
from pathlib import Path


_SECTION_HEADERS = (
    "success criteria",
    "core requirements",
    "goals",
    "acceptance",
)


def load_prd_context(path: Path | None, max_chars: int = 6000) -> str | None:
    if not path or not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    sections = _extract_sections(text)
    if not sections:
        return _truncate(text, max_chars)
    combined = "\n\n".join(f"## {title}\n{body}" for title, body in sections)
    return _truncate(combined, max_chars)


def _extract_sections(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return []
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        if title.lower() not in _SECTION_HEADERS:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((title, body))
    return sections


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
