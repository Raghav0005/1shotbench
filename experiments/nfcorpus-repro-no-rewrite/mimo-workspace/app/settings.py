"""Configuration settings for the NFCorpus diagnostics workbench."""
import os

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
ANSERINI_JAR = os.environ.get("ANSERINI_JAR", os.path.join(BASE_DIR, "anserini-2.1.1-fatjar.jar"))

# Server
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "10000"))

# Anserini
ANSERINI_VERSION = "2.1.1"
JAVA_CMD = "java"
JAVA_FLAGS = ["--enable-native-access=ALL-UNNAMED"]

# NFCorpus config
NFCORPUS_INDEX = "beir-v1.0.0-nfcorpus.flat"
NFCORPUS_TOPICS = "beir-nfcorpus"
NFCORPUS_EVAL_KEY = "beir-v1.0.0-nfcorpus.test"
NFCORPUS_METRIC = "nDCG@10"
NFCORPUS_METRIC_TRECEVAL_FLAG = "-m ndcg_cut.10"
NFCORPUS_EXPECTED_NDCG10 = 0.3218

# Output files
RUN_FILE = os.path.join(DATA_DIR, "run.nfcorpus.bm25.txt")
EVAL_FILE = os.path.join(DATA_DIR, "eval.nfcorpus.bm25.txt")

# Sample queries for NFCorpus (medical/nutrition domain)
SAMPLE_QUERIES = [
    "health benefits of fish oil",
    "vitamin D deficiency symptoms",
    "effects of caffeine on blood pressure",
    "probiotics and gut health",
    "iron supplements for anemia",
]
