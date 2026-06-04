"""
NFCorpus Live Retrieval Diagnostics Workbench
A Flask backend that prepares Anserini, builds an NFCorpus index,
runs BM25 evaluation, and serves live search via Anserini CLI.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static")

# Configuration
ANSERINI_VERSION = os.environ.get("ANSERINI_VERSION", "2.1.1")
ANSERINI_JAR_NAME = f"anserini-{ANSERINI_VERSION}-fatjar.jar"
CACHE_DIR = Path(os.environ.get("CACHE_DIR", ".cache"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
INDEX_DIR = Path(os.environ.get("INDEX_DIR", "indexes"))
RUNS_DIR = Path(os.environ.get("RUNS_DIR", "runs"))
PORT = int(os.environ.get("PORT", "10000"))

FATJAR_PATH = CACHE_DIR / ANSERINI_JAR_NAME
NFCORPUS_ZIP_URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip"
NFCORPUS_ZIP_PATH = DATA_DIR / "nfcorpus.zip"
NFCORPUS_EXTRACT_PATH = DATA_DIR / "nfcorpus"
CORPUS_PATH = DATA_DIR / "collections" / "beir-v1.0.0" / "corpus" / "nfcorpus"
INDEX_PATH = INDEX_DIR / "lucene-inverted.beir-v1.0.0-nfcorpus.flat"
RUN_PATH = RUNS_DIR / "run.nfcorpus.bm25.txt"
QRELS_PATH = DATA_DIR / "qrels.nfcorpus.test.txt"
EVAL_PATH = RUNS_DIR / "eval.nfcorpus.bm25.txt"

# Expected metrics from reproduction config
EXPECTED_METRICS = {
    "nDCG@10": 0.3218,
    "R@100": 0.2457,
    "R@1000": 0.3704,
}

# Global state
_state = {
    "java_ok": False,
    "java_version": "",
    "fatjar_ready": False,
    "fatjar_path": str(FATJAR_PATH),
    "corpus_ready": False,
    "index_ready": False,
    "index_path": str(INDEX_PATH),
    "evaluation_ready": False,
    "search_ready": False,
    "setup_in_progress": False,
    "setup_error": None,
    "setup_log": [],
    "commands": {},
    "artifacts": {},
    "evaluation": {
        "observed": {},
        "expected": EXPECTED_METRICS.copy(),
        "status": {},
        "elapsed_ms": 0,
    },
    "sample_queries": [],
}

_state_lock = threading.Lock()


def _log(msg: str):
    print(msg, flush=True)
    with _state_lock:
        _state["setup_log"].append(msg)


def _set(**kwargs):
    with _state_lock:
        _state.update(kwargs)


def _get(key: str, default=None):
    with _state_lock:
        return _state.get(key, default)


def run_cmd(cmd: list[str], cwd: Path = None, timeout: int = 300, capture: bool = True) -> tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    _log(f"$ {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        if capture:
            if result.stdout:
                _log(result.stdout[:2000])
            if result.stderr:
                _log(result.stderr[:2000])
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired:
        _log(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        return -1, "", "timeout"
    except Exception as e:
        _log(f"Command failed: {e}")
        return -1, "", str(e)


def check_java():
    rc, out, err = run_cmd(["java", "-version"], capture=True)
    version_text = out + err
    _set(java_version=version_text.strip().splitlines()[0] if version_text else "")
    match = re.search(r'version "?(\d+)', version_text)
    if match:
        major = int(match.group(1))
        _set(java_ok=major >= 21)
        return major >= 21
    return False


def download_fatjar():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if FATJAR_PATH.exists():
        _log(f"Fatjar already exists at {FATJAR_PATH}")
        return True
    url = f"https://repo1.maven.org/maven2/io/anserini/anserini/{ANSERINI_VERSION}/{ANSERINI_JAR_NAME}"
    _log(f"Downloading Anserini fatjar from {url}...")
    try:
        urllib.request.urlretrieve(url, FATJAR_PATH)
        _log(f"Downloaded to {FATJAR_PATH}")
        return True
    except Exception as e:
        _log(f"Failed to download fatjar: {e}")
        return False


def verify_fatjar():
    """Run CACM smoke test to verify the fatjar works."""
    cmd = [
        "java", "-cp", str(FATJAR_PATH),
        "io.anserini.search.SearchCollection",
        "-threads", "1",
        "-index", "cacm",
        "-topics", "cacm",
        "-output", "run.cacm.bm25.txt",
        "-hits", "1000",
        "-bm25",
    ]
    rc, out, err = run_cmd(cmd, timeout=120)
    if rc != 0:
        _log("CACM smoke test failed.")
        return False
    eval_cmd = [
        "java", "-cp", str(FATJAR_PATH),
        "io.anserini.eval.TrecEval",
        "-c", "-m", "map", "-m", "P.30",
        "cacm", "run.cacm.bm25.txt",
    ]
    rc, out, err = run_cmd(eval_cmd, timeout=60)
    if rc != 0 or "map" not in out:
        _log("TrecEval smoke test failed.")
        return False
    _log("Fatjar verified with CACM smoke test.")
    return True


def download_nfcorpus():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if NFCORPUS_EXTRACT_PATH.exists():
        _log("NFCorpus already extracted.")
        return True
    if not NFCORPUS_ZIP_PATH.exists():
        _log(f"Downloading NFCorpus from {NFCORPUS_ZIP_URL}...")
        try:
            urllib.request.urlretrieve(NFCORPUS_ZIP_URL, NFCORPUS_ZIP_PATH)
            _log(f"Downloaded {NFCORPUS_ZIP_PATH}")
        except Exception as e:
            _log(f"Failed to download NFCorpus: {e}")
            return False
    _log("Extracting NFCorpus...")
    try:
        with zipfile.ZipFile(NFCORPUS_ZIP_PATH, "r") as z:
            z.extractall(DATA_DIR)
        _log(f"Extracted to {NFCORPUS_EXTRACT_PATH}")
        return True
    except Exception as e:
        _log(f"Failed to extract NFCorpus: {e}")
        return False


def prepare_corpus():
    CORPUS_PATH.mkdir(parents=True, exist_ok=True)
    src = NFCORPUS_EXTRACT_PATH / "corpus.jsonl"
    dst = CORPUS_PATH / "corpus.jsonl"
    if not dst.exists() and src.exists():
        shutil.copy2(src, dst)
        _log(f"Copied corpus to {dst}")
    return dst.exists()


def convert_qrels():
    src = NFCORPUS_EXTRACT_PATH / "qrels" / "test.tsv"
    if not src.exists():
        return False
    if QRELS_PATH.exists():
        return True
    with open(src, "r", encoding="utf-8") as f:
        lines = f.readlines()
    with open(QRELS_PATH, "w", encoding="utf-8") as f:
        for line in lines[1:]:
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                f.write(f"{parts[0]} 0 {parts[1]} {parts[2]}\n")
    _log(f"Converted qrels to {QRELS_PATH}")
    return True


def build_index():
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    if INDEX_PATH.exists():
        _log(f"Index already exists at {INDEX_PATH}")
        return True
    cmd = [
        "java", "-cp", str(FATJAR_PATH),
        "io.anserini.index.IndexCollection",
        "-collection", "BeirFlatCollection",
        "-input", str(CORPUS_PATH),
        "-index", str(INDEX_PATH),
        "-generator", "DefaultLuceneDocumentGenerator",
        "-threads", "1",
        "-storePositions", "-storeDocvectors", "-storeRaw",
    ]
    rc, out, err = run_cmd(cmd, timeout=300)
    return rc == 0 and INDEX_PATH.exists()


def run_search_collection():
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        "java", "-cp", str(FATJAR_PATH),
        "io.anserini.search.SearchCollection",
        "-index", str(INDEX_PATH),
        "-topics", "beir-nfcorpus",
        "-output", str(RUN_PATH),
        "-bm25",
        "-hits", "1000",
        "-removeQuery",
    ]
    rc, out, err = run_cmd(cmd, timeout=300)
    return rc == 0 and RUN_PATH.exists()


def run_eval():
    metrics = [
        ("ndcg_cut.10", "nDCG@10"),
        ("recall.100", "R@100"),
        ("recall.1000", "R@1000"),
    ]
    all_out = []
    start = time.time()
    for trec_metric, _ in metrics:
        cmd = [
            "java", "-cp", str(FATJAR_PATH),
            "io.anserini.eval.TrecEval",
            "-c", "-m", trec_metric,
            str(QRELS_PATH),
            str(RUN_PATH),
        ]
        rc, out, err = run_cmd(cmd, timeout=120)
        if rc != 0:
            _log(f"Evaluation failed for metric {trec_metric}.")
            return False
        all_out.append(out)
    elapsed = int((time.time() - start) * 1000)
    combined_out = "\n".join(all_out)
    with open(EVAL_PATH, "w", encoding="utf-8") as f:
        f.write(combined_out)
    observed = {}
    for line in combined_out.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[1] == "all":
            metric_name = parts[0].rstrip(":").replace("ndcg_cut_", "nDCG@").replace("recall_", "R@")
            try:
                observed[metric_name] = float(parts[2])
            except ValueError:
                continue
    status = {}
    for metric, expected in EXPECTED_METRICS.items():
        obs = observed.get(metric)
        if obs is None:
            status[metric] = "unknown"
        elif abs(obs - expected) < 0.0001:
            status[metric] = "pass"
        elif abs(obs - expected) < 0.01:
            status[metric] = "close"
        else:
            status[metric] = "fail"
    _set(evaluation={
        "observed": observed,
        "expected": EXPECTED_METRICS.copy(),
        "status": status,
        "elapsed_ms": elapsed,
    })
    return True


def load_sample_queries():
    """Fetch a few sample queries from the beir-nfcorpus topics."""
    cmd = [
        "java", "-cp", str(FATJAR_PATH),
        "io.anserini.cli.TopicsRegistry",
        "--get", "beir-nfcorpus",
    ]
    rc, out, err = run_cmd(cmd, timeout=60)
    if rc != 0:
        return []
    try:
        topics = json.loads(out)
        queries = []
        # Pick a diverse sample
        keys = list(topics.keys())
        for key in keys[:5]:
            queries.append({"id": key, "text": topics[key].get("title", "")})
        for key in keys[50:55]:
            queries.append({"id": key, "text": topics[key].get("title", "")})
        for key in keys[100:105]:
            queries.append({"id": key, "text": topics[key].get("title", "")})
        return queries
    except Exception as e:
        _log(f"Failed to parse topics: {e}")
        return []


def do_setup():
    _set(setup_in_progress=True, setup_error=None, setup_log=[])
    try:
        commands = {}
        artifacts = {}

        # 1. Java
        if not check_java():
            raise RuntimeError("Java 21+ is required but not found.")
        commands["java_check"] = "java -version"

        # 2. Fatjar
        if not download_fatjar():
            raise RuntimeError("Failed to download Anserini fatjar.")
        _set(fatjar_ready=True)
        artifacts["fatjar"] = str(FATJAR_PATH)
        commands["fatjar_verify"] = (
            f"java -cp {FATJAR_PATH} io.anserini.search.SearchCollection "
            f"-threads 1 -index cacm -topics cacm -output run.cacm.bm25.txt -hits 1000 -bm25"
        )
        if not verify_fatjar():
            raise RuntimeError("Fatjar verification failed.")

        # 3. NFCorpus corpus
        if not download_nfcorpus():
            raise RuntimeError("Failed to download NFCorpus.")
        if not prepare_corpus():
            raise RuntimeError("Failed to prepare corpus.")
        if not convert_qrels():
            raise RuntimeError("Failed to convert qrels.")
        _set(corpus_ready=True)
        artifacts["corpus"] = str(CORPUS_PATH / "corpus.jsonl")
        artifacts["qrels"] = str(QRELS_PATH)
        commands["corpus_download"] = f"curl -fL -o nfcorpus.zip {NFCORPUS_ZIP_URL}"

        # 4. Index
        if not build_index():
            raise RuntimeError("Failed to build NFCorpus index.")
        _set(index_ready=True)
        artifacts["index"] = str(INDEX_PATH)
        commands["index_build"] = (
            f"java -cp {FATJAR_PATH} io.anserini.index.IndexCollection "
            f"-collection BeirFlatCollection -input {CORPUS_PATH} "
            f"-index {INDEX_PATH} -generator DefaultLuceneDocumentGenerator "
            f"-threads 1 -storePositions -storeDocvectors -storeRaw"
        )

        # 5. SearchCollection run
        if not run_search_collection():
            raise RuntimeError("Failed to run SearchCollection.")
        artifacts["run"] = str(RUN_PATH)
        commands["search_collection"] = (
            f"java -cp {FATJAR_PATH} io.anserini.search.SearchCollection "
            f"-index {INDEX_PATH} -topics beir-nfcorpus -output {RUN_PATH} "
            f"-bm25 -hits 1000 -removeQuery"
        )

        # 6. Evaluation
        if not run_eval():
            raise RuntimeError("Failed to run evaluation.")
        _set(evaluation_ready=True)
        artifacts["eval"] = str(EVAL_PATH)
        commands["evaluation"] = (
            f"java -cp {FATJAR_PATH} io.anserini.eval.TrecEval "
            f"-c -m ndcg_cut.10 -m recall.100 -m recall.1000 "
            f"{QRELS_PATH} {RUN_PATH}"
        )

        # 7. Load sample queries
        queries = load_sample_queries()
        _set(sample_queries=queries, search_ready=True)

        _set(commands=commands, artifacts=artifacts)
        _log("Setup complete.")
    except Exception as e:
        _log(f"Setup error: {e}")
        _set(setup_error=str(e))
    finally:
        _set(setup_in_progress=False)


@app.route("/health")
def health():
    with _state_lock:
        s = _state.copy()
    return jsonify({
        "status": "ready" if s["search_ready"] else ("error" if s["setup_error"] else "setting_up"),
        "java_ok": s["java_ok"],
        "java_version": s["java_version"],
        "fatjar_ready": s["fatjar_ready"],
        "nfcorpus_ready": s["corpus_ready"] and s["index_ready"],
        "search_available": s["search_ready"],
        "evaluation_available": s["evaluation_ready"],
    })


@app.route("/api/status")
def api_status():
    with _state_lock:
        s = _state.copy()
    return jsonify({
        "java_ok": s["java_ok"],
        "java_version": s["java_version"],
        "fatjar_ready": s["fatjar_ready"],
        "fatjar_path": s["fatjar_path"],
        "corpus_ready": s["corpus_ready"],
        "index_ready": s["index_ready"],
        "index_path": s["index_path"],
        "evaluation_ready": s["evaluation_ready"],
        "search_ready": s["search_ready"],
        "setup_in_progress": s["setup_in_progress"],
        "setup_error": s["setup_error"],
        "setup_log": s["setup_log"][-50:],
        "commands": s.get("commands", {}),
        "artifacts": s.get("artifacts", {}),
        "evaluation": s.get("evaluation", {}),
        "sample_queries": s.get("sample_queries", []),
        "dataset": "NFCorpus",
    })


@app.route("/api/search", methods=["POST"])
def api_search():
    if not _get("search_ready"):
        return jsonify({"error": "Search not ready."}), 503
    data = request.get_json(force=True, silent=True) or {}
    query = data.get("query", "").strip()
    hits = min(int(data.get("hits", 10)), 50)
    if not query:
        return jsonify({"error": "Query is required."}), 400

    cmd = [
        "java", "-cp", str(FATJAR_PATH),
        "io.anserini.cli.Search",
        "--index", str(INDEX_PATH),
        "--query", query,
        "--json",
        "--hits", str(hits),
    ]
    rc, out, err = run_cmd(cmd, timeout=60, capture=True)
    if rc != 0:
        return jsonify({"error": "Search failed.", "stderr": err[:500]}), 500
    try:
        # Filter out any log lines before the JSON
        json_start = out.find("{")
        if json_start == -1:
            return jsonify({"error": "No JSON in search output."}), 500
        result = json.loads(out[json_start:])
    except Exception as e:
        return jsonify({"error": f"Failed to parse search results: {e}"}), 500

    # Add rank numbers
    candidates = result.get("candidates", [])
    for i, c in enumerate(candidates, start=1):
        c["rank"] = i

    return jsonify({
        "query": query,
        "results": candidates,
        "command": " ".join(cmd),
    })


@app.route("/api/evaluation", methods=["GET"])
def api_evaluation():
    if not _get("evaluation_ready"):
        return jsonify({"error": "Evaluation not ready."}), 503
    with _state_lock:
        ev = _state.get("evaluation", {}).copy()
    ev["artifacts"] = {
        "run": str(RUN_PATH),
        "eval_output": str(EVAL_PATH),
        "qrels": str(QRELS_PATH),
    }
    ev["commands"] = {
        "search_collection": (
            f"java -cp {FATJAR_PATH} io.anserini.search.SearchCollection "
            f"-index {INDEX_PATH} -topics beir-nfcorpus -output {RUN_PATH} "
            f"-bm25 -hits 1000 -removeQuery"
        ),
        "evaluation": (
            f"java -cp {FATJAR_PATH} io.anserini.eval.TrecEval "
            f"-c -m ndcg_cut.10 -m recall.100 -m recall.1000 "
            f"{QRELS_PATH} {RUN_PATH}"
        ),
    }
    return jsonify(ev)


@app.route("/api/evaluation/rerun", methods=["POST"])
def api_evaluation_rerun():
    if not _get("index_ready"):
        return jsonify({"error": "Index not ready."}), 503
    _set(evaluation_ready=False)
    if not run_search_collection():
        return jsonify({"error": "SearchCollection rerun failed."}), 500
    if not run_eval():
        return jsonify({"error": "Evaluation rerun failed."}), 500
    _set(evaluation_ready=True)
    return api_evaluation()


@app.route("/api/commands")
def api_commands():
    with _state_lock:
        return jsonify({
            "commands": _state.get("commands", {}),
            "artifacts": _state.get("artifacts", {}),
        })


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)


def main():
    # Start setup in background
    setup_thread = threading.Thread(target=do_setup, daemon=True)
    setup_thread.start()
    app.run(host="0.0.0.0", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
