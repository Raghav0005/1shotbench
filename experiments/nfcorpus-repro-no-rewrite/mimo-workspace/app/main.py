"""Main Flask application for NFCorpus retrieval diagnostics workbench."""
import json
import os
import re
import subprocess
import time
import threading
from datetime import datetime, timezone
from flask import Flask, jsonify, request, render_template, send_from_directory

from app.settings import (
    ANSERINI_JAR, ANSERINI_VERSION, DATA_DIR, HOST, PORT,
    JAVA_CMD, JAVA_FLAGS, NFCORPUS_INDEX, NFCORPUS_TOPICS,
    NFCORPUS_EVAL_KEY, NFCORPUS_METRIC, NFCORPUS_METRIC_TRECEVAL_FLAG,
    NFCORPUS_EXPECTED_NDCG10, RUN_FILE, EVAL_FILE, SAMPLE_QUERIES,
)

app = Flask(__name__, template_folder="../templates", static_folder="../static")

# ── Global state ─────────────────────────────────────────────────────────────
state = {
    "java_available": False,
    "java_version": None,
    "fatjar_available": False,
    "fatjar_version": None,
    "index_ready": False,
    "evaluation_ready": False,
    "evaluation_results": None,
    "setup_started": False,
    "setup_complete": False,
    "setup_error": None,
    "commands_log": [],
    "last_eval_time": None,
    "eval_in_progress": False,
}
state_lock = threading.Lock()


def log_command(description: str, cmd: list[str], stdout: str, stderr: str, exit_code: int, duration_ms: int):
    """Append a command execution record to the commands log."""
    with state_lock:
        state["commands_log"].append({
            "description": description,
            "command": " ".join(cmd),
            "stdout": stdout[-2000:] if stdout else "",
            "stderr": stderr[-2000:] if stderr else "",
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def run_cmd(description: str, cmd: list[str], timeout: int = 300) -> tuple[int, str, str]:
    """Execute a command, log it, and return (exit_code, stdout, stderr)."""
    start = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        duration_ms = int((time.monotonic() - start) * 1000)
        log_command(description, cmd, result.stdout, result.stderr, result.returncode, duration_ms)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - start) * 1000)
        log_command(description, cmd, "", "TIMEOUT", -1, duration_ms)
        return -1, "", "TIMEOUT"
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        log_command(description, cmd, "", str(e), -1, duration_ms)
        return -1, "", str(e)


# ── Setup ────────────────────────────────────────────────────────────────────
def verify_java():
    """Check that Java 21 is available."""
    with state_lock:
        state["setup_started"] = True
    code, stdout, stderr = run_cmd("Verify Java version", [JAVA_CMD, "-version"])
    combined = stdout + stderr
    if code == 0 and "21" in combined:
        with state_lock:
            state["java_available"] = True
            # Extract version string
            for line in combined.splitlines():
                if "version" in line.lower():
                    state["java_version"] = line.strip()
                    break
        return True
    with state_lock:
        state["setup_error"] = f"Java 21 not found. Exit={code}. Output: {combined[:500]}"
    return False


def verify_fatjar():
    """Check that the Anserini fatjar exists."""
    if os.path.isfile(ANSERINI_JAR):
        with state_lock:
            state["fatjar_available"] = True
            state["fatjar_version"] = f"Anserini {ANSERINI_VERSION} fatjar"
        return True
    with state_lock:
        state["setup_error"] = f"Fatjar not found at {ANSERINI_JAR}"
    return False


def java_cmd(*args: str) -> list[str]:
    """Build a java command list."""
    return [JAVA_CMD] + JAVA_FLAGS + ["-cp", ANSERINI_JAR] + list(args)


