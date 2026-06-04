#!/bin/bash
set -e
ANSERINI_VERSION="2.1.1"
ANSERINI_JAR="anserini-${ANSERINI_VERSION}-fatjar.jar"

if [ ! -f "${ANSERINI_JAR}" ]; then
  echo "Downloading Anserini ${ANSERINI_VERSION}..."
  curl -fL -o "${ANSERINI_JAR}" "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"
fi

echo "Verified ${ANSERINI_JAR}"
java -cp "${ANSERINI_JAR}" io.anserini.search.SearchCollection \
  -threads 1 \
  -index cacm \
  -topics cacm \
  -output run.cacm.bm25.txt \
  -hits 10 \
  -bm25
echo "Anserini smoke test passed."
