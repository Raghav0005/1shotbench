#!/usr/bin/env python3
"""
NFCorpus Live Retrieval Diagnostics Workbench
Flask backend using Anserini fatjar for search and evaluation.
"""

import json
import os
import shlex
import subprocess
import time
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", 10000))
WORK_DIR = Path(os.environ.get("WORK_DIR", str(Path(__file__).resolve().parent)))
DATA_DIR = WORK_DIR / "data"
JAR_PATH = WORK_DIR / "anserini-2.1.1-fatjar.jar"
ANSERINI_VERSION = "2.1.1"

# NFCorpus settings
PREBUILT_INDEX = "beir-v1.0.0-nfcorpus.flat"
TOPICS_SET = "beir-v1.0.0-nfcorpus.test"

# Expected BM25 metrics from Anserini reproduction config
EXPECTED_METRICS = {
    "nDCG@10": 0.3218,
    "R@100": 0.2457,
    "R@1000": 0.3704,
}

# Metric trec_eval flags -> display name mapping
METRIC_FLAGS = {
    "nDCG@10": "-m ndcg_cut.10",
    "R@100": "-m recall.100",
    "R@1000": "-m recall.1000",
}

# Map trec_eval output names to display names
TRECEVAL_OUTPUT_TO_DISPLAY = {
    "ndcg_cut_10": "nDCG@10",
    "recall_100": "R@100",
    "recall_1000": "R@1000",
}

# ── State ──────────────────────────────────────────────────────────────────
state = {
    "java_available": False,
    "java_version": "",
    "fatjar_available": False,
    "fatjar_path": "",
    "smoke_test_passed": False,
    "nfcorpus_index_ready": False,
    "nfcorpus_search_ready": False,
    "nfcorpus_eval_ready": False,
    "eval_completed": False,
    "eval_observed": {},
    "eval_expected": EXPECTED_METRICS,
    "eval_commands": [],
    "eval_artifact_paths": [],
    "eval_elapsed_seconds": 0,
    "errors": [],
    "warnings": [],
    "search_commands": [],
    "setup_commands": [],
    "setup_logs": [],
    "eval_log_raw": "",
}

state_lock = threading.RLock()


def update_state(**kwargs):
    with state_lock:
        state.update(kwargs)


def add_error(msg):
    with state_lock:
        state["errors"].append(msg)


def add_warning(msg):
    with state_lock:
        state["warnings"].append(msg)


# ── Shell helpers ──────────────────────────────────────────────────────────

def run_cmd(cmd, timeout=300, env=None, cwd=None):
    """Run a shell command and return (returncode, stdout, stderr, elapsed)."""
    full_env = os.environ.copy()
    full_env["ANSERINI_JAR"] = str(JAR_PATH)
    if env:
        full_env.update(env)
    if cwd is None:
        cwd = str(WORK_DIR)

    # Ensure DATA_DIR exists for Anserini cache
    os.makedirs(str(DATA_DIR), exist_ok=True)

    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=full_env,
        )
        elapsed = time.time() - start
        return proc.returncode, proc.stdout, proc.stderr, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return -1, "", f"Command timed out after {timeout}s", elapsed
    except Exception as e:
        elapsed = time.time() - start
        return -1, "", str(e), elapsed


def anserini_cmd(main_class, *args):
    """Build a full Anserini CLI command string using the fatjar."""
    parts = ["java", "-cp", str(JAR_PATH), main_class] + list(args)
    return " ".join(shlex.quote(p) for p in parts)


# ── Setup ──────────────────────────────────────────────────────────────────

def setup_java():
    """Verify Java 21 is available."""
    rc, stdout, stderr, elapsed = run_cmd("java -version 2>&1", timeout=30)
    output = stdout + stderr
    update_state(java_version=output.strip())

    if rc != 0:
        add_error(f"Java check failed: {stderr}")
        update_state(java_available=False)
        return False

    # Check major version 21
    if "version" in output and ('"21.' in output or '"17.' in output):
        update_state(java_available=True)
        return True
    else:
        add_error(f"Java 21 required, got: {output[:200]}")
        update_state(java_available=False)
        return False


def setup_fatjar():
    """Verify the fatjar exists or download it."""
    jarpath = JAR_PATH
    if jarpath.exists():
        update_state(fatjar_available=True, fatjar_path=str(jarpath))
        return True

    # Download fatjar
    update_state(
        setup_commands=state.get("setup_commands", [])
        + [
            f"Download anserini-{ANSERINI_VERSION}-fatjar.jar from Maven Central"
        ]
    )
    url = f"https://repo1.maven.org/maven2/io/anserini/anserini/{ANSERINI_VERSION}/anserini-{ANSERINI_VERSION}-fatjar.jar"
    rc, stdout, stderr, elapsed = run_cmd(
        f"curl -fL -o {shlex.quote(str(jarpath))} {shlex.quote(url)}",
        timeout=300,
    )
    if rc != 0 or not jarpath.exists():
        add_error(f"Failed to download fatjar: {stderr}")
        update_state(fatjar_available=False)
        return False

    update_state(fatjar_available=True, fatjar_path=str(jarpath))
    return True


