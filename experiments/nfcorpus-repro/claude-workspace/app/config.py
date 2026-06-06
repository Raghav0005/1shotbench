"""Static configuration values for the NFCorpus diagnostics workbench."""
from __future__ import annotations

import os
from pathlib import Path

# Anserini version pinned to a Maven Central release. The fatjar is downloaded
# at container start by app/setup.py if it is not already cached.
ANSERINI_VERSION = os.environ.get("ANSERINI_VERSION", "2.1.1")

# Repo-local cache root. On Render this should be backed by a persistent disk
# mount so that the ~7 MB NFCorpus prebuilt index is downloaded only once.
CACHE_DIR = Path(os.environ.get("WORKBENCH_CACHE_DIR", "cache")).resolve()

FATJAR_PATH = CACHE_DIR / f"anserini-{ANSERINI_VERSION}-fatjar.jar"
RUNS_DIR = CACHE_DIR / "runs"
LOGS_DIR = CACHE_DIR / "logs"

# Anserini reproduction discovery uses ReproduceFromPrebuiltIndexes --config beir.core
# which lists NFCorpus with these symbols (verified via the anserini-reproduction skill).
REPRODUCTION_CONFIG = "beir.core"
REPRODUCTION_CONDITION = "flat"
INDEX_NAME = "beir-v1.0.0-nfcorpus.flat"
TOPICS_KEY = "beir-nfcorpus"
EVAL_KEY = "beir-v1.0.0-nfcorpus.test"

# The expected BM25 nDCG@10 for this condition is published as 0.3218 in the
# reproduction config (verified at runtime by parsing the config YAML output).
EXPECTED_METRICS = {
    "nDCG@10": {"value": 0.3218, "trec_eval_args": ["-c", "-m", "ndcg_cut.10"]},
}

# Internal port used to talk to the embedded Anserini RestServer subprocess.
ANSERINI_REST_PORT = int(os.environ.get("ANSERINI_REST_PORT", "18099"))

# HTTP port the public-facing FastAPI server binds to. Render injects PORT and
# expects 0.0.0.0 binding; the documented default when PORT is unset is 10000.
PUBLIC_PORT = int(os.environ.get("PORT", "10000"))
PUBLIC_HOST = os.environ.get("HOST", "0.0.0.0")

# Pre-canned NFCorpus topical queries surfaced in the UI as one-click samples.
# These are short medical/nutritional phrases consistent with the NFCorpus
# domain; they are inputs to live search, not pre-baked results.
SAMPLE_QUERIES = [
    "vitamin c cancer",
    "diabetes diet",
    "cholesterol soy",
    "antioxidants heart disease",
    "gluten celiac",
    "omega 3 fish oil",
]


def cmd_for_display(parts: list[str]) -> str:
    """Render a command list as a shell-safe display string."""
    out = []
    for p in parts:
        if not p or any(c in p for c in " \t\"'$"):
            out.append('"' + p.replace('"', '\\"') + '"')
        else:
            out.append(p)
    return " ".join(out)
