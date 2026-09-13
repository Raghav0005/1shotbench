#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
OUTPUT_NAME = "trajectory.jsonl"


def _warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def discover_event_files(paths: Iterable[Path]) -> list[Path]:
    discovered: set[Path] = set()
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"input path does not exist: {path}")
        if path.is_file():
            if path.name != "events.jsonl":
                raise ValueError(f"input file must be named events.jsonl: {path}")
            discovered.add(path.resolve())
            continue
        discovered.update(candidate.resolve() for candidate in path.rglob("events.jsonl"))
    return sorted(discovered, key=lambda item: str(item))


def _load_source_events(events_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with events_path.open(encoding="utf-8") as file_obj:
        for line_number, line in enumerate(file_obj, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                _warn(f"{events_path}:{line_number}: skipping malformed JSON: {exc.msg}")
                continue
            if not isinstance(event, dict):
                _warn(f"{events_path}:{line_number}: skipping non-object event")
                continue
            events.append(event)
    return events


def _load_summary(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return {}
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _warn(f"could not read metadata from {summary_path}: {exc}")
        return {}
    return summary if isinstance(summary, dict) else {}


def _summary_result(summary: dict[str, Any], model_key: str) -> dict[str, Any]:
    for result in summary.get("results") or []:
        if isinstance(result, dict) and result.get("model_key") == model_key:
            return result
    return {}


def _task_from_workspace(workspace: Any) -> str | None:
    if not isinstance(workspace, str) or not workspace:
        return None
    path = Path(workspace)
    if path.name.endswith("-workspace") and path.parent.name:
        return path.parent.name
    return None


def _timestamp_ms(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    return None


def _iso_timestamp(value: int | None) -> str | None:
    if value is None:
        return None
    return (
        datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _tokens(usage: Any) -> dict[str, int] | None:
    if not isinstance(usage, dict) or not usage:
        return None
    input_tokens = int(usage.get("input") or 0)
    cache_read = int(usage.get("cacheRead") or 0)
    cache_write = int(usage.get("cacheWrite") or 0)
    return {
        "input": input_tokens,
        "output": int(usage.get("output") or 0),
        "reasoning": int(usage.get("reasoning") or 0),
        "cache_read": cache_read,
        "cache_write": cache_write,
        "prompt": input_tokens + cache_read + cache_write,
        "total": int(usage.get("totalTokens") or 0),
    }


def _content_text(content: Any) -> str | None:
    if not isinstance(content, list):
        return None
    parts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
    text = "\n".join(part for part in parts if part).strip()
    return text or None


def _result_error(result: Any) -> str | None:
    if isinstance(result, dict):
        text = _content_text(result.get("content"))
        if text:
            return text
        if not result:
            return None
        return json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if result is None:
        return None
    return str(result)


def command_action(tool: str | None, arguments: dict[str, Any]) -> str | None:
    if tool == "bash":
        command = arguments.get("command")
        return command if isinstance(command, str) else None
    if tool in {"read", "write", "edit", "ls"}:
        path = arguments.get("path")
        return path if isinstance(path, str) else None
    if tool in {"find", "grep"}:
        pattern = arguments.get("pattern")
        path = arguments.get("path")
        if pattern and path:
            return f"{pattern} in {path}"
        return str(pattern or path) if pattern or path else None
    if not arguments:
        return None
    return json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_SHELL_PUNCTUATION = "<>;&|()\n"
_SHELL_SEPARATORS = {";", "&", "&&", "|", "||", "(", ")", "\n"}
_RUNNER_COMMANDS = {"npm", "pnpm", "yarn", "bun", "cargo", "make", "git", "npx", "uv"}
_OPTIONS_WITH_VALUES = {"--cwd", "--dir", "--filter", "--prefix", "--workspace", "-C", "-F", "-w"}


def _shell_tokens(text: str, punctuation: str, *, preserve_newlines: bool = False) -> list[str]:
    try:
        lexer = shlex.shlex(text, posix=True, punctuation_chars=punctuation)
        if preserve_newlines:
            lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return []


def _heredoc_declarations(line: str) -> list[tuple[str, bool]]:
    tokens = _shell_tokens(line, "<>;&|()")
    declarations: list[tuple[str, bool]] = []
    for index, token in enumerate(tokens[:-1]):
        if token != "<<":
            continue
        delimiter = tokens[index + 1]
        strip_tabs = delimiter.startswith("-")
        delimiter = delimiter.removeprefix("-")
        if delimiter and delimiter not in _SHELL_SEPARATORS:
            declarations.append((delimiter, strip_tabs))
    return declarations


def _without_heredoc_bodies(command: str) -> str:
    kept: list[str] = []
    pending: list[tuple[str, bool]] = []
    for line in command.splitlines(keepends=True):
        if pending:
            delimiter, strip_tabs = pending[0]
            candidate = line.rstrip("\r\n")
            if strip_tabs:
                candidate = candidate.lstrip("\t")
            if candidate == delimiter:
                pending.pop(0)
            kept.append("\n" if line.endswith(("\n", "\r")) else "")
            continue
        kept.append(line)
        pending.extend(_heredoc_declarations(line))
    return "".join(kept)


def _shell_segments(command: str) -> Iterable[list[str]]:
    segment: list[str] = []
    tokens = _shell_tokens(
        _without_heredoc_bodies(command),
        _SHELL_PUNCTUATION,
        preserve_newlines=True,
    )
    for token in tokens:
        if token in _SHELL_SEPARATORS:
            if segment:
                yield segment
                segment = []
        else:
            segment.append(token)
    if segment:
        yield segment


def _command_tokens(tokens: list[str]) -> list[str]:
    cleaned: list[str] = []
    skip_target = False
    for token in tokens:
        if skip_target:
            skip_target = False
            continue
        if ("<" in token or ">" in token) and set(token) <= set("<>&|"):
            if cleaned and cleaned[-1].isdigit():
                cleaned.pop()
            skip_target = True
            continue
        cleaned.append(token)

    tokens = cleaned
    while tokens and "=" in tokens[0] and not tokens[0].startswith(("/", "./")):
        tokens.pop(0)
    if tokens and Path(tokens[0]).name == "sudo":
        tokens.pop(0)
    return tokens


def _positional_args(args: list[str]) -> list[str]:
    positional: list[str] = []
    skip_value = False
    for arg in args:
        if skip_value:
            skip_value = False
        elif arg in _OPTIONS_WITH_VALUES:
            skip_value = True
        elif not arg.startswith("-"):
            positional.append(arg)
    return positional


def _shell_command_identifiers(command: str) -> str:
    identifiers: list[str] = []
    for segment in _shell_segments(command):
        tokens = _command_tokens(segment)
        if not tokens:
            continue

        executable = Path(tokens[0]).name.lower()
        identifiers.append(executable)
        args = tokens[1:]
        if executable in _RUNNER_COMMANDS:
            subcommands = _positional_args(args)
            identifiers.extend(Path(arg).name.lower() for arg in subcommands[:2])
        elif executable.startswith("python") or executable == "node":
            if any(arg in {"-c", "-e", "--eval"} for arg in args):
                continue
            identifiers.extend(arg.removeprefix("--") for arg in args if arg in {"--check", "--test"})
            for index, arg in enumerate(args):
                if arg == "-m" and index + 1 < len(args):
                    identifiers.append(args[index + 1].lower())
                    break
                if not arg.startswith("-"):
                    identifiers.append(Path(arg).name.lower())
                    break
        elif executable == "java":
            skip_next = False
            for index, arg in enumerate(args):
                if skip_next:
                    skip_next = False
                    continue
                if arg == "-jar" and index + 1 < len(args):
                    identifiers.append(Path(args[index + 1]).name.lower())
                    break
                if arg in {"-cp", "-classpath", "--class-path"}:
                    skip_next = True
                    continue
                if not arg.startswith("-"):
                    identifiers.append(Path(arg).name.lower())
                    break

    return " ".join(re.sub(r"[^a-z0-9]+", " ", value) for value in identifiers)


def shell_files_touched(command: str) -> list[str]:
    touched: list[str] = []

    redirect_tokens = _shell_tokens(
        _without_heredoc_bodies(command),
        _SHELL_PUNCTUATION,
        preserve_newlines=True,
    )
    for index, token in enumerate(redirect_tokens[:-1]):
        if token not in {">", ">>"}:
            continue
        candidate = redirect_tokens[index + 1]
        if (
            candidate not in _SHELL_SEPARATORS | {"-", "/dev/null"}
            and not candidate.startswith("&")
        ):
            touched.append(candidate)

    for segment in _shell_segments(command):
        tokens = _command_tokens(segment)
        if not tokens:
            continue
        executable = Path(tokens[0]).name
        args = [token for token in tokens[1:] if not token.startswith("-")]
        if executable in {"touch", "mkdir", "rm", "rmdir"}:
            touched.extend(args)
        elif executable in {"cp", "mv", "install"} and args:
            touched.append(args[-1])
        elif executable == "tee":
            touched.extend(args)
        elif executable == "sed" and any(token == "-i" or token.startswith("-i") for token in tokens[1:]):
            touched.extend(args[-1:])

    return list(dict.fromkeys(touched))


def files_touched(tool: str | None, arguments: dict[str, Any]) -> list[str]:
    if tool in {"write", "edit"} and isinstance(arguments.get("path"), str):
        return [arguments["path"]]
    if tool == "bash" and isinstance(arguments.get("command"), str):
        return shell_files_touched(arguments["command"])
    return []


def semantic_action(tool: str | None, action: str | None, touched: list[str]) -> str | None:
    if tool in {"write", "edit"}:
        return "edit"
    if tool == "read":
        return "read"
    if tool in {"find", "grep", "search"}:
        return "search"
    if tool == "ls":
        return "inspect"
    if tool != "bash":
        return "execute" if tool else None

    command_identifiers = _shell_command_identifiers(action or "")
    if re.search(r"\b(trec ?eval|evaluator|judge|benchmark|eval(?:uate)?)\b", command_identifiers):
        return "evaluate"
    if re.search(r"\b(pytest|unittest|test|lint|tsc|typecheck|compile|build|check)\b", command_identifiers):
        return "validate"
    if re.search(r"\b(lsof|netstat|ps|pgrep|diagnos|debug|stacktrace|traceback)\b", command_identifiers):
        return "debug"
    if touched or re.search(r"\b(touch|mkdir|rm|rmdir|mv|cp|install|chmod|chown|patch)\b", command_identifiers):
        return "edit"
    if re.search(r"\b(rg|grep|find|fd)\b", command_identifiers):
        return "search"
    if re.search(r"\b(pwd|ls|which|whereis|status|diff|version)\b", command_identifiers):
        return "inspect"
    if re.search(r"\b(cat|head|tail|less|more|sed)\b", command_identifiers):
        return "read"
    return "execute"


def _source_display_path(events_path: Path) -> str:
    try:
        return str(events_path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(events_path.resolve())


def parse_events(events_path: Path, summary: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    events_path = events_path.resolve()
    run_dir = events_path.parent.parent
    run_id = run_dir.name
    model_key = events_path.parent.name
    events = _load_source_events(events_path)
    summary = summary or {}
    result_metadata = _summary_result(summary, model_key)

    session_cwd = next(
        (event.get("cwd") for event in events if event.get("type") == "session" and event.get("cwd")),
        None,
    )
    task = _task_from_workspace(result_metadata.get("workspace_path")) or _task_from_workspace(session_cwd)
    model = result_metadata.get("model_name")
    if not model:
        model = next(
            (
                (event.get("message") or {}).get("model")
                for event in events
                if event.get("type") == "message_end"
                and (event.get("message") or {}).get("role") == "assistant"
                and (event.get("message") or {}).get("model")
            ),
            model_key,
        )

    starts: dict[str, dict[str, Any]] = {}
    ends: dict[str, dict[str, Any]] = {}
    result_timestamps: dict[str, int] = {}
    result_messages: dict[str, dict[str, Any]] = {}
    assistant_messages: list[dict[str, Any]] = []

    for event in events:
        event_type = event.get("type")
        if event_type == "tool_execution_start" and event.get("toolCallId"):
            starts[event["toolCallId"]] = event
        elif event_type == "tool_execution_end" and event.get("toolCallId"):
            ends[event["toolCallId"]] = event
        elif event_type == "message_end":
            message = event.get("message") or {}
            if message.get("role") == "assistant":
                assistant_messages.append(message)
            elif message.get("role") == "toolResult" and message.get("toolCallId"):
                call_id = message["toolCallId"]
                result_messages[call_id] = message
                timestamp = _timestamp_ms(message.get("timestamp"))
                if timestamp is not None:
                    result_timestamps[call_id] = timestamp

    rows: list[dict[str, Any]] = []
    common = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "task": task,
        "model": model,
        "model_key": model_key,
        "source_events_path": _source_display_path(events_path),
    }
    for assistant_step, message in enumerate(assistant_messages, start=1):
        content = message.get("content") or []
        calls = [item for item in content if isinstance(item, dict) and item.get("type") == "toolCall"]
        start_ms = _timestamp_ms(message.get("timestamp"))
        usage = _tokens(message.get("usage"))
        if not calls:
            rows.append(
                {
                    **common,
                    "record_type": "assistant",
                    "step": len(rows) + 1,
                    "assistant_step": assistant_step,
                    "timestamp": _iso_timestamp(start_ms),
                    "tool_call_id": None,
                    "tool": None,
                    "command_action": _content_text(content),
                    "arguments": {},
                    "semantic_action": None,
                    "success": None,
                    "error": None,
                    "duration_ms": None,
                    "tokens": usage,
                    "files_touched": [],
                    "parallel_index": 0,
                    "parallel_count": 0,
                }
            )
            continue

        for parallel_index, call in enumerate(calls):
            call_id = call.get("id")
            start_event = starts.get(call_id, {})
            end_event = ends.get(call_id, {})
            result_message = result_messages.get(call_id, {})
            tool = call.get("name") or start_event.get("toolName")
            arguments = call.get("arguments") or start_event.get("args") or {}
            if not isinstance(arguments, dict):
                arguments = {"value": arguments}
            action = command_action(tool, arguments)
            touched = files_touched(tool, arguments)
            has_end = bool(end_event) or bool(result_message)
            is_error = bool(end_event.get("isError") or result_message.get("isError"))
            error = None
            if is_error:
                error = _result_error(end_event.get("result")) or _content_text(result_message.get("content"))
            end_ms = result_timestamps.get(call_id)
            duration_ms = None
            if start_ms is not None and end_ms is not None:
                duration_ms = max(0, end_ms - start_ms)
            rows.append(
                {
                    **common,
                    "record_type": "tool",
                    "step": len(rows) + 1,
                    "assistant_step": assistant_step,
                    "timestamp": _iso_timestamp(start_ms),
                    "tool_call_id": call_id,
                    "tool": tool,
                    "command_action": action,
                    "arguments": arguments,
                    "semantic_action": semantic_action(tool, action, touched),
                    "success": (not is_error) if has_end else None,
                    "error": error,
                    "duration_ms": duration_ms,
                    "tokens": usage if parallel_index == 0 else None,
                    "files_touched": touched,
                    "parallel_index": parallel_index,
                    "parallel_count": len(calls),
                }
            )

    return rows


def _read_existing(output_path: Path, run_id: str) -> tuple[list[str], set[str]]:
    if not output_path.exists():
        return [], set()
    lines: list[str] = []
    model_keys: set[str] = set()
    with output_path.open(encoding="utf-8") as file_obj:
        for line_number, line in enumerate(file_obj, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{output_path}:{line_number}: malformed existing JSON: {exc.msg}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{output_path}:{line_number}: existing row is not an object")
            if row.get("schema_version") != SCHEMA_VERSION:
                raise ValueError(
                    f"{output_path}:{line_number}: unsupported schema_version {row.get('schema_version')!r}"
                )
            if row.get("run_id") != run_id:
                raise ValueError(f"{output_path}:{line_number}: row belongs to run {row.get('run_id')!r}")
            model_key = row.get("model_key")
            if not isinstance(model_key, str) or not model_key:
                raise ValueError(f"{output_path}:{line_number}: row has no model_key")
            model_keys.add(model_key)
            lines.append(line.rstrip("\n"))
    return lines, model_keys


def _atomic_write_lines(output_path: Path, lines: Iterable[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file_obj:
            for line in lines:
                file_obj.write(line)
                file_obj.write("\n")
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.replace(temporary_path, output_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def process_run(run_dir: Path, event_files: Iterable[Path]) -> tuple[int, int, int]:
    output_path = run_dir / OUTPUT_NAME
    existing_lines, represented_models = _read_existing(output_path, run_dir.name)
    summary = _load_summary(run_dir)
    new_rows: list[dict[str, Any]] = []
    parsed_models = 0
    skipped_models = 0

    for events_path in sorted(event_files, key=lambda item: item.parent.name):
        model_key = events_path.parent.name
        if model_key in represented_models:
            skipped_models += 1
            continue
        rows = parse_events(events_path, summary)
        if not rows:
            _warn(f"{events_path}: no assistant trajectory rows found")
            continue
        new_rows.extend(rows)
        represented_models.add(model_key)
        parsed_models += 1

    if new_rows:
        serialized = [
            json.dumps(row, ensure_ascii=False, sort_keys=False, separators=(",", ":")) for row in new_rows
        ]
        _atomic_write_lines(output_path, [*existing_lines, *serialized])
    return parsed_models, skipped_models, len(new_rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Pi events.jsonl files into one incremental trajectory.jsonl per benchmark run."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("runs")],
        help="events.jsonl files or directories to search recursively (default: runs/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        event_files = discover_event_files(args.paths)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not event_files:
        print("error: no events.jsonl files found", file=sys.stderr)
        return 1

    grouped: dict[Path, list[Path]] = {}
    for events_path in event_files:
        grouped.setdefault(events_path.parent.parent, []).append(events_path)

    parsed = skipped = rows = failures = 0
    for run_dir in sorted(grouped, key=lambda item: str(item)):
        try:
            run_parsed, run_skipped, run_rows = process_run(run_dir, grouped[run_dir])
        except (OSError, ValueError) as exc:
            print(f"error: {run_dir}: {exc}", file=sys.stderr)
            failures += 1
            continue
        parsed += run_parsed
        skipped += run_skipped
        rows += run_rows

    print(
        f"Parsed {parsed} model(s), skipped {skipped} existing model(s), "
        f"wrote {rows} row(s) across {len(grouped) - failures} run(s)."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
