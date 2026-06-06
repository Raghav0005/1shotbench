"""Anserini Prebuilt Index Evaluator — Flask backend.

The server is intentionally thin: it shells out to the Anserini fatjar CLI
for every retrieval and evaluation, then exposes the resulting artifacts
through a small JSON API consumed by the browser UI. There is no in-memory
mocking of catalog, run, or evaluation data — every score the UI displays
comes from an actual ``io.anserini.search.SearchCollection`` /
``io.anserini.eval.TrecEval`` invocation, and every catalog entry is read
from ``io.anserini.cli.PrebuiltIndexRegistry`` /
``io.anserini.cli.TopicsRegistry`` at startup.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml  # PyYAML
from flask import Flask, abort, jsonify, request, send_from_directory

# ---------------------------------------------------------------------------
# Paths / environment
# ---------------------------------------------------------------------------

WORKSPACE = Path(__file__).resolve().parent.parent
APP_DIR = WORKSPACE / "app"
DATA_DIR = APP_DIR / "data"
RUNS_DIR = WORKSPACE / "runs"
EVALS_DIR = WORKSPACE / "evals"
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

DATA_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)
EVALS_DIR.mkdir(parents=True, exist_ok=True)

# Resolve the Anserini fatjar. The user installs it once at the workspace
# root following the ``install-anserini-fatjar`` skill; we never assume
# source checkouts here.
CANDIDATE_JARS = sorted(WORKSPACE.glob("anserini-*-fatjar.jar"))
if not CANDIDATE_JARS:
    print(
        "ERROR: no anserini-*-fatjar.jar found in the workspace. "
        "Install the fatjar first (see install-anserini-fatjar skill).",
        file=sys.stderr,
    )
    sys.exit(1)
ANSERINI_JAR = CANDIDATE_JARS[-1]
ANSERINI_VERSION = re.sub(
    r"^anserini-(.*)-fatjar\.jar$", r"\1", ANSERINI_JAR.name
)

# Allow runtime overrides for tests / CI.
ANSERINI_JAR = Path(os.environ.get("ANSERINI_JAR", ANSERINI_JAR))
DEFAULT_PORT = int(os.environ.get("PORT", "5555"))
DEFAULT_HOST = os.environ.get("HOST", "127.0.0.1")

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    template_folder=str(TEMPLATES_DIR),
)

# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def run_anserini(*args: str, timeout: int = 1800) -> Tuple[int, str, str]:
    """Run ``java -cp $ANSERINI_JAR <args>`` and capture stdout/stderr."""

    cmd = ["java", "-cp", str(ANSERINI_JAR), *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, "", f"java executable not found on PATH: {exc}"
    except subprocess.TimeoutExpired:
        return 124, "", f"command timed out after {timeout}s: {' '.join(cmd)}"
    return proc.returncode, proc.stdout, proc.stderr


def read_jar_resource(rel_path: str) -> Optional[bytes]:
    """Read a resource bundled inside the Anserini fatjar."""

    with __import__("zipfile").ZipFile(ANSERINI_JAR) as zf:
        try:
            return zf.read(rel_path)
        except KeyError:
            return None


# ---------------------------------------------------------------------------
# Catalog: prebuilt indexes & topics
# ---------------------------------------------------------------------------


@dataclass
class IndexEntry:
    name: str
    type: str
    description: str
    corpus_index: str
    documents: Optional[int]
    total_terms: Optional[int]
    size_bytes: Optional[int]
    readme: str


@dataclass
class TopicEntry:
    name: str


def load_inverted_indexes() -> List[IndexEntry]:
    """Invoke ``PrebuiltIndexRegistry --type inverted --list`` and parse."""

    code, out, err = run_anserini(
        "io.anserini.cli.PrebuiltIndexRegistry",
        "--type",
        "inverted",
        "--list",
        timeout=120,
    )
    if code != 0:
        raise RuntimeError(
            f"PrebuiltIndexRegistry failed (code={code}): {err.strip()}"
        )
    try:
        items = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"PrebuiltIndexRegistry returned non-JSON output: {exc}: {out[:200]}"
        ) from exc

    entries: List[IndexEntry] = []
    for item in items:
        try:
            entries.append(
                IndexEntry(
                    name=item["name"],
                    type=item.get("type", "inverted"),
                    description=item.get("description", ""),
                    corpus_index=item.get("corpus_index", item["name"]),
                    documents=item.get("documents"),
                    total_terms=item.get("total_terms"),
                    size_bytes=item.get("size"),
                    readme=item.get("readme", ""),
                )
            )
        except KeyError as exc:
            print(
                f"warning: skipping malformed index entry (missing {exc})",
                file=sys.stderr,
            )
    return entries


def load_topic_names() -> List[str]:
    """Invoke ``TopicsRegistry --list`` and parse."""

    code, out, err = run_anserini(
        "io.anserini.cli.TopicsRegistry", "--list", timeout=120
    )
    if code != 0:
        raise RuntimeError(f"TopicsRegistry failed (code={code}): {err.strip()}")
    try:
        names = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"TopicsRegistry returned non-JSON output: {exc}: {out[:200]}"
        ) from exc
    if not isinstance(names, list):
        raise RuntimeError("TopicsRegistry did not return a JSON array")
    return [str(n) for n in names]


# ---------------------------------------------------------------------------
# Evaluable pairings — extracted from the Anserini reproduction YAMLs
# ---------------------------------------------------------------------------


@dataclass
class Pairing:
    """An evaluable (index, topic, qrels, metric) configuration.

    These come from the YAML reproduction configs bundled inside the
    fatjar (``reproduce/from-prebuilt-indexes/configs/*.yaml``). We do not
    hardcode them — we extract them at startup, so updates to the fatjar
    are picked up automatically.
    """

    index: str
    topic_key: str
    eval_key: str
    metrics: Dict[str, Dict[str, Any]]  # metric_name -> {args, expected}
    display: str = ""
    command: str = ""


def load_pairings() -> List[Pairing]:
    """Read all YAML configs from the fatjar and extract known pairings."""

    pairings: List[Pairing] = []
    # First find which YAML resources are in the fatjar.
    with __import__("zipfile").ZipFile(ANSERINI_JAR) as zf:
        yaml_names = [
            n
            for n in zf.namelist()
            if n.startswith("reproduce/from-prebuilt-indexes/configs/")
            and n.endswith(".yaml")
        ]
        for name in yaml_names:
            try:
                raw = zf.read(name).decode("utf-8")
            except Exception as exc:  # noqa: BLE001
                print(f"warning: cannot read {name}: {exc}", file=sys.stderr)
                continue
            # Some reproduction YAMLs mix tabs and spaces inside the same
            # value (a known quirk of the upstream files). PyYAML rejects
            # the resulting mix, so normalise tabs to spaces before
            # parsing.
            raw = raw.replace("\t", "    ")
            try:
                cfg = yaml.safe_load(raw) or {}
            except yaml.YAMLError as exc:
                print(
                    f"warning: cannot parse {name}: {exc}", file=sys.stderr
                )
                continue
            extract_pairings_from_config(cfg, pairings)
    return pairings


def extract_pairings_from_config(cfg: Dict[str, Any], out: List[Pairing]) -> None:
    conditions = cfg.get("conditions") or []
    for cond in conditions:
        command = str(cond.get("command", ""))
        # Extract the literal ``-index <name>`` from the command.
        m = re.search(r"-index\s+(\S+)", command)
        if not m:
            continue
        index_name = m.group(1)
        # Some "optional" configs use ``$topics`` / ``$threads`` / etc.
        # placeholders inside the index name. Skip those — we only want
        # pairings that resolve to a single concrete prebuilt index.
        if "$" in index_name:
            continue
        display = str(cond.get("display", ""))
        for topic in cond.get("topics") or []:
            topic_key = str(topic.get("topic_key", ""))
            eval_key = str(topic.get("eval_key", ""))
            metrics_raw = topic.get("metric_definitions") or {}
            expected = topic.get("expected_scores") or {}
            metrics: Dict[str, Dict[str, Any]] = {}
            for name, args in metrics_raw.items():
                metrics[str(name)] = {
                    "args": str(args),
                    "expected": expected.get(name),
                }
            if not metrics:
                continue
            out.append(
                Pairing(
                    index=index_name,
                    topic_key=topic_key,
                    eval_key=eval_key,
                    metrics=metrics,
                    display=display,
                    command=command,
                )
            )


# ---------------------------------------------------------------------------
# Per-metric argument translation
# ---------------------------------------------------------------------------

# User-friendly labels -> ``trec_eval`` argument string. We add these
# regardless of whether they appear in the YAML for the chosen dataset;
# the request handler will validate them against the pairing.
TRANSLATABLE_METRICS: Dict[str, str] = {
    "nDCG@10": "-c -m ndcg_cut.10",
    "Recall@1000": "-c -m recall.1000",
    "MAP": "-c -m map",
    "P.30": "-c -m P.30",
    "MRR@10": "-c -M 10 -m recip_rank",
    "MRR@100": "-c -M 100 -m recip_rank",
    "AP@100": "-c -M 100 -m map",
}

# Friendly aliases that the Anserini reproduction YAMLs use but that
# should be exposed to the UI under a more conventional label. Keys are
# the YAML name, values are the user-facing label.
YAML_METRIC_ALIASES: Dict[str, str] = {
    "R@1K": "Recall@1000",
}


def normalize_metric_label(label: str) -> str:
    """Map a YAML metric name to a user-facing label."""

    return YAML_METRIC_ALIASES.get(label, label)


def _serialize_metrics(metrics: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Return a copy of ``metrics`` with user-facing labels."""

    out: Dict[str, Dict[str, Any]] = {}
    for name, payload in metrics.items():
        out[normalize_metric_label(name)] = payload
    return out


def _expected_score_for(pairing: Pairing, metric_label: str) -> Optional[float]:
    """Return the YAML-declared expected score for a given metric label.

    The label is the user-facing label (post-``normalize_metric_label``).
    Falls back to a reverse lookup against the raw YAML keys for
    backwards compatibility.
    """

    yaml_metrics = _serialize_metrics(pairing.metrics)
    if metric_label in yaml_metrics:
        return yaml_metrics[metric_label].get("expected")
    return pairing.metrics.get(metric_label, {}).get("expected")


def metrics_for_pairing(pairing: Pairing) -> List[Dict[str, Any]]:
    """Return the list of metric options the UI should show.

    The list always includes the modern metrics ``nDCG@10`` and
    ``Recall@1000`` (per the PRD), with the YAML-declared metrics as a
    fallback when the dataset does not support the modern ones. The list
    is de-duplicated by metric label.
    """

    yaml_metrics = _serialize_metrics(pairing.metrics)
    options: List[Dict[str, Any]] = []
    seen: set = set()
    for label, payload in yaml_metrics.items():
        options.append(
            {
                "label": label,
                "args": payload["args"],
                "expected": payload.get("expected"),
                "source": "yaml",
            }
        )
        seen.add(label)
    # Always offer the modern metrics; the user-facing label will be
    # the canonical one. We do not override YAML values — if the YAML
    # already declared the same label we keep that.
    for label in ("nDCG@10", "Recall@1000"):
        if label in seen:
            continue
        args = TRANSLATABLE_METRICS.get(label)
        if args is None:
            continue
        options.append(
            {
                "label": label,
                "args": args,
                "expected": None,
                "source": "standard",
            }
        )
        seen.add(label)
    return options


def metric_args(metric: str) -> Optional[str]:
    """Translate a user-facing metric label to ``trec_eval`` args."""

    if metric in TRANSLATABLE_METRICS:
        return TRANSLATABLE_METRICS[metric]
    # Allow already-formed args (power user escape hatch).
    if metric.startswith("-"):
        return metric
    return None


# ---------------------------------------------------------------------------
# Application state (loaded once at startup)
# ---------------------------------------------------------------------------


@dataclass
class AppState:
    indexes: List[IndexEntry] = field(default_factory=list)
    topic_names: List[str] = field(default_factory=list)
    pairings: List[Pairing] = field(default_factory=list)
    loaded_at: float = 0.0
    error: Optional[str] = None

    def evaluable_indexes(self) -> Dict[str, List[Pairing]]:
        out: Dict[str, List[Pairing]] = {}
        for p in self.pairings:
            out.setdefault(p.index, []).append(p)
        return out


state = AppState()


def reload_state() -> None:
    state.indexes = []
    state.topic_names = []
    state.pairings = []
    state.error = None
    try:
        state.indexes = load_inverted_indexes()
    except Exception as exc:  # noqa: BLE001
        state.error = f"indexes: {exc}"
        print(f"warning: {state.error}", file=sys.stderr)
    try:
        state.topic_names = load_topic_names()
    except Exception as exc:  # noqa: BLE001
        state.error = (
            (state.error + "; " if state.error else "") + f"topics: {exc}"
        )
        print(f"warning: topics: {exc}", file=sys.stderr)
    try:
        state.pairings = load_pairings()
    except Exception as exc:  # noqa: BLE001
        state.error = (
            (state.error + "; " if state.error else "") + f"pairings: {exc}"
        )
        print(f"warning: pairings: {exc}", file=sys.stderr)
    state.loaded_at = time.time()
    print(
        f"loaded {len(state.indexes)} indexes, "
        f"{len(state.topic_names)} topics, "
        f"{len(state.pairings)} pairings",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@app.route("/")
def index_page():
    return send_from_directory(TEMPLATES_DIR, "index.html")


@app.route("/static/<path:filename>")
def static_files(filename: str):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/api/health")
def api_health():
    return jsonify(
        {
            "status": "ok" if state.indexes or state.error is None else "degraded",
            "anserini_jar": str(ANSERINI_JAR),
            "anserini_version": ANSERINI_VERSION,
            "indexes_loaded": len(state.indexes),
            "topics_loaded": len(state.topic_names),
            "pairings_loaded": len(state.pairings),
            "loaded_at": state.loaded_at,
            "error": state.error,
        }
    )


@app.route("/api/catalog")
def api_catalog():
    """Return the inverted-index catalog with pairing info attached."""

    evaluable = state.evaluable_indexes()
    catalog: List[Dict[str, Any]] = []
    for entry in state.indexes:
        pairings = evaluable.get(entry.name, [])
        catalog.append(
            {
                "name": entry.name,
                "type": entry.type,
                "description": entry.description,
                "corpus_index": entry.corpus_index,
                "documents": entry.documents,
                "total_terms": entry.total_terms,
                "size_bytes": entry.size_bytes,
                "readme": entry.readme,
                "evaluable": bool(pairings),
                "pairings": [
                    {
                        "topic_key": p.topic_key,
                        "eval_key": p.eval_key,
                        "metrics": _serialize_metrics(p.metrics),
                        "display": p.display,
                    }
                    for p in pairings
                ],
            }
        )
    return jsonify(
        {
            "anserini_jar": str(ANSERINI_JAR),
            "anserini_version": ANSERINI_VERSION,
            "indexes": catalog,
            "total": len(catalog),
        }
    )


@app.route("/api/topics")
def api_topics():
    return jsonify({"topics": state.topic_names, "total": len(state.topic_names)})


@app.route("/api/pairings")
def api_pairings():
    return jsonify(
        {
            "pairings": [
                {
                    "index": p.index,
                    "topic_key": p.topic_key,
                    "eval_key": p.eval_key,
                    "metrics": _serialize_metrics(p.metrics),
                    "display": p.display,
                }
                for p in state.pairings
            ],
            "translatable_metrics": list(TRANSLATABLE_METRICS.keys()),
        }
    )


@app.route("/api/metrics")
def api_metrics():
    """Return the metric options for a specific index/topic pairing."""

    index = (request.args.get("index") or "").strip()
    topic_key = (request.args.get("topic_key") or "").strip()
    if not (index and topic_key):
        return jsonify({"metrics": [], "error": "index and topic_key required"}), 400
    pairing, err = _resolve_pairing(index, topic_key)
    if err:
        return jsonify({"metrics": [], "error": err}), 404
    return jsonify(
        {
            "index": index,
            "topic_key": topic_key,
            "eval_key": pairing.eval_key,
            "metrics": metrics_for_pairing(pairing),
        }
    )


def _resolve_pairing(
    index: str, topic_key: str
) -> Tuple[Optional[Pairing], Optional[str]]:
    for p in state.pairings:
        if p.index == index and p.topic_key == topic_key:
            return p, None
    return None, f"no known pairing for index={index!r} topic_key={topic_key!r}"


def _metric_args_for(pairing: Pairing, metric: str) -> Tuple[Optional[str], Optional[str]]:
    # 1. Direct match against the YAML metric name.
    if metric in pairing.metrics:
        return pairing.metrics[metric]["args"], None
    # 2. Match against the user-facing (normalized) metric label.
    for opt in metrics_for_pairing(pairing):
        if opt["label"] == metric:
            return opt["args"], None
    # 3. Allow raw trec_eval arg strings as a power-user escape hatch.
    translated = metric_args(metric)
    if translated is None:
        return None, f"unknown metric {metric!r}"
    return translated, None


@app.route("/api/evaluate", methods=["POST"])
def api_evaluate():
    body = request.get_json(force=True, silent=True) or {}
    index = (body.get("index") or "").strip()
    topic_key = (body.get("topic_key") or "").strip()
    metric = (body.get("metric") or "").strip()
    if not (index and topic_key and metric):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "missing required fields: index, topic_key, metric",
                }
            ),
            400,
        )

    pairing, err = _resolve_pairing(index, topic_key)
    if err:
        return jsonify({"ok": False, "error": err}), 400

    args, err = _metric_args_for(pairing, metric)
    if err:
        return jsonify({"ok": False, "error": err}), 400

    # Build unique artifact paths. The run file is a TREC run produced by
    # ``SearchCollection``; the eval file is the trec_eval stdout.
    run_id = uuid.uuid4().hex[:12]
    run_path = RUNS_DIR / f"run.{index}.{topic_key}.{metric}.{run_id}.txt"
    eval_path = EVALS_DIR / f"eval.{index}.{topic_key}.{metric}.{run_id}.txt"

    started = time.time()
    search_cmd = [
        "io.anserini.search.SearchCollection",
        "-threads",
        "1",
        "-index",
        index,
        "-topics",
        topic_key,
        "-output",
        str(run_path),
        "-hits",
        "1000",
        "-bm25",
    ]
    search_code, search_out, search_err = run_anserini(*search_cmd, timeout=1800)
    if search_code != 0 or not run_path.exists():
        return (
            jsonify(
                {
                    "ok": False,
                    "stage": "search",
                    "command": search_cmd,
                    "returncode": search_code,
                    "stdout": search_out[-4000:],
                    "stderr": search_err[-4000:],
                    "error": f"SearchCollection failed (code={search_code})",
                    "elapsed_seconds": round(time.time() - started, 3),
                }
            ),
            500,
        )

    # The ``metric_args`` string may include multiple -m flags, e.g.
    # ``"-c -m map -m P.30"``. We split them so each becomes a separate
    # ``-m`` flag in the argv passed to TrecEval.
    metric_argv: List[str] = []
    for token in args.split():
        metric_argv.append(token)

    eval_cmd = [
        "io.anserini.eval.TrecEval",
        *metric_argv,
        pairing.eval_key,
        str(run_path),
    ]
    eval_code, eval_out, eval_err = run_anserini(*eval_cmd, timeout=600)
    eval_path.write_text(eval_out)
    if eval_code != 0:
        return (
            jsonify(
                {
                    "ok": False,
                    "stage": "eval",
                    "command": eval_cmd,
                    "returncode": eval_code,
                    "stdout": eval_out[-4000:],
                    "stderr": eval_err[-4000:],
                    "error": f"TrecEval failed (code={eval_code})",
                    "run_file": str(run_path),
                    "elapsed_seconds": round(time.time() - started, 3),
                }
            ),
            500,
        )

    # Parse the trec_eval output. Each non-empty line is typically
    # ``measure_name<tab>subset<tab>value``.
    metrics: Dict[str, Dict[str, Any]] = {}
    for line in eval_out.splitlines():
        line = line.rstrip()
        if not line:
            continue
        parts = re.split(r"\s+", line.strip())
        if len(parts) >= 3:
            measure, subset, value = parts[0], parts[1], parts[2]
            try:
                metrics[measure] = {"subset": subset, "value": float(value)}
            except ValueError:
                continue

    primary_score: Optional[float] = None
    if metric in metrics:
        primary_score = metrics[metric]["value"]
    else:
        # Fallback: pick the first metric whose key is a normalized form.
        for key, payload in metrics.items():
            if metric.replace(".", "").lower() in key.lower():
                primary_score = payload["value"]
                break
    if primary_score is None and metrics:
        primary_score = next(iter(metrics.values()))["value"]

    return jsonify(
        {
            "ok": True,
            "index": index,
            "topic_key": topic_key,
            "eval_key": pairing.eval_key,
            "metric": metric,
            "metric_args": args,
            "score": primary_score,
            "metrics": metrics,
            "expected": _expected_score_for(pairing, metric),
            "command": {
                "search": ["java", "-cp", str(ANSERINI_JAR), *search_cmd],
                "eval": ["java", "-cp", str(ANSERINI_JAR), *eval_cmd],
            },
            "run_file": str(run_path),
            "run_file_size": run_path.stat().st_size,
            "run_file_preview": _read_preview(run_path, max_lines=5),
            "eval_file": str(eval_path),
            "eval_output_preview": _read_preview(eval_path, max_lines=20),
            "elapsed_seconds": round(time.time() - started, 3),
            "anserini_jar": str(ANSERINI_JAR),
            "anserini_version": ANSERINI_VERSION,
        }
    )


def _read_preview(path: Path, max_lines: int = 10) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                lines.append(line.rstrip())
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return f"<error reading {path}: {exc}>"


@app.route("/api/artifact")
def api_artifact():
    """Serve a generated run or evaluation file safely.

    The path must live inside ``RUNS_DIR`` or ``EVALS_DIR`` and must exist.
    """

    rel = (request.args.get("path") or "").strip()
    if not rel:
        abort(400, "path is required")
    abs_path = Path(rel).resolve()
    for allowed_root in (RUNS_DIR.resolve(), EVALS_DIR.resolve()):
        try:
            abs_path.relative_to(allowed_root)
            break
        except ValueError:
            continue
    else:
        abort(403, "path is outside the allowed artifact directories")
    if not abs_path.is_file():
        abort(404, "artifact not found")
    return send_from_directory(
        abs_path.parent, abs_path.name, as_attachment=False
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    reload_state()
    host = os.environ.get("HOST", DEFAULT_HOST)
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    print(
        f"Anserini Prebuilt Index Evaluator listening on http://{host}:{port}",
        file=sys.stderr,
    )
    print(
        f"  jar:   {ANSERINI_JAR} (version {ANSERINI_VERSION})",
        file=sys.stderr,
    )
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
