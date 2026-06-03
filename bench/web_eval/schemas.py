from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

FeatureVerdict = Literal["pass", "fail", "uncertain"]


@dataclass
class BrowserAction:
    action: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeatureCheck:
    id: str
    title: str
    description: str
    acceptance: str
    steps: list[BrowserAction] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "acceptance": self.acceptance,
            "steps": [{"action": s.action, **s.params} for s in self.steps],
        }


@dataclass
class AppProfile:
    base_url: str
    start_command: list[str] | None = None
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    ready_url: str | None = None
    ready_timeout_seconds: int = 120

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidencePacket:
    feature_id: str
    url: str | None = None
    page_title: str | None = None
    visible_text: str | None = None
    aria_snapshot: str | None = None
    screenshot_path: str | None = None
    interactive_elements: list[dict[str, Any]] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    network_errors: list[str] = field(default_factory=list)
    action_log: list[str] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def compact_dict(self, max_text: int = 2500, max_aria: int = 3500) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "url": self.url,
            "page_title": self.page_title,
            "visible_text": _truncate(self.visible_text, max_text),
            "aria_snapshot": _truncate(self.aria_snapshot, max_aria),
            "screenshot_path": self.screenshot_path,
            "interactive_elements": self.interactive_elements[:80],
            "console_errors": self.console_errors[:10],
            "network_errors": self.network_errors[:10],
            "action_log": self.action_log[-20:],
            "checks": self.checks,
            "error": self.error,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FeatureJudgment:
    feature_id: str
    verdict: FeatureVerdict
    confidence: float
    reason: str
    evidence_used: list[str] = field(default_factory=list)
    raw_response: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WebEvalSummary:
    eval_id: str
    label: str
    started_at: str
    ended_at: str
    project_path: str
    features_path: str
    prd_path: str | None
    base_url: str
    total_features: int
    passed: int
    failed: int
    uncertain: int
    correctness_pct: float
    judgments: list[FeatureJudgment]
    git_commit: str | None = None
    judge_model: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_id": self.eval_id,
            "label": self.label,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "project_path": self.project_path,
            "features_path": self.features_path,
            "prd_path": self.prd_path,
            "base_url": self.base_url,
            "total_features": self.total_features,
            "passed": self.passed,
            "failed": self.failed,
            "uncertain": self.uncertain,
            "correctness_pct": self.correctness_pct,
            "judgments": [j.to_dict() for j in self.judgments],
            "git_commit": self.git_commit,
            "judge_model": self.judge_model,
            "notes": self.notes,
            "scoring": {
                "formula": "passed / total * 100",
                "uncertain_counts_as": "not passed (same as fail for percentage)",
            },
        }


def _truncate(value: str | None, limit: int) -> str | None:
    if not value:
        return value
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
