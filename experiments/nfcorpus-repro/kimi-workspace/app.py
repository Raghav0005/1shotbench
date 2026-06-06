import os
import sys
import json
import re
import subprocess
import shlex
import time
import threading
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

APP_DIR = Path(__file__).resolve().parent
CACHE_DIR = APP_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

ANSERINI_VERSION = os.environ.get("ANSERINI_VERSION", "2.1.1")
FATJAR_NAME = f"anserini-{ANSERINI_VERSION}-fatjar.jar"
FATJAR_PATH = CACHE_DIR / FATJAR_NAME

RUN_FILE = CACHE_DIR / "run.nfcorpus.bm25.txt"
EVAL_FILE = CACHE_DIR / "eval.nfcorpus.bm25.txt"
SETUP_LOG = CACHE_DIR / "setup.log"
EVAL_LOG = CACHE_DIR / "eval.log"
DISCOVERY_LOG = CACHE_DIR / "discovery.log"

INDEX_NAME = "beir-v1.0.0-nfcorpus.flat"
TOPICS_NAME = "beir-nfcorpus"
EVAL_KEY = "beir-v1.0.0-nfcorpus.test"

EXPECTED_METRIC = "nDCG@10"
EXPECTED_SCORE = 0.3218
METRIC_TREC_EVAL = "ndcg_cut.10"

# Global state
state = {
    "java_ok": False,
    "java_version": None,
    "fatjar_ok": False,
    "fatjar_path": str(FATJAR_PATH),
    "index_ready": False,
    "index_path": None,
    "discovery_ok": False,
    "discovery_info": {},
    "evaluation_ready": False,
    "evaluation_running": False,
    "evaluation_result": None,
    "eval_run_count": 0,
    "search_available": False,
    "commands": {},
    "errors": [],
    "setup_done": False,
}

state_lock = threading.Lock()


def log(msg):
    print(msg, flush=True)
    with open(SETUP_LOG, "a") as f:
        f.write(msg + "\n")


