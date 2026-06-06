#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

java -version >/dev/null

ANSERINI_VERSION="${ANSERINI_VERSION:-}"
if [[ -z "$ANSERINI_VERSION" ]]; then
  ANSERINI_VERSION="$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml \
    | sed -n 's:.*<release>\(.*\)</release>.*:\1:p')"
fi

test -n "$ANSERINI_VERSION"
mkdir -p .anserini
JAR=".anserini/anserini-${ANSERINI_VERSION}-fatjar.jar"

if [[ ! -f "$JAR" ]]; then
  curl -fL -o "$JAR" \
    "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"
fi

echo "ANSERINI_JAR=$ROOT_DIR/$JAR"