def download_index_if_needed():
    """Trigger a lightweight search to ensure the NFCorpus prebuilt index is cached."""
    os.makedirs(DATA_DIR, exist_ok=True)
    test_output = os.path.join(DATA_DIR, "test_index_download.txt")
    cmd = java_cmd(
        "io.anserini.search.SearchCollection",
        "-threads", "1",
        "-index", NFCORPUS_INDEX,
        "-topics", NFCORPUS_TOPICS,
        "-output", test_output,
        "-hits", "10",
        "-bm25",
        "-removeQuery",
    )
    code, stdout, stderr = run_cmd("Download/cache NFCorpus prebuilt index (1 topic, 10 hits)", cmd, timeout=600)
    if code == 0 or os.path.isfile(test_output):
        with state_lock:
            state["index_ready"] = True
        return True
    with state_lock:
        state["setup_error"] = f"Failed to download NFCorpus index. Exit={code}. {stderr[-500:]}"
    return False


def run_evaluation():
    """Run BM25 evaluation on NFCorpus and parse metrics."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with state_lock:
        state["eval_in_progress"] = True

    # Step 1: Run SearchCollection for full evaluation
    search_cmd = java_cmd(
        "io.anserini.search.SearchCollection",
        "-threads", "1",
        "-index", NFCORPUS_INDEX,
        "-topics", NFCORPUS_TOPICS,
        "-output", RUN_FILE,
        "-hits", "1000",
        "-bm25",
        "-removeQuery",
    )
    code, stdout, stderr = run_cmd("BM25 retrieval: SearchCollection over NFCorpus", search_cmd, timeout=600)
    if code != 0:
        with state_lock:
            state["eval_in_progress"] = False
            state["setup_error"] = f"SearchCollection failed. Exit={code}. {stderr[-500:]}"
        return False

    # Step 2: Evaluate with TrecEval
    eval_cmd = java_cmd(
        "io.anserini.eval.TrecEval",
        "-c",
        *NFCORPUS_METRIC_TRECEVAL_FLAG.split(),
        NFCORPUS_EVAL_KEY,
        RUN_FILE,
    )
    code, stdout, stderr = run_cmd("TrecEval: nDCG@10 evaluation", eval_cmd, timeout=120)
    if code != 0:
        with state_lock:
            state["eval_in_progress"] = False
            state["setup_error"] = f"TrecEval failed. Exit={code}. {stderr[-500:]}"
        return False

    # Parse observed metric
    observed = None
    for line in stdout.strip().splitlines():
        parts = line.strip().split()
        if len(parts) >= 3:
            try:
                observed = float(parts[2])
            except ValueError:
                pass

    if observed is None:
        with state_lock:
            state["eval_in_progress"] = False
            state["setup_error"] = f"Could not parse nDCG@10 from TrecEval output: {stdout[:200]}"
        return False

    # Save eval output
    with open(EVAL_FILE, "w") as f:
        f.write(stdout)

    expected = NFCORPUS_EXPECTED_NDCG10
    delta = round(observed - expected, 4)
    status = "PASS" if abs(delta) < 0.001 else ("CLOSE" if abs(delta) < 0.01 else "FAIL")

    with state_lock:
        state["evaluation_results"] = {
            "metric": NFCORPUS_METRIC,
            "expected": expected,
            "observed": observed,
            "delta": delta,
            "status": status,
            "run_file": RUN_FILE,
            "eval_file": EVAL_FILE,
            "eval_output": stdout.strip(),
            "eval_time": datetime.now(timezone.utc).isoformat(),
        }
        state["evaluation_ready"] = True
        state["eval_in_progress"] = False
        state["last_eval_time"] = time.time()

    return True


def setup_background():
    """Run full setup in background thread."""
    try:
        if not verify_java():
            return
        if not verify_fatjar():
            return
        if not download_index_if_needed():
            return
        run_evaluation()
        with state_lock:
            state["setup_complete"] = True
    except Exception as e:
        with state_lock:
            state["setup_error"] = f"Setup exception: {e}"
            state["eval_in_progress"] = False


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", sample_queries=SAMPLE_QUERIES)


@app.route("/health")
def health():
    with state_lock:
        return jsonify({
            "status": "ok" if state["setup_complete"] else ("initializing" if state["setup_started"] else "not_started"),
            "anserini_available": state["java_available"] and state["fatjar_available"],
            "nfcorpus_ready": state["index_ready"],
            "search_available": state["index_ready"],
            "evaluation_available": state["evaluation_ready"],
            "java_version": state.get("java_version"),
            "error": state.get("setup_error"),
        })


@app.route("/api/status")
def api_status():
    with state_lock:
        return jsonify({
            "java_available": state["java_available"],
            "java_version": state.get("java_version"),
            "fatjar_available": state["fatjar_available"],
            "fatjar_version": state.get("fatjar_version"),
            "fatjar_path": ANSERINI_JAR,
            "index_ready": state["index_ready"],
            "evaluation_ready": state["evaluation_ready"],
            "setup_complete": state["setup_complete"],
            "setup_error": state.get("setup_error"),
            "eval_in_progress": state.get("eval_in_progress", False),
            "anserini_version": ANSERINI_VERSION,
            "index_name": NFCORPUS_INDEX,
            "dataset": "NFCorpus (BEIR v1.0.0)",
            "eval_key": NFCORPUS_EVAL_KEY,
        })


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(force=True)
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Empty query"}), 400

    with state_lock:
        if not state["index_ready"]:
            return jsonify({"error": "Index not ready yet"}), 503

    tmp_out = os.path.join(DATA_DIR, f"search_{int(time.time()*1000)}.txt")
    cmd = java_cmd(
        "io.anserini.search.SearchCollection",
        "-threads", "1",
        "-index", NFCORPUS_INDEX,
        "-topics", NFCORPUS_TOPICS,
        "-output", tmp_out,
        "-hits", "10",
        "-bm25",
        "-removeQuery",
    )
    # We use the CLI Search for single query instead
    search_cmd = java_cmd(
        "io.anserini.cli.Search",
        "--index", NFCORPUS_INDEX,
        "--query", query,
        "--hits", "10",
        "--json",
    )
    code, stdout, stderr = run_cmd(f"Live search: \"{query}\"", search_cmd, timeout=60)

    if code != 0:
        return jsonify({"error": f"Search failed: {stderr[-500:]}"}), 500

    # Parse JSON output
    results = []
    try:
        data = json.loads(stdout)
        candidates = data.get("candidates", [])
        for i, c in enumerate(candidates):
            doc = c.get("doc", {})
            results.append({
                "rank": i + 1,
                "docid": c.get("docid", ""),
                "score": c.get("score", 0),
                "title": doc.get("title", ""),
                "text": doc.get("text", "")[:500],
                "url": doc.get("metadata", {}).get("url", ""),
            })
    except json.JSONDecodeError:
        return jsonify({"error": f"Failed to parse search output", "raw": stdout[:500]}), 500

    # Clean up temp file
    if os.path.exists(tmp_out):
        os.remove(tmp_out)

    return jsonify({"query": query, "results": results, "count": len(results)})


@app.route("/api/evaluation")
def api_evaluation():
    with state_lock:
        if state["eval_in_progress"]:
            return jsonify({"status": "in_progress"})
        if not state["evaluation_ready"]:
            return jsonify({"status": "not_ready", "error": state.get("setup_error")})
        return jsonify({"status": "ready", **state["evaluation_results"]})


@app.route("/api/evaluation/rerun", methods=["POST"])
def api_evaluation_rerun():
    with state_lock:
        if state["eval_in_progress"]:
            return jsonify({"error": "Evaluation already in progress"}), 409

    # Run evaluation in background
    threading.Thread(target=run_evaluation, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/commands")
def api_commands():
    with state_lock:
        return jsonify({"commands": state["commands_log"]})


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


# ── Startup ──────────────────────────────────────────────────────────────────
def start_setup():
    os.makedirs(DATA_DIR, exist_ok=True)
    t = threading.Thread(target=setup_background, daemon=True)
    t.start()


start_setup()


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)
