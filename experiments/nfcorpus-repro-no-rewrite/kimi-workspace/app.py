"""NFCorpus Live Retrieval Diagnostics Workbench."""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from threading import Lock

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Configuration
PORT = int(os.environ.get("PORT", 10000))
CACHE_DIR = Path(os.environ.get("CACHE_DIR", "./cache")).resolve()
RUNS_DIR = CACHE_DIR / "runs"
INDEX_CACHE_DIR = Path(os.environ.get("INDEX_CACHE_DIR", str(Path.home() / ".cache" / "pyserini" / "indexes")))
ANSERINI_VERSION = os.environ.get("ANSERINI_VERSION", "2.1.1")
ANSERINI_JAR = os.environ.get("ANSERINI_JAR", str(CACHE_DIR / f"anserini-{ANSERINI_VERSION}-fatjar.jar"))
JAVA_OPTS = os.environ.get("JAVA_OPTS", "--enable-native-access=ALL-UNNAMED --add-modules jdk.incubator.vector")

# NFCorpus config (discovered from skills)
INDEX_NAME = "beir-v1.0.0-nfcorpus.flat"
TOPICS_KEY = "beir-nfcorpus"
EVAL_KEY = "beir-v1.0.0-nfcorpus.test"
EXPECTED_NDCG10 = 0.3218
METRIC_DEF = "-c -m ndcg_cut.10"
RUN_FILE_NAME = "run.nfcorpus.bm25.txt"
EVAL_FILE_NAME = "eval.nfcorpus.bm25.txt"

# Global state
state = {
    "java_ok": False,
    "java_version": None,
    "fatjar_path": None,
    "fatjar_ok": False,
    "cacm_smoke_ok": False,
    "nfcorpus_index_ready": False,
    "reproduction_discovered": False,
    "evaluation_run": False,
    "evaluation_observed": {},
    "evaluation_expected": {},
    "evaluation_delta": {},
    "evaluation_status": {},
    "evaluation_elapsed_ms": 0,
    "commands": {},
    "artifacts": {},
    "errors": [],
    "setup_complete": False,
}
state_lock = Lock()


def run_cmd(cmd, cwd=None, timeout=300, env=None):
    """Run a shell command and return (returncode, stdout, stderr)."""
    merged_env = {**os.environ, **(env or {})}
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            env=merged_env,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def log_error(msg: str):
    with state_lock:
        state["errors"].append(msg)
    print(f"[ERROR] {msg}", file=sys.stderr)


def set_command(key, cmd):
    with state_lock:
        state["commands"][key] = cmd if isinstance(cmd, str) else " ".join(cmd)


def set_artifact(key: str, path: str):
    with state_lock:
        state["artifacts"][key] = path


def verify_java():
    """Step 1: Verify Java runtime."""
    rc, out, err = run_cmd(["java", "-version"])
    version_text = out + err
    with state_lock:
        state["java_version"] = version_text.strip()
        state["java_ok"] = rc == 0 and "21" in version_text
    if not state["java_ok"]:
        log_error("Java 21 is required but not found or wrong version.")
    set_command("java_version", ["java", "-version"])


def locate_or_download_fatjar():
    """Step 2: Locate or download Anserini fatjar."""
    jar_path = Path(ANSERINI_JAR)
    if jar_path.exists():
        with state_lock:
            state["fatjar_path"] = str(jar_path)
            state["fatjar_ok"] = True
        set_command("fatjar_locate", f"test -f {jar_path}")
        return

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = (
        f"https://repo1.maven.org/maven2/io/anserini/anserini/"
        f"{ANSERINI_VERSION}/anserini-{ANSERINI_VERSION}-fatjar.jar"
    )
    cmd = [
        "curl", "-fL", "-o", str(jar_path), url
    ]
    set_command("fatjar_download", cmd)
    rc, out, err = run_cmd(cmd)
    if rc != 0 or not jar_path.exists():
        log_error(f"Failed to download Anserini fatjar from {url}: {err}")
        return

    with state_lock:
        state["fatjar_path"] = str(jar_path)
        state["fatjar_ok"] = True


def cacm_smoke_test():
    """Step 3: Run CACM smoke test."""
    if not state["fatjar_ok"]:
        return
    jar = state["fatjar_path"]
    run_file = str(CACHE_DIR / "run.cacm.bm25.txt")
    eval_file = str(CACHE_DIR / "eval.cacm.bm25.txt")

    search_cmd = [
        "java", *(JAVA_OPTS.split()), "-cp", jar,
        "io.anserini.search.SearchCollection",
        "-threads", "1",
        "-index", "cacm",
        "-topics", "cacm",
        "-output", run_file,
        "-hits", "1000",
        "-bm25",
    ]
    set_command("cacm_search", search_cmd)
    rc, out, err = run_cmd(search_cmd)
    if rc != 0:
        log_error(f"CACM smoke test search failed: {err}")
        return

    eval_cmd = [
        "java", *(JAVA_OPTS.split()), "-cp", jar,
        "io.anserini.eval.TrecEval",
        "-c", "-m", "map", "-m", "P.30",
        "cacm", run_file,
    ]
    set_command("cacm_eval", eval_cmd)
    rc, out, err = run_cmd(eval_cmd)
    if rc != 0:
        log_error(f"CACM smoke test eval failed: {err}")
        return

    # Verify expected scores
    ok = bool(re.search(r"map\s+all\s+0\.3123", out)) and bool(re.search(r"P_30\s+all\s+0\.1942", out))
    with state_lock:
        state["cacm_smoke_ok"] = ok
    if not ok:
        log_error(f"CACM smoke test scores unexpected. Output:\n{out}")


