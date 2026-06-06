"""Configuration and runtime paths for the NFCorpus Diagnostics Workbench.

All paths are anchored at the project root so that the application behaves the
same in local development, in a Render container, and inside CI. Runtime caches
(runs, evaluator output, logs) live under a single data directory that is
documented in the README as the recommended Render disk mount.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Anserini fatjar. The Docker image downloads the fatjar into this location.
# We resolve the fatjar in this order:
#   1. $ANSERINI_JAR (explicit override)
#   2. <data>/anserini-*-fatjar.jar (any versioned fatjar in the data dir)
#   3. <data>/anserini-fatjar.jar (un-versioned fallback, e.g. a symlink)
ANSERINI_JAR_ENV = os.environ.get("ANSERINI_JAR")
_DATA_DIR = Path(os.environ.get("NFCORPUS_DATA_DIR", str(PROJECT_ROOT / "data")))


def _resolve_default_fatjar() -> Path:
    candidates = []
    if ANSERINI_JAR_ENV:
        candidates.append(Path(ANSERINI_JAR_ENV))
    # Versioned fatjar names that match the Maven Central convention.
    candidates.extend(sorted(_DATA_DIR.glob("anserini-*-fatjar.jar"), reverse=True))
    # Un-versioned fallback.
    fallback = _DATA_DIR / "anserini-fatjar.jar"
    if fallback.exists():
        candidates.append(fallback)
    for cand in candidates:
        if cand.exists():
            return cand
    # Return the first candidate (used as the download target) even if missing.
    return candidates[0] if candidates else fallback


ANSERINI_JAR = _resolve_default_fatjar()

# Runtime data and cache directory. Persistent disk on Render should be
# mounted here (see README). The directory is created lazily on first access.
DATA_DIR = Path(os.environ.get("NFCORPUS_DATA_DIR", str(PROJECT_ROOT / "data")))
CACHE_DIR = DATA_DIR / "cache"
RUNS_DIR = DATA_DIR / "runs"
EVAL_DIR = DATA_DIR / "eval"
LOG_DIR = DATA_DIR / "logs"

# HTTP port. Render sets PORT in the container environment; we default to
# 10000 to match the PRD contract.
PORT = int(os.environ.get("PORT", "10000"))
HOST = os.environ.get("HOST", "0.0.0.0")

# NFCorpus reproduction target. These values come from
# `io.anserini.reproduce.ReproduceFromPrebuiltIndexes --config beir.core
# --show` filtered to the `nfcorpus` topic under the `flat` condition.
NFCORPUS_INDEX = "beir-v1.0.0-nfcorpus.flat"
NFCORPUS_TOPICS = "beir-nfcorpus"
NFCORPUS_EVAL_KEY = "beir-v1.0.0-nfcorpus.test"
NFCORPUS_EXPECTED_NDCG10 = 0.3218
NFCORPUS_REPRODUCTION_CONFIG = "beir.core"
NFCORPUS_REPRODUCTION_CONDITION = "flat"

# Slightly relaxed match threshold for the "close" verdict (within 1% relative
# difference) since JVM/Anserini minor version drift can shift the last digit.
NFCORPUS_CLOSE_REL_TOL = 0.01

# Sample NFCorpus queries, taken from the BEIR/nfcorpus test topic titles.
# The TopicsRegistry returns titles only, so a user clicking a sample query
# will issue a free-text search using the title as the query.
SAMPLE_QUERIES = [
    "Preventing the Common Cold with Probiotics?",
    "Heart Disease Starts in Childhood",
    "Aspartame and the Brain",
    "Dairy and Prostate Cancer Risk",
    "Alkylphenol Endocrine Disruptors and Allergies",
    "Is Milk Good for Our Bones?",
    "Caloric Restriction vs. Plant-Based Diets",
    "Treating Asthma With Plants vs. Supplements?",
    "Food Dyes and ADHD",
    "Diabetes as a Disease of Fat Toxicity",
]


def ensure_dirs() -> None:
    """Create the runtime data directories on first access."""
    for path in (DATA_DIR, CACHE_DIR, RUNS_DIR, EVAL_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Runtime checks (mirrors `install-anserini-fatjar` step 1)
# ---------------------------------------------------------------------------


def java_version() -> dict:
    """Return Java major version info, mirroring the runtime check from the
    `install-anserini-fatjar` skill."""
    java_bin = shutil.which("java")
    if not java_bin:
        return {
            "available": False,
            "java_bin": None,
            "version_string": None,
            "major": None,
            "supported": False,
            "error": "java executable not found on PATH",
        }
    try:
        out = subprocess.check_output(
            [java_bin, "-version"], stderr=subprocess.STDOUT, text=True
        )
    except subprocess.CalledProcessError as exc:
        return {
            "available": False,
            "java_bin": java_bin,
            "version_string": None,
            "major": None,
            "supported": False,
            "error": exc.output.strip(),
        }
    version_string = out.strip().splitlines()[0]
    # Parse "openjdk version "21.0.11" 2026-04-21" -> 21
    major = None
    if '"' in version_string:
        try:
            major = int(version_string.split('"')[1].split(".")[0])
        except (ValueError, IndexError):
            major = None
    return {
        "available": True,
        "java_bin": java_bin,
        "version_string": version_string,
        "major": major,
        "supported": major == 21,
    }