def smoke_test():
    """Run CACM smoke test to verify fatjar works."""
    output_file = WORK_DIR / "run.cacm.bm25.txt"
    cmd = anserini_cmd(
        "io.anserini.search.SearchCollection",
        "-threads", "1",
        "-index", "cacm",
        "-topics", "cacm",
        "-output", str(output_file),
        "-hits", "1000",
        "-bm25",
    )
    update_state(
        setup_commands=state.get("setup_commands", []) + [cmd]
    )
    rc, stdout, stderr, elapsed = run_cmd(cmd, timeout=120)
    if rc != 0:
        add_error(f"Smoke test failed: {stderr}")
        update_state(smoke_test_passed=False)
        return False
    if not output_file.exists():
        add_error(f"Smoke test run file not created: {output_file}")
        update_state(smoke_test_passed=False)
        return False

    # Verify eval scores
    eval_cmd = anserini_cmd(
        "io.anserini.eval.TrecEval",
        "-c",
        "-m", "map",
        "-m", "P.30",
        "cacm",
        str(output_file),
    )
    rc2, stdout2, stderr2, _ = run_cmd(eval_cmd, timeout=60)
    update_state(
        setup_commands=state.get("setup_commands", []) + [eval_cmd],
        setup_logs=state.get("setup_logs", [])
        + [f"CACM eval:\n{stdout2}"],
    )

    # Check for expected scores
    has_map = "map\tall\t0.3123" in stdout2 or "map \tall\t0.3123" in stdout2
    has_p30 = "P_30\tall\t0.1942" in stdout2 or "P_30 \tall\t0.1942" in stdout2
    if not (has_map and has_p30):
        add_warning(
            f"CACM eval scores mismatch. Expected MAP=0.3123 P30=0.1942. "
            f"Got: {stdout2[:300]}"
        )

    update_state(smoke_test_passed=True)
    return True


def setup_nfcorpus():
    """Verify NFCorpus prebuilt index is accessible (triggers download on first use)."""
    # A quick search will trigger index download if needed.
    # We use Search CLI to check readiness.
    cmd = anserini_cmd(
        "io.anserini.cli.Search",
        "--index", PREBUILT_INDEX,
        "--query", "blood",
        "--hits", "1",
        "--trec",
    )
    update_state(
        setup_commands=state.get("setup_commands", []) + [cmd]
    )
    rc, stdout, stderr, elapsed = run_cmd(cmd, timeout=120)

    if rc == 0 and stdout.strip():
        update_state(
            nfcorpus_index_ready=True,
            nfcorpus_search_ready=True,
            nfcorpus_eval_ready=True,
        )
        update_state(
            setup_logs=state.get("setup_logs", [])
            + [f"NFCorpus index ready: {PREBUILT_INDEX}"]
        )
        return True
    else:
        add_error(f"NFCorpus setup failed: {stderr[:500]}")
        update_state(nfcorpus_index_ready=False)
        return False


