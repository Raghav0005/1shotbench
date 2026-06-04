from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bench.config import ROOT_DIR, RUNS_DIR, discover_shared_task_files, load_workspace_configs
from bench.runner import BenchmarkRunner, RunnerOptions


app = FastAPI(title="Pi Agent Bench")
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "bench" / "static")), name="static")

workspaces = load_workspace_configs()
runner = BenchmarkRunner(ROOT_DIR, workspaces)
event_queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
active_runs: dict[str, dict[str, Any]] = {}


class StartRunRequest(BaseModel):
    prompt: str = Field(min_length=1)
    models: list[str] = Field(min_length=1)
    mode: str = "parallel"
    max_concurrency: int = 2
    timeout_seconds: int = 1800
    retries: int = 0
    label: str = "benchmark"
    warmup: bool = False
    rewrite_task_files: bool = True
    rewrite_timeout_seconds: int = 600


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT_DIR / "bench" / "static" / "index.html")


@app.get("/api/models")
async def models() -> list[dict[str, Any]]:
    return [
        {
            "key": cfg.key,
            "name": cfg.name,
            "model": cfg.model,
            "provider": cfg.provider,
            "thinking": cfg.thinking,
            "tools": cfg.tools,
            "path": cfg.path,
        }
        for cfg in workspaces.values()
    ]


@app.get("/api/task-files")
async def task_files() -> list[dict[str, Any]]:
    return [
        {
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
        }
        for path in discover_shared_task_files()
    ]


@app.post("/api/runs")
async def start_run(req: StartRunRequest) -> dict[str, Any]:
    errors = runner.preflight(req.models)
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    options = RunnerOptions(
        prompt=req.prompt,
        selected_models=req.models,
        mode=req.mode,
        max_concurrency=req.max_concurrency,
        timeout_seconds=req.timeout_seconds,
        retries=req.retries,
        label=req.label,
        warmup=req.warmup,
        rewrite_task_files=req.rewrite_task_files,
        rewrite_timeout_seconds=req.rewrite_timeout_seconds,
    )

    run_id = f"run-{len(active_runs) + 1}-{asyncio.get_running_loop().time():.0f}"
    active_runs[run_id] = {"status": "running", "summary": None}

    options.run_id = run_id

    async def execute() -> None:
        try:
            summary = await runner.run(options=options, event_callback=emit_event)
            active_runs[run_id] = {"status": "completed", "summary": summary.to_dict()}
            for queue in event_queues[run_id]:
                await queue.put({"type": "run_complete", "summary": summary.to_dict()})
        except Exception as exc:  # keep background task failures visible
            active_runs[run_id] = {"status": "failed", "summary": None, "error": str(exc)}
            for queue in event_queues[run_id]:
                await queue.put({"type": "run_failed", "error": str(exc)})

    async def emit_event(event: dict[str, Any]) -> None:
        for queue in event_queues[run_id]:
            await queue.put(event)

    asyncio.create_task(execute())
    return {"run_id": run_id}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run = active_runs.get(run_id)
    if run:
        return run
    summary_path = RUNS_DIR / run_id / "summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return {"status": "completed", "summary": json.loads(summary_path.read_text(encoding="utf-8"))}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    event_queues[run_id].append(queue)

    async def stream():
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "run_complete":
                    break
        finally:
            if queue in event_queues[run_id]:
                event_queues[run_id].remove(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/history")
async def history() -> list[dict[str, Any]]:
    if not RUNS_DIR.exists():
        return []
    items = []
    for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        deployments_path = run_dir / "deployments.json"
        deployments = json.loads(deployments_path.read_text(encoding="utf-8")) if deployments_path.exists() else None
        items.append(
            {
                "run_id": summary.get("run_id"),
                "label": summary.get("label"),
                "started_at": summary.get("started_at"),
                "duration_ms": summary.get("duration_ms"),
                "mode": summary.get("mode"),
                "deployments": deployments,
            }
        )
    return items[:50]


@app.get("/api/runs/{run_id}/details")
async def run_details(run_id: str) -> dict[str, Any]:
    summary_path = RUNS_DIR / run_id / "summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    deployments_path = RUNS_DIR / run_id / "deployments.json"
    deployments = json.loads(deployments_path.read_text(encoding="utf-8")) if deployments_path.exists() else None
    prompt_path = RUNS_DIR / run_id / "prompt.txt"
    prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

    outputs: dict[str, dict[str, str]] = {}
    for result in summary.get("results", []):
        model_key = result.get("model_key")
        if not model_key:
            continue
        stdout_path = Path(result.get("stdout_path", ""))
        stderr_path = Path(result.get("stderr_path", ""))
        outputs[model_key] = {
            "stdout": stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else "",
            "stderr": stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else "",
        }
    return {"summary": summary, "prompt": prompt, "outputs": outputs, "deployments": deployments}
