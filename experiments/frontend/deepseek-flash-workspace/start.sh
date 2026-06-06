#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Start the MS MARCO Passage Search App
#
# Environment variables (optional):
#   ANSERINI_JAR   - Path to the Anserini fatjar (default: ./anserini-*-fatjar.jar)
#   API_PORT       - Port for the Anserini REST server (default: 8080)
#   FRONTEND_PORT  - Port for the Next.js dev server (default: 3000)
# ============================================================

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

# --- Resolve fatjar ---
if [ -z "${ANSERINI_JAR:-}" ]; then
  JAR="$(ls "$ROOT_DIR"/anserini-*-fatjar.jar 2>/dev/null | head -1)"
  if [ -z "$JAR" ]; then
    echo "ERROR: No anserini-*-fatjar.jar found in $ROOT_DIR"
    echo "Set ANSERINI_JAR or run install-anserini-fatjar first."
    exit 1
  fi
  ANSERINI_JAR="$JAR"
fi
export ANSERINI_JAR

API_PORT="${API_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

echo "=========================================="
echo " MS MARCO Passage Search App"
echo "=========================================="
echo " Anserini JAR : $ANSERINI_JAR"
echo " API port     : $API_PORT"
echo " Frontend port: $FRONTEND_PORT"
echo "------------------------------------------"

# --- Start Anserini REST server ---
echo "Starting Anserini REST server on port $API_PORT ..."
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "$API_PORT" &
API_PID=$!
echo "  PID: $API_PID"

# Wait for the REST server to be ready
for i in $(seq 1 15); do
  if curl -s "http://localhost:$API_PORT/v1/msmarco-v1-passage/search?query=test&hits=1" >/dev/null 2>&1; then
    echo "  REST server is ready."
    break
  fi
  if [ "$i" -eq 15 ]; then
    echo "ERROR: REST server did not start within 15 seconds. Check /tmp/anserini-rest-server.log"
    exit 1
  fi
  sleep 1
done

# --- Start Next.js dev server ---
echo "Starting Next.js dev server on port $FRONTEND_PORT ..."
cd "$FRONTEND_DIR"
API_PORT="$API_PORT" npx next dev --port "$FRONTEND_PORT" &
FRONTEND_PID=$!
echo "  PID: $FRONTEND_PID"

echo ""
echo "=========================================="
echo " App is running!"
echo " Frontend: http://localhost:$FRONTEND_PORT"
echo " API:      http://localhost:$API_PORT"
echo "=========================================="
echo ""
echo "Press Ctrl+C to stop both servers."

# Trap exit to clean up
cleanup() {
  echo ""
  echo "Shutting down..."
  kill "$FRONTEND_PID" 2>/dev/null || true
  kill "$API_PID" 2>/dev/null || true
  wait
}
trap cleanup EXIT INT TERM

# Wait for both
wait
