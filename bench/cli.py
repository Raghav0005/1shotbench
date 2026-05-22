from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from bench.config import ROOT_DIR, load_workspace_configs
from bench.runner import BenchmarkRunner, RunnerOptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pi agent benchmark runner")
    parser.add_argument("--prompt", help="Prompt text to run")
    parser.add_argument("--prompt-file", help="Read prompt from file path")
    parser.add_argument("--task-dir", default=None, help="Task workspace directory, e.g. anserini-frontend")
    parser.add_argument("--models", nargs="+", required=True, help="Model keys to run")
    parser.add_argument("--mode", choices=["sequential", "parallel"], default="parallel")
    parser.add_argument("--max-concurrency", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--label", default="benchmark")
    parser.add_argument("--warmup", action="store_true")
    return parser


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    raise ValueError("Provide --prompt or --prompt-file")


async def main_async(args: argparse.Namespace) -> int:
    prompt = read_prompt(args)
    workspaces = load_workspace_configs(args.task_dir)
    runner = BenchmarkRunner(ROOT_DIR, workspaces)
    errors = runner.preflight(args.models)
    if errors:
        print("\n".join(errors))
        return 1

    options = RunnerOptions(
        prompt=prompt,
        selected_models=args.models,
        mode=args.mode,
        max_concurrency=args.max_concurrency,
        timeout_seconds=args.timeout_seconds,
        retries=args.retries,
        label=args.label,
        warmup=args.warmup,
    )

    async def on_event(event: dict) -> None:
        kind = event.get("type")
        model = event.get("model")
        status = event.get("status")
        print(f"[{kind}] {model}: {status}")

    summary = await runner.run(options=options, event_callback=on_event)
    print(json.dumps(summary.to_dict(), indent=2))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
