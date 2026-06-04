"""
NFCorpus Live Retrieval Diagnostics Workbench

Flask server that wraps Anserini CLI commands for live search and
BM25 evaluation over the NFCorpus dataset.
"""

import json
import os
import subprocess
import threading
import time
import logging

from flask import Flask, jsonify, request, send_from_directory

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PORT = int(os.environ.get("PORT", "10000"))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
CACHE_DIR = os.environ.get("CACHE_DIR", os.path.join(DATA_DIR, "cache"))
ANSERINI_VERSION = os.environ.get("ANSERINI_VERSION", "2.1.1")
ANSERINI_JAR = os.environ.get(
    "ANSERINI_JAR",
    os.path.join(DATA_DIR, f"anserini-{ANSERINI_VERSION}-fatjar.jar"),
)

# NFCorpus-specific config derived from beir.core reproduction YAML
NFCORPUS_INDEX = "beir-v1.0.0-nfcorpus.flat"
NFCORPUS_TOPICS = "beir-nfcorpus"
NFCORPUS_QRELS = "beir-v1.0.0-nfcorpus.test"
NFCORPUS_EXPECTED_NDCG10 = 0.3218
NFCORPUS_METRIC_FLAG = "-c -m ndcg_cut.10"

RUNS_DIR = os.path.join(DATA_DIR, "runs")
RUN_FILE = os.path.join(RUNS_DIR, "run.nfcorpus.bm25.flat.txt")
EVAL_FILE = os.path.join(RUNS_DIR, "eval.nfcorpus.bm25.flat.txt")

# Sample queries from the NFCorpus topics
SAMPLE_QUERIES = [
    {"id": "PLAIN-307", "title": "Vitamin D: Shedding some light on the new recommendations"},
    {"id": "PLAIN-1635", "title": "milk"},
    {"id": "PLAIN-227", "title": "Increasing Muscle Strength with Fenugreek"},
    {"id": "PLAIN-934", "title": "coffee"},
    {"id": "PLAIN-280", "title": "Mercury Testing Recommended Before Pregnancy"},
    {"id": "PLAIN-1741", "title": "nuts"},
    {"id": "PLAIN-2", "title": "Do Cholesterol Statin Drugs Cause Breast Cancer?"},
    {"id": "PLAIN-112", "title": "Food Dyes and ADHD"},
    {"id": "PLAIN-2470", "title": "Is Milk Good for Our Bones?"},
    {"id": "PLAIN-1109", "title": "endocrine disruptors"},
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nfcorpus-workbench")

# ---------------------------------------------------------------------------
# Application State
# ---------------------------------------------------------------------------
app_state = {
    "setup_complete": False,
    "setup_running": False,
    "setup_error": None,
    "java_version": None,
    "fatjar_ready": False,
    "nfcorpus_index_ready": False,
    "topics_discovered": False,
    "reproduction_discovered": False,
    "sample_topics": [],
    "evaluation": None,
    "evaluation_error": None,
    "evaluation_elapsed": None,
    "evaluation_cached": False,
    "commands": {
        "fatjar_verify": None,
        "smoke_test": None,
        "reproduction_dry_run": None,
        "search_collection": None,
        "eval_command": None,
        "search_cli_template": None,
    },
    "artifacts": {},
    "setup_log": [],
}

setup_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_cmd(cmd_str, timeout=600, cwd=None):
    """Run a shell command, capture stdout/stderr, return result dict."""
    log.info("Running: %s", cmd_str)
    app_state["setup_log"].append(f"$ {cmd_str}")
    try:
        result = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if out:
            app_state["setup_log"].append(out)
        if err:
            app_state["setup_log"].append(f"[stderr] {err[:2000]}")
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": out,
            "stderr": err,
        }
    except subprocess.TimeoutExpired:
        app_state["setup_log"].append("[timeout]")
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": "timeout"}
    except Exception as e:
        app_state["setup_log"].append(f"[error] {e}")
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(e)}


def java_cmd(extra_args):
    """Build a java -cp command with the fatjar."""
    return f'java -cp "{ANSERINI_JAR}" {extra_args}'


