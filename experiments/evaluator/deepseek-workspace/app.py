#!/usr/bin/env python3
"""Anserini Prebuilt Index Evaluator - Flask backend."""

import json
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, abort

APP = Flask(__name__, static_folder="static", static_url_path="/static")
WORKSPACE = Path(__file__).resolve().parent
ANSERINI_JAR = str(WORKSPACE / "anserini-2.1.1-fatjar.jar")
RUNS_DIR = WORKSPACE / "runs"
RUNS_DIR.mkdir(exist_ok=True)

# In-memory store for run results
_runs = {}
_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Known metric translations: user label → trec_eval metric argument
# ---------------------------------------------------------------------------
METRIC_MAP = {
    "map": "map",
    "ndcg_cut.10": "ndcg_cut.10",
    "ndcg_cut.20": "ndcg_cut.20",
    "ndcg_cut.100": "ndcg_cut.100",
    "ndcg_cut.1000": "ndcg_cut.1000",
    "recall.10": "recall.10",
    "recall.20": "recall.20",
    "recall.100": "recall.100",
    "recall.1000": "recall.1000",
    "P.5": "P.5",
    "P.10": "P.10",
    "P.20": "P.20",
    "P.30": "P.30",
    "P.100": "P.100",
    "P.1000": "P.1000",
    "Rprec": "Rprec",
    "bpref": "bpref",
    "recip_rank": "recip_rank",
}

# Metric groups per qrels key (since not all metrics make sense for all datasets)
# CACM has binary relevance (0/1), so nDCG works but treats all relevant as gain=1
DEFAULT_METRICS_CACM = ["map", "ndcg_cut.10", "recall.1000", "P.10", "P.30"]
DEFAULT_METRICS_GENERAL = ["map", "ndcg_cut.10", "recall.1000", "P.10", "P.30"]

# Human-readable labels for metrics
METRIC_LABELS = {
    "map": "MAP (Mean Average Precision)",
    "ndcg_cut.10": "nDCG@10",
    "ndcg_cut.20": "nDCG@20",
    "ndcg_cut.100": "nDCG@100",
    "ndcg_cut.1000": "nDCG@1000",
    "recall.10": "Recall@10",
    "recall.20": "Recall@20",
    "recall.100": "Recall@100",
    "recall.1000": "Recall@1000",
    "P.5": "Precision@5",
    "P.10": "Precision@10",
    "P.20": "Precision@20",
    "P.30": "Precision@30",
    "P.100": "Precision@100",
    "P.1000": "Precision@1000",
    "Rprec": "R-Precision",
    "bpref": "B-Pref",
    "recip_rank": "Reciprocal Rank",
}


def run_java(*args, timeout=300):
    """Run a java command against the Anserini fatjar."""
    cmd = ["java", "-cp", ANSERINI_JAR] + list(args)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(WORKSPACE),
    )
    return proc


def get_prebuilt_indexes():
    """Fetch all prebuilt inverted indexes from Anserini registry."""
    proc = run_java(
        "io.anserini.cli.PrebuiltIndexRegistry",
        "--list",
        "--type", "inverted",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"PrebuiltIndexRegistry failed: {proc.stderr}")
    # Filter out stderr lines (log output) and parse JSON
    data = _parse_java_json_output(proc.stdout)
    return data


def get_topics():
    """Fetch all topic sets from Anserini TopicsRegistry."""
    proc = run_java(
        "io.anserini.cli.TopicsRegistry",
        "--list",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"TopicsRegistry failed: {proc.stderr}")
    data = _parse_java_json_output(proc.stdout)
    return data if isinstance(data, list) else []