def discover_reproduction():
    """Step 4: Discover NFCorpus reproduction config via ReproduceFromPrebuiltIndexes."""
    if not state["fatjar_ok"]:
        return
    jar = state["fatjar_path"]

    # --list
    list_cmd = [
        "java", *(JAVA_OPTS.split()), "-cp", jar,
        "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
        "--list",
    ]
    set_command("reproduction_list", list_cmd)
    rc, out, err = run_cmd(list_cmd)
    if rc != 0:
        log_error(f"Reproduction listing failed: {err}")
        return

    # --show beir.core
    show_cmd = [
        "java", *(JAVA_OPTS.split()), "-cp", jar,
        "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
        "--config", "beir.core", "--show",
    ]
    set_command("reproduction_show", show_cmd)
    rc, out, err = run_cmd(show_cmd)
    if rc != 0:
        log_error(f"Reproduction show failed: {err}")
        return

    # --dry-run beir.core
    dryrun_cmd = [
        "java", *(JAVA_OPTS.split()), "-cp", jar,
        "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
        "--config", "beir.core", "--dry-run",
    ]
    set_command("reproduction_dryrun", dryrun_cmd)
    rc, out, err = run_cmd(dryrun_cmd)
    if rc != 0:
        log_error(f"Reproduction dry-run failed: {err}")
        return

    # Parse expected nDCG@10 for nfcorpus
    expected = None
    for line in out.splitlines():
        if "nfcorpus" in line and "nDCG@10:" in line:
            m = re.search(r"nDCG@10:\s*([0-9.]+)", line)
            if m:
                expected = float(m.group(1))
                break

    with state_lock:
        state["reproduction_discovered"] = True
        if expected is not None:
            state["evaluation_expected"]["nDCG@10"] = expected
        else:
            # Fallback to known value from skill
            state["evaluation_expected"]["nDCG@10"] = EXPECTED_NDCG10


def verify_nfcorpus_index():
    """Step 5: Verify NFCorpus prebuilt index is available (triggers download on first use)."""
    if not state["fatjar_ok"]:
        return
    jar = state["fatjar_path"]

    # Use PrebuiltIndexRegistry to confirm
    registry_cmd = [
        "java", *(JAVA_OPTS.split()), "-cp", jar,
        "io.anserini.cli.PrebuiltIndexRegistry",
        "--list", "--filter", f"^{INDEX_NAME}$",
    ]
    set_command("index_registry", registry_cmd)
    rc, out, err = run_cmd(registry_cmd)
    if rc != 0 or INDEX_NAME not in out:
        log_error(f"NFCorpus index not found in registry: {err}")
        return

    # A quick search to force index download/cache
    probe_cmd = [
        "java", *(JAVA_OPTS.split()), "-cp", jar,
        "io.anserini.cli.Search",
        "--index", INDEX_NAME,
        "--query", "deafness",
        "--hits", "1",
        "--json",
    ]
    set_command("index_probe", probe_cmd)
    rc, out, err = run_cmd(probe_cmd, timeout=180)
    if rc != 0:
        log_error(f"NFCorpus index probe/download failed: {err}")
        return

    with state_lock:
        state["nfcorpus_index_ready"] = True


