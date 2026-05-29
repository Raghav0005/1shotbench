#!/usr/bin/env python3
"""
Anserini Prebuilt Index Evaluator - Flask backend server.

Provides a REST API for:
- Discovering Anserini prebuilt Lucene inverted indexes
- Discovering Anserini topic sets
- Pairing indexes with compatible topics and qrels
- Running retrieval (SearchCollection) and evaluation (TrecEval)
- Serving the browser frontend
"""

import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

# ── Configuration ────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder="static", static_url_path="")

# Resolve ANSERINI_JAR from environment or default download location
ANSERINI_JAR = os.environ.get(
    "ANSERINI_JAR",
    "",
)

# Java executable
JAVA_BIN = os.environ.get("JAVA_BIN", "java")

# Working directory for runs and evaluation output
WORK_DIR = Path(os.environ.get("ANSERINI_EVAL_WORKDIR", Path.cwd() / "runs"))
WORK_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ─────────────────────────────────────────────────────────────────

def find_fatjar() -> str | None:
    """Locate the Anserini fatjar."""
    if ANSERINI_JAR and Path(ANSERINI_JAR).exists():
        return ANSERINI_JAR
    # Search current directory for anserini fatjars
    for path in Path.cwd().glob("anserini-*-fatjar.jar"):
        return str(path)
    return None


def java_cp_args() -> list[str]:
    """Return the Java classpath arguments for the Anserini fatjar."""
    jar = find_fatjar()
    if not jar:
        raise RuntimeError(
            "Anserini fatjar not found. Set ANSERINI_JAR or download the fatjar. "
            "Run: $install-anserini-fatjar first."
        )
    return [JAVA_BIN, "-cp", jar]


