#!/usr/bin/env bash
set -euo pipefail

PORT="${ANSERINI_PORT:-8080}"
HOST="${ANSERINI_BIND_HOST:-0.0.0.0}"
JAR="${ANSERINI_JAR:-}"

if [[ -z "$JAR" ]]; then
  JAR="$(find "$(pwd)" -maxdepth 1 -name 'anserini-*-fatjar.jar' | sort -V | tail -n 1)"
fi

if [[ -z "$JAR" || ! -f "$JAR" ]]; then
  echo "ANSERINI_JAR must point to an existing anserini-*-fatjar.jar." >&2
  echo "Download it with the install-anserini-fatjar workflow first." >&2
  exit 1
fi

echo "Starting Anserini REST API on ${HOST}:${PORT} with ${JAR}"
echo "MS MARCO endpoint: http://localhost:${PORT}/v1/msmarco-v1-passage/search?query=what%20is%20a%20lobster%20roll&hits=5"
exec java -cp "$JAR" io.anserini.api.RestServer --host "$HOST" --port "$PORT"