def run_cmd(cmd_list, cwd=None, timeout=300, capture=True):
    """Run a command and return (returncode, stdout, stderr)."""
    cmd_str = " ".join(shlex.quote(str(c)) for c in cmd_list)
    log(f"[CMD] {cmd_str}")
    try:
        result = subprocess.run(
            cmd_list,
            cwd=cwd,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        if capture:
            if result.stdout:
                log(f"[OUT] {result.stdout[:2000]}")
            if result.stderr:
                log(f"[ERR] {result.stderr[:2000]}")
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired:
        log(f"[TIMEOUT] {cmd_str}")
        return -1, "", "timeout"
    except Exception as e:
        log(f"[EXCEPTION] {cmd_str}: {e}")
        return -1, "", str(e)


def ensure_fatjar():
    if FATJAR_PATH.exists():
        return True
    url = (
        f"https://repo1.maven.org/maven2/io/anserini/anserini/"
        f"{ANSERINI_VERSION}/{FATJAR_NAME}"
    )
    log(f"Downloading fatjar from {url}")
    code, out, err = run_cmd(["curl", "-fL", "-o", str(FATJAR_PATH), url], timeout=180)
    if code != 0 or not FATJAR_PATH.exists():
        state["errors"].append(f"Failed to download fatjar: {err}")
        return False
    return True


def check_java():
    code, out, err = run_cmd(["java", "-version"], timeout=30)
    combined = out + "\n" + err
    version_match = re.search(r'version "?(\d+)', combined)
    if version_match:
        major = int(version_match.group(1))
        state["java_version"] = combined.strip().splitlines()[0]
        if major == 21:
            state["java_ok"] = True
        else:
            state["errors"].append(f"Java major version {major} found, require 21")
    else:
        state["errors"].append("Could not determine Java version")


def discovery_reproduction():
    """Run reproduction discovery to get expected metrics."""
    if not state["fatjar_ok"]:
        return
    cmd = [
        "java",
        "-cp", str(FATJAR_PATH),
        "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
        "--config", "beir.core",
        "--show",
    ]
    code, out, err = run_cmd(cmd, timeout=60)
    with open(DISCOVERY_LOG, "w") as f:
        f.write(f"Command: {' '.join(cmd)}\n")
        f.write(f"Stdout:\n{out}\n")
        f.write(f"Stderr:\n{err}\n")
    state["commands"]["discovery"] = " ".join(shlex.quote(str(c)) for c in cmd)
    if code == 0 and out:
        # Parse YAML-like output for nfcorpus expected score
        # Look for nfcorpus under flat condition
        try:
            import yaml
            data = yaml.safe_load(out)
            conditions = data.get("conditions", [])
            for cond in conditions:
                if cond.get("name") == "flat":
                    for topic in cond.get("topics", []):
                        if topic.get("topic_key") == "nfcorpus":
                            expected = topic.get("expected_scores", {})
                            metric_defs = topic.get("metric_definitions", {})
                            state["discovery_info"] = {
                                "condition": "flat",
                                "topic_key": "nfcorpus",
                                "eval_key": topic.get("eval_key"),
                                "expected_scores": expected,
                                "metric_definitions": metric_defs,
                            }
                            state["discovery_ok"] = True
                            return
        except Exception as e:
            log(f"YAML parse error: {e}")
            # Fallback regex parsing
            if "nfcorpus" in out and "nDCG@10" in out:
                match = re.search(r'nDCG@10:\s*([0-9.]+)', out)
                if match:
                    state["discovery_info"] = {
                        "condition": "flat",
                        "topic_key": "nfcorpus",
                        "eval_key": EVAL_KEY,
                        "expected_scores": {EXPECTED_METRIC: float(match.group(1))},
                        "metric_definitions": {EXPECTED_METRIC: "-c -m ndcg_cut.10"},
                    }
                    state["discovery_ok"] = True
                    return
    state["errors"].append("Reproduction discovery failed or returned no expected metrics")


def find_index_path():
    """Try to locate the cached index path."""
    cache_root = Path.home() / ".cache" / "pyserini" / "indexes"
    if cache_root.exists():
        for p in cache_root.iterdir():
            if "nfcorpus" in p.name.lower() and p.is_dir():
                return str(p)
    return None


def run_evaluation():
    """Run SearchCollection + TrecEval for NFCorpus."""
    with state_lock:
        if state["evaluation_running"]:
            return
        state["evaluation_running"] = True
        state["evaluation_ready"] = False

    log("Starting NFCorpus BM25 evaluation...")
    start = time.time()

    # SearchCollection
    search_cmd = [
        "java",
        "-cp", str(FATJAR_PATH),
        "io.anserini.search.SearchCollection",
        "-threads", "1",
        "-index", INDEX_NAME,
        "-topics", TOPICS_NAME,
        "-output", str(RUN_FILE),
        "-hits", "1000",
        "-bm25",
        "-removeQuery",
    ]
    code, out, err = run_cmd(search_cmd, timeout=300)
    state["commands"]["searchcollection"] = " ".join(shlex.quote(str(c)) for c in search_cmd)
    if code != 0:
        state["errors"].append(f"SearchCollection failed: {err}")
        state["evaluation_running"] = False
        return

    # Find index path after search (it downloads on first use)
    idx_path = find_index_path()
    if idx_path:
        state["index_path"] = idx_path
        state["index_ready"] = True

    # TrecEval
    eval_cmd = [
        "java",
        "-cp", str(FATJAR_PATH),
        "io.anserini.eval.TrecEval",
        "-c",
        "-m", METRIC_TREC_EVAL,
        EVAL_KEY,
        str(RUN_FILE),
    ]
    code, out, err = run_cmd(eval_cmd, timeout=60)
    state["commands"]["trec_eval"] = " ".join(shlex.quote(str(c)) for c in eval_cmd)
    elapsed = time.time() - start

    with open(EVAL_FILE, "w") as f:
        f.write(out)
    with open(EVAL_LOG, "w") as f:
        f.write(f"Command: {' '.join(eval_cmd)}\n")
        f.write(f"Stdout:\n{out}\n")
        f.write(f"Stderr:\n{err}\n")

    observed = None
    if code == 0:
        # Parse ndcg_cut_10            all    0.3218
        m = re.search(r'ndcg_cut_10\s+all\s+([0-9.]+)', out)
        if m:
            observed = float(m.group(1))

    expected = EXPECTED_SCORE
    if state["discovery_ok"] and state["discovery_info"].get("expected_scores"):
        expected = state["discovery_info"]["expected_scores"].get(EXPECTED_METRIC, EXPECTED_SCORE)

    delta = round(observed - expected, 4) if observed is not None else None
    if delta is not None and abs(delta) < 0.0001:
        status = "pass"
    elif delta is not None and abs(delta) < 0.01:
        status = "close"
    else:
        status = "fail" if observed is not None else "unknown"

    with state_lock:
        state["eval_run_count"] = state.get("eval_run_count", 0) + 1
        run_count = state["eval_run_count"]

    result = {
        "metric": EXPECTED_METRIC,
        "trec_metric": METRIC_TREC_EVAL,
        "expected": expected,
        "observed": observed,
        "delta": delta,
        "status": status,
        "elapsed_seconds": round(elapsed, 2),
        "run_file": str(RUN_FILE),
        "eval_file": str(EVAL_FILE),
        "eval_stdout": out,
        "run_count": run_count,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "fresh": run_count > 1,
    }

    with state_lock:
        state["evaluation_result"] = result
        state["evaluation_ready"] = True
        state["evaluation_running"] = False
        state["search_available"] = True
    log(f"Evaluation complete: observed={observed}, expected={expected}, status={status}")


def setup():
    """One-time setup on startup."""
    log("=== Setup starting ===")
    check_java()
    if not state["java_ok"]:
        log("Java check failed, aborting setup")
        return

    state["fatjar_ok"] = ensure_fatjar()
    if not state["fatjar_ok"]:
        log("Fatjar unavailable, aborting setup")
        return

    discovery_reproduction()

    # Run evaluation (this also downloads the index on first use)
    run_evaluation()

    state["setup_done"] = True
    log("=== Setup complete ===")


# Start setup in background thread so the server can boot immediately
threading.Thread(target=setup, daemon=True).start()

app = Flask(__name__, static_folder="static")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/health")
def health():
    with state_lock:
        return jsonify({
            "status": "healthy" if state["setup_done"] and state["evaluation_ready"] else "starting",
            "anserini_available": state["fatjar_ok"] and state["java_ok"],
            "nfcorpus_ready": state["index_ready"],
            "search_available": state["search_available"],
            "evaluation_available": state["evaluation_ready"],
        })


@app.route("/api/status")
def api_status():
    with state_lock:
        return jsonify({
            "java_ok": state["java_ok"],
            "java_version": state["java_version"],
            "fatjar_ok": state["fatjar_ok"],
            "fatjar_path": state["fatjar_path"],
            "index_ready": state["index_ready"],
            "index_path": state["index_path"],
            "discovery_ok": state["discovery_ok"],
            "discovery_info": state["discovery_info"],
            "evaluation_ready": state["evaluation_ready"],
            "evaluation_running": state["evaluation_running"],
            "evaluation_result": state["evaluation_result"],
            "search_available": state["search_available"],
            "commands": state["commands"],
            "errors": state["errors"],
            "setup_done": state["setup_done"],
            "cache_dir": str(CACHE_DIR),
        })


@app.route("/api/topics")
def api_topics():
    # Return a curated set of sample topics from NFCorpus
    samples = [
        {"id": "PLAIN-1008", "title": "deafness"},
        {"id": "PLAIN-1018", "title": "DHA"},
        {"id": "PLAIN-102", "title": "Stopping Heart Disease in Childhood"},
        {"id": "PLAIN-12", "title": "Exploiting Autophagy to Live Longer"},
        {"id": "PLAIN-78", "title": "What Do Meat Purge and Cola Have in Common?"},
        {"id": "PLAIN-1817", "title": "peanut butter"},
        {"id": "PLAIN-1950", "title": "prunes"},
        {"id": "PLAIN-2800", "title": "Prolonged Liver Function Enhancement From Broccoli"},
        {"id": "PLAIN-44", "title": "Who Should be Careful About Curcumin?"},
        {"id": "PLAIN-2", "title": "Do Cholesterol Statin Drugs Cause Breast Cancer?"},
    ]
    return jsonify({"dataset": "NFCorpus", "topics": samples})


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    hits = request.args.get("hits", "10")
    if not q:
        return jsonify({"error": "Missing query parameter 'q'"}), 400
    if not state["search_available"]:
        return jsonify({"error": "Search not available yet"}), 503

    try:
        hits_int = min(int(hits), 50)
    except ValueError:
        hits_int = 10

    cmd = [
        "java",
        "-cp", str(FATJAR_PATH),
        "io.anserini.cli.Search",
        "--index", INDEX_NAME,
        "--query", q,
        "--hits", str(hits_int),
        "--json",
    ]
    code, out, err = run_cmd(cmd, timeout=60)
    if code != 0:
        return jsonify({"error": f"Search failed: {err}", "command": " ".join(shlex.quote(str(c)) for c in cmd)}), 500

    # Parse JSON output (may be mixed with log lines)
    json_str = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            json_str = line
            break
    results = None
    if json_str:
        try:
            results = json.loads(json_str)
        except json.JSONDecodeError:
            pass

    return jsonify({
        "query": q,
        "hits": hits_int,
        "results": results,
        "command": " ".join(shlex.quote(str(c)) for c in cmd),
    })


@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    if state["evaluation_running"]:
        return jsonify({"error": "Evaluation already running"}), 409
    # Run in background thread
    threading.Thread(target=run_evaluation, daemon=True).start()
    return jsonify({"message": "Evaluation started", "cached_result": state["evaluation_result"]})


@app.route("/api/evaluate")
def api_evaluate_get():
    with state_lock:
        return jsonify({
            "evaluation_ready": state["evaluation_ready"],
            "evaluation_running": state["evaluation_running"],
            "result": state["evaluation_result"],
        })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
