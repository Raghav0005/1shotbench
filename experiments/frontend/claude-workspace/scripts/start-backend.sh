#!/usr/bin/env bash
# Convenience launcher for the Anserini REST API server.
#
# Honors:
#   ANSERINI_JAR   path to the anserini fatjar (required)
#   BACKEND_PORT   port to bind (default 8080)
#   PORT           used as fallback for BACKEND_PORT
set -euo pipefail

if [[ -z "${ANSERINI_JAR:-}" ]]; then
  # Try to autodetect a fatjar in the repo root.
  ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
  candidate="$(ls "$ROOT_DIR"/anserini-*-fatjar.jar 2>/dev/null | head -n1 || true)"
  if [[ -n "$candidate" ]]; then
    ANSERINI_JAR="$candidate"
  else
    echo "ANSERINI_JAR is not set and no anserini-*-fatjar.jar was found in $ROOT_DIR." >&2
    echo "Install the fatjar first (see README.md, step 1)." >&2
    exit 1
  fi
fi

if [[ ! -f "$ANSERINI_JAR" ]]; then
  echo "ANSERINI_JAR does not exist: $ANSERINI_JAR" >&2
  exit 1
fi

PORT_TO_USE="${BACKEND_PORT:-${PORT:-8080}}"

echo "Starting Anserini RestServer on port $PORT_TO_USE using $ANSERINI_JAR"
exec java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "$PORT_TO_USE"
