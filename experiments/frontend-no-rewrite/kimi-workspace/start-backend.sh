#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ANSERINI_JAR="${ANSERINI_JAR:-anserini-2.1.1-fatjar.jar}"
BACKEND_PORT="${BACKEND_PORT:-8080}"

if [[ ! -f "$ANSERINI_JAR" ]]; then
  echo "Anserini fatjar not found: $ANSERINI_JAR"
  echo "Run the install step first or set ANSERINI_JAR to the correct path."
  exit 1
fi

echo "Starting Anserini REST server on port $BACKEND_PORT..."
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "$BACKEND_PORT"
