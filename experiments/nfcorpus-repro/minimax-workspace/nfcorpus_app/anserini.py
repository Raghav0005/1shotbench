"""Thin wrapper around the Anserini fatjar for NFCorpus retrieval.

The wrappers here are deliberately small: each method invokes a single Anserini
main class via subprocess and parses the resulting stdout/stderr. The exact
command lines, output paths, and elapsed times are captured so the UI can
display them as part of the diagnostics contract.

All commands follow the conventions from the repo-local Anserini skills:

* `install-anserini-fatjar` -- runtime check + fatjar download + smoke test.
* `anserini-cli` -- PrebuiltIndexRegistry, TopicsRegistry, Search, REST.
* `anserini-reproduction` -- ReproduceFromPrebuiltIndexes for NFCorpus config
  discovery, `--show`/`--dry-run`/`--list`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import config


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class CommandResult:
    """The result of running a single Anserini CLI command."""

    command: str
    argv: list[str]
    cwd: str
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    output_paths: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "argv": self.argv,
            "cwd": self.cwd,
            "returncode": self.returncode,
            "stdout_excerpt": _excerpt(self.stdout),
            "stderr_excerpt": _excerpt(self.stderr),
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "output_paths": self.output_paths,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _excerpt(text: str, limit: int = 4000) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text) - limit} more chars]"


def _log_path(name: str) -> Path:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    return config.LOG_DIR / name


def _run_java(main_class: str, args: list[str], log_name: str,
              cwd: Optional[Path] = None) -> CommandResult:
    """Invoke `java -cp <jar> <main_class> <args>` and capture the result.

    The full command line, stdout, and stderr are persisted to the log
    directory so the UI can show them later.
    """
    if not config.ANSERINI_JAR.exists():
        raise FileNotFoundError(
            f"Anserini fatjar not found at {config.ANSERINI_JAR}. "
            "Run the fatjar download step (POST /api/setup/fatjar)."
        )

    java_bin = shutil.which("java")
    if not java_bin:
        raise FileNotFoundError("java executable not found on PATH")

    argv = [java_bin, "-cp", str(config.ANSERINI_JAR), main_class, *args]
    cmd_str = " ".join(_quote(a) for a in argv)

    cwd = str(cwd or config.PROJECT_ROOT)
    log_file = _log_path(log_name)

    start = time.time()
    with log_file.open("w") as logf:
        logf.write(f"# Command: {cmd_str}\n")
        logf.write(f"# cwd: {cwd}\n\n")
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:  # pragma: no cover - defensive
            elapsed = time.time() - start
            logf.write(f"\n# Exception: {exc!r}\n")
            return CommandResult(
                command=cmd_str,
                argv=argv,
                cwd=cwd,
                returncode=1,
                stdout="",
                stderr=str(exc),
                elapsed_seconds=elapsed,
            )
        elapsed = time.time() - start
        logf.write(f"# returncode: {proc.returncode}\n")
        logf.write(f"# elapsed: {elapsed:.3f}s\n\n")
        logf.write("# --- stdout ---\n")
        logf.write(proc.stdout or "")
        logf.write("\n# --- stderr ---\n")
        logf.write(proc.stderr or "")

    return CommandResult(
        command=cmd_str,
        argv=argv,
        cwd=cwd,
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        elapsed_seconds=elapsed,
    )


def _quote(token: str) -> str:
    if re.search(r"[\s'\"]", token):
        return "'" + token.replace("'", "'\\''") + "'"
    return token


# ---------------------------------------------------------------------------
# Fatjar discovery & download
# ---------------------------------------------------------------------------


def fatjar_status() -> dict:
    """Return a dict describing the local fatjar, if any."""
    path = config.ANSERINI_JAR
    if path.exists():
        try:
            size = path.stat().st_size
        except OSError:
            size = -1
        return {
            "available": True,
            "path": str(path),
            "size_bytes": size,
            "version": _detect_jar_version(path),
        }
    return {
        "available": False,
        "path": str(path),
        "size_bytes": None,
        "version": None,
    }


def _detect_jar_version(path: Path) -> Optional[str]:
    """Best-effort version extraction from the fatjar filename or MANIFEST."""
    match = re.search(r"anserini-([0-9][0-9A-Za-z\.\-]*)-fatjar\.jar", path.name)
    if match:
        return match.group(1)
    # Fall back to reading the manifest.
    try:
        with __import__("zipfile").ZipFile(path) as zf:
            data = zf.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.lower().startswith("implementation-version:"):
                return line.split(":", 1)[1].strip()
            if line.lower().startswith("specification-version:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        return None
    return None


def discover_latest_version() -> str:
    """Look up the latest published Anserini version on Maven Central.

    Mirrors the `install-anserini-fatjar` skill step 2.
    """
    url = "https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml"
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    release = root.findtext("release") or root.findtext("latest") or root.findtext("version")
    if not release:
        raise RuntimeError("Could not discover latest Anserini version on Maven Central")
    return release.strip()


def download_fatjar(version: Optional[str] = None) -> CommandResult:
    """Download the Anserini fatjar to ANSERINI_JAR.

    Uses `curl` if available, otherwise falls back to Python urllib.
    """
    if version is None:
        version = discover_latest_version()
    target = config.ANSERINI_JAR
    target.parent.mkdir(parents=True, exist_ok=True)
    url = (
        f"https://repo1.maven.org/maven2/io/anserini/anserini/"
        f"{version}/anserini-{version}-fatjar.jar"
    )
    curl = shutil.which("curl")
    if curl:
        argv = [curl, "-fL", "-o", str(target), url]
        cmd_str = " ".join(_quote(a) for a in argv)
        start = time.time()
        proc = subprocess.run(argv, capture_output=True, text=True, check=False)
        elapsed = time.time() - start
        log_file = _log_path("fatjar-download.log")
        with log_file.open("w") as f:
            f.write(f"# Command: {cmd_str}\n# elapsed: {elapsed:.3f}s\n")
            f.write(f"# returncode: {proc.returncode}\n")
            f.write(proc.stdout or "")
            f.write(proc.stderr or "")
        return CommandResult(
            command=cmd_str,
            argv=argv,
            cwd=str(config.PROJECT_ROOT),
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            elapsed_seconds=elapsed,
            output_paths=[str(target)] if target.exists() else [],
        )

    # Fallback: urllib download.
    cmd_str = f"urllib.request.urlretrieve({url!r}, {str(target)!r})"
    start = time.time()
    try:
        with urllib.request.urlopen(url, timeout=120) as resp, target.open("wb") as out:
            shutil.copyfileobj(resp, out)
        return_code = 0
        stderr = ""
    except Exception as exc:
        return_code = 1
        stderr = str(exc)
    elapsed = time.time() - start
    return CommandResult(
        command=cmd_str,
        argv=[],
        cwd=str(config.PROJECT_ROOT),
        returncode=return_code,
        stdout=f"Downloaded {url} -> {target}" if return_code == 0 else "",
        stderr=stderr,
        elapsed_seconds=elapsed,
        output_paths=[str(target)] if target.exists() else [],
    )


# ---------------------------------------------------------------------------
# Reproduction discovery
# ---------------------------------------------------------------------------


def reproduction_list() -> CommandResult:
    """`ReproduceFromPrebuiltIndexes --list` -- discover all reproduction configs."""
    return _run_java(
        "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
        ["--list"],
        "reproduction-list.log",
    )


def reproduction_show(config_name: str) -> CommandResult:
    """`ReproduceFromPrebuiltIndexes --config <name> --show`."""
    return _run_java(
        "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
        ["--config", config_name, "--show"],
        f"reproduction-show-{config_name}.log",
    )


def reproduction_dry_run(config_name: str) -> CommandResult:
    """`ReproduceFromPrebuiltIndexes --config <name> --dry-run`."""
    return _run_java(
        "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
        ["--config", config_name, "--dry-run"],
        f"reproduction-dryrun-{config_name}.log",
    )


def parse_nfcorpus_reproduction() -> dict:
    """Return the NFCorpus section of `beir.core --show` as structured data.

    Falls back to a hand-built descriptor (using the verified reproduction
    config) if JSON parsing fails, so that the readiness panel still has
    expected metrics to compare against.
    """
    cmd = reproduction_show(config.NFCORPUS_REPRODUCTION_CONFIG)
    expected: dict[str, float] = {}
    eval_key = None
    topics_name = None
    index_name = None
    raw_command = None
    if cmd.ok:
        data: Optional[dict] = None
        # `--show` emits YAML in the current fatjar. Try JSON first, then YAML.
        try:
            data = json.loads(cmd.stdout)
        except json.JSONDecodeError:
            try:
                import yaml
                data = yaml.safe_load(cmd.stdout)
            except Exception:
                data = None
        if data:
            for condition in data.get("conditions", []):
                if condition.get("name") == config.NFCORPUS_REPRODUCTION_CONDITION:
                    raw_command = condition.get("command")
                    for topic in condition.get("topics", []):
                        if topic.get("topic_key") == "nfcorpus":
                            topics_name = "beir-nfcorpus"
                            index_name = f"beir-v1.0.0-nfcorpus.{config.NFCORPUS_REPRODUCTION_CONDITION}"
                            eval_key = topic.get("eval_key")
                            expected = topic.get("expected_scores", {})
                            break
    return {
        "command": cmd.to_dict(),
        "reproduction_config": config.NFCORPUS_REPRODUCTION_CONFIG,
        "condition": config.NFCORPUS_REPRODUCTION_CONDITION,
        "raw_condition_command": raw_command,
        "topics": topics_name or config.NFCORPUS_TOPICS,
        "index": index_name or config.NFCORPUS_INDEX,
        "eval_key": eval_key or config.NFCORPUS_EVAL_KEY,
        "expected_scores": expected or {
            "nDCG@10": config.NFCORPUS_EXPECTED_NDCG10,
        },
    }


# ---------------------------------------------------------------------------
# Index readiness check
# ---------------------------------------------------------------------------


def index_status() -> dict:
    """Look for the NFCorpus prebuilt index in the local pyserini cache."""
    cache_root = Path(os.environ.get(
        "PYSERINI_CACHE",
        str(Path.home() / ".cache" / "pyserini" / "indexes"),
    ))
    matches: list[dict] = []
    if cache_root.exists():
        needle = config.NFCORPUS_INDEX
        for entry in cache_root.iterdir():
            if needle in entry.name and entry.is_dir():
                try:
                    size = sum(p.stat().st_size for p in entry.rglob("*") if p.is_file())
                except OSError:
                    size = -1
                matches.append({"path": str(entry), "size_bytes": size})
    return {
        "cache_root": str(cache_root),
        "expected_index": config.NFCORPUS_INDEX,
        "available": bool(matches),
        "entries": matches,
    }


# ---------------------------------------------------------------------------
# Live search
# ---------------------------------------------------------------------------


def live_search(query: str, hits: int = 10) -> CommandResult:
    """Issue a single-query BM25 search via `io.anserini.cli.Search --json`.

    The JSON output (returned on stdout) is consumed by the caller -- we do
    not parse it here so the UI can stream the raw payload to the browser.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")
    args = [
        "--index", config.NFCORPUS_INDEX,
        "--query", query,
        "--hits", str(hits),
        "--json",
    ]
    return _run_java(
        "io.anserini.cli.Search",
        args,
        "search.log",
    )