def run_evaluation():
    """Step 6: Run BM25 evaluation for NFCorpus."""
    if not state["nfcorpus_index_ready"]:
        return
    jar = state["fatjar_path"]
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_file = str(RUNS_DIR / RUN_FILE_NAME)
    eval_file = str(RUNS_DIR / EVAL_FILE_NAME)

    search_cmd = [
        "java", *(JAVA_OPTS.split()), "-cp", jar,
        "io.anserini.search.SearchCollection",
        "-threads", "4",
        "-index", INDEX_NAME,
        "-topics", TOPICS_KEY,
        "-output", run_file,
        "-bm25",
        "-removeQuery",
    ]
    set_command("nfcorpus_search", search_cmd)
    set_artifact("run_file", run_file)

    t0 = time.time()
    rc, out, err = run_cmd(search_cmd)
    if rc != 0:
        log_error(f"NFCorpus SearchCollection failed: {err}")
        return

    eval_cmd = [
        "java", *(JAVA_OPTS.split()), "-cp", jar,
        "trec_eval",
        "-c", "-m", "ndcg_cut.10",
        EVAL_KEY, run_file,
    ]
    set_command("nfcorpus_eval", eval_cmd)
    set_artifact("eval_file", eval_file)

    rc, out, err = run_cmd(eval_cmd)
    elapsed = int((time.time() - t0) * 1000)
    if rc != 0:
        log_error(f"NFCorpus evaluation failed: {err}")
        return

    # Parse observed metric
    observed = {}
    for line in out.splitlines():
        m = re.search(r"ndcg_cut_10\s+all\s+([0-9.]+)", line)
        if m:
            observed["nDCG@10"] = float(m.group(1))
            break

    # Compare
    delta = {}
    status = {}
    expected = state["evaluation_expected"].get("nDCG@10", EXPECTED_NDCG10)
    for metric, obs_val in observed.items():
        delta[metric] = round(obs_val - expected, 4)
        if abs(delta[metric]) < 0.0001:
            status[metric] = "pass"
        elif abs(delta[metric]) < 0.01:
            status[metric] = "close"
        else:
            status[metric] = "fail"

    with state_lock:
        state["evaluation_run"] = True
        state["evaluation_observed"] = observed
        state["evaluation_delta"] = delta
        state["evaluation_status"] = status
        state["evaluation_elapsed_ms"] = elapsed

    # Write eval output to artifact
    Path(eval_file).write_text(out)


def full_setup():
    """Run all setup steps sequentially."""
    verify_java()
    locate_or_download_fatjar()
    cacm_smoke_test()
    discover_reproduction()
    verify_nfcorpus_index()
    run_evaluation()
    with state_lock:
        state["setup_complete"] = True


# Run setup in background so the web server can start immediately
@app.before_request
def lazy_setup():
    if not state["setup_complete"] and not hasattr(app, "_setup_started"):
        app._setup_started = True
        import threading
        threading.Thread(target=full_setup, daemon=True).start()


@app.route("/health")
def health():
    with state_lock:
        return jsonify(
            {
                "status": "ok" if state["setup_complete"] else "starting",
                "anserini_available": state["fatjar_ok"] and (state["cacm_smoke_ok"] or state["nfcorpus_index_ready"]),
                "nfcorpus_ready": state["nfcorpus_index_ready"],
                "search_available": state["nfcorpus_index_ready"],
                "evaluation_available": state["evaluation_run"],
            }
        )


@app.route("/api/status")
def api_status():
    with state_lock:
        return jsonify(
            {
                "java": {
                    "ok": state["java_ok"],
                    "version": state["java_version"],
                },
                "fatjar": {
                    "ok": state["fatjar_ok"],
                    "path": state["fatjar_path"],
                },
                "cacm_smoke": state["cacm_smoke_ok"],
                "nfcorpus_index_ready": state["nfcorpus_index_ready"],
                "reproduction_discovered": state["reproduction_discovered"],
                "evaluation": {
                    "run": state["evaluation_run"],
                    "expected": state["evaluation_expected"],
                    "observed": state["evaluation_observed"],
                    "delta": state["evaluation_delta"],
                    "status": state["evaluation_status"],
                    "elapsed_ms": state["evaluation_elapsed_ms"],
                },
                "setup_complete": state["setup_complete"],
                "errors": state["errors"],
                "commands": state["commands"],
                "artifacts": state["artifacts"],
            }
        )


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    hits = request.args.get("hits", "10")
    if not q:
        return jsonify({"error": "Missing query parameter 'q'"}), 400
    if not state["nfcorpus_index_ready"]:
        return jsonify({"error": "NFCorpus index not ready"}), 503

    jar = state["fatjar_path"]
    cmd = [
        "java", *(JAVA_OPTS.split()), "-cp", jar,
        "io.anserini.cli.Search",
        "--index", INDEX_NAME,
        "--query", q,
        "--hits", str(hits),
        "--json",
    ]
    rc, out, err = run_cmd(cmd, timeout=60)
    if rc != 0:
        return jsonify({"error": f"Search failed: {err}"}), 500

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON from search", "raw": out}), 500

    return jsonify(data)


@app.route("/api/evaluate", methods=["POST", "GET"])
def api_evaluate():
    if not state["nfcorpus_index_ready"]:
        return jsonify({"error": "NFCorpus index not ready"}), 503
    run_evaluation()
    with state_lock:
        return jsonify(
            {
                "expected": state["evaluation_expected"],
                "observed": state["evaluation_observed"],
                "delta": state["evaluation_delta"],
                "status": state["evaluation_status"],
                "elapsed_ms": state["evaluation_elapsed_ms"],
            }
        )


@app.route("/api/commands")
def api_commands():
    with state_lock:
        return jsonify(state["commands"])


@app.route("/api/artifacts")
def api_artifacts():
    with state_lock:
        return jsonify(state["artifacts"])


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    # In development, run setup blocking so first request isn't slow
    if os.environ.get("FLASK_ENV") == "development" or os.environ.get("BLOCKING_SETUP"):
        full_setup()
    app.run(host="0.0.0.0", port=PORT, threaded=True)
