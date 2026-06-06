"""Subprocess helpers that record exact command lines into shared state."""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path

from .config import cmd_for_display
from .state import STATE, CommandRecord


def run_command(
    argv: list[str],
    *,
    label: str,
    cwd: Path | str | None = None,
    timeout: float | None = None,
    env_extra: dict[str, str] | None = None,
    full_stdout: bool = False,
) -> CommandRecord:
    """Run a command, record it on STATE.commands, return the record.

    stdout/stderr are captured. The UI preview is trimmed to the trailing 4 KB,
    but the raw stdout can be attached to the record via `full_stdout=True` for
    later parsing without bloating the JSON payload.
    """
    cwd_path = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    rec = CommandRecord(
        label=label,
        argv=list(argv),
        display=cmd_for_display(argv),
        cwd=str(cwd_path),
        started_at=time.time(),
    )
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        rec.exit_code = proc.returncode
        rec.stdout_preview = _tail(proc.stdout, 4096)
        rec.stderr_preview = _tail(proc.stderr, 4096)
        if full_stdout:
            setattr(rec, "full_stdout", proc.stdout or "")
    except subprocess.TimeoutExpired as e:
        rec.exit_code = -1
        rec.stderr_preview = f"TIMEOUT after {e.timeout}s"
    except FileNotFoundError as e:
        rec.exit_code = -2
        rec.stderr_preview = f"FileNotFoundError: {e}"
    finally:
        rec.finished_at = time.time()
        STATE.record_command(rec)
    return rec


def _tail(text: str, n: int) -> str:
    if not text:
        return ""
    if len(text) <= n:
        return text
    return "...\n" + text[-n:]


def display(argv: list[str]) -> str:
    return cmd_for_display(argv)


__all__ = ["run_command", "display", "shlex"]
