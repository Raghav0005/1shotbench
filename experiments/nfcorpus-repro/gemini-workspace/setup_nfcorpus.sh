#!/bin/bash
set -e
ANSERINI_VERSION="2.1.1"
ANSERINI_JAR="anserini-${ANSERINI_VERSION}-fatjar.jar"
mkdir -p runs

echo "Downloading NFCorpus index and evaluating BM25..."
java -cp "${ANSERINI_JAR}" io.anserini.search.SearchCollection \
  -threads 1 \
  -index beir-v1.0.0-nfcorpus.flat \
  -topics beir-nfcorpus \
  -output runs/run.beir.core.flat.nfcorpus.txt \
  -bm25 -removeQuery

java -cp "${ANSERINI_JAR}" trec_eval -c -m ndcg_cut.10 beir-v1.0.0-nfcorpus.test runs/run.beir.core.flat.nfcorpus.txt > runs/eval.txt
echo "NFCorpus setup complete."
