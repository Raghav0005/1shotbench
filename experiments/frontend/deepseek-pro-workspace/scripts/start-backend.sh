#!/usr/bin/env bash
#
# start-backend.sh — Start the Anserini REST API server.
#
# Prerequisites:
#   - Run scripts/install-anserini.sh first (or source .env with ANSERINI_JAR set).
#
# Usage:
#   bash scripts/start-backend.sh
#
# Environment variables:
#   BACKEND_PORT  — HTTP port for the REST server (default: 8080)
#   ANSERINI_JAR  — Path to the Anserini fatjar
#
set -euo pipefail

# ---- Load env ----
if [ -f .env ]; then
  set -a; source .env; set +a
fi

if [ -z "${ANSERINI_JAR:-}" ]; then
  echo "ERROR: ANSERINI_JAR is not set. Run scripts/install-anserini.sh first."
  echo "       Or set it manually in .env."
  exit 1
fi

if [ ! -f "$ANSERINI_JAR" ]; then
  echo "ERROR: ANSERINI_JAR file not found: $ANSERINI_JAR"
  exit 1
fi

PORT="${BACKEND_PORT:-8080}"

echo "============================================"
echo " Starting Anserini REST API Server"
echo "============================================"
echo ""
echo "   Fatjar: $ANSERINI_JAR"
echo "   Port:   $PORT"
echo "   Index:  msmarco-v1-passage (auto-downloaded on first query)"
echo ""
echo " Test with:"
echo "   curl \"http://localhost:$PORT/v1/msmarco-v1-passage/search?query=test&hits=3\""
echo ""

java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "$PORT"
