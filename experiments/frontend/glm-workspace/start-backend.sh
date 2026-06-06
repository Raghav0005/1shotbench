#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Resolve the fatjar
ANSERINI_JAR="${ANSERINI_JAR:-$(ls anserini-*-fatjar.jar 2>/dev/null | head -1)}"
if [ ! -f "$ANSERINI_JAR" ]; then
  echo "ERROR: Cannot find Anserini fatjar. Set ANSERINI_JAR or place anserini-*-fatjar.jar in $SCRIPT_DIR" >&2
  exit 1
fi

BACKEND_PORT="${BACKEND_PORT:-8080}"
echo "Starting Anserini REST API server on port $BACKEND_PORT ..."
echo "  JAR: $ANSERINI_JAR"
echo "  Press Ctrl+C to stop."
exec java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "$BACKEND_PORT"
