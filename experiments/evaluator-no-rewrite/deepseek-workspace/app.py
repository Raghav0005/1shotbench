#!/usr/bin/env python3
"""Anserini Prebuilt Index Evaluator - Flask web application."""

import json
import os
import subprocess
import time
import uuid
import threading
from datetime import datetime
from pathlib import Path

import yaml
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="/static")

WORKSPACE = Path(__file__).parent
ANSERINI_JAR = str(WORKSPACE / "anserini-fatjar.jar")
RUNS_DIR = WORKSPACE / "runs"
RUNS_DIR.mkdir(exist_ok=True)

# Global state loaded at startup
INDEX_CATALOG = []       # All prebuilt indexes from registry
EVALUABLE_MAP = {}       # index_name -> {topics, qrels, metrics, ...}
RUN_STATUS = {}          # run_id -> status dict


def load_registry():
    """Load prebuilt index registry JSON."""
    reg_file = WORKSPACE / "prebuilt_indexes.json"
    if reg_file.exists():
        with open(reg_file) as f:
            return json.load(f)
    return []


def parse_reproduce_configs():
    """Parse ReproduceFromPrebuiltIndexes configs to build evaluable map.

    Returns:
        dict mapping index_name -> {
            "conditions": [
                {
                    "condition_name": "bm25",
                    "topics": [
                        {
                            "topic_key": "cacm",
                            "eval_key": "cacm",
                            "metrics": {
                                "MAP": {"trec_args": "-c -m map"},
                                "P30": {"trec_args": "-c -m P.30"},
                            }
                        }
                    ]
                }
            ]
        }
    """
    config_file = WORKSPACE / "reproduce_configs.yaml"
    if not config_file.exists():
        return {}

    with open(config_file) as f:
        raw = f.read()

    # Split by "=== config ===" delimiters
    evaluable = {}
    sections = raw.split("=== ")
    for section in sections:
        if not section.strip():
            continue
        # section looks like "config_name ===\n<yaml>"
        parts = section.split(" ===", 1)
        if len(parts) != 2:
            continue
        config_name = parts[0].strip()
        yaml_text = parts[1].strip()

        try:
            parsed = yaml.safe_load(yaml_text)
        except Exception:
            continue

        if not parsed or "conditions" not in parsed:
            continue

        for condition in parsed["conditions"]:
            command = condition.get("command", "")
            # Extract index name from command
            index_name = _extract_index_from_command(command)
            if not index_name:
                continue

            if index_name not in evaluable:
                evaluable[index_name] = []

            for topic_entry in condition.get("topics", []):
                topic_key = topic_entry.get("topic_key", "")
                eval_key = topic_entry.get("eval_key", "")
                metrics = {}

                for metric_name, metric_val in topic_entry.get("metric_definitions", {}).items():
                    metrics[metric_name] = {
                        "trec_args": metric_val,
                    }

                evaluable[index_name].append({
                    "condition_name": condition.get("name", "default"),
                    "topic_key": topic_key,
                    "eval_key": eval_key,
                    "metrics": metrics,
                    "display": condition.get("display", condition.get("name", "")),
                })

    return evaluable


def _extract_index_from_command(command):
    """Extract -index <value> from a SearchCollection command."""
    import re
    match = re.search(r'-index\s+(\S+)', command)
    return match.group(1) if match else None


def run_search_collection(index_name, topic_key, run_id):
    """Run SearchCollection and return the run file path."""
    run_file = RUNS_DIR / f"{run_id}.run.txt"
    cmd = [
        "java", "-cp", ANSERINI_JAR,
        "io.anserini.search.SearchCollection",
        "-threads", "1",
        "-index", index_name,
        "-topics", topic_key,
        "-output", str(run_file),
        "-hits", "1000",
        "-bm25",
    ]

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    elapsed = time.time() - start

    return {
        "run_file": str(run_file),
        "stdout": result.stdout[-5000:] if result.stdout else "",
        "stderr": result.stderr[-5000:] if result.stderr else "",
        "returncode": result.returncode,
        "elapsed": elapsed,
    }


def run_trec_eval(eval_key, run_file, trec_args):
    """Run TrecEval and return the evaluation output."""
    args_list = trec_args.split()
    cmd = [
        "java", "-cp", ANSERINI_JAR,
        "io.anserini.eval.TrecEval",
    ] + args_list + [eval_key, run_file]

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    elapsed = time.time() - start

    return {
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "returncode": result.returncode,
        "elapsed": elapsed,
    }


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.route("/api/catalog")
def api_catalog():
    """Return the full index catalog with evaluable annotations."""
    evaluable_indexes = set(EVALUABLE_MAP.keys())
    result = []
    for idx in INDEX_CATALOG:
        name = idx.get("name", "")
        result.append({
            "name": name,
            "type": idx.get("type", ""),
            "description": idx.get("description", ""),
            "documents": idx.get("documents", 0),
            "evaluable": name in evaluable_indexes,
        })
    return jsonify(result)


@app.route("/api/evaluable/<index_name>")
def api_evaluable_detail(index_name):
    """Return evaluable details for a specific index."""
    if index_name not in EVALUABLE_MAP:
        return jsonify({"error": f"Index '{index_name}' is not evaluable"}), 404

    entries = EVALUABLE_MAP[index_name]
    # Collect unique topic_key/eval_key pairs with their metrics
    topic_pairs = []
    seen = set()
    for entry in entries:
        key = (entry["topic_key"], entry["eval_key"])
        if key not in seen:
            seen.add(key)
            topic_pairs.append({
                "topic_key": entry["topic_key"],
                "eval_key": entry["eval_key"],
                "metrics": entry["metrics"],
            })

    return jsonify({
        "index_name": index_name,
        "topic_pairs": topic_pairs,
    })


