#!/usr/bin/env bash
# Start the Anserini REST API server backing the MS MARCO passage search app.
# Defaults match the PRD: port 8080. Override with ANSERINI_PORT.
set -euo pipefail

cd "$(dirname "$0")"

JAR_GLOB="anserini-*-fatjar.jar"
JAR_PATH="$(ls -1 $JAR_GLOB 2>/dev/null | head -n 1 || true)"
if [[ -z "${JAR_PATH:-}" ]]; then
  echo "No anserini fatjar found in $(pwd). Run install-anserini-fatjar first." >&2
  exit 1
fi

export ANSERINI_JAR="$(pwd)/$JAR_PATH"
PORT="${ANSERINI_PORT:-8080}"

echo "Starting Anserini REST server on :$PORT using $ANSERINI_JAR"
exec java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "$PORT"
