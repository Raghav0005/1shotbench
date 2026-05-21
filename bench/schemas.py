from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TokenMetrics:
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    requests: int = 0

    def merge(self, other: "TokenMetrics") -> "TokenMetrics":
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.total_tokens += other.total_tokens
        self.cost_usd += other.cost_usd
        self.requests += other.requests
        return self


@dataclass
class WorkspaceConfig:
    key: str
    name: str
    path: str
    model: str
    provider: str | None = None
    thinking: str | None = None
    system_prompt: str | None = None
    append_system_prompt: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)

    def pi_args(self) -> list[str]:
        args = ["pi", "--print", "--no-session"]
        if self.provider:
            args.extend(["--provider", self.provider])
        if self.model:
            args.extend(["--model", self.model])
        if self.thinking:
            args.extend(["--thinking", self.thinking])
        if self.system_prompt:
            args.extend(["--system-prompt", self.system_prompt])
        for value in self.append_system_prompt:
            args.extend(["--append-system-prompt", value])
        if self.tools:
            args.extend(["--tools", ",".join(self.tools)])
        return args


@dataclass
class RunJobResult:
    model_key: str
    workspace_path: str
    model_name: str
    provider: str | None
    status: str
    exit_code: int | None
    started_at: str
    ended_at: str
    duration_ms: int
    prompt_hash: str
    stdout_path: str
    stderr_path: str
    result_path: str
    command: list[str]
    attempts: int = 1
    error: str | None = None
    metrics: TokenMetrics = field(default_factory=TokenMetrics)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["metrics"] = asdict(self.metrics)
        return data


@dataclass
class BenchmarkSummary:
    run_id: str
    label: str
    started_at: str
    ended_at: str
    duration_ms: int
    mode: str
    max_concurrency: int
    retries: int
    timeout_seconds: int
    warmup: bool
    prompt_hash: str
    selected_models: list[str]
    git_commit: str | None
    results: list[RunJobResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "label": self.label,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "mode": self.mode,
            "max_concurrency": self.max_concurrency,
            "retries": self.retries,
            "timeout_seconds": self.timeout_seconds,
            "warmup": self.warmup,
            "prompt_hash": self.prompt_hash,
            "selected_models": self.selected_models,
            "git_commit": self.git_commit,
            "results": [result.to_dict() for result in self.results],
            "totals": self.compute_totals(),
        }

    def compute_totals(self) -> dict[str, Any]:
        total = TokenMetrics()
        for result in self.results:
            total.merge(result.metrics)
        return asdict(total)


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
