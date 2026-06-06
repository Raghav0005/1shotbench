"""Anserini environment bootstrap.

Follows the repo-local skills:
- install-anserini-fatjar:  download a Maven Central fatjar and verify Java 21.
- anserini-cli:             use PrebuiltIndexRegistry / SearchCollection / TrecEval
                            with `java -cp $ANSERINI_JAR`.
- anserini-reproduction:    use ReproduceFromPrebuiltIndexes --config beir.core
                            --show to discover NFCorpus index / topics / qrels /
                            expected metrics, then run SearchCollection +
                            TrecEval to compare observed vs expected.

The startup pass executes once at boot. A browser-triggered "Rerun" repeats the
SearchCollection + TrecEval steps against the cached index.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from .config import (
    ANSERINI_REST_PORT,
    ANSERINI_VERSION,
    CACHE_DIR,
    EVAL_KEY,
    EXPECTED_METRICS,
    FATJAR_PATH,
    INDEX_NAME,
    LOGS_DIR,
    REPRODUCTION_CONDITION,
    REPRODUCTION_CONFIG,
    RUNS_DIR,
    SAMPLE_QUERIES,
    TOPICS_KEY,
    cmd_for_display,
)
from .runner import run_command
from .state import STATE, EvaluationResult, MetricRow

_REST_PROC: subprocess.Popen | None = None


def _terminate_rest_proc() -> None:
    global _REST_PROC
    p = _REST_PROC
    if p is None:
        return
    if p.poll() is None:
        try:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        except Exception:
            pass
    _REST_PROC = None


atexit.register(_terminate_rest_proc)


def java_cmd(*args: str) -> list[str]:
    """Build a `java -cp $ANSERINI_JAR ...` command line per anserini-cli skill."""
    return [
        "java",
        "-Xms256M",
        "-Xmx1500M",
        "-Dslf4j.internal.verbosity=WARN",
        "--add-modules", "jdk.incubator.vector",
        "-cp", str(FATJAR_PATH),
        *args,
    ]


# ---------------------------------------------------------------------------
# Stage 1: verify Java runtime
# ---------------------------------------------------------------------------
def verify_java() -> bool:
    STATE.phase = "verifying-java"
    rec = run_command(["java", "-version"], label="verify java runtime")
    out = (rec.stderr_preview or "") + (rec.stdout_preview or "")
    m = re.search(r'version "(\d+)', out)
    if rec.exit_code == 0 and m and int(m.group(1)) >= 21:
        STATE.java.state = "ok"
        STATE.java.value = f"Java {m.group(1)} present"
        STATE.java.detail = out.strip().splitlines()[0] if out.strip() else "java -version OK"
        return True
    STATE.java.state = "error"
    STATE.java.value = "Missing or unsupported Java"
    STATE.java.detail = (out.strip() or "java -version failed").splitlines()[0]
    STATE.add_error("Java 21+ is required (per install-anserini-fatjar skill).")
    return False


# ---------------------------------------------------------------------------
# Stage 2: locate or download fatjar
# ---------------------------------------------------------------------------
def ensure_fatjar() -> bool:
    STATE.phase = "preparing-fatjar"
    STATE.anserini_version = ANSERINI_VERSION
    STATE.fatjar_path = str(FATJAR_PATH)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if FATJAR_PATH.exists() and FATJAR_PATH.stat().st_size > 50_000_000:
        STATE.fatjar.state = "ok"
        STATE.fatjar.value = f"anserini-{ANSERINI_VERSION}-fatjar.jar"
        STATE.fatjar.detail = f"{FATJAR_PATH.stat().st_size // (1024*1024)} MB at {FATJAR_PATH}"
        STATE.log(f"fatjar cached at {FATJAR_PATH}")
        return True

    url = (
        "https://repo1.maven.org/maven2/io/anserini/anserini/"
        f"{ANSERINI_VERSION}/anserini-{ANSERINI_VERSION}-fatjar.jar"
    )
    STATE.log(f"downloading {url}")
    rec = run_command(
        ["curl", "-fL", "-o", str(FATJAR_PATH), url],
        label="download anserini fatjar from Maven Central",
        timeout=600,
    )
    if rec.exit_code != 0 or not FATJAR_PATH.exists():
        STATE.fatjar.state = "error"
        STATE.fatjar.value = "download failed"
        STATE.fatjar.detail = rec.stderr_preview[-200:]
        STATE.add_error("Failed to download Anserini fatjar; check network egress.")
        return False
    STATE.fatjar.state = "ok"
    STATE.fatjar.value = f"anserini-{ANSERINI_VERSION}-fatjar.jar"
    STATE.fatjar.detail = f"{FATJAR_PATH.stat().st_size // (1024*1024)} MB at {FATJAR_PATH}"
    return True


# ---------------------------------------------------------------------------
# Stage 3: reproduction discovery (anserini-reproduction skill)
# ---------------------------------------------------------------------------
def discover_reproduction() -> bool:
    STATE.phase = "discovering-reproduction"
    rec = run_command(
        java_cmd(
            "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
            "--config", REPRODUCTION_CONFIG, "--show",
        ),
        label=f"reproduction config show ({REPRODUCTION_CONFIG})",
        timeout=120,
        full_stdout=True,
    )
    text = getattr(rec, "full_stdout", rec.stdout_preview) or ""
    if rec.exit_code != 0 or "nfcorpus" not in text:
        STATE.reproduction.state = "error"
        STATE.reproduction.value = "discovery failed"
        STATE.reproduction.detail = rec.stderr_preview[-200:] or "no nfcorpus entry"
        STATE.add_error("ReproduceFromPrebuiltIndexes --show did not return NFCorpus.")
        return False

    nfc_block = _slice_topic_block(text, "nfcorpus")
    expected: dict[str, dict] = {}
    if nfc_block:
        ndcg_match = re.search(r"nDCG@10:\s*([0-9.]+)", nfc_block)
        if ndcg_match:
            expected["nDCG@10"] = {
                "value": float(ndcg_match.group(1)),
                "trec_eval_args": EXPECTED_METRICS["nDCG@10"]["trec_eval_args"],
                "trec_eval_args_str": " ".join(EXPECTED_METRICS["nDCG@10"]["trec_eval_args"]),
                "source": f"{REPRODUCTION_CONFIG} / nfcorpus / {REPRODUCTION_CONDITION}",
            }
    if not expected:
        for name, meta in EXPECTED_METRICS.items():
            expected[name] = {
                "value": meta["value"],
                "trec_eval_args": meta["trec_eval_args"],
                "trec_eval_args_str": " ".join(meta["trec_eval_args"]),
                "source": "EXPECTED_METRICS fallback",
            }

    # Also issue --dry-run so the command line shown to the user is the exact
    # one the reproduction config emits for nfcorpus.
    run_command(
        java_cmd(
            "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
            "--config", REPRODUCTION_CONFIG, "--dry-run",
        ),
        label=f"reproduction dry-run ({REPRODUCTION_CONFIG})",
        timeout=120,
    )

    STATE.expected_metrics_raw = expected
    STATE.reproduction.state = "ok"
    STATE.reproduction.value = f"config={REPRODUCTION_CONFIG} condition={REPRODUCTION_CONDITION}"
    STATE.reproduction.detail = (
        f"topics={TOPICS_KEY}  qrels={EVAL_KEY}  "
        f"expected nDCG@10={expected.get('nDCG@10', {}).get('value', '?')}"
    )
    return True


def _slice_topic_block(text: str, topic_key: str) -> str:
    """Return the YAML snippet for one topic block from --show output."""
    m = re.search(rf"- topic_key:\s*{re.escape(topic_key)}\b", text)
    if not m:
        return ""
    start = m.start()
    nxt = re.search(r"\n      - topic_key:", text[start + 1 :])
    end = start + 1 + nxt.start() if nxt else len(text)
    return text[start:end]


# ---------------------------------------------------------------------------
# Stage 4: NFCorpus prebuilt index (priming via PrebuiltIndexRegistry filter)
# ---------------------------------------------------------------------------
def ensure_nfcorpus_index() -> bool:
    STATE.phase = "preparing-nfcorpus"
    rec = run_command(
        java_cmd(
            "io.anserini.cli.PrebuiltIndexRegistry",
            "--list", "--filter", f"^{re.escape(INDEX_NAME)}$",
        ),
        label="PrebuiltIndexRegistry lookup NFCorpus",
        timeout=120,
    )
    info = {}
    try:
        info = (json.loads(rec.stdout_preview) or [{}])[0]
    except Exception:
        info = {}
    STATE.index_path = info.get("name", INDEX_NAME)

    # The first SearchCollection call below will download the small (~7 MB)
    # NFCorpus prebuilt index to ~/.cache/pyserini/indexes if not yet cached.
    # We do this implicitly during the startup evaluation pass.
    STATE.nfcorpus.state = "ok"
    STATE.nfcorpus.value = INDEX_NAME
    docs = info.get("documents")
    size = info.get("size")
    detail_bits = []
    if docs:
        detail_bits.append(f"{docs} docs")
    if size:
        detail_bits.append(f"{int(size) // (1024 * 1024)} MB")
    detail_bits.append("prebuilt; auto-downloads on first search")
    STATE.nfcorpus.detail = " • ".join(detail_bits)
    return True


# ---------------------------------------------------------------------------
# Stage 5: BM25 evaluation pass (SearchCollection + TrecEval)
# ---------------------------------------------------------------------------
def run_bm25_evaluation(source_label: str) -> EvaluationResult:
    STATE.phase = "running-evaluation"
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    run_path = RUNS_DIR / f"run.{REPRODUCTION_CONFIG}.{REPRODUCTION_CONDITION}.nfcorpus.txt"
    eval_path = RUNS_DIR / f"eval.{REPRODUCTION_CONFIG}.{REPRODUCTION_CONDITION}.nfcorpus.txt"

    result = EvaluationResult(
        status="running",
        source=source_label,
        run_path=str(run_path),
        eval_path=str(eval_path),
        rerun_count=STATE.evaluation.rerun_count,
    )
    STATE.evaluation = result
    started = time.time()

    search_argv = java_cmd(
        "io.anserini.search.SearchCollection",
        "-threads", "2",
        "-index", INDEX_NAME,
        "-topics", TOPICS_KEY,
        "-output", str(run_path),
        "-bm25",
        "-removeQuery",
    )
    rec = run_command(search_argv, label="BM25 SearchCollection over NFCorpus", timeout=900)
    if rec.exit_code != 0 or not run_path.exists():
        result.status = "failed"
        result.error = f"SearchCollection exit={rec.exit_code}: {rec.stderr_preview[-300:]}"
        result.elapsed_seconds = time.time() - started
        STATE.evaluation_card.state = "error"
        STATE.evaluation_card.value = "SearchCollection failed"
        STATE.evaluation_card.detail = result.error[:200]
        STATE.add_error(result.error)
        return result

    # One TrecEval per expected metric.
    metrics: list[MetricRow] = []
    expected = STATE.expected_metrics_raw or EXPECTED_METRICS
    for name, meta in expected.items():
        args = meta["trec_eval_args"] if isinstance(meta, dict) else meta
        expected_value = meta["value"] if isinstance(meta, dict) else None
        eval_argv = java_cmd("io.anserini.eval.TrecEval", *args, EVAL_KEY, str(run_path))
        eval_rec = run_command(eval_argv, label=f"TrecEval {name}", timeout=120)
        observed = _parse_trec_eval_value(eval_rec.stdout_preview)
        eval_path.write_text(eval_rec.stdout_preview or "")
        if observed is None:
            metrics.append(MetricRow(
                name=name,
                trec_eval_args=" ".join(args),
                expected=expected_value,
                observed=None,
                delta=None,
                status="fail",
            ))
            continue
        delta = None if expected_value is None else round(observed - expected_value, 4)
        status = "match"
        if expected_value is not None:
            abs_d = abs(observed - expected_value)
            if abs_d <= 5e-5:
                status = "match"
            elif abs_d <= 5e-3:
                status = "close"
            else:
                status = "fail"
        metrics.append(MetricRow(
            name=name,
            trec_eval_args=" ".join(args),
            expected=expected_value,
            observed=round(observed, 4),
            delta=delta,
            status=status,
        ))

    result.metrics = metrics
    result.status = "done"
    result.elapsed_seconds = round(time.time() - started, 3)
    result.last_finished_at = time.time()

    # Overall card status.
    has_fail = any(m.status == "fail" for m in metrics)
    has_close = any(m.status == "close" for m in metrics)
    if has_fail:
        STATE.evaluation_card.state = "error"
        STATE.evaluation_card.value = "deviates from expected"
    elif has_close:
        STATE.evaluation_card.state = "warn"
        STATE.evaluation_card.value = "close to expected"
    else:
        STATE.evaluation_card.state = "ok"
        STATE.evaluation_card.value = "matches expected"
    primary = metrics[0] if metrics else None
    if primary is not None:
        STATE.evaluation_card.detail = (
            f"{primary.name} observed={primary.observed} expected={primary.expected} "
            f"Δ={primary.delta} in {result.elapsed_seconds}s"
        )
    return result


def _parse_trec_eval_value(text: str) -> float | None:
    if not text:
        return None
    for line in text.strip().splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "all":
            try:
                return float(parts[2])
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Stage 6: spawn Anserini REST server for live search
# ---------------------------------------------------------------------------
def start_rest_server() -> bool:
    global _REST_PROC
    STATE.phase = "starting-rest"
    if _port_in_use(ANSERINI_REST_PORT):
        STATE.search.state = "warn"
        STATE.search.value = "port busy; reusing existing REST server"
        STATE.search.detail = f"127.0.0.1:{ANSERINI_REST_PORT}"
        STATE.rest_url = f"http://127.0.0.1:{ANSERINI_REST_PORT}"
        return True
    log_path = LOGS_DIR / "anserini-rest.log"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    argv = java_cmd(
        "io.anserini.api.RestServer",
        "--host", "127.0.0.1",
        "--port", str(ANSERINI_REST_PORT),
    )
    STATE.log(f"spawning REST server: {cmd_for_display(argv)}")
    # Record the command line in commands so the UI exposes it.
    from .state import CommandRecord
    STATE.record_command(CommandRecord(
        label="Anserini REST server (background)",
        argv=argv,
        display=cmd_for_display(argv),
        cwd=str(Path.cwd()),
        exit_code=None,
        stdout_preview=f"-> logs piped to {log_path}",
        stderr_preview="",
        started_at=time.time(),
        finished_at=0.0,
    ))
    fh = open(log_path, "ab")
    _REST_PROC = subprocess.Popen(
        argv,
        stdout=fh,
        stderr=subprocess.STDOUT,
        cwd=str(CACHE_DIR),
    )
    if not _wait_for_port("127.0.0.1", ANSERINI_REST_PORT, timeout=60):
        STATE.search.state = "error"
        STATE.search.value = "REST server failed to bind"
        STATE.search.detail = f"see {log_path}"
        STATE.add_error("Anserini RestServer did not become reachable.")
        return False
    STATE.rest_url = f"http://127.0.0.1:{ANSERINI_REST_PORT}"
    STATE.search.state = "ok"
    STATE.search.value = "Anserini REST server ready"
    STATE.search.detail = f"{STATE.rest_url}/v1/{INDEX_NAME}/search"
    return True


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.4)
    return False


# ---------------------------------------------------------------------------
# Public entry point used by main.py at process startup
# ---------------------------------------------------------------------------
def bootstrap_in_background() -> None:
    """Schedule the full setup pipeline in a daemon thread."""
    STATE.sample_queries = list(SAMPLE_QUERIES)
    t = threading.Thread(target=_bootstrap_pipeline, name="workbench-bootstrap", daemon=True)
    t.start()


def _bootstrap_pipeline() -> None:
    try:
        if not verify_java():
            STATE.phase = "failed:java"
            return
        if not ensure_fatjar():
            STATE.phase = "failed:fatjar"
            return
        if not discover_reproduction():
            STATE.phase = "failed:reproduction"
            return
        if not ensure_nfcorpus_index():
            STATE.phase = "failed:nfcorpus"
            return
        STATE.phase = "running-initial-evaluation"
        STATE.evaluation_card.state = "pending"
        STATE.evaluation_card.value = "running…"
        result = run_bm25_evaluation(source_label="cached startup pass")
        if result.status != "done":
            STATE.phase = "failed:evaluation"
            return
        if not start_rest_server():
            STATE.phase = "failed:rest"
            return
        STATE.phase = "ready"
        STATE.log("workbench ready: live search + evaluation available.")
    except Exception as e:  # noqa: BLE001
        STATE.add_error(f"bootstrap crashed: {e!r}")
        STATE.phase = "failed:exception"


def trigger_rerun() -> EvaluationResult:
    """Run a fresh SearchCollection + TrecEval pass on demand."""
    STATE.evaluation.rerun_count = (STATE.evaluation.rerun_count or 0) + 1
    return run_bm25_evaluation(source_label=f"fresh rerun #{STATE.evaluation.rerun_count}")
