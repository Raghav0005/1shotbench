#!/usr/bin/env bash
set -euo pipefail

export PORT="${PORT:-10000}"
export DATA_DIR="${DATA_DIR:-/app/data}"
export CACHE_DIR="${CACHE_DIR:-/app/data/cache}"
export ANSERINI_VERSION="${ANSERINI_VERSION:-2.1.1}"
export ANSERINI_JAR="${DATA_DIR}/anserini-${ANSERINI_VERSION}-fatjar.jar"

mkdir -p "${DATA_DIR}" "${CACHE_DIR}"

# Download fatjar if not present
if [ ! -f "${ANSERINI_JAR}" ]; then
    echo "Downloading Anserini fatjar v${ANSERINI_VERSION}..."
    curl -fL -o "${ANSERINI_JAR}" \
        "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"
    echo "Download complete."
fi

echo "Anserini jar: ${ANSERINI_JAR}"
echo "Starting app on port ${PORT}..."

cd /app
exec python3 /app/server.py