# ---------------------------------------------------------------------------
# BM25 evaluation
# ---------------------------------------------------------------------------


def batch_search(output_path: Path, hits: int = 1000, threads: int = 1) -> CommandResult:
    """Run `SearchCollection` over the full NFCorpus test topic set.

    Writes a TREC-format run file at `output_path` that the evaluator
    consumes in the next step.
    """
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        "-threads", str(threads),
        "-index", config.NFCORPUS_INDEX,
        "-topics", config.NFCORPUS_TOPICS,
        "-output", str(output_path),
        "-hits", str(hits),
        "-bm25",
        "-removeQuery",
    ]
    cmd = _run_java(
        "io.anserini.search.SearchCollection",
        args,
        "batch-search.log",
    )
    if output_path.exists():
        cmd.output_paths.append(str(output_path))
    return cmd


def evaluate_run(run_path: Path, output_path: Path) -> CommandResult:
    """Run `TrecEval` on a TREC run file and capture observed metrics."""
    config.EVAL_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        "-c",
        "-m", "ndcg_cut.10",
        "-m", "map",
        "-m", "P.10",
        "-m", "recall.10",
        config.NFCORPUS_EVAL_KEY,
        str(run_path),
    ]
    cmd = _run_java(
        "io.anserini.eval.TrecEval",
        args,
        "evaluate.log",
    )
    # Tee the eval output to a file the UI can show in the artifacts drawer.
    if cmd.ok:
        output_path.write_text(cmd.stdout)
        cmd.output_paths.append(str(output_path))
    return cmd


