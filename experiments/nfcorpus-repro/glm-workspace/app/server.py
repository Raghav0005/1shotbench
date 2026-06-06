#!/usr/bin/env python3
"""NFCorpus Live Retrieval Diagnostics Workbench – Flask application."""

import json
import os
import re
import subprocess
import sys
import time
import threading
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(os.environ.get("WORKBENCH_HOME", "/opt/workbench"))
ANSERINI_VERSION = os.environ.get("ANSERINI_VERSION", "2.1.1")
ANSERINI_JAR = BASE_DIR / f"anserini-{ANSERINI_VERSION}-fatjar.jar"
DATA_DIR = BASE_DIR / "data"
RUN_FILE = DATA_DIR / "run.nfcorpus.bm25.txt"
EVAL_FILE = DATA_DIR / "eval.nfcorpus.bm25.txt"
TOPICS_FILE = DATA_DIR / "nfcorpus_topics.json"
SETUP_LOG = DATA_DIR / "setup.log"

INDEX_NAME = "beir-v1.0.0-nfcorpus.flat"
TOPICS_NAME = "beir-nfcorpus"
EVAL_QRELS = "beir-v1.0.0-nfcorpus.test"
EXPECTED_NDCG10 = 0.3218

# Sample queries from NFCorpus topics
SAMPLE_QUERIES = [
    {"id": "PLAIN-2", "title": "Do Cholesterol Statin Drugs Cause Breast Cancer?"},
    {"id": "PLAIN-12", "title": "Exploiting Autophagy to Live Longer"},
    {"id": "PLAIN-33", "title": "What's Driving America's Obesity Problem?"},
    {"id": "PLAIN-44", "title": "Who Should be Careful About Curcumin?"},
    {"id": "PLAIN-56", "title": "Foods for Glaucoma"},
    {"id": "PLAIN-91", "title": "Chronic Headaches and Pork Parasites"},
    {"id": "PLAIN-123", "title": "How Citrus Might Help Keep Your Hands Warm"},
    {"id": "PLAIN-320", "title": "Breast Cancer and Diet"},
]

app = Flask(__name__)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
state = {
    "setup_status": "pending",  # pending | running | done | error
    "setup_error": None,
    "java_ok": False,
    "fatjar_ok": False,
    "index_ok": False,
    "topics_ok": False,
    "search_ok": False,
    "eval_ok": False,
    "repro_discovery_ok": False,
    "observed_metrics": {},
    "expected_metrics": {"nDCG@10": EXPECTED_NDCG10},
    "comparison": None,
    "eval_elapsed": None,
    "setup_log_lines": [],
    "commands": [],
    "artifacts": [],
}


def _log(msg):
    state["setup_log_lines"].append(msg)
    try:
        print(msg, flush=True)
    except (BrokenPipeError, OSError):
        pass


