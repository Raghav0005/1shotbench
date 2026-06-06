#!/usr/bin/env python3
"""NFCorpus Live Retrieval Diagnostics Workbench — Flask backend."""

import json
import os
import subprocess
import tempfile
import time
import threading
import re
import sys
import glob as globmod
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
CACHE_DIR = os.path.join(DATA_DIR, "cache")
ANSERINI_JAR_DIR = os.path.join(DATA_DIR, "jar")
RUN_DIR = os.path.join(DATA_DIR, "runs")
LOG_DIR = os.path.join(DATA_DIR, "logs")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(ANSERINI_JAR_DIR, exist_ok=True)
os.makedirs(RUN_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

PREBUILT_INDEX = "beir-v1.0.0-nfcorpus.flat"
TOPICS_SYMBOL = "beir-v1.0.0-nfcorpus.test"
EXPECTED_METRICS = {
    "nDCG@10": 0.3218,
    "R@100": 0.2457,
    "R@1000": 0.3704,
}

SAMPLE_QUERIES = [
    "Do Cholesterol Statin Drugs Cause Breast Cancer?",
    "Health Benefits of Turmeric",
    "Are Organic Foods Safer?",
    "How to Reduce Exposure to Alkylphenols Through Your Diet",
    "Plant-Based Diets for Psoriasis",
    "Preventing Strokes with Diet",
    "Are Avocados Good for You?",
    "Breast Cancer and Diet",
]

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder="static", static_url_path="/static")