def _parse_java_json_output(stdout):
    """Parse JSON from java output, handling log lines mixed in."""
    # Some Anserini commands emit log lines to stdout before JSON
    # Try to find the JSON portion
    lines = stdout.strip().split("\n")
    # Filter lines that look like JSON
    json_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") or stripped.startswith("{"):
            json_lines.append(stripped)

    if not json_lines:
        # Try parsing the whole output as JSON
        try:
            return json.loads(stdout.strip())
        except json.JSONDecodeError:
            return []

    combined = "".join(json_lines)
    try:
        return json.loads(combined)
    except json.JSONDecodeError:
        # Try last JSON-looking line
        for line in reversed(json_lines):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        return []


def test_qrels_key(qrels_key):
    """Test whether a given key is recognized as a valid qrels source by TrecEval."""
    # Create a minimal valid TREC run file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", dir=str(WORKSPACE), delete=False
    ) as f:
        f.write("1 Q0 DOC1 1 1.0 test\n")
        tmp_path = f.name

    try:
        proc = run_java(
            "io.anserini.eval.TrecEval",
            "-c",
            "-m", "map",
            qrels_key,
            tmp_path,
            timeout=30,
        )
        stderr = proc.stderr.lower()
        stdout = proc.stdout.lower()
        # "cannot read qrels file" → not a valid qrels key
        if "cannot read qrels file" in stderr or "cannot read qrels" in stderr:
            return False
        # If it ran (maybe 0.0 or actual score), it's valid
        if "no queries with both results" in stderr or "no queries with both results" in stdout:
            return True  # qrels exist, just no query overlap — still valid
        return True
    except Exception:
        return False
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def discover_evaluable_pairs():
    """Discover evaluable index/topics/qrels triplets.

    Strategy:
    1. Get all inverted indexes from PrebuiltIndexRegistry
    2. Get all topics from TopicsRegistry
    3. For CACM, use the known pairing (index=cacm, topics=cacm, qrels=cacm)
    4. For other indexes, attempt to find matching topic entries and qrels keys
    """
    indexes = get_prebuilt_indexes()
    topics_list = get_topics()

    # Index the topic list for quick lookup (lowercase)
    topics_set = set()
    for t in topics_list:
        if isinstance(t, str):
            topics_set.add(t.lower())

    evaluable = []

    for idx in indexes:
        idx_name = idx.get("name", "")
        idx_name_lower = idx_name.lower()

        # CACM is always evaluable
        if idx_name_lower == "cacm":
            evaluable.append({
                "index": idx_name,
                "index_info": idx,
                "topics": "cacm",
                "qrels": "cacm",
                "metrics": DEFAULT_METRICS_CACM,
            })
            continue

        # Try to find matching topics
        # Many Anserini topics have the index name as a prefix or exact match
        candidate_topics = []

        # Check exact match (e.g., "robust04" index matches "robust04" topic)
        if idx_name_lower in topics_set:
            candidate_topics.append(idx_name_lower)

        # Check with .dev or .test suffix (e.g., "msmarco-v1-passage" → "msmarco-v1-passage.dev")
        for suffix in [".dev", ".test", "-dev", "-test", ".dev-subset", "-dev-subset"]:
            candidate = idx_name_lower + suffix
            if candidate in topics_set:
                candidate_topics.append(candidate)

        # For beir indexes like "beir-v1.0.0-arguana.flat", try "beir-v1.0.0-arguana.test"
        # Remove trailing .flat or .multifield
        base = re.sub(r"\.(flat|multifield)$", "", idx_name_lower)
        if base != idx_name_lower:
            if base in topics_set:
                candidate_topics.append(base)
            for suffix in [".test", ".dev"]:
                candidate = base + suffix
                if candidate in topics_set:
                    candidate_topics.append(candidate)

        if not candidate_topics:
            continue

        # Try each candidate topic as a qrels key
        for topics_key in candidate_topics:
            if test_qrels_key(topics_key):
                evaluable.append({
                    "index": idx_name,
                    "index_info": idx,
                    "topics": topics_key,
                    "qrels": topics_key,
                    "metrics": DEFAULT_METRICS_GENERAL,
                })
                break  # Use first valid pairing

    return evaluable


