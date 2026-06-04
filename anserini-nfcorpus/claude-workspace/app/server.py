"""Flask application: NFCorpus Live Retrieval Diagnostics Workbench."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import requests
from flask import Flask, jsonify, request, send_from_directory

from . import anserini, setup as setup_mod
from .restserver import RestServerProcess


HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"


SAMPLE_QUERIES: List[Dict[str, str]] = [
    {"id": "PLAIN-3131", "title": "Are Avocados Good for You?"},
    {"id": "PLAIN-2460", "title": "Diabetes as a Disease of Fat Toxicity"},
    {"id": "PLAIN-2820", "title": "Preventing Strokes with Diet"},
    {"id": "PLAIN-2730", "title": "Anti-Angiogenesis: Cutting Off Tumor Supply Lines"},
    {"id": "PLAIN-1635", "title": "milk"},
    {"id": "PLAIN-3221", "title": "Dietary Theory of Alzheimer's"},
]


def _default_cache_dir() -> str:
    return os.environ.get("APP_CACHE_DIR") or str(Path.cwd() / "cache")


def _short(text: str, n: int = 4000) -> str:
    if text is None:
        return ""
    return text if len(text) <= n else text[: n - 200] + "\n... [truncated]"


def _redact_cmd_payload(cmd_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Trim long stdout/stderr fields for transport without losing the command."""
    out = dict(cmd_dict)
    out["stdout"] = _short(out.get("stdout") or "")
    out["stderr"] = _short(out.get("stderr") or "")
    out.pop("argv", None)
    return out


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    cache_dir = _default_cache_dir()
    os.makedirs(cache_dir, exist_ok=True)

    state = setup_mod.initial_state(cache_dir=cache_dir)
    rest_port = int(os.environ.get("ANSERINI_REST_PORT", "8081"))
    rest = RestServerProcess(
        port=rest_port,
        log_path=str(Path(cache_dir) / "restserver.log"),
    )

    app.config["STATE"] = state
    app.config["REST"] = rest
    app.config["SETUP_LOCK"] = threading.Lock()

    # Fire-and-forget the Anserini RestServer.  We do not await it before
    # serving HTTP -- the dashboard renders status while the JVM warms.
    try:
        anserini.jar_path()  # raises if ANSERINI_JAR is missing
        rest.start()
    except Exception as exc:  # pragma: no cover - defensive
        state["errors"].append(f"Failed to start RestServer: {exc}")

    # Background setup pipeline.
    setup_mod.start_background(state)

    @app.route("/health")
    def health():
        ev = state["evaluation"]
        rest_status = rest.status()
        body = {
            "status": "ok" if state["phase"] == "ready" else state["phase"],
            "phase": state["phase"],
            "anserini_available": bool(state["fatjar"].get("verified")),
            "nfcorpus_ready": bool(state["nfcorpus"].get("ready")),
            "search_available": bool(rest_status["ready"]),
            "evaluation_available": bool(ev.get("ran")),
            "dataset": "nfcorpus",
            "anserini_jar": state["fatjar"].get("path"),
            "errors": state["errors"],
        }
        http_status = 200 if state["phase"] in {"ready", "starting", "verifying-java", "verifying-fatjar", "discovering", "searching", "evaluating", "rerunning"} else 503
        return jsonify(body), http_status

    @app.route("/api/status")
    def api_status():
        rest_status = rest.status()
        commands = {k: _redact_cmd_payload(v) for k, v in state["commands"].items()}
        body = {
            "phase": state["phase"],
            "ok": state["ok"],
            "errors": state["errors"],
            "log": state["log"][-40:],
            "started_at": state["started_at"],
            "finished_at": state["finished_at"],
            "java": state["java"],
            "fatjar": state["fatjar"],
            "nfcorpus": state["nfcorpus"],
            "reproduction": state["reproduction"],
            "evaluation": state["evaluation"],
            "rest_server": rest_status,
            "commands": commands,
            "deployment": {
                "port": int(os.environ.get("PORT", "10000")),
                "host_bind": "0.0.0.0",
                "anserini_rest_port": rest_port,
                "cache_dir": cache_dir,
            },
            "sample_queries": SAMPLE_QUERIES,
        }
        return jsonify(body)

    @app.route("/api/sample-queries")
    def api_sample_queries():
        return jsonify({"queries": SAMPLE_QUERIES})

    @app.route("/api/search")
    def api_search():
        q = (request.args.get("q") or "").strip()
        try:
            hits = max(1, min(50, int(request.args.get("hits", "10"))))
        except ValueError:
            hits = 10
        if not q:
            return jsonify({"ok": False, "error": "query parameter q is required"}), 400
        if not rest.status()["ready"]:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Anserini RestServer is not ready yet",
                        "rest_server": rest.status(),
                    }
                ),
                503,
            )
        try:
            result = rest.search(q, hits=hits)
        except requests.HTTPError as exc:
            return (
                jsonify({"ok": False, "error": f"RestServer HTTP error: {exc}"}),
                502,
            )
        except requests.RequestException as exc:
            return (
                jsonify({"ok": False, "error": f"RestServer request failed: {exc}"}),
                502,
            )
        payload = result["payload"]
        candidates = payload.get("candidates") or []
        results = []
        for rank, cand in enumerate(candidates, start=1):
            doc = cand.get("doc") or {}
            results.append(
                {
                    "rank": cand.get("rank") or rank,
                    "docid": cand.get("docid"),
                    "score": cand.get("score"),
                    "title": doc.get("title"),
                    "text": (doc.get("text") or "")[:1500],
                    "metadata": doc.get("metadata") or {},
                }
            )
        return jsonify(
            {
                "ok": True,
                "query": q,
                "hits_requested": hits,
                "elapsed_seconds": result["elapsed_seconds"],
                "request_url": result["request_url"],
                "backend": "anserini.api.RestServer",
                "index": anserini.NFCORPUS_INDEX,
                "results": results,
                "result_count": len(results),
                "rest_server_cmd": rest.cmd_string(),
            }
        )

    @app.route("/api/evaluation")
    def api_evaluation():
        ev = state["evaluation"]
        target = state["reproduction"].get("target") or {}
        commands = {
            k: _redact_cmd_payload(state["commands"][k])
            for k in ("search_collection", "trec_eval")
            if k in state["commands"]
        }
        return jsonify(
            {
                "phase": state["phase"],
                "evaluation": ev,
                "reproduction_target": target,
                "commands": commands,
            }
        )

    @app.route("/api/evaluation/rerun", methods=["POST"])
    def api_rerun():
        lock = app.config["SETUP_LOCK"]
        if not lock.acquire(blocking=False):
            return jsonify({"ok": False, "error": "Another setup/rerun is in progress"}), 409
        try:
            result = setup_mod.rerun_evaluation(state)
            return jsonify(result)
        finally:
            lock.release()

    @app.route("/api/artifacts")
    def api_artifacts():
        artifacts = []
        for path in [
            state["evaluation"].get("run_path"),
            state["evaluation"].get("eval_path"),
            rest.log_path,
            state["fatjar"].get("path"),
        ]:
            if path and os.path.exists(path):
                artifacts.append(
                    {
                        "path": os.path.abspath(path),
                        "bytes": os.path.getsize(path),
                        "modified": os.path.getmtime(path),
                    }
                )
        return jsonify({"artifacts": artifacts, "cache_dir": cache_dir})

    @app.route("/api/artifact-preview")
    def api_artifact_preview():
        path = request.args.get("path", "")
        # Restrict previews to the cache dir + the fatjar path for safety.
        allowed_roots = [os.path.abspath(cache_dir)]
        fatjar = state["fatjar"].get("path")
        if not path or not os.path.isfile(path):
            return jsonify({"ok": False, "error": "path missing"}), 404
        abs_path = os.path.abspath(path)
        if not any(abs_path == os.path.abspath(fatjar or "") or abs_path.startswith(root + os.sep) or abs_path == root for root in allowed_roots):
            return jsonify({"ok": False, "error": "path not allowed"}), 403
        size = os.path.getsize(abs_path)
        max_bytes = 16 * 1024
        with open(abs_path, "rb") as fh:
            head = fh.read(max_bytes)
        try:
            text = head.decode("utf-8")
        except UnicodeDecodeError:
            text = f"[binary file, {size} bytes]"
        return jsonify(
            {
                "ok": True,
                "path": abs_path,
                "bytes": size,
                "preview": text,
                "truncated": size > max_bytes,
            }
        )

    @app.route("/")
    def index():
        return send_from_directory(str(STATIC_DIR), "index.html")

    @app.route("/static/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(str(STATIC_DIR), filename)

    return app


def main() -> None:
    app = create_app()
    port = int(os.environ.get("PORT", "10000"))
    # Render expects the container to bind 0.0.0.0:$PORT.
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
