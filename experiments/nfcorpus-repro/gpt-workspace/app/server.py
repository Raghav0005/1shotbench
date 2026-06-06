#!/usr/bin/env python3
"""NFCorpus live retrieval diagnostics workbench.

This server intentionally delegates retrieval and evaluation to Anserini command
line tools. It does not contain a retrieval implementation or baked-in run data.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("NFCORPUS_CACHE_DIR", APP_ROOT / ".runtime")).resolve()
HOME_DIR = DATA_ROOT / "home"
JAR_DIR = DATA_ROOT / "anserini"
RUNS_DIR = DATA_ROOT / "runs"
LOGS_DIR = DATA_ROOT / "logs"
ARTIFACTS_DIR = DATA_ROOT / "artifacts"
for d in (DATA_ROOT, HOME_DIR, JAR_DIR, RUNS_DIR, LOGS_DIR, ARTIFACTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

PORT = int(os.environ.get("PORT", "10000"))
HOST = "0.0.0.0"
CONFIG = os.environ.get("ANSERINI_REPRO_CONFIG", "beir.core")
TOPIC_KEY = "nfcorpus"
INDEX_NAME = "beir-v1.0.0-nfcorpus.flat"
TOPICS = "beir-nfcorpus"
EVAL_KEY_DEFAULT = "beir-v1.0.0-nfcorpus.test"
SAMPLE_QUERIES = [
    "vitamin d",
    "effects of green tea",
    "omega 3 fatty acids cardiovascular disease",
    "low carbohydrate diet diabetes",
]

STATE_LOCK = threading.RLock()
STATE: dict[str, Any] = {
    "app": "initializing",
    "dataset": "NFCorpus",
    "datasetKey": TOPIC_KEY,
    "index": INDEX_NAME,
    "config": CONFIG,
    "portBinding": f"HTTP binds {HOST}:${{PORT:-10000}}",
    "cacheRoot": str(DATA_ROOT),
    "homeForAnseriniCache": str(HOME_DIR),
    "anserini": {"available": False, "jar": None, "version": None, "java": None, "error": None},
    "nfcorpus": {"ready": False, "indexReady": False, "registry": None, "error": None},
    "reproduction": {"ready": False, "expected": {}, "evalKey": None, "metricDefinitions": {}, "dryRunNfcorpus": [], "error": None},
    "search": {"available": False, "last": None, "error": None},
    "evaluation": {"available": False, "running": False, "last": None, "error": None},
    "commands": [],
    "artifacts": [],
    "errors": [],
    "sampleQueries": SAMPLE_QUERIES,
    "startedAt": time.time(),
}


def update_state(path: list[str], value: Any) -> None:
    with STATE_LOCK:
        cur = STATE
        for key in path[:-1]:
            cur = cur[key]
        cur[path[-1]] = value


def snapshot() -> dict[str, Any]:
    with STATE_LOCK:
        return json.loads(json.dumps(STATE, default=str))


def append_error(message: str) -> None:
    with STATE_LOCK:
        STATE["errors"].append({"time": time.time(), "message": message})


def command_string(args: list[str], env_prefix: dict[str, str] | None = None) -> str:
    prefix = ""
    if env_prefix:
        prefix = " ".join(f"{k}={shlex.quote(v)}" for k, v in env_prefix.items()) + " "
    return prefix + " ".join(shlex.quote(a) for a in args)


def preview(text: str, max_chars: int = 5000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n… [truncated]"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def anserini_env() -> dict[str, str]:
    env = os.environ.copy()
    # Anserini's prebuilt-index downloader uses ~/.cache/pyserini. Pin HOME so
    # downloads are NFCorpus-specific runtime artifacts under DATA_ROOT.
    env["HOME"] = str(HOME_DIR)
    return env


def record_artifact(kind: str, path: Path, description: str) -> None:
    item = {"kind": kind, "path": str(path), "description": description, "exists": path.exists()}
    if path.exists() and path.is_file():
        try:
            item["sizeBytes"] = path.stat().st_size
            item["preview"] = preview(path.read_text(encoding="utf-8", errors="replace"), 2500)
        except Exception as exc:  # pragma: no cover - filesystem race guard
            item["previewError"] = str(exc)
    with STATE_LOCK:
        existing = [a for a in STATE["artifacts"] if a["path"] != str(path)]
        existing.append(item)
        STATE["artifacts"] = existing


def run_command(stage: str, args: list[str], timeout: int = 300, env_prefix: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = anserini_env()
    display = command_string(args, env_prefix or {"HOME": str(HOME_DIR)})
    safe_stage = re.sub(r"[^A-Za-z0-9_.-]+", "-", stage).strip("-")
    stamp = int(time.time() * 1000)
    stdout_path = LOGS_DIR / f"{stamp}.{safe_stage}.stdout.log"
    stderr_path = LOGS_DIR / f"{stamp}.{safe_stage}.stderr.log"
    started = time.time()
    try:
        proc = subprocess.run(args, cwd=str(APP_ROOT), env=env, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + f"\nTimed out after {timeout}s"
        write_text(stdout_path, stdout)
        write_text(stderr_path, stderr)
        elapsed = time.time() - started
        entry = {"stage": stage, "command": display, "exitCode": 124, "elapsedSeconds": elapsed,
                 "stdoutPath": str(stdout_path), "stderrPath": str(stderr_path), "stdoutPreview": preview(stdout),
                 "stderrPreview": preview(stderr)}
        with STATE_LOCK:
            STATE["commands"].append(entry)
        raise RuntimeError(f"Command timed out during {stage}: {display}") from exc
    write_text(stdout_path, proc.stdout)
    write_text(stderr_path, proc.stderr)
    elapsed = time.time() - started
    entry = {"stage": stage, "command": display, "exitCode": proc.returncode, "elapsedSeconds": elapsed,
             "stdoutPath": str(stdout_path), "stderrPath": str(stderr_path), "stdoutPreview": preview(proc.stdout),
             "stderrPreview": preview(proc.stderr)}
    with STATE_LOCK:
        STATE["commands"].append(entry)
    record_artifact("log", stdout_path, f"stdout for {stage}")
    record_artifact("log", stderr_path, f"stderr for {stage}")
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed during {stage} (exit {proc.returncode}): {display}\n{preview(proc.stderr or proc.stdout, 1200)}")
    return proc


def java_args() -> list[str]:
    jar = STATE["anserini"].get("jar")
    if not jar:
        jar = os.environ.get("ANSERINI_JAR", "")
    return ["java", "-cp", str(jar)]


def discover_or_download_jar() -> Path:
    env_jar = os.environ.get("ANSERINI_JAR")
    if env_jar and Path(env_jar).exists():
        return Path(env_jar).resolve()

    version = os.environ.get("ANSERINI_VERSION")
    if not version:
        metadata_url = "https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml"
        proc = run_command("fatjar-maven-metadata", ["curl", "-sS", metadata_url], timeout=60, env_prefix={})
        m = re.search(r"<release>([^<]+)</release>", proc.stdout)
        if not m:
            raise RuntimeError("Unable to discover latest Anserini release from Maven metadata")
        version = m.group(1)
    jar = JAR_DIR / f"anserini-{version}-fatjar.jar"
    if not jar.exists():
        url = f"https://repo1.maven.org/maven2/io/anserini/anserini/{version}/anserini-{version}-fatjar.jar"
        run_command("fatjar-download", ["curl", "-fL", "-o", str(jar), url], timeout=600, env_prefix={})
    return jar.resolve()


def parse_reproduction_show(show_text: str) -> dict[str, Any]:
    flat_match = re.search(r"(?ms)^  - name: flat\n(?P<block>.*?)(?=^  - name:|\Z)", show_text)
    if not flat_match:
        raise RuntimeError("beir.core reproduction config does not expose a flat BM25 condition")
    block = flat_match.group("block")
    command_match = re.search(r"^    command:\s*(.+)$", block, re.M)
    topic_match = re.search(
        r"(?ms)^      - topic_key:\s*nfcorpus\n(?P<topic>.*?)(?=^      - topic_key:|^  - name:|\Z)", block
    )
    if not topic_match:
        raise RuntimeError("beir.core reproduction config does not expose NFCorpus")
    topic = topic_match.group("topic")
    eval_key = re.search(r"eval_key:\s*(\S+)", topic)
    expected_block = re.search(r"expected_scores:\n(?P<expected>(?:\s{10}.+\n)+)", topic)
    metric_block = re.search(r"metric_definitions:\n(?P<defs>(?:\s{10}.+\n)+)", topic)
    expected: dict[str, float] = {}
    metric_defs: dict[str, str] = {}
    if expected_block:
        for name, value in re.findall(r"\s{10}([^:]+):\s*([0-9.]+)", expected_block.group("expected")):
            expected[name.strip()] = float(value)
    if metric_block:
        for name, value in re.findall(r"\s{10}([^:]+):\s*\"?([^\"\n]+)\"?", metric_block.group("defs")):
            metric_defs[name.strip()] = value.strip()
    return {
        "condition": "flat",
        "commandTemplate": command_match.group(1).strip() if command_match else None,
        "evalKey": eval_key.group(1) if eval_key else EVAL_KEY_DEFAULT,
        "expected": expected,
        "metricDefinitions": metric_defs,
    }


def extract_nfcorpus_dryrun(dry_text: str) -> list[str]:
    lines = []
    for line in dry_text.splitlines():
        if "nfcorpus" in line and ("Retrieval command:" in line or "Eval command:" in line or INDEX_NAME in line):
            lines.append(line.strip())
    return lines[:20]


def parse_search_json(stdout: str) -> dict[str, Any]:
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith('{"query"'):
            return json.loads(line)
    # Fallback for future pretty-printed JSON: take the first JSON object start.
    idx = stdout.find('{"query"')
    if idx >= 0:
        return json.loads(stdout[idx:])
    raise RuntimeError("Anserini search did not emit JSON candidates")


def normalize_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for i, cand in enumerate(payload.get("candidates", []), start=1):
        doc = cand.get("doc") or {}
        text = doc.get("text") or doc.get("contents") or ""
        title = doc.get("title") or ""
        snippet = (text[:700] + "…") if len(text) > 700 else text
        rows.append({
            "rank": i,
            "docid": cand.get("docid"),
            "score": cand.get("score"),
            "title": title,
            "snippet": snippet,
            "metadata": doc.get("metadata") or {},
        })
    return rows


def run_live_search(query: str, hits: int = 10) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("Missing query")
    args = java_args() + ["io.anserini.cli.Search", "--index", INDEX_NAME, "--query", query, "--hits", str(hits), "--json"]
    proc = run_command("live-search", args, timeout=180)
    payload = parse_search_json(proc.stdout)
    result = {
        "query": query,
        "index": INDEX_NAME,
        "backedBy": "anserini-cli",
        "command": command_string(args, {"HOME": str(HOME_DIR)}),
        "results": normalize_candidates(payload),
        "rawPreview": preview(proc.stdout, 4000),
        "timestamp": time.time(),
    }
    update_state(["search", "last"], result)
    update_state(["search", "error"], None)
    return result


def metric_to_trec_arg(metric_name: str, metric_defs: dict[str, str]) -> str:
    definition = metric_defs.get(metric_name)
    if definition:
        return definition
    if metric_name == "nDCG@10":
        return "-c -m ndcg_cut.10"
    return f"-c -m {metric_name}"


def run_evaluation(source: str = "startup") -> dict[str, Any]:
    with STATE_LOCK:
        if STATE["evaluation"].get("running"):
            return {"running": True, "message": "Evaluation is already running"}
        STATE["evaluation"]["running"] = True
        STATE["evaluation"]["error"] = None
    started = time.time()
    try:
        repro = snapshot()["reproduction"]
        eval_key = repro.get("evalKey") or EVAL_KEY_DEFAULT
        expected = repro.get("expected") or {}
        metric_defs = repro.get("metricDefinitions") or {}
        run_file = RUNS_DIR / "run.beir.core.flat.nfcorpus.txt"
        eval_file = RUNS_DIR / "eval.beir.core.flat.nfcorpus.txt"
        retrieval_args = java_args() + [
            "-Xms128M", "-Xmx1G", "-Dslf4j.internal.verbosity=WARN",
            "io.anserini.search.SearchCollection",
            "-threads", os.environ.get("ANSERINI_THREADS", "1"),
            "-index", INDEX_NAME,
            "-topics", TOPICS,
            "-output", str(run_file),
            "-bm25", "-removeQuery",
        ]
        run_command("bm25-retrieval", retrieval_args, timeout=600)
        observed: dict[str, float] = {}
        eval_outputs = []
        metrics = list(expected.keys()) or ["nDCG@10"]
        for metric in metrics:
            trec_args = shlex.split(metric_to_trec_arg(metric, metric_defs))
            eval_args = java_args() + ["trec_eval"] + trec_args + [eval_key, str(run_file)]
            proc = run_command(f"evaluation-{metric}", eval_args, timeout=180)
            eval_outputs.append(proc.stdout)
            for line in proc.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        value = float(parts[2])
                    except ValueError:
                        continue
                    observed[metric] = value
        write_text(eval_file, "\n".join(eval_outputs))
        comparisons = []
        for metric, value in observed.items():
            exp = expected.get(metric)
            delta = None if exp is None else value - exp
            if exp is None:
                status = "expected-unavailable"
            elif abs(delta) <= 0.00005:
                status = "pass"
            elif abs(delta) <= 0.001:
                status = "close"
            else:
                status = "fail"
            comparisons.append({"metric": metric, "observed": value, "expected": exp, "delta": delta, "status": status})
        elapsed = time.time() - started
        result = {
            "source": source,
            "backedBy": "anserini-searchcollection-and-trec_eval",
            "running": False,
            "elapsedSeconds": elapsed,
            "runFile": str(run_file),
            "evalFile": str(eval_file),
            "evalKey": eval_key,
            "observed": observed,
            "expected": expected,
            "comparisons": comparisons,
            "retrievalCommand": command_string(retrieval_args, {"HOME": str(HOME_DIR)}),
            "timestamp": time.time(),
        }
        record_artifact("run", run_file, "TREC-format BM25 NFCorpus run file generated by SearchCollection")
        record_artifact("evaluation", eval_file, "trec_eval output for NFCorpus BM25")
        with STATE_LOCK:
            STATE["evaluation"]["last"] = result
            STATE["evaluation"]["available"] = bool(observed)
            STATE["evaluation"]["error"] = None
        return result
    except Exception as exc:
        append_error(f"Evaluation failure: {exc}")
        with STATE_LOCK:
            STATE["evaluation"]["available"] = False
            STATE["evaluation"]["error"] = str(exc)
        raise
    finally:
        update_state(["evaluation", "running"], False)


def setup_workflow() -> None:
    try:
        update_state(["app"], "initializing Anserini")
        java = run_command("java-version", ["java", "-version"], timeout=30, env_prefix={})
        jar = discover_or_download_jar()
        update_state(["anserini", "jar"], str(jar))
        m = re.search(r"version \"([^\"]+)\"", java.stderr + java.stdout)
        update_state(["anserini", "java"], m.group(1) if m else preview(java.stderr + java.stdout, 200))
        # Fatjar verification mirrors the CLI runtime check without forcing a non-NFCorpus download.
        run_command("fatjar-verification", ["test", "-f", str(jar)], timeout=10, env_prefix={})
        help_proc = run_command("fatjar-class-check", java_args() + ["io.anserini.search.SearchCollection", "-help"], timeout=60)
        if os.environ.get("RUN_CACM_SMOKE", "1") != "0":
            cacm_run = RUNS_DIR / "run.cacm.bm25.txt"
            cacm_eval = RUNS_DIR / "eval.cacm.bm25.txt"
            run_command("fatjar-cacm-smoke-search", java_args() + [
                "io.anserini.search.SearchCollection", "-threads", "1", "-index", "cacm", "-topics", "cacm",
                "-output", str(cacm_run), "-hits", "1000", "-bm25"
            ], timeout=300)
            cacm_eval_proc = run_command("fatjar-cacm-smoke-eval", java_args() + [
                "io.anserini.eval.TrecEval", "-c", "-m", "map", "-m", "P.30", "cacm", str(cacm_run)
            ], timeout=120)
            write_text(cacm_eval, cacm_eval_proc.stdout)
            if "map" not in cacm_eval_proc.stdout or "0.3123" not in cacm_eval_proc.stdout or "P_30" not in cacm_eval_proc.stdout or "0.1942" not in cacm_eval_proc.stdout:
                raise RuntimeError("CACM fatjar smoke test did not match expected MAP 0.3123 and P_30 0.1942")
            record_artifact("fatjar-smoke-run", cacm_run, "CACM SearchCollection smoke-test run file from install-anserini-fatjar skill")
            record_artifact("fatjar-smoke-evaluation", cacm_eval, "CACM TrecEval smoke-test output from install-anserini-fatjar skill")
        update_state(["anserini", "version"], f"fatjar {jar.name}")
        update_state(["anserini", "available"], True)
        update_state(["anserini", "error"], None)
        _ = help_proc

        update_state(["app"], "discovering reproduction")
        list_proc = run_command("reproduction-list", java_args() + ["io.anserini.reproduce.ReproduceFromPrebuiltIndexes", "--list"], timeout=120)
        configs = json.loads(list_proc.stdout)
        if CONFIG not in configs:
            raise RuntimeError(f"Required reproduction config {CONFIG!r} not listed by Anserini")
        show_proc = run_command("reproduction-show", java_args() + ["io.anserini.reproduce.ReproduceFromPrebuiltIndexes", "--config", CONFIG, "--show"], timeout=120)
        parsed = parse_reproduction_show(show_proc.stdout)
        dry_proc = run_command("reproduction-dry-run", java_args() + ["io.anserini.reproduce.ReproduceFromPrebuiltIndexes", "--config", CONFIG, "--dry-run"], timeout=180)
        with STATE_LOCK:
            STATE["reproduction"].update({
                "ready": True,
                "expected": parsed["expected"],
                "evalKey": parsed["evalKey"],
                "metricDefinitions": parsed["metricDefinitions"],
                "commandTemplate": parsed["commandTemplate"],
                "dryRunNfcorpus": extract_nfcorpus_dryrun(dry_proc.stdout),
                "error": None,
            })

        update_state(["app"], "checking NFCorpus index")
        registry_proc = run_command("nfcorpus-prebuilt-index-registry", java_args() + ["io.anserini.cli.PrebuiltIndexRegistry", "--list", "--filter", f"^{INDEX_NAME}$"], timeout=120)
        registry = json.loads(registry_proc.stdout)
        if not registry:
            raise RuntimeError(f"No Anserini prebuilt index named {INDEX_NAME}")
        with STATE_LOCK:
            STATE["nfcorpus"].update({"registry": registry[0], "error": None})
        # Warm the exact NFCorpus prebuilt index with an Anserini search, which downloads only this small index.
        warm = run_live_search("vitamin d", hits=3)
        if not warm["results"]:
            raise RuntimeError("NFCorpus warmup search returned no Anserini candidates")
        index_cache_root = HOME_DIR / ".cache" / "pyserini" / "indexes"
        record_artifact("cache-directory", index_cache_root, "Anserini/Pyserini prebuilt-index cache root pinned to the app data directory")
        for index_path in sorted(index_cache_root.glob("lucene-inverted.beir-v1.0.0-nfcorpus.flat*")):
            record_artifact("nfcorpus-index-cache", index_path, "Cached NFCorpus-only prebuilt Lucene index used by live search and BM25 evaluation")
        with STATE_LOCK:
            STATE["nfcorpus"].update({"ready": True, "indexReady": True})
            STATE["search"].update({"available": True, "error": None})

        update_state(["app"], "running startup evaluation")
        if os.environ.get("SKIP_STARTUP_EVAL", "0") != "1":
            run_evaluation("startup-cache-refresh")
        update_state(["app"], "ready")
    except Exception as exc:
        append_error(str(exc))
        with STATE_LOCK:
            STATE["app"] = "error"
            if not STATE["anserini"].get("available"):
                STATE["anserini"]["error"] = str(exc)
            elif not STATE["reproduction"].get("ready"):
                STATE["reproduction"]["error"] = str(exc)
            elif not STATE["nfcorpus"].get("ready"):
                STATE["nfcorpus"]["error"] = str(exc)


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>NFCorpus Live Retrieval Diagnostics Workbench</title>
  <style>
    :root{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#18212f;background:#f5f7fb}body{margin:0}.wrap{max-width:1200px;margin:0 auto;padding:28px}header{display:flex;justify-content:space-between;gap:16px;align-items:start}h1{margin:0 0 6px;font-size:30px}.sub{color:#526072}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:18px}.card{background:white;border:1px solid #dfe5ee;border-radius:16px;padding:18px;box-shadow:0 8px 22px rgba(29,48,73,.06)}.wide{grid-column:1/-1}.status{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;font-weight:700;font-size:13px}.ok{background:#e8f8ef;color:#106b35}.bad{background:#fdebea;color:#9b1c18}.wait{background:#fff6dd;color:#806000}.kv{display:grid;grid-template-columns:180px 1fr;gap:8px;margin-top:12px}.kv div:nth-child(odd){font-weight:700;color:#374357}.queryrow{display:flex;gap:8px}input{flex:1;padding:12px 14px;border:1px solid #cbd5e1;border-radius:10px;font-size:16px}button{border:0;background:#2457d6;color:white;padding:11px 14px;border-radius:10px;font-weight:700;cursor:pointer}button.secondary{background:#edf2ff;color:#24489b}.samples{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.result{border-top:1px solid #e7ecf3;padding:12px 0}.rank{font-weight:800;color:#24489b}.score{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#eef3ff;border-radius:6px;padding:2px 6px}.docid{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.snippet{color:#3d4a5c;margin-top:6px}.metric{display:grid;grid-template-columns:120px 100px 100px 100px 90px;gap:10px;align-items:center;border-top:1px solid #e7ecf3;padding:10px 0}.metric b{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}pre{white-space:pre-wrap;word-break:break-word;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px;max-height:360px;overflow:auto}.muted{color:#64748b}.err{color:#a32922;font-weight:700}.artifact{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;background:#f3f6fa;border-radius:8px;padding:8px;margin:6px 0}.small{font-size:13px}@media (max-width:850px){.grid{grid-template-columns:1fr}.kv{grid-template-columns:1fr}.metric{grid-template-columns:1fr 1fr}}
  </style>
</head>
<body><div class="wrap">
<header><div><h1>NFCorpus Live Retrieval Diagnostics Workbench</h1><div class="sub">Real Anserini-backed BM25 search and evaluation for one dataset only: <b>NFCorpus</b>.</div></div><span id="appStatus" class="status wait">loading</span></header>
<section class="grid">
  <div class="card" id="readiness"><h2>Readiness / Health</h2><div id="healthRows" class="kv"></div></div>
  <div class="card"><h2>Dataset Scope & Render Contract</h2><p><b>Active dataset:</b> NFCorpus (<span class="docid">beir-v1.0.0-nfcorpus.flat</span>)</p><p class="small">No full-BEIR, MS MARCO, dense-vector, or all-corpus downloads are used. Runtime caches live under the documented data directory and Anserini uses that as <span class="docid">HOME</span>.</p><p class="small"><b>Docker/Render:</b> bind <span class="docid">0.0.0.0</span> and read <span class="docid">PORT</span>, default <span class="docid">10000</span>. Health JSON is at <span class="docid">/health</span>.</p></div>
  <div class="card wide"><h2>Live NFCorpus Search</h2><div class="queryrow"><input id="query" placeholder="Try: vitamin d" /><button onclick="search()">Search with Anserini</button></div><div id="samples" class="samples"></div><p id="searchMeta" class="muted small"></p><div id="results"></div></div>
  <div class="card wide"><h2>BM25 Evaluation</h2><p class="muted">SearchCollection writes a TREC run file, then Anserini trec_eval evaluates it against the NFCorpus qrels key discovered from reproduction config.</p><button onclick="rerunEval()">Verify / Rerun evaluation</button><span id="evalState" class="muted small"></span><div id="metrics"></div><div id="evalArtifacts"></div></div>
  <div class="card wide"><h2>Command & Artifact Drawer</h2><p class="muted small">Exact commands, stdout/stderr previews, run files, qrels/eval keys, and cache paths. Search/evaluation rows are generated by Anserini commands, not mocked.</p><details open><summary>Reproduction discovery and NFCorpus dry-run excerpts</summary><pre id="repro"></pre></details><details open><summary>Commands</summary><div id="commands"></div></details><details><summary>Artifacts</summary><div id="artifacts"></div></details><details><summary>Errors</summary><pre id="errors"></pre></details></div>
</section></div>
<script>
let status = null;
const cls = v => v ? 'status ok' : 'status bad';
function esc(s){return String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function statusPill(text, ok){return `<span class="${ok?'status ok':'status wait'}">${esc(text)}</span>`}
async function loadStatus(){
  const r = await fetch('/api/status'); status = await r.json(); renderStatus(status); return status;
}
function renderStatus(s){
  const app = document.getElementById('appStatus'); app.textContent = s.app; app.className = s.app==='ready'?'status ok':(s.app==='error'?'status bad':'status wait');
  document.getElementById('healthRows').innerHTML = `
    <div>App status</div><div>${esc(s.app)}</div>
    <div>Anserini setup status</div><div>${statusPill(s.anserini.available?'available':'not ready', s.anserini.available)} ${esc(s.anserini.version||s.anserini.error||'')}</div>
    <div>Java / fatjar</div><div>${esc(s.anserini.java||'pending')}<br><span class="docid">${esc(s.anserini.jar||'pending')}</span></div>
    <div>NFCorpus readiness</div><div>${statusPill(s.nfcorpus.ready?'ready':'not ready', s.nfcorpus.ready)} index: <span class="docid">${esc(s.index)}</span></div>
    <div>Reproduction discovery</div><div>${statusPill(s.reproduction.ready?'ready':'not ready', s.reproduction.ready)} eval key: <span class="docid">${esc(s.reproduction.evalKey||'pending')}</span></div>
    <div>Search available</div><div>${statusPill(s.search.available?'available':'not ready', s.search.available)}</div>
    <div>Evaluation available</div><div>${statusPill(s.evaluation.available?'available':'not ready', s.evaluation.available)} ${s.evaluation.running?'running…':''}</div>
    <div>Cache/data directory</div><div><span class="docid">${esc(s.cacheRoot)}</span></div>`;
  document.getElementById('samples').innerHTML = (s.sampleQueries||[]).map(q=>`<button class="secondary" onclick="choose('${esc(q)}')">${esc(q)}</button>`).join('');
  renderEvaluation(s.evaluation.last, s.evaluation.running, s.evaluation.error);
  document.getElementById('repro').textContent = JSON.stringify({config:s.config, expected:s.reproduction.expected, metricDefinitions:s.reproduction.metricDefinitions, nfcorpusDryRun:s.reproduction.dryRunNfcorpus, commandTemplate:s.reproduction.commandTemplate}, null, 2);
  renderCommands(s.commands||[]); renderArtifacts(s.artifacts||[]); document.getElementById('errors').textContent = JSON.stringify(s.errors||[], null, 2);
  if(s.search.last) renderResults(s.search.last);
}
function renderCommands(commands){
  document.getElementById('commands').innerHTML = commands.slice().reverse().map(c=>`<details><summary><b>${esc(c.stage)}</b> exit ${esc(c.exitCode)} (${Number(c.elapsedSeconds||0).toFixed(2)}s)</summary><pre>${esc(c.command)}\n\n# stdout: ${esc(c.stdoutPath)}\n${esc(c.stdoutPreview||'')}\n\n# stderr: ${esc(c.stderrPath)}\n${esc(c.stderrPreview||'')}</pre></details>`).join('');
}
function renderArtifacts(arts){
  document.getElementById('artifacts').innerHTML = arts.slice().reverse().map(a=>`<div class="artifact"><b>${esc(a.kind)}</b> ${esc(a.path)} (${esc(a.sizeBytes||0)} bytes)<br>${esc(a.description)}${a.preview?`<pre>${esc(a.preview)}</pre>`:''}</div>`).join('');
}
function choose(q){document.getElementById('query').value=q; search();}
async function search(){
  const q = document.getElementById('query').value || 'vitamin d'; document.getElementById('searchMeta').textContent='Running Anserini CLI search…';
  const r = await fetch('/api/search?q='+encodeURIComponent(q)); const data = await r.json();
  if(!r.ok){document.getElementById('searchMeta').innerHTML='<span class="err">'+esc(data.error)+'</span>'; return;}
  renderResults(data); document.getElementById('searchMeta').textContent = `Backed by ${data.backedBy}; command visible in drawer.`; await loadStatus();
}
function renderResults(data){
  document.getElementById('results').innerHTML = (data.results||[]).map(x=>`<div class="result"><span class="rank">#${esc(x.rank)}</span> <span class="docid">${esc(x.docid)}</span> <span class="score">score ${esc(x.score)}</span><h3>${esc(x.title)}</h3><div class="snippet">${esc(x.snippet)}</div></div>`).join('') || '<p class="muted">No results.</p>';
}
async function rerunEval(){
  document.getElementById('evalState').textContent=' Running Anserini BM25 evaluation…';
  const r = await fetch('/api/evaluate',{method:'POST'}); const data = await r.json();
  if(!r.ok){document.getElementById('evalState').innerHTML='<span class="err"> '+esc(data.error)+'</span>'; return;}
  renderEvaluation(data, false, null); await loadStatus();
}
function renderEvaluation(ev, running, error){
  document.getElementById('evalState').textContent = running ? ' Running…' : (error ? ' Error: '+error : (ev ? ` ${ev.source}; ${Number(ev.elapsedSeconds||0).toFixed(2)}s` : ' waiting for startup evaluation'));
  if(!ev){document.getElementById('metrics').innerHTML=''; return;}
  document.getElementById('metrics').innerHTML = `<div class="metric"><b>metric</b><b>observed</b><b>expected</b><b>delta</b><b>status</b></div>` + (ev.comparisons||[]).map(m=>`<div class="metric"><span>${esc(m.metric)}</span><b>${esc(m.observed)}</b><span>${esc(m.expected)}</span><span>${m.delta===null?'n/a':Number(m.delta).toExponential(2)}</span><span class="${m.status==='pass'?'status ok':(m.status==='close'?'status wait':'status bad')}">${esc(m.status)}</span></div>`).join('');
  document.getElementById('evalArtifacts').innerHTML = `<p class="small"><b>Run file:</b> <span class="docid">${esc(ev.runFile)}</span><br><b>Evaluation output:</b> <span class="docid">${esc(ev.evalFile)}</span><br><b>Eval/qrels key:</b> <span class="docid">${esc(ev.evalKey)}</span></p>`;
}
(async()=>{document.getElementById('query').value='vitamin d'; await loadStatus(); setInterval(loadStatus, 4000);})();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "NFCorpusWorkbench/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self) -> None:
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/":
                return self.send_html()
            if parsed.path == "/health":
                s = snapshot()
                return self.send_json({
                    "status": s["app"],
                    "anseriniAvailable": s["anserini"]["available"],
                    "nfcorpusReady": s["nfcorpus"]["ready"],
                    "searchAvailable": s["search"]["available"],
                    "evaluationAvailable": s["evaluation"]["available"],
                    "dataset": s["dataset"],
                    "errors": s["errors"][-3:],
                })
            if parsed.path == "/api/status":
                return self.send_json(snapshot())
            if parsed.path == "/api/search":
                s = snapshot()
                if not s["search"]["available"]:
                    return self.send_json({"error": s["search"].get("error") or "Search is not available yet; Anserini/NFCorpus setup is still running."}, 503)
                params = urllib.parse.parse_qs(parsed.query)
                query = params.get("q", [""])[0]
                hits = int(params.get("hits", ["10"])[0])
                return self.send_json(run_live_search(query, min(max(hits, 1), 50)))
            return self.send_json({"error": "not found"}, 404)
        except Exception as exc:
            append_error(str(exc))
            return self.send_json({"error": str(exc)}, 500)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/evaluate":
                s = snapshot()
                if not s["nfcorpus"]["ready"] or not s["reproduction"]["ready"]:
                    return self.send_json({"error": "Evaluation is not ready; setup has not completed."}, 503)
                return self.send_json(run_evaluation("browser-rerun"))
            return self.send_json({"error": "not found"}, 404)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, 500)


def main() -> None:
    setup = threading.Thread(target=setup_workflow, name="anserini-setup", daemon=True)
    setup.start()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"NFCorpus workbench listening on http://{HOST}:{PORT}; cache={DATA_ROOT}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
