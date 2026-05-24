import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

import yaml
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# Configuration
WORKSPACE = Path(__file__).parent.resolve()
ANSERINI_JAR = WORKSPACE / "anserini-2.1.1-fatjar.jar"
RUNS_DIR = WORKSPACE / "runs"
RUNS_DIR.mkdir(exist_ok=True)

# In-memory caches
_indexes_cache = None
_evaluable_cache = None
_runs_cache = {}

CACHE_DIR = WORKSPACE / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
INDEXES_CACHE_FILE = CACHE_DIR / "indexes.json"
EVALUABLE_CACHE_FILE = CACHE_DIR / "evaluable.json"
CATALOG_CACHE_FILE = CACHE_DIR / "catalog.json"


def get_anserini_jar():
    if not ANSERINI_JAR.exists():
        raise RuntimeError(f"Anserini fatjar not found at {ANSERINI_JAR}")
    return str(ANSERINI_JAR)


def run_java(main_class, args):
    jar = get_anserini_jar()
    cmd = ["java", "-cp", jar, main_class] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def discover_indexes():
    global _indexes_cache
    if _indexes_cache is not None:
        return _indexes_cache
    if INDEXES_CACHE_FILE.exists():
        with open(INDEXES_CACHE_FILE) as f:
            _indexes_cache = json.load(f)
        return _indexes_cache

    result = run_java("io.anserini.cli.PrebuiltIndexRegistry", ["--list", "--type", "inverted"])
    if result.returncode != 0:
        raise RuntimeError(f"Failed to list indexes: {result.stderr}")

    data = json.loads(result.stdout)
    indexes = []
    for item in data:
        indexes.append({
            "name": item.get("name"),
            "type": item.get("type"),
            "description": item.get("description"),
            "filename": item.get("filename"),
            "documents": item.get("documents"),
            "unique_terms": item.get("unique_terms"),
            "total_terms": item.get("total_terms"),
            "size": item.get("size"),
        })
    _indexes_cache = indexes
    with open(INDEXES_CACHE_FILE, "w") as f:
        json.dump(indexes, f)
    return indexes


def discover_evaluable():
    global _evaluable_cache
    if _evaluable_cache is not None:
        return _evaluable_cache
    if EVALUABLE_CACHE_FILE.exists():
        with open(EVALUABLE_CACHE_FILE) as f:
            _evaluable_cache = json.load(f)
        return _evaluable_cache

    result = run_java("io.anserini.reproduce.ReproduceFromPrebuiltIndexes", ["--list"])
    if result.returncode != 0:
        raise RuntimeError(f"Failed to list reproduction configs: {result.stderr}")

    configs = json.loads(result.stdout)
    pairings = []
    for cfg in configs:
        res = run_java("io.anserini.reproduce.ReproduceFromPrebuiltIndexes", ["--config", cfg, "--show"])
        if res.returncode != 0:
            continue
        try:
            data = yaml.safe_load(res.stdout)
        except Exception:
            continue
        if not data or "conditions" not in data:
            continue
        for cond in data["conditions"]:
            cmd = cond.get("command", "")
            m = re.search(r"-index\s+(\S+)", cmd)
            index = m.group(1) if m else None
            for topic in cond.get("topics", []):
                topic_key = topic.get("topic_key", "")
                resolved_index = index
                if resolved_index and "$topics" in resolved_index:
                    resolved_index = resolved_index.replace("$topics", topic_key)
                entry = {
                    "config": cfg,
                    "condition": cond.get("name"),
                    "index": resolved_index,
                    "topic_key": topic_key,
                    "eval_key": topic.get("eval_key"),
                    "metrics": {},
                }
                for metric_name, metric_args in topic.get("metric_definitions", {}).items():
                    entry["metrics"][metric_name] = metric_args
                pairings.append(entry)

    _evaluable_cache = pairings
    with open(EVALUABLE_CACHE_FILE, "w") as f:
        json.dump(pairings, f)
    return pairings