def parse_eval_output(text):
    """Parse trec_eval output lines like 'ndcg_cut_10\\tall\\t0.3218'."""
    metrics = {}
    for line in text.strip().split("\n"):
        parts = line.strip().split("\t")
        if len(parts) >= 3:
            metric_name = parts[0].strip()
            metric_val = parts[2].strip()
            try:
                metrics[metric_name] = float(metric_val)
            except ValueError:
                pass
    return metrics


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def do_setup():
    """Run the full setup sequence in a background thread."""
    with setup_lock:
        if app_state["setup_running"]:
            return
        app_state["setup_running"] = True

    try:
        os.makedirs(RUNS_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)

        # 1. Check Java
        r = run_cmd("java -version 2>&1")
        if r["ok"]:
            version_line = r["stdout"].split("\n")[0] if r["stdout"] else "unknown"
            app_state["java_version"] = version_line
        else:
            app_state["setup_error"] = "Java not available"
            return

        # 2. Check/download fatjar
        app_state["commands"]["fatjar_verify"] = f'test -f "{ANSERINI_JAR}"'
        if not os.path.isfile(ANSERINI_JAR):
            dl_cmd = (
                f'curl -fL -o "{ANSERINI_JAR}" '
                f'"https://repo1.maven.org/maven2/io/anserini/anserini/'
                f'{ANSERINI_VERSION}/anserini-{ANSERINI_VERSION}-fatjar.jar"'
            )
            r = run_cmd(dl_cmd, timeout=300)
            if not r["ok"]:
                app_state["setup_error"] = f"Fatjar download failed: {r['stderr']}"
                return

        app_state["fatjar_ready"] = os.path.isfile(ANSERINI_JAR)
        app_state["artifacts"]["fatjar"] = ANSERINI_JAR

        if not app_state["fatjar_ready"]:
            app_state["setup_error"] = "Fatjar not found after download"
            return

        # 3. Smoke test (CACM)
        smoke_cmd = (
            f'java -cp "{ANSERINI_JAR}" io.anserini.search.SearchCollection '
            f"-threads 1 -index cacm -topics cacm "
            f'-output {CACHE_DIR}/run.cacm.bm25.txt -hits 1000 -bm25'
        )
        app_state["commands"]["smoke_test"] = smoke_cmd
        r = run_cmd(smoke_cmd, timeout=300)
        if not r["ok"]:
            log.warning("CACM smoke test failed: %s", r["stderr"])

        # 4. Reproduction discovery (dry-run for beir.core, filter nfcorpus)
        repro_cmd = (
            f'java -cp "{ANSERINI_JAR}" '
            f"io.anserini.reproduce.ReproduceFromPrebuiltIndexes "
            f"--config beir.core --dry-run"
        )
        app_state["commands"]["reproduction_dry_run"] = repro_cmd
        r = run_cmd(repro_cmd, timeout=120)
        if r["ok"]:
            app_state["reproduction_discovered"] = True
            # Store the full dry-run output
            app_state["artifacts"]["reproduction_dry_run_output"] = r["stdout"]

        # 5. Discover topics
        topics_cmd = (
            f'java -cp "{ANSERINI_JAR}" '
            f"io.anserini.cli.TopicsRegistry --get {NFCORPUS_TOPICS}"
        )
        r = run_cmd(topics_cmd, timeout=120)
        if r["ok"]:
            try:
                topics_data = json.loads(r["stdout"])
                app_state["topics_discovered"] = True
                app_state["sample_topics"] = [
                    {"id": k, "title": v.get("title", k)}
                    for k, v in list(topics_data.items())[:10]
                ]
                # If no sample queries loaded from config, use discovered ones
                if not SAMPLE_QUERIES:
                    pass  # keep SAMPLE_QUERIES
                app_state["artifacts"]["topics_count"] = len(topics_data)
            except json.JSONDecodeError:
                log.warning("Failed to parse topics JSON")

        # 6. Run SearchCollection for NFCorpus BM25 evaluation
        search_cmd = (
            f'java -cp "{ANSERINI_JAR}" '
            f"io.anserini.search.SearchCollection "
            f"-threads 1 -index {NFCORPUS_INDEX} "
            f"-topics {NFCORPUS_TOPICS} "
            f"-output {RUN_FILE} -bm25 -removeQuery"
        )
        app_state["commands"]["search_collection"] = search_cmd
        r = run_cmd(search_cmd, timeout=600)
        if not r["ok"]:
            app_state["evaluation_error"] = f"SearchCollection failed: {r['stderr']}"
            # Don't return; we still want search to work via CLI
        else:
            app_state["nfcorpus_index_ready"] = True
            app_state["artifacts"]["run_file"] = RUN_FILE

            # 7. Evaluate
            eval_cmd = (
                f'java -cp "{ANSERINI_JAR}" io.anserini.eval.TrecEval '
                f"{NFCORPUS_METRIC_FLAG} {NFCORPUS_QRELS} {RUN_FILE}"
            )
            app_state["commands"]["eval_command"] = eval_cmd
            eval_start = time.time()
            r = run_cmd(eval_cmd, timeout=300)
            app_state["evaluation_elapsed"] = round(time.time() - eval_start, 2)

            if r["ok"]:
                observed = parse_eval_output(r["stdout"])
                # Write eval output
                with open(EVAL_FILE, "w") as f:
                    f.write(r["stdout"])
                app_state["artifacts"]["eval_file"] = EVAL_FILE

                # Compare with expected
                comparisons = []
                for metric_key, expected_val in [
                    ("ndcg_cut_10", NFCORPUS_EXPECTED_NDCG10)
                ]:
                    obs_val = observed.get(metric_key)
                    if obs_val is not None:
                        delta = round(obs_val - expected_val, 4)
                        abs_delta = abs(delta)
                        if abs_delta < 0.0005:
                            status = "PASS"
                        elif abs_delta < 0.005:
                            status = "CLOSE"
                        else:
                            status = "FAIL"
                        comparisons.append(
                            {
                                "metric": metric_key,
                                "expected": expected_val,
                                "observed": obs_val,
                                "delta": delta,
                                "status": status,
                            }
                        )

                app_state["evaluation"] = {
                    "raw_output": r["stdout"],
                    "observed_metrics": observed,
                    "expected_metrics": {"ndcg_cut_10": NFCORPUS_EXPECTED_NDCG10},
                    "comparisons": comparisons,
                    "run_file": RUN_FILE,
                    "eval_file": EVAL_FILE,
                }
                app_state["evaluation_cached"] = True
            else:
                app_state["evaluation_error"] = f"Evaluation failed: {r['stderr']}"

        # Also try single-query search to verify the index is ready
        test_search_cmd = (
            f'java -cp "{ANSERINI_JAR}" '
            f"io.anserini.cli.Search "
            f"--index {NFCORPUS_INDEX} --query 'test' --hits 1 --json"
        )
        r = run_cmd(test_search_cmd, timeout=120)
        if r["ok"]:
            app_state["nfcorpus_index_ready"] = True
        else:
            log.warning("Test search failed: %s", r["stderr"][:500])

        # Search CLI template
        app_state["commands"]["search_cli_template"] = (
            f'java -cp "{ANSERINI_JAR}" io.anserini.cli.Search '
            f"--index {NFCORPUS_INDEX} --query '<QUERY>' --hits 10 --json"
        )

        app_state["setup_complete"] = True
        log.info("Setup complete.")

    except Exception as e:
        log.exception("Setup failed")
        app_state["setup_error"] = str(e)
    finally:
        app_state["setup_running"] = False


# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    # Serve index.html from the same directory as server.py
    return send_from_directory(os.path.dirname(__file__), "index.html")


@app.route("/health")
def health():
    ready = (
        app_state["setup_complete"]
        and app_state["fatjar_ready"]
        and app_state["nfcorpus_index_ready"]
    )
    return jsonify(
        {
            "status": "ok" if app_state["setup_complete"] else "initializing",
            "anserini_available": app_state["fatjar_ready"],
            "nfcorpus_ready": app_state["nfcorpus_index_ready"],
            "search_available": app_state["nfcorpus_index_ready"],
            "evaluation_available": app_state["evaluation"] is not None,
        }
    )


@app.route("/api/status")
def status():
    return jsonify(
        {
            "setup_complete": app_state["setup_complete"],
            "setup_running": app_state["setup_running"],
            "setup_error": app_state["setup_error"],
            "java_version": app_state["java_version"],
            "fatjar_ready": app_state["fatjar_ready"],
            "nfcorpus_index_ready": app_state["nfcorpus_index_ready"],
            "topics_discovered": app_state["topics_discovered"],
            "reproduction_discovered": app_state["reproduction_discovered"],
            "nfcorpus_index": NFCORPUS_INDEX,
            "nfcorpus_topics": NFCORPUS_TOPICS,
            "nfcorpus_qrels": NFCORPUS_QRELS,
            "anserini_version": ANSERINI_VERSION,
            "anserini_jar": ANSERINI_JAR,
        }
    )


@app.route("/api/sample-queries")
def sample_queries():
    return jsonify({"queries": SAMPLE_QUERIES, "discovered": app_state["sample_topics"]})


@app.route("/api/search", methods=["POST"])
def search():
    body = request.get_json(force=True) if request.is_json else {}
    query = body.get("query", "").strip()
    hits = min(int(body.get("hits", 10)), 100)
    if not query:
        return jsonify({"error": "query is required"}), 400

    search_cmd = (
        f'java -cp "{ANSERINI_JAR}" io.anserini.cli.Search '
        f"--index {NFCORPUS_INDEX} --query '{query.replace("'", "'\\''")}' "
        f"--hits {hits} --json"
    )
    r = run_cmd(search_cmd, timeout=60)
    if not r["ok"]:
        return jsonify({"error": r["stderr"][:1000], "command": search_cmd}), 500

    try:
        data = json.loads(r["stdout"])
        results = []
        candidates = data.get("candidates", [])
        for i, c in enumerate(candidates):
            doc = c.get("doc", {})
            results.append(
                {
                    "rank": i + 1,
                    "docid": c.get("docid", ""),
                    "score": c.get("score", 0),
                    "title": doc.get("title", ""),
                    "text": doc.get("text", "")[:500],
                    "url": doc.get("metadata", {}).get("url", ""),
                }
            )
        return jsonify(
            {
                "query": query,
                "results": results,
                "total": len(results),
                "command": search_cmd,
            }
        )
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Failed to parse search output: {e}", "raw": r["stdout"][:2000]}), 500


