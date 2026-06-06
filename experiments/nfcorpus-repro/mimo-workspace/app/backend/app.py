"""
Flask application for the NFCorpus Retrieval Diagnostics Workbench.
"""

import threading
from flask import Flask, jsonify, request
from flask_cors import CORS

from .config import Config
from .anserini import manager, initialize_async


def create_app() -> Flask:
    app = Flask(__name__, static_folder="../frontend", static_url_path="")
    CORS(app)

    # Start background initialization
    init_thread = threading.Thread(target=initialize_async, daemon=True)
    init_thread.start()

    @app.route("/health")
    def health():
        """Health endpoint for Render/docker readiness."""
        status = manager.get_status()
        return jsonify({
            "status": "ok" if status["java"]["ok"] and status["fatjar"]["ok"] else "initializing",
            "anserini_available": status["fatjar"]["ok"],
            "nfcorpus_ready": status["nfcorpus"]["index_ready"],
            "search_available": status["search_available"],
            "evaluation_available": status["evaluation_available"],
            "setup_done": manager._setup_done,
            "java_version": status["java"]["version"],
            "anserini_version": status["fatjar"]["version"]
        })

    @app.route("/api/status")
    def api_status():
        """Full status of all components."""
        status = manager.get_status()
        status["setup_done"] = manager._setup_done
        return jsonify(status)

    @app.route("/api/search", methods=["POST"])
    def api_search():
        """Live search endpoint."""
        data = request.get_json() or {}
        query = data.get("query", "").strip()
        hits = min(int(data.get("hits", 10)), 50)

        if not query:
            return jsonify({"error": "Query is required"}), 400

        result = manager.search(query, hits)
        return jsonify(result)

    @app.route("/api/evaluation")
    def api_evaluation():
        """Get evaluation results."""
        force = request.args.get("force", "false").lower() == "true"
        result = manager.run_bm25_evaluation(force=force)
        return jsonify(result)

    @app.route("/api/evaluation/rerun", methods=["POST"])
    def api_evaluation_rerun():
        """Force re-run evaluation."""
        result = manager.run_bm25_evaluation(force=True)
        return jsonify(result)

    @app.route("/api/commands")
    def api_commands():
        """Get the command log."""
        return jsonify({
            "commands": manager.commands_log,
            "artifacts": manager.artifacts
        })

    @app.route("/api/commands/<int:idx>")
    def api_command_detail(idx):
        """Get detail of a specific command."""
        if 0 <= idx < len(manager.commands_log):
            return jsonify(manager.commands_log[idx])
        return jsonify({"error": "Command not found"}), 404

    @app.route("/")
    def index():
        """Serve the frontend."""
        return app.send_static_file("index.html")

    return app


if __name__ == "__main__":
    Config.ensure_dirs()
    app = create_app()
    app.run(host=Config.HOST, port=Config.PORT)