def build_index_catalog():
    if CATALOG_CACHE_FILE.exists():
        with open(CATALOG_CACHE_FILE) as f:
            return json.load(f)

    indexes = discover_indexes()
    pairings = discover_evaluable()

    # Build a map from index name to list of evaluable pairings
    eval_map = {}
    for p in pairings:
        idx = p.get("index")
        if not idx:
            continue
        if idx not in eval_map:
            eval_map[idx] = []
        eval_map[idx].append(p)

    catalog = []
    for idx in indexes:
        name = idx["name"]
        pairings_for_index = eval_map.get(name, [])
        catalog.append({
            **idx,
            "evaluable": len(pairings_for_index) > 0,
            "pairings": pairings_for_index,
        })

    with open(CATALOG_CACHE_FILE, "w") as f:
        json.dump(catalog, f)
    return catalog


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/catalog")
def api_catalog():
    try:
        catalog = build_index_catalog()
        return jsonify({"catalog": catalog})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    body = request.get_json(force=True)
    index_name = body.get("index")
    topic_key = body.get("topic_key")
    eval_key = body.get("eval_key")
    metric_name = body.get("metric")
    condition = body.get("condition", "bm25")

    if not index_name or not topic_key or not eval_key or not metric_name:
        return jsonify({"error": "Missing required fields: index, topic_key, eval_key, metric"}), 400

    # Find the pairing to get metric args
    pairings = discover_evaluable()
    pairing = None
    for p in pairings:
        if (p["index"] == index_name and p["topic_key"] == topic_key
                and p["eval_key"] == eval_key and p["condition"] == condition):
            pairing = p
            break

    if not pairing or metric_name not in pairing.get("metrics", {}):
        return jsonify({"error": f"Metric {metric_name} not available for this pairing"}), 400

    metric_args = pairing["metrics"][metric_name]
    run_id = str(uuid.uuid4())[:8]
    run_file = RUNS_DIR / f"run.{run_id}.txt"
    eval_file = RUNS_DIR / f"eval.{run_id}.txt"

    start_time = time.time()

    # Run retrieval
    search_result = run_java("io.anserini.search.SearchCollection", [
        "-threads", "1",
        "-index", index_name,
        "-topics", topic_key,
        "-output", str(run_file),
        "-hits", "1000",
        "-bm25",
    ])

    if search_result.returncode != 0:
        return jsonify({
            "error": "Retrieval failed",
            "stderr": search_result.stderr,
            "stdout": search_result.stdout,
        }), 500

    # Run evaluation
    eval_args = metric_args.split()
    eval_result = run_java("io.anserini.eval.TrecEval", [
        *eval_args,
        eval_key,
        str(run_file),
    ])

    elapsed = time.time() - start_time

    # Save eval output
    eval_file.write_text(eval_result.stdout)

    # Parse score
    score = None
    for line in eval_result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[1] == "all":
            try:
                score = float(parts[2])
            except ValueError:
                pass

    run_record = {
        "id": run_id,
        "index": index_name,
        "topic_key": topic_key,
        "eval_key": eval_key,
        "metric": metric_name,
        "metric_args": metric_args,
        "condition": condition,
        "score": score,
        "elapsed_seconds": round(elapsed, 2),
        "run_file": str(run_file),
        "eval_file": str(eval_file),
        "eval_output": eval_result.stdout,
        "search_stdout": search_result.stdout,
        "search_stderr": search_result.stderr,
    }
    _runs_cache[run_id] = run_record

    return jsonify(run_record)


@app.route("/api/runs")
def api_runs():
    return jsonify({"runs": list(_runs_cache.values())})


@app.route("/api/runs/<run_id>")
def api_run(run_id):
    if run_id not in _runs_cache:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(_runs_cache[run_id])


@app.route("/api/health")
def api_health():
    try:
        jar = get_anserini_jar()
        return jsonify({"status": "ok", "jar": jar})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
