"""FastAPI application entry point for the NFCorpus diagnostics workbench."""
from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import INDEX_NAME, PUBLIC_HOST, PUBLIC_PORT
from .setup import _terminate_rest_proc, bootstrap_in_background, trigger_rerun
from .state import STATE

APP_ROOT = Path(__file__).resolve().parent
TEMPLATES = APP_ROOT / "templates"
STATIC = APP_ROOT / "static"

app = FastAPI(title="NFCorpus Live Retrieval Diagnostics Workbench")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

_INDEX_HTML = (TEMPLATES / "index.html").read_text()


@app.on_event("startup")
async def _on_startup() -> None:
    bootstrap_in_background()


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    _terminate_rest_proc()


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(_INDEX_HTML)


@app.get("/health")
async def health() -> JSONResponse:
    snap = STATE.to_dict()
    eval_done = snap["evaluation"]["status"] == "done"
    has_observed = any(
        m.get("observed") is not None for m in snap["evaluation"]["metrics"]
    )
    payload = {
        "status": "ok" if snap["phase"] == "ready" else "starting",
        "phase": snap["phase"],
        "anserini": {
            "available": snap["cards"]["fatjar"]["state"] == "ok"
            and snap["cards"]["java"]["state"] == "ok",
            "version": snap["anserini_version"],
            "fatjar": snap["fatjar_path"],
        },
        "nfcorpus": {
            "ready": snap["cards"]["nfcorpus"]["state"] == "ok",
            "index": snap["index_path"],
        },
        "search": {
            "available": snap["cards"]["search"]["state"] == "ok",
            "rest_url": snap["rest_url"],
        },
        "evaluation": {
            "available": eval_done and has_observed,
            "status": snap["evaluation"]["status"],
        },
        "errors": snap["errors"],
    }
    code = 200 if payload["status"] == "ok" else 503 if snap["phase"].startswith("failed") else 200
    return JSONResponse(payload, status_code=code)


@app.get("/api/status")
async def api_status() -> JSONResponse:
    return JSONResponse(STATE.to_dict())


@app.get("/api/search")
async def api_search(q: str = Query(..., min_length=1), hits: int = Query(10, ge=1, le=50)) -> JSONResponse:
    if STATE.search.state != "ok" or not STATE.rest_url:
        raise HTTPException(status_code=503, detail="Live search is not ready yet.")
    qs = urlencode({"query": q, "hits": hits})
    url = f"{STATE.rest_url}/v1/{INDEX_NAME}/search?{qs}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"REST upstream failed: {e!r}")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"REST status {r.status_code}: {r.text[:200]}")
    data = r.json()
    candidates = data.get("candidates", []) or []
    normalized = []
    for i, c in enumerate(candidates[:hits], start=1):
        doc = c.get("doc") or {}
        normalized.append({
            "rank": c.get("rank", i),
            "docid": c.get("docid"),
            "score": c.get("score"),
            "title": doc.get("title", "") or "",
            "text": doc.get("text", "") or "",
            "url": (doc.get("metadata") or {}).get("url", ""),
        })
    return JSONResponse({
        "query": q,
        "hits_requested": hits,
        "hits_returned": len(normalized),
        "index": INDEX_NAME,
        "rest_url": url,
        "results": normalized,
    })


@app.post("/api/evaluate")
async def api_evaluate() -> JSONResponse:
    if STATE.phase != "ready" and not STATE.phase.startswith("running"):
        raise HTTPException(status_code=503, detail=f"Workbench not ready (phase={STATE.phase}).")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, trigger_rerun)
    return JSONResponse({
        "status": result.status,
        "source": result.source,
        "elapsed_seconds": result.elapsed_seconds,
        "run_path": result.run_path,
        "eval_path": result.eval_path,
        "metrics": [m.__dict__ for m in result.metrics],
        "rerun_count": result.rerun_count,
        "error": result.error,
    })


def serve() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=PUBLIC_HOST,
        port=PUBLIC_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    serve()