def _extract_metric_value(output, metric_key):
    """Extract a metric value from trec_eval output.

    Output format: metric_name  \tall\tvalue
    """
    # trec_eval output: "ndcg_cut_10           	all	0.4543"
    # The metric_key is "ndcg_cut.10" but output uses "ndcg_cut_10"
    output_metric = metric_key.replace(".", "_")
    for line in output.split("\n"):
        parts = line.strip().split()
        if len(parts) >= 3 and parts[0] == output_metric:
            try:
                return float(parts[2])
            except ValueError:
                return None
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@APP.route("/")
def index():
    """Serve the main application page."""
    return send_from_directory(str(WORKSPACE), "index.html")


@APP.route("/api/health")
def health():
    """Health check endpoint."""
    issues = []

    # Check Java
    try:
        proc = subprocess.run(
            ["java", "-version"],
            capture_output=True, text=True, timeout=10,
        )
        java_output = proc.stderr or proc.stdout
        version_match = re.search(r'version "(\d+)', java_output)
        java_major = int(version_match.group(1)) if version_match else 0
        if java_major < 21:
            issues.append(f"Java version {java_major} is too old (need 21+)")
    except Exception as e:
        issues.append(f"Java not found: {e}")

    # Check fatjar
    if not os.path.exists(ANSERINI_JAR):
        issues.append(f"Fatjar not found at {ANSERINI_JAR}")

    return jsonify({
        "status": "ok" if not issues else "degraded",
        "issues": issues,
        "java_version": java_major if 'java_major' in dir() else None,
        "fatjar": ANSERINI_JAR if os.path.exists(ANSERINI_JAR) else None,
    })


