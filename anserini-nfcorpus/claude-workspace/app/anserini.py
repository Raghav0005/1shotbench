"""Thin subprocess wrappers around the Anserini fatjar.

All public functions return structured dicts so the Flask layer can show the
exact command that was executed, its stdout/stderr, exit code, and any parsed
result.  No retrieval or evaluation logic is mocked here -- every call shells
out to the real `java -cp $ANSERINI_JAR ...` command documented in the
`install-anserini-fatjar`, `anserini-cli`, and `anserini-reproduction` skills.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from typing import Any, Dict, List, Optional

import yaml


# Identifiers come straight from `ReproduceFromPrebuiltIndexes --config beir.core --show`.
NFCORPUS_INDEX = "beir-v1.0.0-nfcorpus.flat"
NFCORPUS_TOPICS = "beir-nfcorpus"
NFCORPUS_QRELS = "beir-v1.0.0-nfcorpus.test"
REPRODUCE_CONFIG = "beir.core"
REPRODUCE_CONDITION = "flat"  # BM25 flat bag-of-words baseline


def jar_path() -> str:
    path = os.environ.get("ANSERINI_JAR", "")
    if not path:
        raise RuntimeError("ANSERINI_JAR environment variable is not set")
    if not os.path.isfile(path):
        raise RuntimeError(f"ANSERINI_JAR points to a missing file: {path}")
    return path


def java_cmd(main_class: str, args: List[str]) -> List[str]:
    return ["java", "-cp", jar_path(), main_class, *args]


def _format_cmd(cmd: List[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def run(cmd: List[str], timeout: Optional[int] = None) -> Dict[str, Any]:
    """Run a subprocess and capture stdout/stderr and timing."""
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - start
        return {
            "cmd": _format_cmd(cmd),
            "argv": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "elapsed_seconds": round(elapsed, 3),
            "timeout": False,
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.time() - start
        return {
            "cmd": _format_cmd(cmd),
            "argv": cmd,
            "returncode": -1,
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + f"\n[timeout after {timeout}s]",
            "elapsed_seconds": round(elapsed, 3),
            "timeout": True,
        }


def java_version() -> Dict[str, Any]:
    result = run(["java", "-version"])
    # `java -version` prints to stderr on most JDKs.
    text = (result.get("stderr") or "") + (result.get("stdout") or "")
    major = None
    m = re.search(r'version "(\d+)', text)
    if m:
        try:
            major = int(m.group(1))
        except ValueError:
            major = None
    return {**result, "version_text": text.strip(), "major": major}


def verify_fatjar_registry() -> Dict[str, Any]:
    """Confirm the fatjar exposes the NFCorpus prebuilt index entry."""
    cmd = java_cmd(
        "io.anserini.cli.PrebuiltIndexRegistry",
        ["--list", "--filter", f"^{re.escape(NFCORPUS_INDEX)}$"],
    )
    result = run(cmd, timeout=120)
    entry: Optional[Dict[str, Any]] = None
    if result["returncode"] == 0:
        try:
            payload = json.loads(result["stdout"])
            if isinstance(payload, list) and payload:
                entry = payload[0]
        except json.JSONDecodeError:
            pass
    return {**result, "entry": entry}


def reproduce_show(config: str = REPRODUCE_CONFIG) -> Dict[str, Any]:
    """Capture the YAML for a reproduction config via `--show`."""
    cmd = java_cmd(
        "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
        ["--config", config, "--show"],
    )
    result = run(cmd, timeout=120)
    parsed: Optional[Dict[str, Any]] = None
    if result["returncode"] == 0:
        try:
            parsed = yaml.safe_load(result["stdout"])
        except yaml.YAMLError:
            parsed = None
    return {**result, "parsed": parsed}


def reproduce_dry_run(config: str = REPRODUCE_CONFIG) -> Dict[str, Any]:
    """Capture the dry-run output (exact commands per condition/topic)."""
    cmd = java_cmd(
        "io.anserini.reproduce.ReproduceFromPrebuiltIndexes",
        ["--config", config, "--dry-run"],
    )
    return run(cmd, timeout=180)


def extract_nfcorpus_target(reproduce_yaml: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Walk the parsed reproduction YAML and return the NFCorpus / flat target.

    Returns a dict with topic_key, eval_key, expected_scores, metric_definitions,
    and the condition's command template.
    """
    if not isinstance(reproduce_yaml, dict):
        return None
    for cond in reproduce_yaml.get("conditions") or []:
        if not isinstance(cond, dict):
            continue
        if cond.get("name") != REPRODUCE_CONDITION:
            continue
        for topic in cond.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            if topic.get("topic_key") == "nfcorpus":
                return {
                    "condition_name": cond.get("name"),
                    "condition_display": cond.get("display"),
                    "command_template": cond.get("command"),
                    "topic_key": topic.get("topic_key"),
                    "eval_key": topic.get("eval_key"),
                    "expected_scores": topic.get("expected_scores") or {},
                    "metric_definitions": topic.get("metric_definitions") or {},
                }
    return None