def run_java(main_class: str, args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Run an Anserini Java main class and return the result."""
    cmd = java_cp_args() + [main_class] + args
    env = os.environ.copy()
    env["JAVA_TOOL_OPTIONS"] = "-Djava.awt.headless=true"
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        cwd=str(WORK_DIR),
    )
    return proc


def run_java(
    main_class: str,
    args: list[str],
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """Run an Anserini Java main class and return the result."""
    cmd = java_cp_args() + [main_class] + args
    env = os.environ.copy()
    env["JAVA_TOOL_OPTIONS"] = "-Djava.awt.headless=true"
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        cwd=str(WORK_DIR),
    )
    return proc


def check_java() -> dict:
    """Verify Java is available."""
    try:
        proc = subprocess.run(
            [JAVA_BIN, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version_output = proc.stderr or proc.stdout
        match = re.search(r'version "(\d+(?:\.\d+)*)', version_output)
        version = match.group(1) if match else "unknown"
        return {"ok": True, "version": version, "raw": version_output.strip()}
    except FileNotFoundError:
        return {"ok": False, "error": f"Java not found on PATH. Looking for: {JAVA_BIN}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_fatjar() -> dict:
    """Verify the Anserini fatjar is available."""
    try:
        jar = find_fatjar()
        if not jar:
            return {"ok": False, "error": "Anserini fatjar not found"}
        return {"ok": True, "jar": jar, "size": Path(jar).stat().st_size}
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}


def normalize_metric_label(label: str) -> str:
    """Map a user-friendly metric label to the trec_eval -m argument.

    Examples:
        nDCG@10   -> ndcg_cut.10
        Recall@1000 -> recall.1000
        MAP       -> map
        P@30      -> P.30
    """
    label = label.strip()
    # Handle nDCG@k
    m = re.match(r'^nDCG@(\d+)$', label, re.IGNORECASE)
    if m:
        return f"ndcg_cut.{m.group(1)}"
    # Handle Recall@k
    m = re.match(r'^Recall@(\d+)$', label, re.IGNORECASE)
    if m:
        return f"recall.{m.group(1)}"
    # Handle P@k
    m = re.match(r'^P@(\d+)$', label, re.IGNORECASE)
    if m:
        return f"P.{m.group(1)}"
    # Handle MAP
    if label.upper() in ("MAP",):
        return "map"
    # Pass through as-is
    return label


def denormalize_metric(trec_name: str) -> str:
    """Convert a trec_eval metric name back to a user-friendly label."""
    m = re.match(r'^ndcg_cut\.(\d+)$', trec_name)
    if m:
        return f"nDCG@{m.group(1)}"
    m = re.match(r'^recall\.(\d+)$', trec_name)
    if m:
        return f"Recall@{m.group(1)}"
    m = re.match(r'^P\.(\d+)$', trec_name)
    if m:
        return f"P@{m.group(1)}"
    if trec_name.lower() == "map":
        return "MAP"
    return trec_name


# ── API Endpoints ───────────────────────────────────────────────────────────


@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check - verify Java and fatjar are available."""
    java_status = check_java()
    fatjar_status = check_fatjar()
    return jsonify({
        "java": java_status,
        "fatjar": fatjar_status,
        "ready": java_status.get("ok") and fatjar_status.get("ok"),
    })


@app.route("/api/indexes", methods=["GET"])
def api_indexes():
    """List all prebuilt Lucene inverted indexes and annotate with evaluable status."""
    try:
        # Get all prebuilt indexes
        proc = run_java(
            "io.anserini.cli.PrebuiltIndexRegistry",
            ["--list"],
            timeout=60,
        )
        if proc.returncode != 0:
            return jsonify({
                "error": "Failed to query prebuilt index registry",
                "stderr": proc.stderr,
            }), 500

        all_indexes = json.loads(proc.stdout)

        # Get topic sets for pairing
        try:
            topics_proc = run_java(
                "io.anserini.cli.TopicsRegistry",
                ["--list"],
                timeout=60,
            )
            topics_data = json.loads(topics_proc.stdout) if topics_proc.returncode == 0 else []
        except Exception:
            topics_data = []

        topic_names = {t.get("name", "") for t in topics_data} if isinstance(topics_data, list) else set()
        if isinstance(topics_data, dict):
            # Some versions return a dict keyed by name
            topic_names = set(topics_data.keys())

        # Build the result: annotate each index with evaluability
        result = []
        for idx in all_indexes:
            index_name = idx.get("name", "")
            index_type = idx.get("type", "unknown")

            # Only consider inverted indexes for evaluation
            is_inverted = index_type == "inverted"

            # Determine evaluability
            evaluable = False
            paired_topic = None
            paired_qrels = None

            if is_inverted:
                # Check if the index name itself is a known topic/qrels (like cacm)
                if index_name in topic_names:
                    paired_topic = index_name
                    paired_qrels = index_name
                    evaluable = True
                else:
                    # Check if there's a topic that has the index name as a prefix
                    # e.g., msmarco-v1-passage -> msmarco-v1-passage.dev
                    for tname in topic_names:
                        if tname.startswith(index_name):
                            paired_topic = tname
                            # Try the index name as qrels (may or may not work)
                            paired_qrels = index_name
                            evaluable = True
                            break

            result.append({
                "name": index_name,
                "type": index_type,
                "description": idx.get("description", ""),
                "filename": idx.get("filename", ""),
                "evaluable": evaluable,
                "paired_topic": paired_topic,
                "paired_qrels": paired_qrels,
                "is_inverted": is_inverted,
            })

        # Sort: evaluable inverted first, then other inverted, then rest
        result.sort(key=lambda x: (
            not x["evaluable"],
            not x["is_inverted"],
            x["name"],
        ))

        return jsonify(result)

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout querying prebuilt index registry"}), 504
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Failed to parse registry output: {e}"}), 500
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/topics", methods=["GET"])
def api_topics():
    """List all available topic sets."""
    try:
        proc = run_java(
            "io.anserini.cli.TopicsRegistry",
            ["--list"],
            timeout=60,
        )
        if proc.returncode != 0:
            return jsonify({
                "error": "Failed to query topics registry",
                "stderr": proc.stderr,
            }), 500

        topics = json.loads(proc.stdout)
        return jsonify(topics)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout querying topics registry"}), 504
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Failed to parse topics output: {e}"}), 500
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics", methods=["GET"])
def api_metrics():
    """Return the available evaluation metrics."""
    metrics = [
        {"label": "nDCG@10", "trec_name": "ndcg_cut.10", "category": "ranking"},
        {"label": "Recall@1000", "trec_name": "recall.1000", "category": "recall"},
        {"label": "MAP", "trec_name": "map", "category": "classic"},
        {"label": "P@10", "trec_name": "P.10", "category": "precision"},
        {"label": "P@30", "trec_name": "P.30", "category": "precision"},
        {"label": "Rprec", "trec_name": "Rprec", "category": "classic"},
        {"label": "MRR", "trec_name": "recip_rank", "category": "ranking"},
    ]
    return jsonify(metrics)


@app.route("/api/pairings/<index_name>", methods=["GET"])
def api_pairings(index_name):
    """Get topic/qrels pairings for a specific index."""
    try:
        # Get topics
        topics_proc = run_java(
            "io.anserini.cli.TopicsRegistry",
            ["--list"],
            timeout=60,
        )
        topic_names = []
        if topics_proc.returncode == 0:
            topics_data = json.loads(topics_proc.stdout)
            if isinstance(topics_data, list):
                topic_names = [t.get("name", "") for t in topics_data]
            elif isinstance(topics_data, dict):
                topic_names = list(topics_data.keys())

        # Determine pairing
        paired_topic = None
        paired_qrels = None

        if index_name in topic_names:
            paired_topic = index_name
            paired_qrels = index_name
        else:
            for tname in topic_names:
                if tname.startswith(index_name):
                    paired_topic = tname
                    paired_qrels = index_name
                    break

        return jsonify({
            "index": index_name,
            "paired_topic": paired_topic,
            "paired_qrels": paired_qrels,
            "evaluable": paired_topic is not None and paired_qrels is not None,
        })

    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    """Run retrieval and evaluation for a given index/topic/metric."""
    data = request.get_json() or {}
    index = data.get("index", "")
    topics = data.get("topics", "")
    qrels = data.get("qrels", "")
    metric_label = data.get("metric", "nDCG@10")
    hits = int(data.get("hits", 1000))
    threads = int(data.get("threads", 1))

    if not index or not topics or not qrels:
        return jsonify({
            "error": "Missing required parameters: index, topics, qrels",
        }), 400

    trec_metric = normalize_metric_label(metric_label)

    run_id = uuid.uuid4().hex[:12]
    run_filename = f"run.{index}.{run_id}.txt"
    eval_filename = f"eval.{index}.{run_id}.txt"
    run_path = WORK_DIR / run_filename

    start_time = time.time()

    # Step 1: Run retrieval
    try:
        search_args = [
            "-index", index,
            "-topics", topics,
            "-output", str(run_path),
            "-hits", str(hits),
            "-threads", str(threads),
            "-bm25",
        ]

        search_proc = run_java(
            "io.anserini.search.SearchCollection",
            search_args,
            timeout=600,
        )

        if search_proc.returncode != 0:
            elapsed = time.time() - start_time
            return jsonify({
                "status": "error",
                "stage": "retrieval",
                "error": "SearchCollection failed",
                "stderr": search_proc.stderr[-2000:],
                "stdout": search_proc.stdout[-2000:],
                "elapsed_seconds": round(elapsed, 2),
            }), 500

        if not run_path.exists():
            elapsed = time.time() - start_time
            return jsonify({
                "status": "error",
                "stage": "retrieval",
                "error": f"Run file not generated: {run_path}",
                "stderr": search_proc.stderr[-2000:],
                "elapsed_seconds": round(elapsed, 2),
            }), 500

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        return jsonify({
            "status": "error",
            "stage": "retrieval",
            "error": "SearchCollection timed out",
            "elapsed_seconds": round(elapsed, 2),
        }), 504

    # Step 2: Run evaluation
    try:
        # Determine if -c flag is needed (traditional TREC formatting)
        # CACM requires -c; we'll include it generally
        eval_args = [
            "-c",
            "-m", trec_metric,
            qrels,
            str(run_path),
        ]

        eval_proc = run_java(
            "io.anserini.eval.TrecEval",
            eval_args,
            timeout=120,
        )

        elapsed = time.time() - start_time

        if eval_proc.returncode != 0:
            return jsonify({
                "status": "error",
                "stage": "evaluation",
                "error": "TrecEval failed",
                "stderr": eval_proc.stderr[-2000:],
                "stdout": eval_proc.stdout[-2000:],
                "elapsed_seconds": round(elapsed, 2),
                "run_file": str(run_path),
                "index": index,
                "topics": topics,
                "qrels": qrels,
                "metric": metric_label,
            }), 500

        # Parse trec_eval output
        eval_output = eval_proc.stdout.strip()
        score = None
        metric_display = None

        # Expected format: "metric_name\tall\t0.1234" or similar
        for line in eval_output.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                try:
                    score_val = float(parts[-1])
                    score = score_val
                    metric_display = denormalize_metric(parts[0])
                    break
                except ValueError:
                    pass

        # Write eval output to file
        eval_path = WORK_DIR / eval_filename
        eval_path.write_text(eval_output)

        return jsonify({
            "status": "success",
            "score": score,
            "metric_display": metric_display or metric_label,
            "metric_trec": trec_metric,
            "eval_output": eval_output,
            "index": index,
            "topics": topics,
            "qrels": qrels,
            "hits": hits,
            "elapsed_seconds": round(elapsed, 2),
            "run_file": str(run_path),
            "run_file_size": run_path.stat().st_size,
            "eval_file": str(eval_path),
        })

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        return jsonify({
            "status": "error",
            "stage": "evaluation",
            "error": "TrecEval timed out",
            "elapsed_seconds": round(elapsed, 2),
            "run_file": str(run_path),
        }), 504


@app.route("/api/run-file/<path:filename>", methods=["GET"])
def api_run_file(filename):
    """Serve a generated run file for inspection."""
    filepath = WORK_DIR / filename
    # Prevent path traversal
    filepath = filepath.resolve()
    if not str(filepath).startswith(str(WORK_DIR.resolve())):
        return jsonify({"error": "Invalid path"}), 403
    if not filepath.exists():
        return jsonify({"error": "File not found"}), 404
    return send_from_directory(str(WORK_DIR), filename)


# ── Static file serving ─────────────────────────────────────────────────────


@app.route("/")
def index():
    """Serve the main frontend."""
    return send_from_directory("static", "index.html")


@app.route("/<path:path>")
def static_files(path):
    """Serve static files."""
    return send_from_directory("static", path)


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    port = int(os.environ.get("PORT", 8089))
    print(f"Anserini Prebuilt Index Evaluator")
    print(f"Starting on http://localhost:{port}")
    print(f"Work directory: {WORK_DIR}")

    # Pre-flight checks
    java = check_java()
    if not java["ok"]:
        print(f"WARNING: Java check failed: {java.get('error')}")
        print("The app will start, but retrieval/evaluation will fail.")
    else:
        print(f"Java version: {java['version']}")

    jar = find_fatjar()
    if jar:
        print(f"Fatjar: {jar}")
    else:
        print("WARNING: Anserini fatjar not found. Set ANSERINI_JAR or download it.")
        print("The app will start, but retrieval/evaluation will fail.")

    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
