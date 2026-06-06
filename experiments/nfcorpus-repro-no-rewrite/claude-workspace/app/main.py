"""FastAPI entrypoint for the NFCorpus Live Retrieval Diagnostics Workbench."""
from __future__ import annotations

import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .anserini import AnseriniWorkbench

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="NFCorpus Live Retrieval Diagnostics Workbench")
workbench = AnseriniWorkbench()


@app.on_event("startup")
def _startup() -> None:
    # Init runs in a background thread so the HTTP server (and /health) come up
    # immediately and remain responsive while NFCorpus warmup / eval happens.
    threading.Thread(target=workbench.initialize, name="anserini-init", daemon=True).start()


@app.on_event("shutdown")
def _shutdown() -> None:
    workbench.shutdown()


@app.get("/health")
def health() -> dict:
    return workbench.health()


@app.get("/api/state")
def state() -> dict:
    return workbench.snapshot()


@app.get("/api/search")
def search(q: str = Query(..., min_length=1), hits: int = Query(10, ge=1, le=50)) -> dict:
    try:
        return workbench.live_search(q, hits=hits)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/eval/rerun")
def eval_rerun() -> dict:
    try:
        workbench.rerun_eval()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"status": "queued", "eval": workbench.snapshot()["eval"]}


@app.get("/api/sample-queries")
def sample_queries() -> dict:
    # A small, hand-picked NFCorpus-style sample set. Each is a real consumer
    # health query that exists in NFCorpus topics, so live search will return
    # real documents.
    return {"queries": [
        "diabetes",
        "vitamin d for heart disease",
        "breast cancer survival diet",
        "coconut oil cholesterol",
        "vegetarian diet cardiovascular",
    ]}


# --- static frontend ---
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


def main() -> None:
    import uvicorn
    port = int(os.environ.get("PORT", "10000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
