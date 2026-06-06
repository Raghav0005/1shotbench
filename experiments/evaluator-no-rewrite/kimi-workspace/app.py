import os
import re
import json
import time
import uuid
import shutil
import subprocess
import threading
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder='static')

ANSERINI_JAR = os.environ.get("ANSERINI_JAR", "anserini-2.1.1-fatjar.jar")
RUNS_DIR = Path("runs")
RUNS_DIR.mkdir(exist_ok=True)

# In-memory cache for runs
runs = {}

# Pre-computed pairings from reproduction configs
pairings_cache = {}
# Pre-computed inverted indexes
indexes_cache = []

def get_indexes():
    global indexes_cache
    if indexes_cache:
        return indexes_cache
    try:
        result = subprocess.run(
            ["java", "-cp", ANSERINI_JAR, "io.anserini.cli.PrebuiltIndexRegistry", "--list", "--type", "inverted"],
            capture_output=True, text=True, timeout=60
        )
        indexes = json.loads(result.stdout)
        indexes_cache = indexes
        return indexes
    except Exception as e:
        print(f"Error fetching indexes: {e}")
        return []

def get_pairings():
    global pairings_cache
    if pairings_cache:
        return pairings_cache
    try:
        result = subprocess.run(
            ["java", "-cp", ANSERINI_JAR, "io.anserini.reproduce.ReproduceFromPrebuiltIndexes", "--list"],
            capture_output=True, text=True, timeout=60
        )
        configs = json.loads(result.stdout.strip())
        pairings = {}
        for config in configs:
            res = subprocess.run(
                ["java", "-cp", ANSERINI_JAR, "io.anserini.reproduce.ReproduceFromPrebuiltIndexes", "--config", config, "--show"],
                capture_output=True, text=True, timeout=60
            )
            sanitized = res.stdout.replace('\t', '    ')
            try:
                import yaml
                data = yaml.safe_load(sanitized)
            except Exception as e:
                print(f"Error parsing config {config}: {e}")
                continue
            for condition in data.get("conditions", []):
                cmd = condition.get("command", "")
                m = re.search(r'-index\s+(\S+)', cmd)
                if not m:
                    continue
                index = m.group(1)
                for topic in condition.get("topics", []):
                    topic_key = topic.get("topic_key")
                    eval_key = topic.get("eval_key")
                    metrics = {}
                    for metric_name, metric_def in topic.get("metric_definitions", {}).items():
                        metrics[metric_name] = metric_def
                    if index not in pairings:
                        pairings[index] = []
                    pairings[index].append({
                        "config": config,
                        "condition": condition.get("name"),
                        "topic_key": topic_key,
                        "eval_key": eval_key,
                        "metrics": metrics,
                        "expected_scores": topic.get("expected_scores", {})
                    })
        pairings_cache = pairings
        return pairings
    except Exception as e:
        print(f"Error fetching pairings: {e}")
        return {}

# Warm up pairings in background
def warmup():
    try:
        get_pairings()
    except Exception as e:
        print(f"Warmup error: {e}")

threading.Thread(target=warmup, daemon=True).start()

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/indexes")
def api_indexes():
    indexes = get_indexes()
    pairings = get_pairings()
    result = []
    for idx in indexes:
        name = idx.get("name")
        is_evaluable = name in pairings and len(pairings[name]) > 0
        result.append({
            "name": name,
            "type": idx.get("type"),
            "description": idx.get("description", ""),
            "documents": idx.get("documents"),
            "size": idx.get("size"),
            "evaluable": is_evaluable
        })
    return jsonify(result)

@app.route("/api/pairings/<index_name>")
def api_pairings(index_name):
    pairings = get_pairings()
    return jsonify(pairings.get(index_name, []))

@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    data = request.get_json()
    index = data.get("index")
    topic_key = data.get("topic_key")
    eval_key = data.get("eval_key")
    metric = data.get("metric")
    metric_args = data.get("metric_args")

    if not all([index, topic_key, eval_key, metric, metric_args]):
        return jsonify({"error": "Missing required parameters"}), 400

    run_id = str(uuid.uuid4())
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(exist_ok=True)
    run_file = run_dir / "run.txt"
    eval_file = run_dir / "eval.txt"

    run_record = {
        "id": run_id,
        "index": index,
        "topic_key": topic_key,
        "eval_key": eval_key,
        "metric": metric,
        "metric_args": metric_args,
        "status": "running",
        "run_file": str(run_file),
        "eval_file": str(eval_file),
        "score": None,
        "eval_output": "",
        "elapsed_ms": 0,
        "error": None
    }
    runs[run_id] = run_record

    def do_run():
        start = time.time()
        try:
            # Run retrieval
            search_cmd = [
                "java", "-cp", ANSERINI_JAR,
                "io.anserini.search.SearchCollection",
                "-threads", "1",
                "-index", index,
                "-topics", topic_key,
                "-output", str(run_file),
                "-hits", "1000",
                "-bm25"
            ]
            proc = subprocess.run(search_cmd, capture_output=True, text=True, timeout=300)
            if proc.returncode != 0:
                raise RuntimeError(f"Search failed: {proc.stderr}")

            # Run evaluation
            eval_cmd = [
                "java", "-cp", ANSERINI_JAR,
                "io.anserini.eval.TrecEval"
            ] + metric_args.split() + [
                eval_key,
                str(run_file)
            ]
            proc = subprocess.run(eval_cmd, capture_output=True, text=True, timeout=60)
            eval_output = proc.stdout + proc.stderr
            run_record["eval_output"] = eval_output
            with open(eval_file, "w") as f:
                f.write(eval_output)

            # Parse score
            score = None
            for line in eval_output.strip().splitlines():
                parts = line.strip().split()
                if len(parts) >= 3 and parts[1] == "all":
                    try:
                        score = float(parts[2])
                    except ValueError:
                        pass

            run_record["score"] = score
            run_record["status"] = "completed" if score is not None else "failed"
            if score is None:
                run_record["error"] = "Could not parse evaluation score"
        except Exception as e:
            run_record["status"] = "failed"
            run_record["error"] = str(e)
        finally:
            run_record["elapsed_ms"] = int((time.time() - start) * 1000)

    threading.Thread(target=do_run, daemon=True).start()
    return jsonify({"run_id": run_id, "status": "running"})

@app.route("/api/run/<run_id>")
def api_run(run_id):
    run = runs.get(run_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(run)

@app.route("/api/health")
def api_health():
    jar_ok = os.path.isfile(ANSERINI_JAR)
    return jsonify({"jar": ANSERINI_JAR, "jar_exists": jar_ok})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