def _run(cmd, label, timeout=300, capture=True):
    """Run a command, log it, and return (success, stdout, stderr)."""
    cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
    state["commands"].append({"label": label, "command": cmd_str})
    _log(f"[{label}] $ {cmd_str}")
    try:
        result = subprocess.run(
            cmd if isinstance(cmd, list) else cmd,
            shell=isinstance(cmd, str),
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        out = (result.stdout or "")[-2000:] if capture else ""
        err = (result.stderr or "")[-2000:] if capture else ""
        if result.returncode != 0:
            _log(f"  EXIT {result.returncode}: {err[:500]}")
            return False, out, err
        if out.strip():
            _log(f"  {out[:500]}")
        return True, out, err
    except subprocess.TimeoutExpired:
        _log(f"  TIMEOUT after {timeout}s")
        return False, "", f"timeout after {timeout}s"
    except Exception as e:
        _log(f"  ERROR: {e}")
        return False, "", str(e)


def _java_cmd(*args):
    """Build a java -cp fatjar command."""
    return ["java", "-cp", str(ANSERINI_JAR)] + list(args)


def _setup():
    """Run full setup in a background thread."""
    state["setup_status"] = "running"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_lines = []

    try:
        # --- 1. Java check ---
        _log("[setup] Checking Java ...")
        ok, out, _ = _run("java -version", "java-version")
        state["java_ok"] = ok
        if not ok:
            raise RuntimeError("Java not available")

        # --- 2. Fatjar download ---
        if not ANSERINI_JAR.exists():
            _log(f"[setup] Downloading Anserini fatjar v{ANSERINI_VERSION} ...")
            ok, _, _ = _run(
                f"curl -fL -o '{ANSERINI_JAR}' "
                f"'https://repo1.maven.org/maven2/io/anserini/anserini/"
                f"{ANSERINI_VERSION}/anserini-{ANSERINI_VERSION}-fatjar.jar'",
                "fatjar-download",
                timeout=300,
            )
            if not ok:
                raise RuntimeError("Failed to download Anserini fatjar")
        else:
            _log(f"[setup] Fatjar already present: {ANSERINI_JAR}")
        state["fatjar_ok"] = ANSERINI_JAR.exists()
        state["artifacts"].append({"label": "Anserini fatjar", "path": str(ANSERINI_JAR)})

        # --- 3. Fatjar smoke test (CACM) ---
        _log("[setup] Running CACM smoke test ...")
        cacm_run = DATA_DIR / "run.cacm.bm25.txt"
        ok, _, _ = _run(
            _java_cmd(
                "io.anserini.search.SearchCollection",
                "-threads", "1", "-index", "cacm", "-topics", "cacm",
                "-output", str(cacm_run), "-hits", "1000", "-bm25",
            ),
            "smoke-test-cacm",
            timeout=120,
        )
        if ok and cacm_run.exists():
            _log("[setup] CACM smoke test passed.")
        else:
            _log("[setup] WARNING: CACM smoke test did not pass, continuing.")

        # --- 4. NFCorpus SearchCollection (BM25 evaluation run) ---
        _log("[setup] Running NFCorpus BM25 SearchCollection ...")
        t0 = time.time()
        ok, out, err = _run(
            _java_cmd(
                "io.anserini.search.SearchCollection",
                "-threads", "1",
                "-index", INDEX_NAME,
                "-topics", TOPICS_NAME,
                "-output", str(RUN_FILE),
                "-bm25",
                "-removeQuery",
            ),
            "nfcorpus-search",
            timeout=600,
        )
        elapsed = time.time() - t0
        state["eval_elapsed"] = round(elapsed, 2)
        state["index_ok"] = ok
        state["search_ok"] = ok and RUN_FILE.exists()
        if ok and RUN_FILE.exists():
            state["artifacts"].append({"label": "NFCorpus BM25 run file", "path": str(RUN_FILE)})
            _log(f"[setup] SearchCollection completed in {elapsed:.1f}s → {RUN_FILE}")
        else:
            raise RuntimeError(f"SearchCollection failed: {err[:300]}")

        # --- 5. Evaluation with TrecEval ---
        _log("[setup] Evaluating with TrecEval (nDCG@10) ...")
        ok, out, err = _run(
            _java_cmd(
                "io.anserini.eval.TrecEval",
                "-c", "-m", "ndcg_cut.10",
                EVAL_QRELS,
                str(RUN_FILE),
            ),
            "nfcorpus-eval-ndcg",
            timeout=120,
        )
        if ok and out.strip():
            # Parse: "ndcg_cut_10\tall\t0.3218"
            for line in out.strip().splitlines():
                parts = line.strip().split()
                if len(parts) >= 3 and parts[1] == "all":
                    metric_raw = parts[0]  # e.g. "ndcg_cut_10"
                    val = float(parts[2])
                    # Normalize to "nDCG@10"
                    state["observed_metrics"]["nDCG@10"] = val
                    _log(f"[setup] Observed {metric_raw} = {val}")
            state["eval_ok"] = bool(state["observed_metrics"])

            # Also get additional metrics
            ok2, out2, _ = _run(
                _java_cmd(
                    "io.anserini.eval.TrecEval",
                    "-c", "-m", "map", "-m", "P.10", "-m", "recall.100",
                    EVAL_QRELS,
                    str(RUN_FILE),
                ),
                "nfcorpus-eval-extra",
                timeout=120,
            )
            if ok2 and out2.strip():
                for line in out2.strip().splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 3 and parts[1] == "all":
                        raw = parts[0]
                        val = float(parts[2])
                        label = raw
                        if raw == "map":
                            label = "MAP"
                        elif raw.startswith("P_"):
                            label = f"P@{raw[2:]}"
                        elif raw.startswith("recall_"):
                            label = f"Recall@{raw[7:]}"
                        state["observed_metrics"][label] = val
                        _log(f"[setup] Observed {raw} ({label}) = {val}")

            # Save eval output
            EVAL_FILE.write_text(out)
            state["artifacts"].append({"label": "Evaluation output", "path": str(EVAL_FILE)})
        else:
            _log(f"[setup] WARNING: TrecEval failed: {err[:300]}")

        # --- 6. Comparison ---
        obs = state["observed_metrics"].get("nDCG@10")
        exp = EXPECTED_NDCG10
        if obs is not None:
            delta = round(obs - exp, 4)
            if abs(delta) < 0.001:
                status = "PASS"
            elif abs(delta) < 0.01:
                status = "CLOSE"
            else:
                status = "FAIL"
            state["comparison"] = {
                "metric": "nDCG@10",
                "expected": exp,
                "observed": obs,
                "delta": delta,
                "status": status,
            }

        # --- 7. Extract topics for sample queries ---
        _log("[setup] Extracting NFCorpus topics ...")
        ok, out, _ = _run(
            _java_cmd("io.anserini.cli.TopicsRegistry", "--get", TOPICS_NAME),
            "topics-registry",
            timeout=60,
        )
        if ok and out.strip():
            try:
                topics = json.loads(out.strip())
                TOPICS_FILE.write_text(json.dumps(topics, indent=2))
                state["topics_ok"] = True
                state["artifacts"].append({"label": "NFCorpus topics", "path": str(TOPICS_FILE)})
            except json.JSONDecodeError:
                state["topics_ok"] = False

        # --- 8. Reproduction discovery ---
        _log("[setup] Running reproduction discovery ...")
        ok, out, _ = _run(
            _java_cmd(
                "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
                "--config", "beir.core", "--show",
            ),
            "repro-discovery-show",
            timeout=60,
        )
        state["repro_discovery_ok"] = ok
        if ok:
            state["artifacts"].append({"label": "Reproduction config (beir.core)", "path": "in-memory"})

        state["setup_status"] = "done"
        _log("[setup] Setup complete.")

    except Exception as e:
        state["setup_status"] = "error"
        state["setup_error"] = str(e)
        _log(f"[setup] ERROR: {e}")

    # Persist setup log
    SETUP_LOG.write_text("\n".join(state["setup_log_lines"]))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/health")
def health():
    ready = state["setup_status"] == "done"
    return jsonify({
        "status": "ok" if ready else "setting_up",
        "anserini_available": state["fatjar_ok"],
        "nfcorpus_ready": state["index_ok"] and state["search_ok"],
        "search_available": state["search_ok"],
        "evaluation_available": state["eval_ok"],
        "setup_status": state["setup_status"],
        "setup_error": state["setup_error"],
    })


@app.route("/api/status")
def api_status():
    return jsonify(state)


@app.route("/api/sample-queries")
def api_sample_queries():
    return jsonify(SAMPLE_QUERIES)


@app.route("/api/search", methods=["POST"])
def api_search():
    """Execute a live search query against NFCorpus using Anserini CLI."""
    body = request.get_json(force=True) if request.is_json else request.form
    query = body.get("query", "").strip()
    hits = int(body.get("hits", 10))
    if not query:
        return jsonify({"error": "query is required"}), 400
    if not state["search_ok"]:
        return jsonify({"error": "Search not ready yet"}), 503

    cmd = _java_cmd(
        "io.anserini.cli.Search",
        "--index", INDEX_NAME,
        "--query", query,
        "--hits", str(hits),
        "--json",
    )
    cmd_str = " ".join(cmd)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = result.stdout or ""
        if result.returncode != 0:
            return jsonify({
                "error": "Search command failed",
                "stderr": (result.stderr or "")[:500],
                "command": cmd_str,
            }), 500
        # Parse JSON output from Search CLI
        try:
            parsed = json.loads(output)
            # The CLI returns {"query": ..., "candidates": [...]}
            raw_candidates = []
            if isinstance(parsed, list):
                raw_candidates = parsed
            elif isinstance(parsed, dict):
                raw_candidates = parsed.get("candidates", parsed.get("results", []))
                if not isinstance(raw_candidates, list):
                    raw_candidates = [parsed]
            # Normalize to a flat format for the frontend
            results = []
            for i, c in enumerate(raw_candidates):
                doc = c.get("doc", {})
                if isinstance(doc, str):
                    doc = {"text": doc}
                results.append({
                    "rank": i + 1,
                    "docid": c.get("docid", c.get("doc_id", "")),
                    "score": c.get("score", 0),
                    "title": doc.get("title", "") if isinstance(doc, dict) else "",
                    "text": doc.get("text", "") if isinstance(doc, dict) else str(doc),
                })
        except json.JSONDecodeError:
            results = []

        return jsonify({
            "query": query,
            "results": results,
            "command": cmd_str,
            "raw_output_preview": output[:2000],
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Search timed out", "command": cmd_str}), 504
    except Exception as e:
        return jsonify({"error": str(e), "command": cmd_str}), 500


@app.route("/api/rerun-eval", methods=["POST"])
def api_rerun_eval():
    """Re-run the BM25 evaluation pipeline."""
    if not state["fatjar_ok"]:
        return jsonify({"error": "Fatjar not available"}), 503

    t0 = time.time()
    ok, out, err = _run(
        _java_cmd(
            "io.anserini.search.SearchCollection",
            "-threads", "1",
            "-index", INDEX_NAME,
            "-topics", TOPICS_NAME,
            "-output", str(RUN_FILE),
            "-bm25",
            "-removeQuery",
        ),
        "rerun-search",
        timeout=600,
    )
    elapsed = time.time() - t0
    state["eval_elapsed"] = round(elapsed, 2)

    if not ok:
        return jsonify({"error": f"Search failed: {err[:300]}"}), 500

    ok, out, err = _run(
        _java_cmd(
            "io.anserini.eval.TrecEval",
            "-c", "-m", "ndcg_cut.10",
            EVAL_QRELS,
            str(RUN_FILE),
        ),
        "rerun-eval",
        timeout=120,
    )

    observed = {}
    if ok and out.strip():
        for line in out.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 3 and parts[1] == "all":
                val = float(parts[2])
                observed["nDCG@10"] = val

    # Update comparison
    obs = observed.get("nDCG@10")
    exp = EXPECTED_NDCG10
    comparison = None
    if obs is not None:
        delta = round(obs - exp, 4)
        if abs(delta) < 0.001:
            status = "PASS"
        elif abs(delta) < 0.01:
            status = "CLOSE"
        else:
            status = "FAIL"
        comparison = {
            "metric": "nDCG@10",
            "expected": exp,
            "observed": obs,
            "delta": delta,
            "status": status,
        }

    state["observed_metrics"].update(observed)
    state["comparison"] = comparison
    state["eval_ok"] = bool(observed)

    return jsonify({
        "observed_metrics": observed,
        "comparison": comparison,
        "elapsed": round(elapsed, 2),
        "rerun": True,
    })


@app.route("/api/commands")
def api_commands():
    return jsonify(state["commands"])


@app.route("/api/artifacts")
def api_artifacts():
    return jsonify(state["artifacts"])


@app.route("/api/setup-log")
def api_setup_log():
    return jsonify({"log": state["setup_log_lines"]})


# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NFCorpus Live Retrieval Diagnostics</title>
<style>
  :root {
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8;
    --green: #4ade80; --yellow: #facc15; --red: #f87171;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.5; padding: 1rem; }
  h1 { font-size: 1.4rem; margin-bottom: 0.25rem; }
  h2 { font-size: 1.1rem; margin-bottom: 0.5rem; color: var(--accent); }
  .subtitle { color: var(--muted); font-size: 0.85rem; margin-bottom: 1rem; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; max-width: 1400px; margin: 0 auto; }
  .full { grid-column: 1 / -1; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }
  .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.5rem; }
  .status-item { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; padding: 0.4rem 0.6rem;
                 background: rgba(255,255,255,0.03); border-radius: 4px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
  .dot.ok { background: var(--green); }
  .dot.pending { background: var(--yellow); animation: pulse 1s infinite; }
  .dot.err { background: var(--red); }
  @keyframes pulse { 50% { opacity: 0.4; } }
  .search-bar { display: flex; gap: 0.5rem; margin-bottom: 0.75rem; }
  .search-bar input { flex: 1; padding: 0.5rem 0.75rem; border-radius: 6px; border: 1px solid var(--border);
                      background: var(--bg); color: var(--text); font-size: 0.95rem; }
  .search-bar button { padding: 0.5rem 1rem; border-radius: 6px; border: none; cursor: pointer;
                       background: var(--accent); color: #000; font-weight: 600; }
  .search-bar button:disabled { opacity: 0.5; cursor: not-allowed; }
  .samples { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.75rem; }
  .sample-btn { font-size: 0.75rem; padding: 0.25rem 0.5rem; border-radius: 4px; border: 1px solid var(--border);
                background: transparent; color: var(--muted); cursor: pointer; }
  .sample-btn:hover { border-color: var(--accent); color: var(--accent); }
  .result-table { width: 100%; font-size: 0.82rem; border-collapse: collapse; }
  .result-table th { text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border);
                     color: var(--muted); font-weight: 600; }
  .result-table td { padding: 0.4rem 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.05);
                     vertical-align: top; }
  .result-table .rank { color: var(--accent); font-weight: 600; }
  .result-table .score { font-family: monospace; }
  .result-table .docid { font-family: monospace; color: var(--accent); }
  .result-table .snippet { color: var(--muted); max-width: 400px; overflow: hidden; text-overflow: ellipsis;
                           white-space: nowrap; }
  .metric-row { display: flex; justify-content: space-between; padding: 0.3rem 0;
                border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem; }
  .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem;
           font-weight: 700; }
  .badge-pass { background: rgba(74,222,128,0.15); color: var(--green); }
  .badge-close { background: rgba(250,204,21,0.15); color: var(--yellow); }
  .badge-fail { background: rgba(248,113,113,0.15); color: var(--red); }
  pre { background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 0.75rem;
        font-size: 0.75rem; overflow-x: auto; max-height: 300px; overflow-y: auto; white-space: pre-wrap;
        word-break: break-all; }
  .cmd-item { margin-bottom: 0.5rem; }
  .cmd-label { font-size: 0.75rem; color: var(--accent); font-weight: 600; }
  .cmd-text { font-family: monospace; font-size: 0.75rem; color: var(--muted); }
  .artifact-item { font-size: 0.82rem; padding: 0.2rem 0; }
  .artifact-path { font-family: monospace; color: var(--muted); font-size: 0.75rem; }
  .rerun-btn { padding: 0.4rem 0.8rem; border-radius: 6px; border: 1px solid var(--accent);
               background: transparent; color: var(--accent); cursor: pointer; font-size: 0.82rem; }
  .rerun-btn:hover { background: rgba(56,189,248,0.1); }
  .rerun-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .search-cmd { font-family: monospace; font-size: 0.72rem; color: var(--muted); margin-top: 0.5rem;
                padding: 0.4rem; background: var(--bg); border-radius: 4px; }
  .loading { text-align: center; padding: 2rem; color: var(--muted); }
  .error-msg { color: var(--red); font-size: 0.85rem; }
  #search-info { margin-top: 0.5rem; }
  @media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<h1>🔬 NFCorpus Live Retrieval Diagnostics</h1>
<p class="subtitle">Anserini-backed BM25 retrieval &bull; Dataset: <strong>nfcorpus</strong> (BEIR v1.0.0) &bull; Render-ready Docker service</p>

<div class="grid">
  <!-- Readiness Panel -->
  <div class="card full" id="readiness-card">
    <h2>Readiness Status</h2>
    <div class="status-grid" id="readiness-grid">
      <div class="status-item"><div class="dot pending" id="dot-java"></div><span id="lbl-java">Java</span></div>
      <div class="status-item"><div class="dot pending" id="dot-fatjar"></div><span id="lbl-fatjar">Anserini Fatjar</span></div>
      <div class="status-item"><div class="dot pending" id="dot-index"></div><span id="lbl-index">NFCorpus Index</span></div>
      <div class="status-item"><div class="dot pending" id="dot-topics"></div><span id="lbl-topics">NFCorpus Topics</span></div>
      <div class="status-item"><div class="dot pending" id="dot-repro"></div><span id="lbl-repro">Repro Discovery</span></div>
      <div class="status-item"><div class="dot pending" id="dot-search"></div><span id="lbl-search">Live Search</span></div>
      <div class="status-item"><div class="dot pending" id="dot-eval"></div><span id="lbl-eval">BM25 Evaluation</span></div>
    </div>
    <div id="setup-error" class="error-msg" style="margin-top:0.5rem;"></div>
  </div>

  <!-- Live Search -->
  <div class="card">
    <h2>Live Search</h2>
    <div class="search-bar">
      <input type="text" id="search-input" placeholder="Enter query..." disabled />
      <button id="search-btn" disabled>Search</button>
    </div>
    <div class="samples" id="sample-queries">Loading sample queries...</div>
    <div id="search-results">
      <div class="loading">Waiting for setup to complete...</div>
    </div>
    <div id="search-info"></div>
  </div>

  <!-- Evaluation Panel -->
  <div class="card">
    <h2>BM25 Evaluation</h2>
    <div id="eval-panel">
      <div class="loading">Waiting for evaluation...</div>
    </div>
    <div style="margin-top:0.75rem;">
      <button class="rerun-btn" id="rerun-btn" disabled>🔄 Verify / Rerun</button>
    </div>
  </div>

  <!-- Commands Drawer -->
  <div class="card">
    <h2>Commands Executed</h2>
    <div id="commands-panel"><div class="loading">Loading...</div></div>
  </div>

  <!-- Artifacts Drawer -->
  <div class="card">
    <h2>Artifacts &amp; Paths</h2>
    <div id="artifacts-panel"><div class="loading">Loading...</div></div>
  </div>

  <!-- Setup Log -->
  <div class="card full">
    <h2>Setup Log</h2>
    <pre id="setup-log">Waiting...</pre>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
let pollInterval = null;

function dot(id, ok, pending) {
  const d = $('dot-' + id);
  d.className = 'dot ' + (ok ? 'ok' : (pending ? 'pending' : 'err'));
}

async function pollStatus() {
  try {
    const r = await fetch('/api/status');
    const s = await r.json();

    dot('java', s.java_ok, s.setup_status === 'running');
    dot('fatjar', s.fatjar_ok, s.setup_status === 'running');
    dot('index', s.index_ok, s.setup_status === 'running');
    dot('topics', s.topics_ok, s.setup_status === 'running');
    dot('repro', s.repro_discovery_ok, s.setup_status === 'running');
    dot('search', s.search_ok, s.setup_status === 'running');
    dot('eval', s.eval_ok, s.setup_status === 'running');

    if (s.setup_error) $('setup-error').textContent = s.setup_error;

    // Enable search when ready
    $('search-input').disabled = !s.search_ok;
    $('search-btn').disabled = !s.search_ok;
    $('rerun-btn').disabled = !s.eval_ok;

    // Evaluation panel
    if (s.eval_ok && Object.keys(s.observed_metrics).length) {
      let html = '';
      for (const [m, v] of Object.entries(s.observed_metrics)) {
        html += '<div class="metric-row"><span>' + m + '</span><span class="score">' + v.toFixed(4) + '</span></div>';
      }
      if (s.comparison) {
        const c = s.comparison;
        const cls = c.status.toLowerCase();
        html += '<div class="metric-row" style="margin-top:0.5rem;border-top:1px solid var(--border);padding-top:0.5rem;">';
        html += '<span>Expected ' + c.metric + '</span><span>' + c.expected.toFixed(4) + '</span></div>';
        html += '<div class="metric-row"><span>Observed ' + c.metric + '</span><span>' + c.observed.toFixed(4) + '</span></div>';
        html += '<div class="metric-row"><span>Delta</span><span>' + (c.delta >= 0 ? '+' : '') + c.delta.toFixed(4) + '</span></div>';
        html += '<div class="metric-row"><span>Status</span><span class="badge badge-' + cls + '">' + c.status +
                '</span></div>';
      }
      if (s.eval_elapsed != null) {
        html += '<div class="metric-row"><span>Elapsed</span><span>' + s.eval_elapsed + 's</span></div>';
      }
      $('eval-panel').innerHTML = html;
    } else if (s.setup_status === 'error') {
      $('eval-panel').innerHTML = '<div class="error-msg">Setup failed: ' + (s.setup_error || 'unknown') + '</div>';
    }

    if (s.setup_status === 'done' || s.setup_status === 'error') {
      clearInterval(pollInterval);
    }
  } catch (e) { console.error('poll error', e); }
}

async function loadCommands() {
  const r = await fetch('/api/commands');
  const cmds = await r.json();
  if (!cmds.length) { $('commands-panel').innerHTML = '<div class="loading">No commands yet.</div>'; return; }
  $('commands-panel').innerHTML = cmds.map(c =>
    '<div class="cmd-item"><div class="cmd-label">' + c.label + '</div><div class="cmd-text">' +
    escHtml(c.command) + '</div></div>'
  ).join('');
}

async function loadArtifacts() {
  const r = await fetch('/api/artifacts');
  const arts = await r.json();
  if (!arts.length) { $('artifacts-panel').innerHTML = '<div class="loading">No artifacts yet.</div>'; return; }
  $('artifacts-panel').innerHTML = arts.map(a =>
    '<div class="artifact-item"><strong>' + escHtml(a.label) + '</strong><br><span class="artifact-path">' +
    escHtml(a.path) + '</span></div>'
  ).join('');
}

async function loadSamples() {
  const r = await fetch('/api/sample-queries');
  const qs = await r.json();
  $('sample-queries').innerHTML = qs.map(q =>
    '<button class="sample-btn" data-query="' + escAttr(q.title) + '">' + escHtml(q.title) + '</button>'
  ).join('');
  $('sample-queries').querySelectorAll('.sample-btn').forEach(btn => {
    btn.addEventListener('click', () => doSearch(btn.dataset.query));
  });
}

async function loadSetupLog() {
  const r = await fetch('/api/setup-log');
  const d = await r.json();
  $('setup-log').textContent = d.log.join('\n');
}

async function doSearch(query) {
  if (!query) return;
  $('search-input').value = query;
  $('search-btn').disabled = true;
  $('search-results').innerHTML = '<div class="loading">Searching...</div>';
  $('search-info').innerHTML = '';

  try {
    const r = await fetch('/api/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query, hits: 10}),
    });
    const data = await r.json();
    if (data.error) {
      $('search-results').innerHTML = '<div class="error-msg">' + escHtml(data.error) + '</div>';
    } else {
      renderResults(data);
    }
    if (data.command) {
      $('search-info').innerHTML = '<div class="search-cmd"><strong>Command:</strong> ' + escHtml(data.command) + '</div>';
    }
  } catch (e) {
    $('search-results').innerHTML = '<div class="error-msg">Request failed</div>';
  }
  $('search-btn').disabled = false;
}

function renderResults(data) {
  const results = data.results || [];
  if (!results.length) {
    $('search-results').innerHTML = '<div style="color:var(--muted);">No results found.</div>';
    return;
  }
  let html = '<table class="result-table"><thead><tr><th>Rank</th><th>DocID</th><th>Score</th><th>Title / Content</th></tr></thead><tbody>';
  results.forEach((r, i) => {
    const rank = r.rank || (i + 1);
    const docid = r.docid || r.doc_id || '';
    const score = r.score != null ? r.score : 0;
    const title = r.title || '';
    const text = r.text || r.contents || r.content || r.snippet || r.raw || '';
    const snippet = (typeof text === 'string' ? text : JSON.stringify(text)).substring(0, 250);
    const titleHtml = title ? '<strong>' + escHtml(title) + '</strong><br>' : '';
    html += '<tr><td class="rank">' + rank + '</td><td class="docid">' + escHtml(docid) +
            '</td><td class="score">' + score.toFixed(4) + '</td><td class="snippet">' +
            titleHtml + escHtml(snippet) + '</td></tr>';
  });
  html += '</tbody></table>';
  $('search-results').innerHTML = html;
}

async function rerunEval() {
  $('rerun-btn').disabled = true;
  $('eval-panel').innerHTML = '<div class="loading">Re-running evaluation...</div>';
  try {
    const r = await fetch('/api/rerun-eval', {method: 'POST'});
    const data = await r.json();
    if (data.error) {
      $('eval-panel').innerHTML = '<div class="error-msg">' + escHtml(data.error) + '</div>';
    } else {
      let html = '';
      for (const [m, v] of Object.entries(data.observed_metrics)) {
        html += '<div class="metric-row"><span>' + m + ' (rerun)</span><span class="score">' + v.toFixed(4) + '</span></div>';
      }
      if (data.comparison) {
        const c = data.comparison;
        const cls = c.status.toLowerCase();
        html += '<div class="metric-row"><span>Expected ' + c.metric + '</span><span>' + c.expected.toFixed(4) + '</span></div>';
        html += '<div class="metric-row"><span>Observed ' + c.metric + '</span><span>' + c.observed.toFixed(4) + '</span></div>';
        html += '<div class="metric-row"><span>Delta</span><span>' + (c.delta >= 0 ? '+' : '') + c.delta.toFixed(4) + '</span></div>';
        html += '<div class="metric-row"><span>Status</span><span class="badge badge-' + cls + '">' + c.status + '</span></div>';
      }
      if (data.elapsed != null) html += '<div class="metric-row"><span>Elapsed</span><span>' + data.elapsed + 's</span></div>';
      $('eval-panel').innerHTML = html + '<div style="color:var(--green);font-size:0.8rem;margin-top:0.5rem;">✓ Fresh rerun completed</div>';
    }
    await loadCommands();
    await loadArtifacts();
  } catch (e) {
    $('eval-panel').innerHTML = '<div class="error-msg">Rerun failed</div>';
  }
  $('rerun-btn').disabled = false;
}

function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function escAttr(s) { return s.replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }

// Init
document.addEventListener('DOMContentLoaded', () => {
  $('search-btn').addEventListener('click', () => doSearch($('search-input').value));
  $('search-input').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch($('search-input').value); });
  $('rerun-btn').addEventListener('click', rerunEval);

  pollInterval = setInterval(pollStatus, 2000);
  pollStatus();
  loadSamples();
  loadCommands();
  loadArtifacts();
  loadSetupLog();
  setInterval(() => { loadCommands(); loadArtifacts(); loadSetupLog(); }, 5000);
});
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    # Start setup in background
    setup_thread = threading.Thread(target=_setup, daemon=True)
    setup_thread.start()
    print(f"Starting NFCorpus Workbench on 0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