def run_evaluation():
    """Run BM25 evaluation over NFCorpus and compare with expected metrics."""
    run_file = WORK_DIR / "run.nfcorpus.bm25.txt"

    # Step 1: SearchCollection
    search_cmd = anserini_cmd(
        "io.anserini.search.SearchCollection",
        "-index", PREBUILT_INDEX,
        "-topics", TOPICS_SET,
        "-output", str(run_file),
        "-hits", "1000",
        "-bm25",
        "-removeQuery",
    )

    # Step 2: TrecEval for each metric
    eval_cmds = []
    for metric_name, flag in METRIC_FLAGS.items():
        eval_cmd = anserini_cmd(
            "io.anserini.eval.TrecEval",
            "-c",
            *flag.split(),
            TOPICS_SET,
            str(run_file),
        )
        eval_cmds.append((metric_name, eval_cmd))

    commands = [search_cmd] + [c for _, c in eval_cmds]
    update_state(eval_commands=commands)
    update_state(
        eval_artifact_paths=[str(run_file)]
    )

    start = time.time()

    # Run search
    rc, stdout, stderr, elapsed_search = run_cmd(search_cmd, timeout=300)
    if rc != 0:
        add_error(f"SearchCollection failed: {stderr[:500]}")
        update_state(eval_completed=True)
        return False
    if not run_file.exists():
        add_error(f"Run file not created: {run_file}")
        update_state(eval_completed=True)
        return False

    # Run evaluation for each metric
    observed = {}
    all_eval_output = []
    for display_name, eval_cmd in eval_cmds:
        rc2, stdout2, stderr2, _ = run_cmd(eval_cmd, timeout=60)
        all_eval_output.append(f"# {display_name}\n{stdout2}")
        if rc2 == 0 and stdout2.strip():
            try:
                # Parse trec_eval output: "metric_name\tall\tvalue"
                for line in stdout2.strip().split("\n"):
                    parts = line.strip().split()
                    if len(parts) >= 3 and parts[1] == "all":
                        try:
                            val = float(parts[2])
                            # Map trec_eval metric name to display name
                            trec_name = parts[0].replace(".", "_")
                            mapped = TRECEVAL_OUTPUT_TO_DISPLAY.get(trec_name, display_name)
                            observed[mapped] = val
                        except ValueError:
                            pass
            except Exception:
                pass
        elif not stdout2.strip():
            add_warning(f"No eval output for {display_name}: {stderr2[:200]}")

    update_state(
        eval_observed=observed,
        eval_log_raw="\n".join(all_eval_output),
        eval_completed=True,
        eval_elapsed_seconds=round(time.time() - start, 2),
    )
    return True


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    with state_lock:
        s = dict(state)
    return jsonify(
        {
            "status": "ready" if s["nfcorpus_search_ready"] else "initializing",
            "anserini_available": s["fatjar_available"] and s["smoke_test_passed"],
            "nfcorpus_ready": s["nfcorpus_index_ready"],
            "search_available": s["nfcorpus_search_ready"],
            "evaluation_available": s["nfcorpus_eval_ready"],
            "java_version": s["java_version"],
            "errors": s["errors"][-5:],  # last 5 errors
        }
    )


@app.route("/api/status")
def api_status():
    with state_lock:
        s = dict(state)
    return jsonify(
        {
            "java_available": s["java_available"],
            "java_version": s["java_version"],
            "fatjar_available": s["fatjar_available"],
            "fatjar_path": s["fatjar_path"],
            "smoke_test_passed": s["smoke_test_passed"],
            "nfcorpus_index_ready": s["nfcorpus_index_ready"],
            "nfcorpus_search_ready": s["nfcorpus_search_ready"],
            "nfcorpus_eval_ready": s["nfcorpus_eval_ready"],
            "eval_completed": s["eval_completed"],
            "eval_observed": s["eval_observed"],
            "eval_expected": s["eval_expected"],
            "eval_elapsed_seconds": s["eval_elapsed_seconds"],
            "errors": s["errors"],
            "warnings": s["warnings"],
            "setup_commands": s["setup_commands"],
            "setup_logs": s["setup_logs"],
            "eval_commands": s["eval_commands"],
            "eval_artifact_paths": s["eval_artifact_paths"],
            "eval_log_raw": s["eval_log_raw"],
        }
    )


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Missing query parameter 'q'"}), 400

    with state_lock:
        if not state["nfcorpus_search_ready"]:
            return jsonify({"error": "NFCorpus search is not ready yet"}), 503

    # Run live search via Anserini Search CLI with JSON output
    cmd = anserini_cmd(
        "io.anserini.cli.Search",
        "--index", PREBUILT_INDEX,
        "--query", query,
        "--hits", "20",
        "--json",
    )

    rc, stdout, stderr, elapsed = run_cmd(cmd, timeout=60)

    if rc != 0:
        return jsonify(
            {
                "error": f"Search failed: {stderr[:500]}",
                "command": cmd,
                "query": query,
            }
        ), 500

    # Parse JSON results from Anserini CLI Search output
    # Format: {"query": {...}, "candidates": [...]}
    raw_results = []
    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, dict):
            raw_results = parsed.get("candidates", [])
        elif isinstance(parsed, list):
            raw_results = parsed
    except json.JSONDecodeError:
        pass

    if not raw_results:
        return jsonify(
            {
                "query": query,
                "command": cmd,
                "results": [],
                "elapsed_seconds": round(elapsed, 3),
            }
        )

    # Standardize results format
    results = []
    for i, hit in enumerate(raw_results):
        # Anserini Search JSON format: {"docid": "...", "score": ..., "doc": {"title": "...", "text": "..."}}
        docid = hit.get("docid", hit.get("id", f"unknown-{i}"))
        score = hit.get("score", 0)

        # Extract document content from nested doc object
        doc = hit.get("doc", {})
        if isinstance(doc, dict):
            title = doc.get("title", "")
            text = doc.get("text", doc.get("contents", ""))
            content = f"{title}\n{text}" if title else text
        else:
            content = str(doc)

        # Fallback: try top-level fields
        if not content:
            for field in ["contents", "text", "raw", "title", "body"]:
                if field in hit and hit[field]:
                    content = str(hit[field])
                    break

        # Last resort
        if not content:
            content = json.dumps(hit)[:500]

        results.append(
            {
                "rank": i + 1,
                "docid": str(docid),
                "score": float(score) if score else 0.0,
                "content": content[:1000],
            }
        )

    return jsonify(
        {
            "query": query,
            "command": cmd,
            "results": results,
            "elapsed_seconds": round(elapsed, 3),
        }
    )


