"""Startup orchestration for the NFCorpus diagnostics workbench.

`run_setup(state)` drives the full real-Anserini setup pipeline:

1. Verify Java + fatjar runtime checks (install-anserini-fatjar skill).
2. Confirm the NFCorpus prebuilt index is registered (anserini-cli skill).
3. Discover the NFCorpus reproduction target via ReproduceFromPrebuiltIndexes
   (anserini-reproduction skill).
4. Run BM25 SearchCollection over the NFCorpus topics.
5. Run TrecEval and compare observed vs expected nDCG@10.

It mutates the supplied `state` dict so the Flask layer can stream phase
updates and any captured commands/logs into the dashboard.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Optional

from . import anserini


def _log(state: Dict[str, Any], message: str) -> None:
    state.setdefault("log", []).append(
        {"ts": round(time.time(), 3), "msg": message}
    )


def _record(state: Dict[str, Any], key: str, value: Any) -> None:
    state["commands"][key] = value


def initial_state(cache_dir: str) -> Dict[str, Any]:
    return {
        "phase": "starting",
        "started_at": time.time(),
        "finished_at": None,
        "ok": False,
        "errors": [],
        "log": [],
        "commands": {},
        "fatjar": {
            "path": os.environ.get("ANSERINI_JAR"),
            "exists": False,
            "verified": False,
        },
        "java": {"available": False, "major": None},
        "reproduction": {
            "config": anserini.REPRODUCE_CONFIG,
            "condition": anserini.REPRODUCE_CONDITION,
            "target": None,
            "available": False,
        },
        "nfcorpus": {
            "index": anserini.NFCORPUS_INDEX,
            "topics": anserini.NFCORPUS_TOPICS,
            "qrels": anserini.NFCORPUS_QRELS,
            "registry_entry": None,
            "ready": False,
        },
        "evaluation": {
            "ran": False,
            "fresh": False,
            "rerun_count": 0,
            "metrics": {},
            "comparison": [],
            "overall_status": "pending",
            "run_path": None,
            "eval_path": None,
            "elapsed_seconds": None,
            "ran_at": None,
        },
        "cache_dir": cache_dir,
    }


def _evaluate(
    state: Dict[str, Any],
    fresh: bool,
    threads: int = 4,
) -> None:
    cache_dir = state["cache_dir"]
    os.makedirs(cache_dir, exist_ok=True)
    run_path = os.path.join(cache_dir, "run.beir.bm25.nfcorpus.txt")
    eval_path = os.path.join(cache_dir, "eval.beir.bm25.nfcorpus.txt")

    # 1. SearchCollection -> TREC run file.
    state["phase"] = "searching"
    _log(state, f"Running SearchCollection (threads={threads}) over NFCorpus")
    search_result = anserini.search_collection(
        output_path=run_path,
        threads=threads,
    )
    _record(state, "search_collection", search_result)
    if search_result["returncode"] != 0 or not os.path.isfile(run_path):
        state["errors"].append("SearchCollection failed; see commands.search_collection")
        state["phase"] = "failed"
        return

    _log(state, f"Run file written ({search_result['run_file_lines']} lines)")

    # 2. TrecEval -> observed metrics.
    state["phase"] = "evaluating"
    metric_args = ["-m", "ndcg_cut.10"]
    target = state["reproduction"].get("target") or {}
    metric_defs = target.get("metric_definitions") or {}
    # The reproduction YAML gives metric definitions like "-c -m ndcg_cut.10".
    # We always pass `-c`, so strip duplicates and forward the rest.
    for raw in metric_defs.values():
        parts = (raw or "").split()
        if "-m" in parts:
            idx = parts.index("-m")
            if idx + 1 < len(parts):
                value = parts[idx + 1]
                if value not in metric_args:
                    metric_args.extend(["-m", value])
    eval_result = anserini.trec_eval(
        run_path=run_path,
        qrels_key=anserini.NFCORPUS_QRELS,
        metric_args=metric_args,
    )
    _record(state, "trec_eval", eval_result)
    # Persist a copy of the evaluation output next to the run file.
    try:
        with open(eval_path, "w") as fh:
            fh.write(eval_result.get("stdout") or "")
    except OSError:
        pass

    if eval_result["returncode"] != 0 or not eval_result["metrics"]:
        state["errors"].append("TrecEval failed or produced no parsed metrics")
        state["phase"] = "failed"
        return

    expected = (target.get("expected_scores") or {}) if target else {}
    comparison = anserini.compare_metrics(eval_result["metrics"], expected)
    overall = "match" if comparison and all(r["status"] == "match" for r in comparison) else (
        "close" if comparison and all(r["status"] in {"match", "close"} for r in comparison) else (
            "fail" if comparison else "no-expected"
        )
    )
    if not expected:
        overall = "observed-only"

    state["evaluation"] = {
        "ran": True,
        "fresh": fresh,
        "rerun_count": state["evaluation"].get("rerun_count", 0) + (1 if fresh else 0),
        "metrics": eval_result["metrics"],
        "comparison": comparison,
        "overall_status": overall,
        "run_path": run_path,
        "eval_path": eval_path,
        "elapsed_seconds": round(
            (search_result.get("elapsed_seconds") or 0)
            + (eval_result.get("elapsed_seconds") or 0),
            3,
        ),
        "ran_at": time.time(),
        "metric_args": metric_args,
    }
    _log(state, f"Evaluation finished (overall={overall})")


def run_setup(state: Dict[str, Any]) -> None:
    """Drive the full setup pipeline. Mutates `state` in place."""

    # Phase 1: Java.
    state["phase"] = "verifying-java"
    _log(state, "Checking Java runtime")
    jv = anserini.java_version()
    _record(state, "java_version", jv)
    state["java"]["available"] = jv["returncode"] == 0
    state["java"]["major"] = jv.get("major")
    if not state["java"]["available"]:
        state["errors"].append("Java not available on PATH")
        state["phase"] = "failed"
        return
    if state["java"]["major"] is not None and state["java"]["major"] < 21:
        state["errors"].append(
            f"Java major {state['java']['major']} detected; Anserini requires Java 21"
        )
        # We still continue -- the CACM smoke test path documented in
        # install-anserini-fatjar would fail later anyway, but on hosted
        # containers the Dockerfile pins JDK 21 so this branch is informational.

    # Phase 2: fatjar registry verification.
    state["phase"] = "verifying-fatjar"
    fatjar = state["fatjar"]
    fatjar["exists"] = bool(fatjar["path"]) and os.path.isfile(fatjar["path"])
    if not fatjar["exists"]:
        state["errors"].append(
            f"Anserini fatjar not found at ANSERINI_JAR={fatjar['path']}"
        )
        state["phase"] = "failed"
        return
    _log(state, f"Found fatjar at {fatjar['path']} ({os.path.getsize(fatjar['path'])} bytes)")
    reg = anserini.verify_fatjar_registry()
    _record(state, "verify_fatjar_registry", reg)
    if reg["returncode"] != 0 or not reg.get("entry"):
        state["errors"].append(
            "PrebuiltIndexRegistry did not return an entry for "
            f"{anserini.NFCORPUS_INDEX}"
        )
        state["phase"] = "failed"
        return
    fatjar["verified"] = True
    state["nfcorpus"]["registry_entry"] = reg["entry"]
    _log(state, f"NFCorpus index registered: {reg['entry'].get('filename')}")

    # Phase 3: reproduction discovery.
    state["phase"] = "discovering"
    _log(state, "Running ReproduceFromPrebuiltIndexes --show (skill: anserini-reproduction)")
    show = anserini.reproduce_show()
    _record(state, "reproduce_show", show)
    parsed = show.get("parsed")
    target: Optional[Dict[str, Any]] = None
    if parsed:
        target = anserini.extract_nfcorpus_target(parsed)
    state["reproduction"]["target"] = target
    state["reproduction"]["available"] = bool(target)
    if target:
        _log(
            state,
            f"Reproduction target found: condition={target['condition_name']}, "
            f"expected={target['expected_scores']}",
        )
    else:
        state["errors"].append("Reproduction discovery did not surface an NFCorpus target")

    # Dry-run capture (best-effort).
    _log(state, "Capturing reproduction --dry-run (exact commands)")
    dry = anserini.reproduce_dry_run()
    _record(state, "reproduce_dry_run", dry)
    nfcorpus_dry_lines: list = []
    if dry["returncode"] == 0:
        capture = False
        for line in (dry.get("stdout") or "").splitlines():
            if "topic_key: nfcorpus" in line:
                capture = True
                nfcorpus_dry_lines.append(line.strip())
                continue
            if capture:
                if line.startswith("  - topic_key:"):
                    break
                if line.strip():
                    nfcorpus_dry_lines.append(line.strip())
                if len(nfcorpus_dry_lines) > 12:
                    break
    state["reproduction"]["dry_run_excerpt"] = nfcorpus_dry_lines

    # Phase 4 + 5: Search + Eval (cached startup pass).
    _evaluate(state, fresh=False)
    if state["phase"] == "failed":
        return

    state["nfcorpus"]["ready"] = True
    state["phase"] = "ready"
    state["ok"] = True
    state["finished_at"] = time.time()
    _log(state, "Setup complete; live search and evaluation available")


def rerun_evaluation(state: Dict[str, Any], threads: int = 4) -> Dict[str, Any]:
    """Re-execute SearchCollection + TrecEval against the cached NFCorpus index.

    Distinct from the startup pass so the UI can label results as 'fresh rerun'.
    """
    if not state["fatjar"].get("verified"):
        return {"ok": False, "error": "Anserini fatjar has not been verified yet"}
    if not state["nfcorpus"].get("registry_entry"):
        return {"ok": False, "error": "NFCorpus prebuilt index not registered"}
    _log(state, "Manual rerun requested")
    state["phase"] = "rerunning"
    _evaluate(state, fresh=True, threads=threads)
    if state["phase"] != "failed":
        state["phase"] = "ready"
        state["ok"] = True
    return {
        "ok": state["phase"] != "failed",
        "evaluation": state["evaluation"],
        "errors": state["errors"],
    }


def start_background(state: Dict[str, Any]) -> threading.Thread:
    thread = threading.Thread(target=run_setup, args=(state,), daemon=True, name="anserini-setup")
    thread.start()
    return thread