_METRIC_PATTERN = re.compile(r"^(\S+)\s+(\S+)\s+([0-9eE\.\-]+)\s*$")


def parse_eval_output(text: str) -> dict[str, dict[str, float]]:
    """Parse TrecEval stdout into `{metric: {measure: value}}` records."""
    out: dict[str, dict[str, float]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _METRIC_PATTERN.match(line)
        if not m:
            continue
        metric, measure, value = m.group(1), m.group(2), m.group(3)
        try:
            v = float(value)
        except ValueError:
            continue
        out.setdefault(metric, {})[measure] = v
    return out


def compare_metrics(observed: dict, expected: dict, rel_tol: float) -> dict:
    """Compare observed vs expected metric values and assign a verdict."""
    comparison: dict[str, dict] = {}
    for metric, expected_value in expected.items():
        obs = observed.get(metric, {})
        # Prefer the "all" measure; fall back to the first value.
        value = obs.get("all")
        if value is None and obs:
            value = next(iter(obs.values()))
        if value is None:
            comparison[metric] = {
                "expected": expected_value,
                "observed": None,
                "delta": None,
                "rel_delta": None,
                "verdict": "missing",
            }
            continue
        delta = value - expected_value
        rel = abs(delta) / expected_value if expected_value else None
        if abs(delta) < 1e-4:
            verdict = "match"
        elif rel is not None and rel <= rel_tol:
            verdict = "close"
        else:
            verdict = "fail"
        comparison[metric] = {
            "expected": expected_value,
            "observed": value,
            "delta": delta,
            "rel_delta": rel,
            "verdict": verdict,
        }
    return comparison


# ---------------------------------------------------------------------------
# End-to-end evaluation
# ---------------------------------------------------------------------------


def run_full_evaluation(force: bool = False) -> dict:
    """Run batch retrieval + evaluation, returning a structured result.

    Caches the run file and eval output so repeated requests are fast; the
    UI is responsible for distinguishing cached from fresh runs (it tracks
    `cached` in the response).
    """
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    config.EVAL_DIR.mkdir(parents=True, exist_ok=True)
    run_path = config.RUNS_DIR / "run.nfcorpus.bm25.txt"
    eval_path = config.EVAL_DIR / "eval.nfcorpus.bm25.txt"

    cached = run_path.exists() and eval_path.exists() and not force
    started_at = time.time()

    if cached:
        eval_text = eval_path.read_text()
        eval_cmd = CommandResult(
            command="cached: " + " ".join([
                "java -cp ANSERINI_JAR io.anserini.eval.TrecEval -c",
                "-m ndcg_cut.10 -m map -m P.10 -m recall.10",
                config.NFCORPUS_EVAL_KEY, str(run_path),
            ]),
            argv=[],
            cwd=str(config.PROJECT_ROOT),
            returncode=0,
            stdout=eval_text,
            stderr="",
            elapsed_seconds=0.0,
            output_paths=[str(run_path), str(eval_path)],
        )
    else:
        search_cmd = batch_search(run_path)
        if not search_cmd.ok:
            return {
                "ok": False,
                "stage": "search",
                "cached": False,
                "started_at": started_at,
                "elapsed_seconds": time.time() - started_at,
                "search": search_cmd.to_dict(),
                "evaluate": None,
                "observed": {},
                "expected": {},
                "comparison": {},
                "artifact_paths": [],
            }
        eval_cmd = evaluate_run(run_path, eval_path)
        if not eval_cmd.ok:
            return {
                "ok": False,
                "stage": "evaluate",
                "cached": False,
                "started_at": started_at,
                "elapsed_seconds": time.time() - started_at,
                "search": search_cmd.to_dict(),
                "evaluate": eval_cmd.to_dict(),
                "observed": {},
                "expected": {},
                "comparison": {},
                "artifact_paths": [str(run_path)],
            }

    observed = parse_eval_output(eval_cmd.stdout)
    repro = parse_nfcorpus_reproduction()
    expected = {
        name: float(value)
        for name, value in repro["expected_scores"].items()
    }
    comparison = compare_metrics(observed, expected, config.NFCORPUS_CLOSE_REL_TOL)

    # Overall verdict: fail if any metric fails; close if at least one is close; match if all match.
    verdicts = [c["verdict"] for c in comparison.values()]
    if not verdicts:
        overall = "unknown"
    elif any(v == "fail" for v in verdicts):
        overall = "fail"
    elif any(v == "close" for v in verdicts):
        overall = "close"
    elif any(v == "missing" for v in verdicts):
        overall = "missing"
    else:
        overall = "match"

    return {
        "ok": eval_cmd.ok,
        "stage": "complete" if eval_cmd.ok else "evaluate",
        "cached": cached,
        "started_at": started_at,
        "elapsed_seconds": time.time() - started_at,
        "search": None if cached else None,  # populated above when not cached
        "evaluate": eval_cmd.to_dict(),
        "observed": observed,
        "expected": expected,
        "comparison": comparison,
        "overall_verdict": overall,
        "artifact_paths": [str(p) for p in [run_path, eval_path] if p.exists()],
    }


def runtime_status() -> dict:
    """Aggregate readiness signals for the dashboard panel."""
    java = config.java_version()
    fatjar = fatjar_status()
    index = index_status()
    return {
        "java": java,
        "fatjar": fatjar,
        "index": index,
        "ready": all([
            java["available"] and java["supported"],
            fatjar["available"],
            index["available"],
        ]),
    }