def search_collection(
    output_path: str,
    index: str = NFCORPUS_INDEX,
    topics: str = NFCORPUS_TOPICS,
    threads: int = 4,
    timeout: int = 600,
) -> Dict[str, Any]:
    """Run io.anserini.search.SearchCollection -> TREC run file."""
    cmd = java_cmd(
        "io.anserini.search.SearchCollection",
        [
            "-threads",
            str(threads),
            "-index",
            index,
            "-topics",
            topics,
            "-output",
            output_path,
            "-bm25",
            "-removeQuery",
        ],
    )
    result = run(cmd, timeout=timeout)
    lines = 0
    if os.path.isfile(output_path):
        with open(output_path) as fh:
            for _ in fh:
                lines += 1
    return {
        **result,
        "output_path": os.path.abspath(output_path),
        "run_file_lines": lines,
    }


_METRIC_LINE = re.compile(r"^(\S+)\s+(\S+)\s+([0-9.]+)\s*$")


def trec_eval(
    run_path: str,
    qrels_key: str = NFCORPUS_QRELS,
    metric_args: Optional[List[str]] = None,
    timeout: int = 300,
) -> Dict[str, Any]:
    """Invoke Anserini's Java TrecEval and parse out (metric, set, value) rows."""
    metric_args = metric_args or ["-m", "ndcg_cut.10"]
    cmd = java_cmd(
        "io.anserini.eval.TrecEval",
        ["-c", *metric_args, qrels_key, run_path],
    )
    result = run(cmd, timeout=timeout)
    metrics: Dict[str, float] = {}
    for line in (result["stdout"] or "").splitlines():
        m = _METRIC_LINE.match(line.strip())
        if not m:
            continue
        metric_name, set_name, value = m.group(1), m.group(2), m.group(3)
        if set_name != "all":
            continue
        try:
            metrics[metric_name] = float(value)
        except ValueError:
            continue
    return {**result, "metrics": metrics, "qrels_key": qrels_key, "run_path": os.path.abspath(run_path)}


# Map reproduction-YAML metric names (e.g. "nDCG@10") to trec_eval row keys.
METRIC_NAME_MAP = {
    "nDCG@10": "ndcg_cut_10",
    "NDCG@10": "ndcg_cut_10",
    "ndcg@10": "ndcg_cut_10",
}


def compare_metrics(
    observed: Dict[str, float],
    expected: Dict[str, float],
    tolerance: float = 5e-4,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for name, expected_value in (expected or {}).items():
        treckey = METRIC_NAME_MAP.get(name, name)
        observed_value = observed.get(treckey)
        if observed_value is None:
            # also accept exact-match metric name from observed map
            observed_value = observed.get(name)
        delta: Optional[float] = None
        status = "missing"
        if observed_value is not None:
            try:
                delta = round(float(observed_value) - float(expected_value), 6)
                if abs(delta) <= tolerance:
                    status = "match"
                elif abs(delta) <= max(tolerance * 10, 5e-3):
                    status = "close"
                else:
                    status = "fail"
            except (TypeError, ValueError):
                status = "missing"
        rows.append(
            {
                "metric": name,
                "trec_eval_key": treckey,
                "expected": expected_value,
                "observed": observed_value,
                "delta": delta,
                "status": status,
            }
        )
    return rows