state = {
    "setup_status": "pending",       # pending | running | ready | failed
    "setup_error": None,
    "java_version": None,
    "anserini_jar": None,
    "anserini_version": None,
    "index_status": "pending",       # pending | ready | failed
    "evaluation_status": "pending",  # pending | ready | failed
    "evaluation_results": None,
    "evaluation_elapsed": None,
    "search_available": False,
    "commands": {},
    "artifacts": {},
    "setup_log": [],
    "reproduction_config": None,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_jar():
    """Return path to the Anserini fatjar, or None."""
    jars = sorted(Path(ANSERINI_JAR_DIR).glob("anserini-*-fatjar.jar"))
    if jars:
        return str(jars[-1])
    return None


def run_cmd(cmd, timeout=None, log_key=None):
    """Run a command, capture output. Returns (returncode, stdout, stderr)."""
    if isinstance(cmd, str):
        cmd_str = cmd
    else:
        cmd_str = " ".join(str(c) for c in cmd)
    state["setup_log"].append(f"$ {cmd_str}")
    try:
        result = subprocess.run(
            cmd_str, shell=True, capture_output=True, text=True, timeout=timeout,
        )
        state["setup_log"].append(result.stdout[-2000:] if result.stdout else "")
        if result.stderr:
            state["setup_log"].append(result.stderr[-2000:])
        if log_key:
            state["commands"][log_key] = cmd_str
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        state["setup_log"].append(f"[TIMEOUT after {timeout}s]")
        return -1, "", f"Timeout after {timeout}s"
    except Exception as e:
        state["setup_log"].append(f"[ERROR] {e}")
        return -1, "", str(e)


def java_cmd(*args):
    """Build a java -cp ... command."""
    jar = find_jar()
    parts = ["java", "--enable-native-access=ALL-UNNAMED", "-cp", jar] + list(args)
    return " ".join(parts)

# ---------------------------------------------------------------------------
# Setup workflow (runs in background thread)
# ---------------------------------------------------------------------------

def setup_workflow():
    """Download fatjar, verify, run evaluation."""
    state["setup_status"] = "running"
    try:
        # Step 1: Check Java
        rc, out, err = run_cmd("java -version 2>&1", log_key="java_version")
        if rc == 0:
            m = re.search(r'version "([^"]+)"', out)
            state["java_version"] = m.group(1) if m else out.strip().split("\n")[0]
        else:
            raise RuntimeError(f"Java not available: {err}")

        # Step 2: Download fatjar if needed
        jar = find_jar()
        if not jar:
            state["setup_log"].append("Downloading Anserini fatjar...")
            rc, out, _ = run_cmd(
                'curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml | '
                'sed -n \'s:.*<release>\\(.*\\)</release>.*:\\1:p\'',
                log_key="version_check",
            )
            if rc != 0 or not out.strip():
                raise RuntimeError("Could not determine Anserini version from Maven Central")
            version = out.strip().split("\n")[-1].strip()
            state["anserini_version"] = version
            jar_path = os.path.join(ANSERINI_JAR_DIR, f"anserini-{version}-fatjar.jar")
            url = f"https://repo1.maven.org/maven2/io/anserini/anserini/{version}/anserini-{version}-fatjar.jar"
            rc, _, err = run_cmd(f"curl -fL -o '{jar_path}' '{url}'", timeout=300, log_key="fatjar_download")
            if rc != 0:
                raise RuntimeError(f"Failed to download fatjar: {err}")
            jar = jar_path
        else:
            # Extract version from jar name
            m = re.search(r'anserini-(\d+\.\d+[\d.]*)-fatjar\.jar', jar)
            state["anserini_version"] = m.group(1) if m else "unknown"

        state["anserini_jar"] = jar
        state["artifacts"]["fatjar"] = jar

        # Step 3: Verify fatjar with CACM smoke test
        cacm_run = os.path.join(RUN_DIR, "run.cacm.bm25.txt")
        verify_cmd = java_cmd(
            "io.anserini.search.SearchCollection",
            "-threads 1", "-index cacm", "-topics cacm",
            f"-output {cacm_run}", "-hits 1000", "-bm25",
        )
        rc, out, err = run_cmd(verify_cmd, timeout=120, log_key="fatjar_verify")
        if rc != 0:
            raise RuntimeError(f"CACM smoke test failed: {err[:500]}")

        # Step 4: Discover NFCorpus reproduction config (dry-run)
        # Show the config
        rc, out, _ = run_cmd(
            java_cmd("io.anserini.reproduce.ReproduceFromDocumentCollection",
                     "--config beir-v1.0.0-nfcorpus.flat", "--show"),
            timeout=30, log_key="repro_show",
        )
        state["reproduction_config"] = out if rc == 0 else None

        # Dry-run search
        run_cmd(
            java_cmd("io.anserini.reproduce.ReproduceFromDocumentCollection",
                     "--config beir-v1.0.0-nfcorpus.flat", "--search", "--dry-run"),
            timeout=30, log_key="repro_dryrun",
        )

        # Step 5: Run BM25 evaluation against prebuilt NFCorpus index
        state["evaluation_status"] = "running"
        eval_run_file = os.path.join(RUN_DIR, "run.nfcorpus.bm25.txt")
        eval_output_file = os.path.join(RUN_DIR, "eval.nfcorpus.bm25.txt")

        search_cmd = java_cmd(
            "io.anserini.search.SearchCollection",
            "-threads 1",
            f"-index {PREBUILT_INDEX}",
            f"-topics {TOPICS_SYMBOL}",
            f"-output {eval_run_file}",
            "-topicReader TsvString",
            "-bm25 -removeQuery -hits 1000",
        )
        state["commands"]["bm25_search"] = search_cmd
        t0 = time.time()
        rc, out, err = run_cmd(search_cmd, timeout=300, log_key="bm25_search")
        elapsed_search = time.time() - t0

        if rc != 0:
            state["evaluation_status"] = "failed"
            raise RuntimeError(f"BM25 SearchCollection failed: {err[:500]}")

        state["artifacts"]["run_file"] = eval_run_file

        # Step 6: Evaluate with TrecEval (run each metric separately to avoid
        # trec_eval conflating recall.100 and recall.1000)
        metric_flags = {
            "nDCG@10": "-m ndcg_cut.10",
            "R@100": "-m recall.100",
            "R@1000": "-m recall.1000",
        }
        all_eval_output = ""
        observed = {}
        for metric_name, flag in metric_flags.items():
            eval_cmd = java_cmd(
                "io.anserini.eval.TrecEval",
                f"-c {flag}",
                TOPICS_SYMBOL,
                eval_run_file,
            )
            state["commands"][f"eval_{metric_name}"] = eval_cmd
            rc, out, err = run_cmd(eval_cmd, timeout=120, log_key=f"trec_eval_{metric_name}")
            if rc != 0:
                state["evaluation_status"] = "failed"
                raise RuntimeError(f"TrecEval ({metric_name}) failed: {err[:500]}")
            all_eval_output += out
            for line in out.strip().split("\n"):
                parts = line.split("\t")
                if len(parts) >= 3:
                    val = float(parts[2])
                    observed[metric_name] = val

        # Save combined eval output
        with open(eval_output_file, "w") as f:
            f.write(all_eval_output)
        state["artifacts"]["eval_output"] = eval_output_file

        # Compare
        comparison = []
        for metric, expected in EXPECTED_METRICS.items():
            obs = observed.get(metric)
            if obs is not None:
                delta = round(obs - expected, 4)
                if abs(delta) < 0.0001:
                    status = "PASS"
                elif abs(delta) < 0.005:
                    status = "CLOSE"
                else:
                    status = "FAIL"
                comparison.append({
                    "metric": metric,
                    "expected": expected,
                    "observed": obs,
                    "delta": delta,
                    "status": status,
                })

        state["evaluation_results"] = {
            "observed": observed,
            "comparison": comparison,
        }
        state["evaluation_elapsed"] = round(elapsed_search, 2)
        state["evaluation_status"] = "ready"

        # Step 7: Mark search as available
        # Test a quick search to confirm
        test_cmd = java_cmd(
            "io.anserini.cli.Search",
            f"--index {PREBUILT_INDEX}",
            "--query test",
            "--hits 1",
            "--json",
        )
        rc, _, _ = run_cmd(test_cmd, timeout=60, log_key="search_test")
        state["search_available"] = (rc == 0)
        state["index_status"] = "ready"
        state["setup_status"] = "ready"

    except Exception as e:
        state["setup_status"] = "failed"
        state["setup_error"] = str(e)
        if state["evaluation_status"] == "running":
            state["evaluation_status"] = "failed"


def start_setup():
    t = threading.Thread(target=setup_workflow, daemon=True)
    t.start()
    return t

# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({
        "app_status": "running",
        "anserini_available": state["anserini_jar"] is not None,
        "nfcorpus_ready": state["index_status"] == "ready",
        "search_available": state["search_available"],
        "evaluation_available": state["evaluation_status"] == "ready",
        "setup_status": state["setup_status"],
    })


