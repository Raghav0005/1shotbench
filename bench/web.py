from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bench.config import ROOT_DIR, RUNS_DIR, discover_shared_task_files, load_workspace_configs, resolve_workspaces_dir
from bench.runner import BenchmarkRunner, RunnerOptions


app = FastAPI(title="Pi Agent Bench")
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "bench" / "static")), name="static")

event_queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
active_runs: dict[str, dict[str, Any]] = {}


class StartRunRequest(BaseModel):
    prompt: str = Field(min_length=1)
    models: list[str] = Field(min_length=1)
    task_dir: str | None = None
    mode: str = "parallel"
    max_concurrency: int = 2
    timeout_seconds: int = 1800
    retries: int = 0
    label: str = "benchmark"
    warmup: bool = False
    rewrite_task_files: bool = True
    rewrite_timeout_seconds: int = 600


def _relative_task_dir(task_dir: str | Path | None = None) -> str:
    path = resolve_workspaces_dir(task_dir).resolve()
    try:
        return path.relative_to(ROOT_DIR).as_posix()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Task directory must be inside {ROOT_DIR}") from exc


def _experiment_name(path: Path) -> str:
    words = path.name.replace("-", " ").replace("_", " ").split()
    return " ".join(word.upper() if word.lower() in {"nfcorpus"} else word.capitalize() for word in words)


def _load_workspaces(task_dir: str | Path | None = None):
    relative = _relative_task_dir(task_dir)
    workspaces = load_workspace_configs(relative)
    if not workspaces:
        raise HTTPException(status_code=404, detail=f"No workspaces found in {relative}")
    return relative, workspaces


def _discover_experiments() -> list[dict[str, Any]]:
    experiments_root = ROOT_DIR / "experiments"
    items: list[dict[str, Any]] = []
    default_task_dir = _relative_task_dir()
    if experiments_root.exists():
        for path in sorted(experiments_root.iterdir()):
            if not path.is_dir():
                continue
            workspaces = load_workspace_configs(path)
            if not workspaces:
                continue
            task_files = discover_shared_task_files(path)
            relative = path.relative_to(ROOT_DIR).as_posix()
            items.append(
                {
                    "key": relative,
                    "name": _experiment_name(path),
                    "path": relative,
                    "model_count": len(workspaces),
                    "task_file_count": len(task_files),
                    "is_default": relative == default_task_dir,
                }
            )
    if not items:
        relative, workspaces = _load_workspaces()
        items.append(
            {
                "key": relative,
                "name": _experiment_name(Path(relative)),
                "path": relative,
                "model_count": len(workspaces),
                "task_file_count": len(discover_shared_task_files(relative)),
                "is_default": True,
            }
        )
    return items


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT_DIR / "bench" / "static" / "index.html")


@app.get("/api/experiments")
async def experiments() -> list[dict[str, Any]]:
    return _discover_experiments()


@app.get("/api/models")
async def models(task_dir: str | None = Query(default=None)) -> list[dict[str, Any]]:
    _, workspaces = _load_workspaces(task_dir)
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
async def task_files(task_dir: str | None = Query(default=None)) -> list[dict[str, Any]]:
    relative = _relative_task_dir(task_dir)
    return [
        {
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
        }
        for path in discover_shared_task_files(relative)
    ]


@app.post("/api/runs")
async def start_run(req: StartRunRequest) -> dict[str, Any]:
    task_dir, workspaces = _load_workspaces(req.task_dir)
    runner = BenchmarkRunner(ROOT_DIR, workspaces)
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
    active_runs[run_id] = {"status": "running", "summary": None, "task_dir": task_dir}

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
