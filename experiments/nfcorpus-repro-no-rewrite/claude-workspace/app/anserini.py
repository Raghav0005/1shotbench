"""Anserini-backed setup, search, and evaluation logic.

This module is the single source of truth for command construction. It does
not mock results: it always shells out to the Anserini fatjar and returns the
exact commands it executed alongside the parsed output.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# NFCorpus reproduction constants - derived from
# `io.anserini.reproduce.ReproduceFromPrebuiltIndexes --config beir.core --show`
# (condition "flat": BM25, flat bag-of-words baseline).
NFCORPUS_INDEX = "beir-v1.0.0-nfcorpus.flat"
NFCORPUS_TOPICS = "beir-v1.0.0-nfcorpus.test"
NFCORPUS_QRELS = "beir-v1.0.0-nfcorpus.test"
REPRODUCTION_CONFIG = "beir.core"
REPRODUCTION_CONDITION = "flat"  # BM25, flat bag-of-words baseline
EXPECTED_METRICS = {
    # nDCG@10 is the metric Anserini's beir.core reproduction config tracks.
    "ndcg_cut_10": 0.3218,
}
# Additional metrics we record (no reproduction-expected value).
EXTRA_METRICS = ["map", "recall_100"]

DATA_DIR = Path(os.environ.get("NFCORPUS_DATA_DIR", "./data")).resolve()
RUNS_DIR = DATA_DIR / "runs"
LOGS_DIR = DATA_DIR / "logs"
INDEX_CACHE_DIR = DATA_DIR / ".cache" / "pyserini" / "indexes"

REST_HOST = "127.0.0.1"
REST_PORT = int(os.environ.get("ANSERINI_REST_PORT", "8081"))

# `subprocess` env to make pyserini index downloads land in DATA_DIR.
def _subprocess_env() -> dict:
    env = os.environ.copy()
    # Pyserini / Anserini's prebuilt index downloader honours HOME for the
    # ~/.cache/pyserini location.
    env["HOME"] = str(DATA_DIR)
    return env


# ---------------------------------------------------------------------------
# Command shells
# ---------------------------------------------------------------------------


def _java_base(extra_modules: bool = True) -> list[str]:
    jar = os.environ.get("ANSERINI_JAR")
    if not jar:
        raise RuntimeError("ANSERINI_JAR is not set")
    cmd = ["java", "-cp", jar, "-Xms256M", "-Xmx2G", "-Dslf4j.internal.verbosity=WARN"]
    if extra_modules:
        cmd += ["--add-modules", "jdk.incubator.vector"]
    return cmd


def search_collection_cmd(output_path: Path, threads: int = 2) -> list[str]:
    return _java_base() + [
        "io.anserini.search.SearchCollection",
        "-threads", str(threads),
        "-index", NFCORPUS_INDEX,
        "-topics", NFCORPUS_TOPICS,
        "-output", str(output_path),
        "-bm25",
        "-removeQuery",
    ]


def trec_eval_cmd(run_path: Path) -> list[str]:
    cmd = _java_base(extra_modules=False) + [
        "io.anserini.eval.TrecEval",
        "-c",
        "-m", "ndcg_cut.10",
        "-m", "map",
        "-m", "recall.100",
        NFCORPUS_QRELS,
        str(run_path),
    ]
    return cmd


def rest_server_cmd() -> list[str]:
    return _java_base() + [
        "io.anserini.api.RestServer",
        "--host", REST_HOST,
        "--port", str(REST_PORT),
    ]


def prebuilt_registry_cmd() -> list[str]:
    return _java_base(extra_modules=False) + [
        "io.anserini.cli.PrebuiltIndexRegistry",
        "--list", "--filter", f"^{NFCORPUS_INDEX}$",
    ]


def reproduce_show_cmd() -> list[str]:
    return _java_base(extra_modules=False) + [
        "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
        "--config", REPRODUCTION_CONFIG, "--show",
    ]


def reproduce_dry_run_cmd() -> list[str]:
    return _java_base(extra_modules=False) + [
        "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
        "--config", REPRODUCTION_CONFIG, "--dry-run",
    ]


def render_cmd(parts: list[str]) -> str:
    return " ".join(shlex.quote(p) for p in parts)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


@dataclass
class EvalResult:
    status: str = "pending"  # pending|running|ok|error
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    elapsed_seconds: Optional[float] = None
    run_file: Optional[str] = None
    eval_file: Optional[str] = None
    log_file: Optional[str] = None
    observed: dict = field(default_factory=dict)  # metric -> float
    expected: dict = field(default_factory=lambda: dict(EXPECTED_METRICS))
    comparisons: list = field(default_factory=list)
    fresh: bool = False  # True if the latest run was a manual rerun
    error: Optional[str] = None
    search_cmd: Optional[str] = None
    eval_cmd: Optional[str] = None


@dataclass
class Readiness:
    java_ok: bool = False
    java_version: Optional[str] = None
    jar_ok: bool = False
    jar_path: Optional[str] = None
    nfcorpus_index_ok: bool = False
    nfcorpus_index_path: Optional[str] = None
    reproduction_ok: bool = False
    reproduction_config: str = REPRODUCTION_CONFIG
    reproduction_condition: str = REPRODUCTION_CONDITION
    search_ok: bool = False
    eval_ok: bool = False
    rest_url: Optional[str] = None
    errors: list = field(default_factory=list)
    setup_log: Optional[str] = None


# A simple in-process orchestrator.
class AnseriniWorkbench:
    def __init__(self) -> None:
        self.readiness = Readiness()
        self.eval = EvalResult()
        self.commands: dict[str, str] = {}
        self.artifacts: dict[str, str] = {}
        self.previews: dict[str, str] = {}
        self.rest_proc: Optional[subprocess.Popen] = None
        self.dataset = "nfcorpus"
        self._eval_lock = threading.Lock()
        self._eval_thread: Optional[threading.Thread] = None
        self._reproduction_text: Optional[str] = None
        self._init_log_lines: list[str] = []

    # -- logging helper --
    def _log(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        self._init_log_lines.append(line)
        print(line, flush=True)

    # -- setup --
    def initialize(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        INDEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        setup_log_path = LOGS_DIR / "setup.log"
        self.readiness.setup_log = str(setup_log_path)
        try:
            self._check_java()
            self._check_jar()
            self._discover_reproduction()
            self._ensure_nfcorpus_index()
            self._start_rest_server()
            self._kick_off_eval(initial=True)
        except Exception as exc:
            self._log(f"ERROR during init: {exc}")
            self.readiness.errors.append(str(exc))
        finally:
            try:
                setup_log_path.write_text("\n".join(self._init_log_lines) + "\n")
            except Exception:
                pass

    # ----- step 1: java -----
    def _check_java(self) -> None:
        if shutil.which("java") is None:
            raise RuntimeError("java not found on PATH")
        try:
            out = subprocess.run(
                ["java", "-version"], capture_output=True, text=True, check=True,
            )
            ver = (out.stderr or out.stdout).strip().splitlines()[0]
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"java -version failed: {exc.stderr}") from exc
        self.readiness.java_ok = True
        self.readiness.java_version = ver
        self._log(f"java: {ver}")

    # ----- step 2: jar -----
    def _check_jar(self) -> None:
        jar = os.environ.get("ANSERINI_JAR")
        if not jar:
            raise RuntimeError("ANSERINI_JAR environment variable is not set")
        if not Path(jar).is_file():
            raise RuntimeError(f"ANSERINI_JAR points to missing file: {jar}")
        self.readiness.jar_ok = True
        self.readiness.jar_path = jar
        self._log(f"fatjar: {jar}")

        # Functional check from install-anserini-fatjar skill: list the
        # prebuilt index registry filtered to NFCorpus. Acts as the smoke test.
        cmd = prebuilt_registry_cmd()
        self.commands["fatjar_verify"] = render_cmd(cmd)
        proc = subprocess.run(cmd, capture_output=True, text=True, env=_subprocess_env())
        if proc.returncode != 0:
            raise RuntimeError(
                f"fatjar verify (PrebuiltIndexRegistry) failed: {proc.stderr[:400]}"
            )
        self.previews["fatjar_verify"] = (proc.stdout or "").strip()[:4000]
        try:
            entries = json.loads(proc.stdout)
            if not entries:
                raise RuntimeError("PrebuiltIndexRegistry returned no entries")
            self._log(
                f"fatjar verify: PrebuiltIndexRegistry returned {len(entries)} entry/entries for filter ^{NFCORPUS_INDEX}$"
            )
        except json.JSONDecodeError:
            # Non-fatal but log it.
            self._log("fatjar verify: PrebuiltIndexRegistry output was not JSON")

    # ----- step 3: reproduction discovery -----
    def _discover_reproduction(self) -> None:
        cmd = reproduce_show_cmd()
        self.commands["reproduction_show"] = render_cmd(cmd)
        proc = subprocess.run(cmd, capture_output=True, text=True, env=_subprocess_env())
        if proc.returncode != 0:
            raise RuntimeError(
                f"ReproduceFromPrebuiltIndexes --show failed: {proc.stderr[:400]}"
            )
        text = proc.stdout
        self._reproduction_text = text
        # Persist a slice we know contains NFCorpus.
        slice_text = self._extract_nfcorpus_slice(text)
        self.previews["reproduction_show"] = slice_text[:4000]
        if "nfcorpus" in text.lower() and "0.3218" in text:
            self.readiness.reproduction_ok = True
            self._log(
                f"reproduction discovery ok: {REPRODUCTION_CONFIG}/{REPRODUCTION_CONDITION} → nfcorpus nDCG@10 expected 0.3218"
            )
        else:
            self.readiness.errors.append(
                "reproduction config did not advertise NFCorpus expected nDCG@10"
            )

    @staticmethod
    def _extract_nfcorpus_slice(text: str) -> str:
        # Pull a context window around the "flat" condition's nfcorpus block.
        lines = text.splitlines()
        out: list[str] = []
        for i, line in enumerate(lines):
            if "topic_key: nfcorpus" in line.lower():
                lo = max(0, i - 2)
                hi = min(len(lines), i + 8)
                out.append("\n".join(lines[lo:hi]))
                out.append("---")
                if len(out) > 6:
                    break
        return "\n".join(out) if out else text[:2000]

    # ----- step 4: index -----
    def _ensure_nfcorpus_index(self) -> None:
        """Triggers a 1-query Search to force the NFCorpus prebuilt index to download.

        Anserini's PrebuiltIndexHandler caches the resolved index path under
        $HOME/.cache/pyserini/indexes. After this returns, the live search and
        the evaluation will reuse the same cached index.
        """
        out_file = RUNS_DIR / "warmup.json"
        cmd = _java_base() + [
            "io.anserini.cli.Search",
            "--index", NFCORPUS_INDEX,
            "--query", "diabetes",
            "--hits", "1",
            "--json",
        ]
        self.commands["index_warmup"] = render_cmd(cmd)
        self._log("ensuring NFCorpus index (will download if absent, ~6 MB)…")
        proc = subprocess.run(cmd, capture_output=True, text=True, env=_subprocess_env())
        if proc.returncode != 0:
            raise RuntimeError(f"NFCorpus index warmup failed: {proc.stderr[:400]}")
        try:
            out_file.write_text(proc.stdout)
        except Exception:
            pass
        # Locate cached index directory. The prebuilt downloader uses
        # $HOME/.cache/pyserini/indexes; we redirect HOME to DATA_DIR inside
        # the subprocess, but a pre-existing host cache may have been reused,
        # so check both paths and parse the warmup log as a final fallback.
        search_dirs = [INDEX_CACHE_DIR,
                       Path.home() / ".cache" / "pyserini" / "indexes"]
        found: Optional[Path] = None
        for d in search_dirs:
            cands = list(d.glob(f"lucene-inverted.{NFCORPUS_INDEX}.*"))
            if cands:
                found = cands[0]
                break
        if not found:
            m = re.search(
                rf"(/\S*lucene-inverted\.{re.escape(NFCORPUS_INDEX)}\.[^\s/]+)",
                proc.stderr or "",
            )
            if m:
                found = Path(m.group(1))
        if found:
            self.readiness.nfcorpus_index_path = str(found)
        else:
            self.readiness.nfcorpus_index_path = (
                f"<resolved internally to prebuilt index name '{NFCORPUS_INDEX}'>"
            )
        self.readiness.nfcorpus_index_ok = True
        self.artifacts["nfcorpus_index"] = self.readiness.nfcorpus_index_path or ""
        self.artifacts["index_warmup"] = str(out_file)
        self.previews["index_warmup"] = (proc.stdout or "")[:1200]
        self._log(f"NFCorpus index ready at: {self.readiness.nfcorpus_index_path}")

    # ----- step 5: REST server for live search -----
    def _start_rest_server(self) -> None:
        cmd = rest_server_cmd()
        self.commands["rest_server"] = render_cmd(cmd)
        log_path = LOGS_DIR / "rest_server.log"
        self.artifacts["rest_server_log"] = str(log_path)
        log_fh = open(log_path, "w", buffering=1)
        self._log(f"starting Anserini RestServer: {render_cmd(cmd)}")
        self.rest_proc = subprocess.Popen(
            cmd, stdout=log_fh, stderr=subprocess.STDOUT, env=_subprocess_env()
        )
        # Wait up to ~25 s for the port to accept connections.
        deadline = time.time() + 25
        ok = False
        while time.time() < deadline:
            if self.rest_proc.poll() is not None:
                raise RuntimeError(
                    "Anserini RestServer exited; see rest_server.log"
                )
            try:
                with socket.create_connection((REST_HOST, REST_PORT), timeout=0.5):
                    ok = True
                    break
            except OSError:
                time.sleep(0.5)
        if not ok:
            raise RuntimeError(f"Anserini RestServer did not bind to {REST_HOST}:{REST_PORT}")
        # Issue a real search to confirm.
        url = f"http://{REST_HOST}:{REST_PORT}/v1/{NFCORPUS_INDEX}/search"
        self.readiness.rest_url = url
        try:
            r = httpx.get(url, params={"query": "diabetes", "hits": 1}, timeout=30)
            r.raise_for_status()
            self.previews["rest_smoke"] = r.text[:1200]
            self.readiness.search_ok = True
            self._log("RestServer smoke test ok")
        except Exception as exc:
            raise RuntimeError(f"RestServer search smoke test failed: {exc}") from exc

    # ----- step 6: evaluation -----
    def _kick_off_eval(self, initial: bool) -> None:
        with self._eval_lock:
            if self._eval_thread and self._eval_thread.is_alive():
                self._log("eval already running; skipping kick-off")
                return
            self.eval = EvalResult(
                status="running",
                started_at=time.time(),
                expected=dict(EXPECTED_METRICS),
                fresh=(not initial),
            )
            self._eval_thread = threading.Thread(
                target=self._run_eval, name="anserini-eval", daemon=True,
            )
            self._eval_thread.start()
            self._log("evaluation thread started")

    def _run_eval(self) -> None:
        run_path = RUNS_DIR / "run.nfcorpus.bm25.txt"
        eval_path = RUNS_DIR / "eval.nfcorpus.bm25.txt"
        log_path = LOGS_DIR / "eval.log"
        self.eval.run_file = str(run_path)
        self.eval.eval_file = str(eval_path)
        self.eval.log_file = str(log_path)
        self.artifacts["run_file"] = str(run_path)
        self.artifacts["eval_file"] = str(eval_path)
        self.artifacts["eval_log"] = str(log_path)

        search = search_collection_cmd(run_path)
        evalc = trec_eval_cmd(run_path)
        self.eval.search_cmd = render_cmd(search)
        self.eval.eval_cmd = render_cmd(evalc)
        self.commands["bm25_search"] = self.eval.search_cmd
        self.commands["bm25_eval"] = self.eval.eval_cmd

        try:
            with open(log_path, "w", buffering=1) as logf:
                logf.write(f"$ {self.eval.search_cmd}\n")
                logf.flush()
                s = subprocess.run(
                    search, env=_subprocess_env(),
                    stdout=logf, stderr=subprocess.STDOUT,
                )
                if s.returncode != 0:
                    raise RuntimeError(
                        f"SearchCollection exited with code {s.returncode}; see eval.log"
                    )
                logf.write(f"\n$ {self.eval.eval_cmd}\n")
                logf.flush()
                e = subprocess.run(
                    evalc, env=_subprocess_env(),
                    capture_output=True, text=True,
                )
                logf.write(e.stdout)
                if e.stderr:
                    logf.write(e.stderr)
                if e.returncode != 0:
                    raise RuntimeError(
                        f"TrecEval exited with code {e.returncode}: {e.stderr[:300]}"
                    )
            eval_text = e.stdout
            eval_path.write_text(eval_text)
            observed = self._parse_trec_eval(eval_text)
            self.eval.observed = observed
            self.eval.comparisons = self._compare(observed, EXPECTED_METRICS)
            self.eval.status = "ok"
            self.eval.completed_at = time.time()
            self.eval.elapsed_seconds = (
                self.eval.completed_at - (self.eval.started_at or self.eval.completed_at)
            )
            self.readiness.eval_ok = True
            self.previews["eval_output"] = eval_text[:2000]
            self._log(
                f"eval ok in {self.eval.elapsed_seconds:.2f}s: {observed}"
            )
        except Exception as exc:
            self.eval.status = "error"
            self.eval.error = str(exc)
            self.eval.completed_at = time.time()
            if self.eval.started_at:
                self.eval.elapsed_seconds = self.eval.completed_at - self.eval.started_at
            self._log(f"eval failed: {exc}")

    @staticmethod
    def _parse_trec_eval(text: str) -> dict:
        out: dict[str, float] = {}
        for line in text.splitlines():
            parts = re.split(r"\s+", line.strip())
            if len(parts) >= 3 and parts[1] == "all":
                metric = parts[0]
                try:
                    out[metric] = float(parts[2])
                except ValueError:
                    continue
        return out

    @staticmethod
    def _compare(observed: dict, expected: dict) -> list[dict]:
        # Anserini's own reproduce harness uses a 0.0005 absolute tolerance
        # for nDCG-style 4-decimal metrics. We follow the same convention.
        rows = []
        for metric, exp in expected.items():
            obs = observed.get(metric)
            if obs is None:
                rows.append({
                    "metric": metric, "expected": exp, "observed": None,
                    "delta": None, "status": "missing",
                })
                continue
            delta = obs - exp
            if abs(delta) < 1e-4:
                status = "match"
            elif abs(delta) <= 5e-4:
                status = "close"
            else:
                status = "fail"
            rows.append({
                "metric": metric, "expected": exp, "observed": obs,
                "delta": delta, "status": status,
            })
        return rows

    # -- public actions --
    def rerun_eval(self) -> None:
        self._kick_off_eval(initial=False)

    def live_search(self, query: str, hits: int = 10) -> dict:
        if not self.readiness.search_ok or not self.readiness.rest_url:
            raise RuntimeError("Live search is not available; Anserini RestServer not ready")
        url = self.readiness.rest_url
        t0 = time.time()
        r = httpx.get(url, params={"query": query, "hits": hits}, timeout=30)
        r.raise_for_status()
        elapsed = time.time() - t0
        data = r.json()
        candidates = data.get("candidates") or []
        results = []
        for i, c in enumerate(candidates, start=1):
            doc = c.get("doc") or {}
            title = doc.get("title") or ""
            text = doc.get("text") or ""
            snippet = text[:400] + ("…" if len(text) > 400 else "")
            results.append({
                "rank": c.get("rank", i),
                "docid": c.get("docid"),
                "score": c.get("score"),
                "title": title,
                "snippet": snippet,
            })
        return {
            "query": query,
            "elapsed_seconds": elapsed,
            "hits": len(results),
            "results": results,
            "rest_url": f"{url}?query={query}&hits={hits}",
            "command_equivalent": render_cmd(
                _java_base()
                + ["io.anserini.cli.Search", "--index", NFCORPUS_INDEX,
                   "--query", query, "--hits", str(hits), "--json"]
            ),
        }

    # -- snapshot --
    def snapshot(self) -> dict:
        return {
            "dataset": self.dataset,
            "readiness": asdict(self.readiness),
            "eval": asdict(self.eval),
            "commands": self.commands,
            "artifacts": self.artifacts,
            "previews": self.previews,
            "expected_metrics": EXPECTED_METRICS,
            "reproduction": {
                "config": REPRODUCTION_CONFIG,
                "condition": REPRODUCTION_CONDITION,
                "index": NFCORPUS_INDEX,
                "topics": NFCORPUS_TOPICS,
                "qrels": NFCORPUS_QRELS,
            },
        }

    def health(self) -> dict:
        return {
            "app": "ok",
            "anserini_available": self.readiness.jar_ok and self.readiness.java_ok,
            "nfcorpus_ready": self.readiness.nfcorpus_index_ok,
            "search_available": self.readiness.search_ok,
            "eval_available": self.readiness.eval_ok,
            "eval_status": self.eval.status,
            "errors": self.readiness.errors,
        }

    def shutdown(self) -> None:
        if self.rest_proc and self.rest_proc.poll() is None:
            try:
                self.rest_proc.terminate()
                self.rest_proc.wait(timeout=5)
            except Exception:
                try:
                    self.rest_proc.kill()
                except Exception:
                    pass