@app.route("/api/status")
def api_status():
    return jsonify({
        "setup_status": state["setup_status"],
        "setup_error": state["setup_error"],
        "java_version": state["java_version"],
        "anserini_jar": state["anserini_jar"],
        "anserini_version": state["anserini_version"],
        "index_status": state["index_status"],
        "evaluation_status": state["evaluation_status"],
        "search_available": state["search_available"],
        "dataset": "NFCorpus (BEIR v1.0.0)",
        "prebuilt_index": PREBUILT_INDEX,
    })


@app.route("/api/evaluation")
def api_evaluation():
    return jsonify({
        "status": state["evaluation_status"],
        "results": state["evaluation_results"],
        "elapsed_seconds": state["evaluation_elapsed"],
        "expected_metrics": EXPECTED_METRICS,
        "reproduction_config": state["reproduction_config"],
    })


@app.route("/api/commands")
def api_commands():
    return jsonify({
        "commands": state["commands"],
        "artifacts": state["artifacts"],
        "setup_log_preview": state["setup_log"][-100:],
    })


@app.route("/api/artifacts/<name>")
def api_artifact(name):
    """Serve an artifact file."""
    allowed = {"run_file": "run_file", "eval_output": "eval_output"}
    if name not in allowed:
        return jsonify({"error": f"Unknown artifact: {name}"}), 404
    path = state["artifacts"].get(name)
    if not path or not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 404
    directory = os.path.dirname(path)
    filename = os.path.basename(path)
    return send_from_directory(directory, filename, as_attachment=True)