@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    """Run retrieval + evaluation."""
    data = request.get_json()
    index_name = data.get("index")
    topic_key = data.get("topic_key")
    eval_key = data.get("eval_key")
    metric_name = data.get("metric")
    trec_args = data.get("trec_args")

    if not all([index_name, topic_key, eval_key, metric_name, trec_args]):
        return jsonify({"error": "Missing required parameters"}), 400

    run_id = str(uuid.uuid4())[:8]
    RUN_STATUS[run_id] = {
        "status": "running",
        "index": index_name,
        "topic_key": topic_key,
        "eval_key": eval_key,
        "metric": metric_name,
        "trec_args": trec_args,
        "started": datetime.now().isoformat(),
        "search": None,
        "eval": None,
        "score": None,
        "error": None,
    }

    def run():
        try:
            # Step 1: Retrieval
            search_result = run_search_collection(index_name, topic_key, run_id)
            RUN_STATUS[run_id]["search"] = {
                "run_file": search_result["run_file"],
                "elapsed": search_result["elapsed"],
                "returncode": search_result["returncode"],
                "stdout": search_result["stdout"],
                "stderr": search_result["stderr"],
            }

            if search_result["returncode"] != 0:
                RUN_STATUS[run_id]["status"] = "error"
                RUN_STATUS[run_id]["error"] = (
                    f"Retrieval failed (exit {search_result['returncode']}): "
                    f"{search_result['stderr'] or search_result['stdout']}"
                )[-1000:]
                return

            # Step 2: Evaluation
            eval_result = run_trec_eval(
                eval_key, search_result["run_file"], trec_args
            )
            RUN_STATUS[run_id]["eval"] = {
                "stdout": eval_result["stdout"],
                "stderr": eval_result["stderr"],
                "elapsed": eval_result["elapsed"],
                "returncode": eval_result["returncode"],
            }

            if eval_result["returncode"] != 0:
                RUN_STATUS[run_id]["status"] = "error"
                RUN_STATUS[run_id]["error"] = (
                    f"Evaluation failed (exit {eval_result['returncode']}): "
                    f"{eval_result['stderr'] or eval_result['stdout']}"
                )[-1000:]
                return

            # Parse score from trec_eval output
            # Format: "metric_name  \tall\t<score>"
            score = _parse_score(eval_result["stdout"], metric_name)
            RUN_STATUS[run_id]["score"] = score
            RUN_STATUS[run_id]["status"] = "complete"
            RUN_STATUS[run_id]["completed"] = datetime.now().isoformat()

        except subprocess.TimeoutExpired:
            RUN_STATUS[run_id]["status"] = "error"
            RUN_STATUS[run_id]["error"] = "Command timed out"
        except Exception as e:
            RUN_STATUS[run_id]["status"] = "error"
            RUN_STATUS[run_id]["error"] = str(e)[:1000]

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"run_id": run_id})


def _parse_score(trec_output, metric_name):
    """Parse trec_eval output to extract the score.

    trec_eval output format varies:
    Standard: "metric_name  \tall\t<score>"
    For ndcg_cut.10: "ndcg_cut_10  \tall\t<score>"
    For recall.1000: "recall_1000  \tall\t<score>"
    For recip_rank with -M 10: "recip_rank  \tall\t<score>"
    """
    import re
    # Map metric name to possible output names
    metric_map = {
        "MAP": "map",
        "nDCG@10": "ndcg_cut_10",
        "Recall@1000": "recall_1000",
        "P30": "P_30",
        "MRR@10": "recip_rank",
        "R@1K": "recall_1000",
    }
    output_name = metric_map.get(metric_name, metric_name.lower().replace("@", "_").replace(".", "_"))

    lines = trec_output.strip().split("\n")
    for line in lines:
        parts = line.split()
        if len(parts) >= 3 and parts[0] == output_name and parts[1] == "all":
            try:
                return float(parts[2])
            except ValueError:
                pass
    return None


@app.route("/api/status/<run_id>")
def api_status(run_id):
    """Poll for run status."""
    if run_id not in RUN_STATUS:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(RUN_STATUS[run_id])


@app.route("/api/runs")
def api_runs():
    """List all runs."""
    runs = []
    for run_id, status in sorted(RUN_STATUS.items(), key=lambda x: x[1].get("started", ""), reverse=True):
        runs.append({
            "run_id": run_id,
            "status": status.get("status"),
            "index": status.get("index"),
            "topic_key": status.get("topic_key"),
            "eval_key": status.get("eval_key"),
            "metric": status.get("metric"),
            "score": status.get("score"),
            "started": status.get("started"),
            "completed": status.get("completed"),
            "error": status.get("error"),
            "search": status.get("search"),
            "eval": status.get("eval"),
        })
    return jsonify(runs)


# ---------------------------------------------------------------------------
# Static Files
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(WORKSPACE, "index.html")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def init():
    global INDEX_CATALOG, EVALUABLE_MAP
    print("Loading prebuilt index registry...")
    INDEX_CATALOG = load_registry()
    print(f"  Loaded {len(INDEX_CATALOG)} indexes")

    print("Parsing reproduce configs...")
    EVALUABLE_MAP = parse_reproduce_configs()
    print(f"  Found {len(EVALUABLE_MAP)} evaluable indexes")
    for name in sorted(EVALUABLE_MAP.keys()):
        print(f"    - {name}")


if __name__ == "__main__":
    init()
    app.run(host="127.0.0.1", port=8765, debug=False)
