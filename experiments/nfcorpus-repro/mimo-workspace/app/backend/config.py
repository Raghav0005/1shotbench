"""
Configuration for the NFCorpus Retrieval Diagnostics Workbench.
"""

import os

class Config:
    # Paths
    ANSERINI_JAR = os.environ.get("ANSERINI_JAR", "")
    CACHE_DIR = os.environ.get("CACHE_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
    RUNS_DIR = os.path.join(CACHE_DIR, "runs")
    EVALS_DIR = os.path.join(CACHE_DIR, "evals")
    LOGS_DIR = os.path.join(CACHE_DIR, "logs")

    # Server
    PORT = int(os.environ.get("PORT", "10000"))
    HOST = "0.0.0.0"

    # Anserini
    ANSERINI_VERSION = os.environ.get("ANSERINI_VERSION", "")

    # NFCorpus
    NFCORPUS_INDEX = "beir-v1.0.0-nfcorpus.flat"
    NFCORPUS_TOPICS = "beir-nfcorpus"
    NFCORPUS_EVAL_KEY = "beir-v1.0.0-nfcorpus.test"
    NFCORPUS_TOPICS_ENUM = "BEIR_V1_0_0_NFCORPUS_TEST"

    # Expected metrics from Anserini beir.core reproduction config
    # Metric names are normalized to match trec_eval output format
    EXPECTED_METRICS = {
        "ndcg_cut_10": 0.3218
    }

    # BM25 parameters
    BM25_K1 = 0.9
    BM25_B = 0.4

    @classmethod
    def ensure_dirs(cls):
        for d in [cls.CACHE_DIR, cls.RUNS_DIR, cls.EVALS_DIR, cls.LOGS_DIR]:
            os.makedirs(d, exist_ok=True)
