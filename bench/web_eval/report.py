from __future__ import annotations

import json
from pathlib import Path

from bench.web_eval.schemas import EvidencePacket, FeatureJudgment, WebEvalSummary


def write_artifacts(
    output_dir: Path,
    *,
    summary: WebEvalSummary,
    evidence_by_feature: dict[str, EvidencePacket],
    judgments: list[FeatureJudgment],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(render_markdown(summary, output_dir), encoding="utf-8")
    judgments_dir = output_dir / "judgments"
    judgments_dir.mkdir(exist_ok=True)
    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    for feature_id, packet in evidence_by_feature.items():
        (evidence_dir / f"{feature_id}.json").write_text(
            json.dumps(packet.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
    for judgment in judgments:
        (judgments_dir / f"{judgment.feature_id}.json").write_text(
            json.dumps(judgment.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )


def render_markdown(summary: WebEvalSummary, output_dir: Path) -> str:
    lines = [
        f"# Web Eval Report: {summary.label}",
        "",
        f"- **Eval ID:** `{summary.eval_id}`",
        f"- **Project:** `{summary.project_path}`",
        f"- **Base URL:** {summary.base_url}",
        f"- **Started:** {summary.started_at}",
        f"- **Ended:** {summary.ended_at}",
        f"- **Correctness:** **{summary.correctness_pct:.1f}%** ({summary.passed}/{summary.total_features} passed)",
        f"- **Failed:** {summary.failed}",
        f"- **Uncertain:** {summary.uncertain}",
        "",
        "## Scoring",
        "",
        "Correctness uses `passed / total * 100`. Uncertain results count as **not passed**.",
        "",
        "## Feature outcomes",
        "",
        "| Feature | Verdict | Confidence | Reason |",
        "| --- | --- | ---: | --- |",
    ]
    for judgment in summary.judgments:
        lines.append(
            f"| `{judgment.feature_id}` | {judgment.verdict} | {judgment.confidence:.2f} | {judgment.reason} |"
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Summary JSON: `{output_dir / 'summary.json'}`",
            f"- Evidence: `{output_dir / 'evidence'}/`",
            f"- Judgments: `{output_dir / 'judgments'}/`",
            f"- Screenshots: `{output_dir / 'screenshots'}/`",
        ]
    )
    failures = [j for j in summary.judgments if j.verdict == "fail"]
    uncertainties = [j for j in summary.judgments if j.verdict == "uncertain"]
    if failures:
        lines.extend(["", "## Major failures", ""])
        for item in failures:
            lines.append(f"- **{item.feature_id}:** {item.reason}")
    if uncertainties:
        lines.extend(["", "## Uncertainties", ""])
        for item in uncertainties:
            lines.append(f"- **{item.feature_id}:** {item.reason}")
    if summary.notes:
        lines.extend(["", "## Notes", "", summary.notes])
    return "\n".join(lines) + "\n"