@app.route("/api/search", methods=["POST"])
def api_search():
    """Live search over NFCorpus via Anserini CLI."""
    if not state["search_available"]:
        return jsonify({"error": "Search not available yet", "status": state["index_status"]}), 503

    body = request.get_json(force=True, silent=True) or {}
    query = body.get("query", "").strip()
    hits = min(int(body.get("hits", 10)), 100)
    if not query:
        return jsonify({"error": "query is required"}), 400

    search_cmd = java_cmd(
        "io.anserini.cli.Search",
        f"--index {PREBUILT_INDEX}",
        f"--query {subprocess.list2cmdline([query])}",
        f"--hits {hits}",
        "--json",
    )

    try:
        result = subprocess.run(
            search_cmd, shell=True, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return jsonify({"error": result.stderr[:500]}), 500

        # Parse JSON output — skip any lines before the JSON object
        stdout = result.stdout
        json_start = stdout.find("{")
        if json_start < 0:
            return jsonify({"error": "No JSON in output"}), 500
        data = json.loads(stdout[json_start:])

        results = []
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
        return jsonify({"query": query, "results": results, "total": len(results)})

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Search timed out"}), 504
    except json.JSONDecodeError as e:
        return jsonify({"error": f"JSON parse error: {e}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/rerun-evaluation", methods=["POST"])
def api_rerun_evaluation():
    """Trigger a fresh evaluation run."""
    if state["setup_status"] not in ("ready", "failed"):
        return jsonify({"error": "Setup still in progress"}), 409

    def rerun():
        state["evaluation_status"] = "running"
        try:
            eval_run_file = os.path.join(RUN_DIR, f"run.nfcorpus.bm25.rerun.{int(time.time())}.txt")
            eval_output_file = os.path.join(RUN_DIR, f"eval.nfcorpus.bm25.rerun.{int(time.time())}.txt")

            search_cmd = java_cmd(
                "io.anserini.search.SearchCollection",
                "-threads 1",
                f"-index {PREBUILT_INDEX}",
                f"-topics {TOPICS_SYMBOL}",
                f"-output {eval_run_file}",
                "-topicReader TsvString",
                "-bm25 -removeQuery -hits 1000",
            )
            t0 = time.time()
            rc, out, err = run_cmd(search_cmd, timeout=300)
            elapsed = time.time() - t0

            if rc != 0:
                state["evaluation_status"] = "failed"
                return

            state["artifacts"]["run_file_rerun"] = eval_run_file

            # Run each metric separately
            metric_flags = {
                "nDCG@10": "-m ndcg_cut.10",
                "R@100": "-m recall.100",
                "R@1000": "-m recall.1000",
            }
            all_eval_output = ""
            observed = {}
            for metric_name, flag in metric_flags.items():
                eval_cmd = java_cmd(
                    "io.anserini.eval.TrecEval",
                    f"-c {flag}",
                    TOPICS_SYMBOL,
                    eval_run_file,
                )
                rc, out, err = run_cmd(eval_cmd, timeout=120)
                if rc != 0:
                    state["evaluation_status"] = "failed"
                    return
                all_eval_output += out
                for line in out.strip().split("\n"):
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        observed[metric_name] = float(parts[2])

            with open(eval_output_file, "w") as f:
                f.write(all_eval_output)
            state["artifacts"]["eval_output_rerun"] = eval_output_file

            comparison = []
            for metric, expected in EXPECTED_METRICS.items():
                obs = observed.get(metric)
                if obs is not None:
                    delta = round(obs - expected, 4)
                    if abs(delta) < 0.0001:
                        status = "PASS"
                    elif abs(delta) < 0.005:
                        status = "CLOSE"
                    else:
                        status = "FAIL"
                    comparison.append({
                        "metric": metric,
                        "expected": expected,
                        "observed": obs,
                        "delta": delta,
                        "status": status,
                    })

            state["evaluation_results"] = {"observed": observed, "comparison": comparison}
            state["evaluation_elapsed"] = round(elapsed, 2)
            state["evaluation_status"] = "ready"

        except Exception:
            state["evaluation_status"] = "failed"

    t = threading.Thread(target=rerun, daemon=True)
    t.start()
    return jsonify({"status": "rerun_started"})


@app.route("/api/sample-queries")
def api_sample_queries():
    return jsonify({"queries": SAMPLE_QUERIES})


# Serve the SPA
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("static", path)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"Starting NFCorpus Diagnostics Workbench on 0.0.0.0:{port}")
    start_setup()
    app.run(host="0.0.0.0", port=port, debug=False)