@app.route("/api/evaluation")
def evaluation():
    return jsonify(
        {
            "evaluation": app_state["evaluation"],
            "error": app_state["evaluation_error"],
            "elapsed": app_state["evaluation_elapsed"],
            "cached": app_state["evaluation_cached"],
            "expected_ndcg10": NFCORPUS_EXPECTED_NDCG10,
        }
    )


@app.route("/api/commands")
def commands():
    return jsonify(
        {
            "commands": app_state["commands"],
            "artifacts": app_state["artifacts"],
        }
    )


@app.route("/api/setup-log")
def setup_log_endpoint():
    # Return last 200 lines of setup log
    return jsonify({"log": app_state["setup_log"][-200:]})


@app.route("/api/rerun-evaluation", methods=["POST"])
def rerun_evaluation():
    """Re-run the BM25 evaluation from scratch."""
    if app_state["setup_running"]:
        return jsonify({"error": "Setup is already running"}), 409

    app_state["evaluation"] = None
    app_state["evaluation_error"] = None
    app_state["evaluation_cached"] = False

    # Run SearchCollection
    search_cmd = (
        f'java -cp "{ANSERINI_JAR}" '
        f"io.anserini.search.SearchCollection "
        f"-threads 1 -index {NFCORPUS_INDEX} "
        f"-topics {NFCORPUS_TOPICS} "
        f"-output {RUN_FILE} -bm25 -removeQuery"
    )
    r = run_cmd(search_cmd, timeout=600)
    if not r["ok"]:
        app_state["evaluation_error"] = f"SearchCollection failed: {r['stderr']}"
        return jsonify({"error": app_state["evaluation_error"]}), 500

    # Evaluate
    eval_cmd = (
        f'java -cp "{ANSERINI_JAR}" io.anserini.eval.TrecEval '
        f"{NFCORPUS_METRIC_FLAG} {NFCORPUS_QRELS} {RUN_FILE}"
    )
    eval_start = time.time()
    r = run_cmd(eval_cmd, timeout=300)
    app_state["evaluation_elapsed"] = round(time.time() - eval_start, 2)

    if r["ok"]:
        observed = parse_eval_output(r["stdout"])
        with open(EVAL_FILE, "w") as f:
            f.write(r["stdout"])

        comparisons = []
        for metric_key, expected_val in [("ndcg_cut_10", NFCORPUS_EXPECTED_NDCG10)]:
            obs_val = observed.get(metric_key)
            if obs_val is not None:
                delta = round(obs_val - expected_val, 4)
                abs_delta = abs(delta)
                if abs_delta < 0.0005:
                    status = "PASS"
                elif abs_delta < 0.005:
                    status = "CLOSE"
                else:
                    status = "FAIL"
                comparisons.append(
                    {
                        "metric": metric_key,
                        "expected": expected_val,
                        "observed": obs_val,
                        "delta": delta,
                        "status": status,
                    }
                )

        app_state["evaluation"] = {
            "raw_output": r["stdout"],
            "observed_metrics": observed,
            "expected_metrics": {"ndcg_cut_10": NFCORPUS_EXPECTED_NDCG10},
            "comparisons": comparisons,
            "run_file": RUN_FILE,
            "eval_file": EVAL_FILE,
        }

    else:
        app_state["evaluation_error"] = f"Evaluation failed: {r['stderr']}"
        return jsonify({"error": app_state["evaluation_error"]}), 500

    return jsonify(
        {
            "evaluation": app_state["evaluation"],
            "elapsed": app_state["evaluation_elapsed"],
            "cached": False,
        }
    )


@app.route("/api/artifact-preview")
def artifact_preview():
    """Return a preview of a generated artifact file."""
    path = request.args.get("path", "")
    # Security: only allow files under DATA_DIR
    abs_path = os.path.abspath(path)
    if not abs_path.startswith(os.path.abspath(DATA_DIR)):
        return jsonify({"error": "path must be under DATA_DIR"}), 400
    if not os.path.isfile(abs_path):
        return jsonify({"error": "file not found"}), 404
    try:
        with open(abs_path, "r") as f:
            content = f.read(5000)
        return jsonify({"path": abs_path, "preview": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Start setup in background
    setup_thread = threading.Thread(target=do_setup, daemon=True)
    setup_thread.start()

    log.info("Starting server on 0.0.0.0:%d", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False)