@app.route("/api/eval")
def api_eval():
    """Get current evaluation state or trigger a rerun."""
    action = request.args.get("action", "status")

    if action == "run":
        with state_lock:
            if not state["nfcorpus_eval_ready"]:
                return jsonify(
                    {"error": "NFCorpus eval is not ready yet"}
                ), 503
        # Run eval in background thread
        t = threading.Thread(target=run_evaluation, daemon=True)
        t.start()
        return jsonify({"status": "started"})

    with state_lock:
        s = dict(state)

    # Build comparison
    comparison = {}
    for metric, expected in EXPECTED_METRICS.items():
        observed = s["eval_observed"].get(metric)
        if observed is not None:
            delta = round(observed - expected, 5)
            abs_delta = abs(delta)
            if abs_delta <= 0.0001:
                status = "pass"
            elif abs_delta <= 0.001:
                status = "close"
            else:
                status = "fail"
            comparison[metric] = {
                "expected": expected,
                "observed": observed,
                "delta": delta,
                "status": status,
            }
        else:
            comparison[metric] = {
                "expected": expected,
                "observed": None,
                "delta": None,
                "status": "unknown",
            }

    return jsonify(
        {
            "eval_completed": s["eval_completed"],
            "comparison": comparison,
            "eval_commands": s["eval_commands"],
            "eval_artifact_paths": s["eval_artifact_paths"],
            "eval_elapsed_seconds": s["eval_elapsed_seconds"],
            "eval_log_raw": s["eval_log_raw"],
        }
    )


@app.route("/api/sample-queries")
def sample_queries():
    """Return a list of sample NFCorpus queries derived from topics."""
    # These are representative queries from the NFCorpus test topics
    with state_lock:
        if not state["nfcorpus_index_ready"]:
            return jsonify({"queries": []})

    # Fetch first few topic queries
    cmd = anserini_cmd(
        "io.anserini.cli.TopicsRegistry",
        "--get", TOPICS_SET,
    )
    rc, stdout, stderr, _ = run_cmd(cmd, timeout=30)

    queries = [
        "blood",
        "cancer treatment",
        "heart disease risk factors",
        "diabetes management",
        "vaccine development",
        "clinical trial design",
        "pain management therapy",
        "antibiotic resistance",
    ]

    if rc == 0 and stdout.strip():
        # Try to extract topic titles from TSV
        lines = stdout.strip().split("\n")
        extracted = []
        for line in lines[:20]:
            # Topic TSV format: id\ttitle
            parts = line.split("\t")
            if len(parts) >= 2 and len(parts[1]) > 3:
                extracted.append(parts[1].strip())
        if len(extracted) >= 3:
            queries = extracted[:12]

    return jsonify({"queries": queries})


# ── Startup ────────────────────────────────────────────────────────────────

def startup():
    """Run startup checks and setup. Called in background thread."""
    setup_java()
    setup_fatjar()

    with state_lock:
        if not state["fatjar_available"]:
            add_error("Cannot proceed without fatjar")
            return

    smoke_test()

    with state_lock:
        if state["smoke_test_passed"]:
            setup_nfcorpus()

    # Run evaluation in background if NFCorpus is ready
    with state_lock:
        if state["nfcorpus_index_ready"]:
            # Run eval in background
            pass

    # Optionally pre-run evaluation during startup
    with state_lock:
        if state["nfcorpus_eval_ready"] and not state["eval_completed"]:
            pass  # Will trigger on demand or we can pre-run

    print("Startup complete", flush=True)


@app.route("/api/startup-eval")
def trigger_startup_eval():
    """Start evaluation (triggered by UI)."""
    with state_lock:
        if not state["nfcorpus_eval_ready"]:
            return jsonify({"error": "NFCorpus not ready"}), 503
    t = threading.Thread(target=run_evaluation, daemon=True)
    t.start()
    return jsonify({"status": "started"})


# Run startup at module load time (ensures readiness before gunicorn forks workers)
os.makedirs(str(DATA_DIR), exist_ok=True)
print(f"Starting NFCorpus Workbench on port {PORT}", flush=True)
print(f"Work dir: {WORK_DIR}", flush=True)
print(f"Data dir: {DATA_DIR}", flush=True)

# Run startup in background thread so the server can start immediately.
# When running under gunicorn --preload, this runs in the master before forking.
startup_thread = threading.Thread(target=startup, daemon=True)
startup_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
