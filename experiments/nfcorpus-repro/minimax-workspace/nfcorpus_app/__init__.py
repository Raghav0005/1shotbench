"""Flask application package for the NFCorpus Diagnostics Workbench.

The app exposes:

* `/` -- diagnostics dashboard (HTML).
* `/api/health` -- JSON health probe suitable for Render.
* `/api/status` -- full readiness signal for the UI.
* `/api/setup/fatjar` -- trigger fatjar download.
* `/api/setup/reproduction` -- reproduction discovery (NFCorpus).
* `/api/search` -- live BM25 search over NFCorpus.
* `/api/evaluate` -- cached or fresh BM25 evaluation.
* `/api/verify` -- alias for evaluation with `force=true`.
* `/api/artifacts` -- list of generated artifact paths.
* `/api/commands/<name>` -- raw stdout/stderr of a recorded command.

The application must be importable as `nfcorpus_app.app:app` for gunicorn.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from . import anserini, config


def create_app() -> Flask:
    config.ensure_dirs()
    app = Flask(
        __name__,
        static_folder=str(Path(__file__).parent / "static"),
        static_url_path="/static",
    )

    # ------------------------------------------------------------------ pages
    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    # ----------------------------------------------------------------- health
    @app.route("/health")
    @app.route("/api/health")
    def health():
        rt = anserini.runtime_status()
        search_available = (
            rt["ready"]
            and config.ANSERINI_JAR.exists()
            and rt["index"]["available"]
        )
        eval_available = search_available
        status_body = {
            "status": "ok" if rt["ready"] else "degraded",
            "app": "nfcorpus-diagnostics-workbench",
            "java_available": rt["java"]["available"],
            "java_major": rt["java"]["major"],
            "anserini_available": rt["fatjar"]["available"],
            "anserini_version": rt["fatjar"].get("version"),
            "nfcorpus_ready": rt["index"]["available"],
            "search_available": search_available,
            "evaluation_available": eval_available,
            "port": config.PORT,
            "timestamp": time.time(),
        }
        return jsonify(status_body), 200 if rt["ready"] else 503

    # ----------------------------------------------------------------- status
    @app.route("/api/status")
    def status():
        rt = anserini.runtime_status()
        repro = anserini.parse_nfcorpus_reproduction()
        return jsonify({
            "runtime": rt,
            "dataset": {
                "name": "nfcorpus",
                "reproduction_config": repro["reproduction_config"],
                "condition": repro["condition"],
                "index": repro["index"],
                "topics": repro["topics"],
                "eval_key": repro["eval_key"],
                "expected_scores": repro["expected_scores"],
            },
            "ready_for_live_search": rt["ready"],
            "ready_for_evaluation": rt["ready"],
        })

    # --------------------------------------------------------------- setup
    @app.route("/api/setup/fatjar", methods=["POST", "GET"])
    def setup_fatjar():
        body = request.get_json(silent=True) or {}
        version = body.get("version")
        if not config.ANSERINI_JAR.exists():
            cmd = anserini.download_fatjar(version=version)
            if not cmd.ok:
                return jsonify({
                    "ok": False,
                    "stage": "download",
                    "command": cmd.to_dict(),
                }), 500
        # Verify by running the `--list` reproduction command -- this is the
        # cheapest way to confirm the jar is reachable and runnable.
        verify = anserini.reproduction_list()
        if not verify.ok:
            return jsonify({
                "ok": False,
                "stage": "verify",
                "command": verify.to_dict(),
            }), 500
        return jsonify({
            "ok": True,
            "fatjar": anserini.fatjar_status(),
            "verify": verify.to_dict(),
        })

    @app.route("/api/setup/reproduction", methods=["GET"])
    def setup_reproduction():
        info = anserini.parse_nfcorpus_reproduction()
        return jsonify(info)

    # -------------------------------------------------------------- search
    @app.route("/api/search")
    def search():
        query = (request.args.get("q") or "").strip()
        if not query:
            return jsonify({"ok": False, "error": "missing query parameter `q`"}), 400
        try:
            hits = int(request.args.get("hits", "10"))
        except ValueError:
            hits = 10
        hits = max(1, min(hits, 50))
        rt = anserini.runtime_status()
        if not rt["ready"]:
            return jsonify({
                "ok": False,
                "error": "application not ready: java, fatjar, and NFCorpus index must be present",
                "runtime": rt,
            }), 503
        try:
            cmd = anserini.live_search(query, hits=hits)
        except FileNotFoundError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503
        if not cmd.ok:
            return jsonify({
                "ok": False,
                "error": "Anserini search command failed",
                "command": cmd.to_dict(),
            }), 500
        # The Anserini Search --json output is wrapped in a top-level object
        # keyed by `query`/`candidates`. Parse it so the UI does not have to.
        try:
            payload = json.loads(cmd.stdout.splitlines()[-1] if cmd.stdout.startswith("WARNING") else cmd.stdout)
        except json.JSONDecodeError:
            # Fall back to the full stdout (Anserini may emit warnings on stdout)
            try:
                payload = json.loads(cmd.stdout)
            except json.JSONDecodeError:
                payload = {"raw": cmd.stdout}
        results = []
        for idx, hit in enumerate(payload.get("candidates", []), start=1):
            doc = hit.get("doc", {}) or {}
            text = doc.get("text", "")
            results.append({
                "rank": idx,
                "docid": hit.get("docid"),
                "score": hit.get("score"),
                "title": doc.get("title"),
                "snippet": (text[:600] + "…") if len(text) > 600 else text,
                "url": (doc.get("metadata") or {}).get("url"),
            })
        return jsonify({
            "ok": True,
            "query": payload.get("query", {}).get("text", query),
            "query_raw": query,
            "results": results,
            "command": cmd.to_dict(),
        })

    # ------------------------------------------------------------- evaluate
    @app.route("/api/evaluate", methods=["GET", "POST"])
    def evaluate():
        force = request.args.get("force", "false").lower() in ("1", "true", "yes")
        if request.method == "POST":
            body = request.get_json(silent=True) or {}
            force = force or bool(body.get("force"))
        result = anserini.run_full_evaluation(force=force)
        result["force"] = force
        return jsonify(result), 200 if result["ok"] else 500

    @app.route("/api/verify", methods=["POST"])
    def verify():
        body = request.get_json(silent=True) or {}
        force = bool(body.get("force", True))
        result = anserini.run_full_evaluation(force=force)
        result["force"] = force
        return jsonify(result), 200 if result["ok"] else 500

    # --------------------------------------------------------- artifacts
    @app.route("/api/artifacts")
    def artifacts():
        config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        config.EVAL_DIR.mkdir(parents=True, exist_ok=True)
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        paths = []
        for root in (config.RUNS_DIR, config.EVAL_DIR, config.LOG_DIR):
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    paths.append({
                        "path": str(p),
                        "size_bytes": p.stat().st_size,
                        "kind": root.name,
                    })
        return jsonify({"paths": paths, "data_dir": str(config.DATA_DIR)})

    @app.route("/api/commands/<name>")
    def command_log(name: str):
        safe = (name or "").replace("/", "_").replace("..", "_")
        log_path = config.LOG_DIR / safe
        if not log_path.exists():
            return jsonify({"ok": False, "error": f"no log named {name}"}), 404
        text = log_path.read_text()
        return jsonify({
            "ok": True,
            "name": name,
            "path": str(log_path),
            "text": text if len(text) < 200000 else text[:200000] + "\n... [truncated]",
        })

    # ------------------------------------------------------- bootstrap
    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "not found"}), 404

    return app


# WSGI entrypoint: `gunicorn nfcorpus_app:app`
app = create_app()
