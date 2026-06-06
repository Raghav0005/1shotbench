"""Shared mutable application state.

All long-running setup / evaluation steps populate this object; the FastAPI
handlers read from it. The structure deliberately mirrors what the diagnostics
UI panels render so that /api/status is a flat passthrough.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandRecord:
    label: str
    argv: list[str]
    display: str
    cwd: str
    exit_code: int | None = None
    stdout_preview: str = ""
    stderr_preview: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0


@dataclass
class StatusCard:
    state: str = "pending"   # pending | ok | warn | error
    value: str = "…"
    detail: str = ""


@dataclass
class MetricRow:
    name: str
    trec_eval_args: str
    expected: float | None
    observed: float | None
    delta: float | None
    status: str        # match | close | fail | pending


@dataclass
class EvaluationResult:
    status: str = "pending"            # pending | running | done | failed
    source: str = "cached startup pass"
    elapsed_seconds: float | None = None
    run_path: str = ""
    eval_path: str = ""
    metrics: list[MetricRow] = field(default_factory=list)
    error: str = ""
    rerun_count: int = 0
    last_finished_at: float = 0.0


@dataclass
class WorkbenchState:
    phase: str = "starting"
    started_at: float = field(default_factory=time.time)
    java: StatusCard = field(default_factory=StatusCard)
    fatjar: StatusCard = field(default_factory=StatusCard)
    nfcorpus: StatusCard = field(default_factory=StatusCard)
    reproduction: StatusCard = field(default_factory=StatusCard)
    search: StatusCard = field(default_factory=StatusCard)
    evaluation_card: StatusCard = field(default_factory=StatusCard)
    setup_log: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    commands: list[CommandRecord] = field(default_factory=list)
    evaluation: EvaluationResult = field(default_factory=EvaluationResult)
    anserini_version: str = ""
    fatjar_path: str = ""
    index_path: str = ""
    expected_metrics_raw: dict[str, Any] = field(default_factory=dict)
    sample_queries: list[str] = field(default_factory=list)
    rest_url: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)

    def log(self, line: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.setup_log.append(f"[{ts}] {line}")

    def add_error(self, line: str) -> None:
        self.errors.append(line)
        self.log("ERROR: " + line)

    def record_command(self, rec: CommandRecord) -> None:
        with self.lock:
            self.commands.append(rec)

    def to_dict(self) -> dict[str, Any]:
        with self.lock:
            return {
                "phase": self.phase,
                "uptime_seconds": time.time() - self.started_at,
                "anserini_version": self.anserini_version,
                "fatjar_path": self.fatjar_path,
                "index_path": self.index_path,
                "rest_url": self.rest_url,
                "expected_metrics": self.expected_metrics_raw,
                "sample_queries": self.sample_queries,
                "cards": {
                    "java": self.java.__dict__,
                    "fatjar": self.fatjar.__dict__,
                    "nfcorpus": self.nfcorpus.__dict__,
                    "reproduction": self.reproduction.__dict__,
                    "search": self.search.__dict__,
                    "evaluation": self.evaluation_card.__dict__,
                },
                "setup_log": list(self.setup_log),
                "errors": list(self.errors),
                "commands": [
                    {
                        "label": c.label,
                        "display": c.display,
                        "argv": c.argv,
                        "cwd": c.cwd,
                        "exit_code": c.exit_code,
                        "stdout_preview": c.stdout_preview,
                        "stderr_preview": c.stderr_preview,
                        "started_at": c.started_at,
                        "finished_at": c.finished_at,
                    }
                    for c in self.commands
                ],
                "evaluation": {
                    "status": self.evaluation.status,
                    "source": self.evaluation.source,
                    "elapsed_seconds": self.evaluation.elapsed_seconds,
                    "run_path": self.evaluation.run_path,
                    "eval_path": self.evaluation.eval_path,
                    "error": self.evaluation.error,
                    "rerun_count": self.evaluation.rerun_count,
                    "last_finished_at": self.evaluation.last_finished_at,
                    "metrics": [m.__dict__ for m in self.evaluation.metrics],
                },
            }


STATE = WorkbenchState()
