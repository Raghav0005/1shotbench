from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import socket
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from bench.config import RUNS_DIR, USAGE_LOG_PATH
from bench.metrics import (
    extract_inline_token_usage,
    extract_session_id,
    get_gpt_metrics_from_ccusage,
    get_non_gpt_metrics,
)
from bench.schemas import BenchmarkSummary, RunJobResult, TokenMetrics, WorkspaceConfig


EventCallback = Callable[[dict], Awaitable[None]]


@dataclass
class RunnerOptions:
    prompt: str
    selected_models: list[str]
    mode: str = "parallel"
    max_concurrency: int = 2
    timeout_seconds: int = 1800
    retries: int = 0
    label: str = "benchmark"
    warmup: bool = False
    run_id: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.isoformat()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _git_commit(root: Path) -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


class BenchmarkRunner:
    def __init__(self, root_dir: Path, workspaces: dict[str, WorkspaceConfig]):
        self.root_dir = root_dir
        self.workspaces = workspaces

    def preflight(self, selected_models: list[str]) -> list[str]:
        errors: list[str] = []
        missing = [model for model in selected_models if model not in self.workspaces]
        if missing:
            errors.append(f"Unknown model keys: {', '.join(missing)}")

        for model in selected_models:
            workspace = self.workspaces.get(model)
            if workspace and not Path(workspace.path).exists():
                errors.append(f"Workspace not found: {workspace.path}")

        codex_check = subprocess.run(
            ["codex", "--version"],
            cwd=str(self.root_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if codex_check.returncode != 0:
            errors.append("`codex` command is not available in PATH.")

        requires_proxy = any(model != "gpt" for model in selected_models)
        if requires_proxy:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.75)
            try:
                sock.connect(("127.0.0.1", 4000))
            except OSError:
                errors.append("Proxy is not reachable at 127.0.0.1:4000 for non-GPT models.")
            finally:
                sock.close()

        return errors

    async def run(
        self,
        options: RunnerOptions,
        event_callback: EventCallback | None = None,
    ) -> BenchmarkSummary:
        run_started = _now()
        run_id = options.run_id or f"{run_started.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        prompt_hash = _sha256(options.prompt)
        prompt_file = run_dir / "prompt.txt"
        prompt_file.write_text(options.prompt, encoding="utf-8")

        selected = [self.workspaces[key] for key in options.selected_models]

        if options.warmup:
            for workspace in selected:
                await self._run_single(
                    run_dir=run_dir,
                    workspace=workspace,
                    prompt=options.prompt,
                    prompt_hash=prompt_hash,
                    timeout_seconds=min(60, options.timeout_seconds),
                    retries=0,
                    event_callback=None,
                    warmup=True,
                )

        if options.mode == "sequential":
            results = []
            for workspace in selected:
                result = await self._run_single(
                    run_dir=run_dir,
                    workspace=workspace,
                    prompt=options.prompt,
                    prompt_hash=prompt_hash,
                    timeout_seconds=options.timeout_seconds,
                    retries=options.retries,
                    event_callback=event_callback,
                    warmup=False,
                )
                results.append(result)
        else:
            sem = asyncio.Semaphore(max(1, options.max_concurrency))
            tasks = [
                asyncio.create_task(
                    self._run_with_semaphore(
                        sem=sem,
                        run_dir=run_dir,
                        workspace=workspace,
                        prompt=options.prompt,
                        prompt_hash=prompt_hash,
                        timeout_seconds=options.timeout_seconds,
                        retries=options.retries,
                        event_callback=event_callback,
                        warmup=False,
                    )
                )
                for workspace in selected
            ]
            results = await asyncio.gather(*tasks)

        run_ended = _now()
        summary = BenchmarkSummary(
            run_id=run_id,
            label=options.label,
            started_at=_iso(run_started),
            ended_at=_iso(run_ended),
            duration_ms=int((run_ended - run_started).total_seconds() * 1000),
            mode=options.mode,
            max_concurrency=options.max_concurrency,
            retries=options.retries,
            timeout_seconds=options.timeout_seconds,
            warmup=options.warmup,
            prompt_hash=prompt_hash,
            selected_models=options.selected_models,
            git_commit=_git_commit(self.root_dir),
            proxy_log_path=str(USAGE_LOG_PATH),
            results=results,
        )
        summary_path = run_dir / "summary.json"
        summary_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
        self._write_summary_csv(run_dir, summary)
        self._write_summary_md(run_dir, summary)
        return summary

    async def _run_with_semaphore(self, sem: asyncio.Semaphore, **kwargs) -> RunJobResult:
        async with sem:
            return await self._run_single(**kwargs)

    async def _emit(self, callback: EventCallback | None, payload: dict) -> None:
        if callback:
            await callback(payload)

    async def _run_single(
        self,
        run_dir: Path,
        workspace: WorkspaceConfig,
        prompt: str,
        prompt_hash: str,
        timeout_seconds: int,
        retries: int,
        event_callback: EventCallback | None,
        warmup: bool,
    ) -> RunJobResult:
        model_dir = run_dir / workspace.key
        model_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = model_dir / ("warmup.stdout.log" if warmup else "stdout.log")
        stderr_path = model_dir / ("warmup.stderr.log" if warmup else "stderr.log")
        result_path = model_dir / ("warmup.result.json" if warmup else "result.json")

        await self._emit(
            event_callback,
            {"type": "status", "model": workspace.key, "status": "running"},
        )

        attempts = 0
        run_started = _now()
        final_status = "failed"
        final_exit_code: int | None = None
        final_error: str | None = None
        final_stdout = ""
        final_stderr = ""

        while attempts <= retries:
            attempts += 1
            try:
                proc = await asyncio.create_subprocess_exec(
                    "codex",
                    "exec",
                    prompt,
                    cwd=workspace.path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_chunks: list[str] = []
                stderr_chunks: list[str] = []

                async def drain(stream, name: str, sink: list[str]) -> None:
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        text = line.decode("utf-8", errors="replace")
                        sink.append(text)
                        await self._emit(
                            event_callback,
                            {
                                "type": "output",
                                "model": workspace.key,
                                "stream": name,
                                "text": text,
                            },
                        )

                stdout_task = asyncio.create_task(drain(proc.stdout, "stdout", stdout_chunks))
                stderr_task = asyncio.create_task(drain(proc.stderr, "stderr", stderr_chunks))
                await asyncio.wait_for(proc.wait(), timeout=timeout_seconds)
                await stdout_task
                await stderr_task
                final_stdout = "".join(stdout_chunks)
                final_stderr = "".join(stderr_chunks)
                final_exit_code = proc.returncode
                if proc.returncode == 0:
                    final_status = "completed"
                    final_error = None
                    break
                final_error = f"Non-zero exit code: {proc.returncode}"
            except asyncio.TimeoutError:
                if "proc" in locals() and proc.returncode is None:
                    proc.kill()
                    await proc.wait()
                final_exit_code = None
                final_error = f"Timed out after {timeout_seconds}s"
                final_status = "timeout"

            if attempts <= retries:
                await self._emit(
                    event_callback,
                    {
                        "type": "status",
                        "model": workspace.key,
                        "status": "retrying",
                        "attempt": attempts,
                    },
                )

        stdout_path.write_text(final_stdout, encoding="utf-8")
        stderr_path.write_text(final_stderr, encoding="utf-8")

        run_ended = _now()
        session_id = extract_session_id(final_stdout + "\n" + final_stderr)
        metrics = self._collect_metrics(
            workspace=workspace,
            started_at=_iso(run_started),
            ended_at=_iso(run_ended),
            output_text=final_stdout + "\n" + final_stderr,
        )
        result = RunJobResult(
            model_key=workspace.key,
            workspace_path=workspace.path,
            model_name=workspace.model,
            provider=workspace.provider,
            status=final_status,
            exit_code=final_exit_code,
            started_at=_iso(run_started),
            ended_at=_iso(run_ended),
            duration_ms=int((run_ended - run_started).total_seconds() * 1000),
            prompt_hash=prompt_hash,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            result_path=str(result_path),
            attempts=attempts,
            session_id=session_id,
            error=final_error,
            metrics=metrics,
        )
        result_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

        await self._emit(
            event_callback,
            {
                "type": "complete",
                "model": workspace.key,
                "status": final_status,
                "exit_code": final_exit_code,
                "duration_ms": result.duration_ms,
                "metrics": result.metrics.__dict__,
                "stdout_tail": final_stdout[-4000:],
                "stderr_tail": final_stderr[-4000:],
            },
        )
        return result

    def _collect_metrics(
        self,
        workspace: WorkspaceConfig,
        started_at: str,
        ended_at: str,
        output_text: str,
    ) -> TokenMetrics:
        if workspace.key == "gpt":
            inline = extract_inline_token_usage(output_text)
            if inline:
                return inline
            return get_gpt_metrics_from_ccusage(Path(workspace.path))
        return get_non_gpt_metrics(
            usage_log_path=USAGE_LOG_PATH,
            provider=workspace.key if workspace.provider else workspace.key,
            model_name=workspace.model,
            started_at=started_at,
            ended_at=ended_at,
        )

    def _write_summary_csv(self, run_dir: Path, summary: BenchmarkSummary) -> None:
        csv_path = run_dir / "summary.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as file_obj:
            writer = csv.writer(file_obj)
            writer.writerow(
                [
                    "model",
                    "status",
                    "duration_ms",
                    "input_tokens",
                    "output_tokens",
                    "reasoning_tokens",
                    "cache_read_tokens",
                    "total_tokens",
                    "cost_usd",
                    "requests",
                    "exit_code",
                ]
            )
            for result in summary.results:
                m = result.metrics
                writer.writerow(
                    [
                        result.model_key,
                        result.status,
                        result.duration_ms,
                        m.input_tokens,
                        m.output_tokens,
                        m.reasoning_tokens,
                        m.cache_read_tokens,
                        m.total_tokens,
                        f"{m.cost_usd:.4f}",
                        m.requests,
                        "" if result.exit_code is None else result.exit_code,
                    ]
                )

    def _write_summary_md(self, run_dir: Path, summary: BenchmarkSummary) -> None:
        md_path = run_dir / "summary.md"
        lines = [
            f"# Benchmark `{summary.run_id}`",
            "",
            f"- label: {summary.label}",
            f"- mode: {summary.mode}",
            f"- concurrency: {summary.max_concurrency}",
            f"- duration_ms: {summary.duration_ms}",
            "",
            "| model | status | duration_ms | total_tokens | cost_usd |",
            "|---|---:|---:|---:|---:|",
        ]
        for result in summary.results:
            lines.append(
                f"| {result.model_key} | {result.status} | {result.duration_ms} | "
                f"{result.metrics.total_tokens} | {result.metrics.cost_usd:.4f} |"
            )
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