@APP.route("/api/indexes")
def list_indexes():
    """List all prebuilt inverted indexes."""
    try:
        indexes = get_prebuilt_indexes()
        # Get evaluable pairs for marking
        evaluable = discover_evaluable_pairs()
        evaluable_indexes = {e["index"] for e in evaluable}

        result = []
        for idx in indexes:
            result.append({
                "name": idx.get("name", ""),
                "type": idx.get("type", ""),
                "description": idx.get("description", ""),
                "filename": idx.get("filename", ""),
                "size": idx.get("size", 0),
                "documents": idx.get("documents", 0),
                "evaluable": idx.get("name", "") in evaluable_indexes,
                "total_terms": idx.get("total_terms"),
                "unique_terms": idx.get("unique_terms"),
            })

        return jsonify({
            "indexes": result,
            "count": len(result),
            "evaluable_count": len(evaluable_indexes),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@APP.route("/api/evaluable")
def list_evaluable():
    """List evaluable index/topics/qrels pairs."""
    try:
        evaluable = discover_evaluable_pairs()

        result = []
        for entry in evaluable:
            idx_info = entry.get("index_info", {})
            result.append({
                "index": entry["index"],
                "topics": entry["topics"],
                "qrels": entry["qrels"],
                "metrics": entry["metrics"],
                "description": idx_info.get("description", ""),
                "documents": idx_info.get("documents", 0),
                "size": idx_info.get("size", 0),
            })

        return jsonify({
            "evaluable": result,
            "count": len(result),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@APP.route("/api/metrics")
def list_metrics():
    """List available metrics."""
    metrics = []
    for key, label in METRIC_LABELS.items():
        metrics.append({"id": key, "label": label})
    return jsonify({"metrics": metrics})


@APP.route("/api/evaluate", methods=["POST"])
def run_evaluation():
    """Run retrieval and evaluation for a given index/topics/qrels/metric triplet."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    index_name = data.get("index")
    topics_key = data.get("topics")
    qrels_key = data.get("qrels")
    metric = data.get("metric", "map")

    if not index_name or not topics_key or not qrels_key:
        return jsonify({"error": "Missing required fields: index, topics, qrels"}), 400

    if metric not in METRIC_MAP:
        return jsonify({"error": f"Unknown metric: {metric}"}), 400

    trec_metric = METRIC_MAP[metric]

    run_id = str(uuid.uuid4())[:8]
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    run_file = str(run_dir / f"run.{index_name}.{run_id}.txt")
    eval_file = str(run_dir / f"eval.{index_name}.{run_id}.txt")

    result = {
        "id": run_id,
        "index": index_name,
        "topics": topics_key,
        "qrels": qrels_key,
        "metric": metric,
        "trec_metric": trec_metric,
        "metric_label": METRIC_LABELS.get(metric, metric),
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "run_file": run_file,
        "eval_file": eval_file,
    }

    with _lock:
        _runs[run_id] = result

    try:
        # Step 1: Run SearchCollection
        search_start = time.time()
        search_proc = run_java(
            "io.anserini.search.SearchCollection",
            "-threads", "1",
            "-index", index_name,
            "-topics", topics_key,
            "-output", run_file,
            "-hits", "1000",
            "-bm25",
            timeout=600,
        )
        search_elapsed = time.time() - search_start

        if search_proc.returncode != 0:
            result["status"] = "error"
            result["error"] = f"SearchCollection failed: {search_proc.stderr[:500]}"
            with _lock:
                _runs[run_id] = result
            return jsonify(result), 500

        if not os.path.exists(run_file):
            result["status"] = "error"
            result["error"] = "Run file was not created"
            with _lock:
                _runs[run_id] = result
            return jsonify(result), 500

        # Step 2: Run TrecEval
        eval_start = time.time()
        eval_proc = run_java(
            "io.anserini.eval.TrecEval",
            "-c",
            "-m", trec_metric,
            qrels_key,
            run_file,
            timeout=120,
        )
        eval_elapsed = time.time() - eval_start

        eval_output = eval_proc.stdout.strip()
        eval_stderr = eval_proc.stderr.strip()

        # Save eval output
        with open(eval_file, "w") as f:
            f.write(eval_output)
            if eval_stderr:
                f.write("\n\n--- stderr ---\n")
                f.write(eval_stderr)

        # Extract score
        score = _extract_metric_value(eval_output, trec_metric)

        # Read run file for preview (first 20 lines)
        run_preview = ""
        try:
            with open(run_file, "r") as f:
                lines = f.readlines()
                run_preview = "".join(lines[:20])
                if len(lines) > 20:
                    run_preview += f"\n... ({len(lines)} total lines)"
        except Exception:
            pass

        result["status"] = "completed"
        result["score"] = score
        result["eval_output"] = eval_output
        result["eval_stderr"] = eval_stderr.strip()
        result["run_preview"] = run_preview
        result["search_elapsed"] = round(search_elapsed, 2)
        result["eval_elapsed"] = round(eval_elapsed, 2)
        result["total_elapsed"] = round(search_elapsed + eval_elapsed, 2)
        result["completed_at"] = datetime.now().isoformat()

    except subprocess.TimeoutExpired as e:
        result["status"] = "error"
        result["error"] = f"Command timed out: {e}"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    with _lock:
        _runs[run_id] = result

    return jsonify(result)


@APP.route("/api/run/<run_id>")
def get_run(run_id):
    """Get status and results for a previous run."""
    with _lock:
        run = _runs.get(run_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(run)


@APP.route("/api/runs")
def list_runs():
    """List all runs."""
    with _lock:
        runs = list(_runs.values())
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return jsonify({"runs": runs})


@APP.route("/api/run/<run_id>/file/<filename>")
def serve_run_file(run_id, filename):
    """Serve a run or eval file."""
    run_dir = RUNS_DIR / run_id
    file_path = run_dir / filename
    if not file_path.exists():
        abort(404)
    return send_from_directory(str(run_dir), filename)


if __name__ == "__main__":
    print(f"Starting Anserini Prebuilt Index Evaluator on http://127.0.0.1:8090")
    print(f"Fatjar: {ANSERINI_JAR}")
    APP.run(host="127.0.0.1", port=8090, debug=False)
