#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


METRIC_KEYS = [
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "prompt_tokens",
    "total_tokens",
    "cost_usd",
    "requests",
]


def _zero_metrics() -> dict[str, int | float]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "prompt_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "requests": 0,
    }


def metrics_from_events(events_path: Path) -> dict[str, int | float] | None:
    metrics = _zero_metrics()
    with events_path.open(encoding="utf-8") as file_obj:
        for line in file_obj:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "message_end":
                continue
            message = event.get("message") or {}
            if message.get("role") != "assistant":
                continue
            usage = message.get("usage") or {}
            total_tokens = int(usage.get("totalTokens") or 0)
            if total_tokens <= 0:
                continue
            input_tokens = int(usage.get("input") or 0)
            output_tokens = int(usage.get("output") or 0)
            cache_read_tokens = int(usage.get("cacheRead") or 0)
            cache_write_tokens = int(usage.get("cacheWrite") or 0)
            cost = usage.get("cost") or {}

            metrics["input_tokens"] += input_tokens
            metrics["output_tokens"] += output_tokens
            metrics["cache_read_tokens"] += cache_read_tokens
            metrics["cache_write_tokens"] += cache_write_tokens
            metrics["prompt_tokens"] += input_tokens + cache_read_tokens + cache_write_tokens
            metrics["total_tokens"] += total_tokens
            metrics["cost_usd"] += float(cost.get("total") or 0)
            metrics["requests"] += 1

    return metrics if metrics["requests"] else None


def _write_json(path: Path, data: dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        return
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _rewrite_summary_csv(run_dir: Path, summary: dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        return
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
                "cache_write_tokens",
                "prompt_tokens",
                "total_tokens",
                "cost_usd",
                "requests",
                "exit_code",
            ]
        )
        for result in summary.get("results") or []:
            metrics = result.get("metrics") or {}
            writer.writerow(
                [
                    result.get("model_key") or "",
                    result.get("status") or "",
                    result.get("duration_ms") or 0,
                    int(metrics.get("input_tokens") or 0),
                    int(metrics.get("output_tokens") or 0),
                    int(metrics.get("reasoning_tokens") or 0),
                    int(metrics.get("cache_read_tokens") or 0),
                    int(metrics.get("cache_write_tokens") or 0),
                    int(metrics.get("prompt_tokens") or 0),
                    int(metrics.get("total_tokens") or 0),
                    f"{float(metrics.get('cost_usd') or 0):.4f}",
                    int(metrics.get("requests") or 0),
                    "" if result.get("exit_code") is None else result.get("exit_code"),
                ]
            )


def _compute_totals(results: list[dict[str, Any]]) -> dict[str, int | float]:
    totals = _zero_metrics()
    for result in results:
        metrics = result.get("metrics") or {}
        for key in METRIC_KEYS:
            totals[key] += metrics.get(key) or 0
    return totals


def _run_dirs(paths: list[Path]) -> list[Path]:
    dirs: list[Path] = []
    for path in paths:
        if (path / "summary.json").exists():
            dirs.append(path)
            continue
        dirs.extend(sorted(child for child in path.iterdir() if (child / "summary.json").exists()))
    return dirs


def backfill_run(run_dir: Path, dry_run: bool) -> list[str]:
    changes: list[str] = []
    repaired_by_model: dict[str, dict[str, int | float]] = {}

    for result_path in sorted(run_dir.glob("*/result.json")):
        data = json.loads(result_path.read_text(encoding="utf-8"))
        events_path_value = data.get("events_path") or str(result_path.with_name("events.jsonl"))
        events_path = Path(events_path_value)
        if not events_path.is_absolute():
            events_path = run_dir / events_path
        if not events_path.exists():
            continue

        metrics = metrics_from_events(events_path)
        if metrics is None:
            continue

        current = data.get("metrics") or {}
        merged = {**current, **metrics}
        if merged == current:
            continue

        data["metrics"] = merged
        _write_json(result_path, data, dry_run)
        model_key = data.get("model_key") or result_path.parent.name
        repaired_by_model[model_key] = merged
        changes.append(f"{run_dir.name}/{model_key}")

    summary_path = run_dir / "summary.json"
    if repaired_by_model and summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        for result in summary.get("results") or []:
            model_key = result.get("model_key")
            if model_key in repaired_by_model:
                result["metrics"] = repaired_by_model[model_key]
        summary["totals"] = _compute_totals(summary.get("results") or [])
        _write_json(summary_path, summary, dry_run)
        _rewrite_summary_csv(run_dir, summary, dry_run)

    return changes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill token metrics in existing benchmark runs from events.jsonl."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("runs")],
        help="Run directories or parent directories containing run directories.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files.")
    args = parser.parse_args()

    changed: list[str] = []
    for run_dir in _run_dirs(args.paths):
        changed.extend(backfill_run(run_dir, args.dry_run))

    action = "Would update" if args.dry_run else "Updated"
    print(f"{action} {len(changed)} result(s).")
    for item in changed:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
