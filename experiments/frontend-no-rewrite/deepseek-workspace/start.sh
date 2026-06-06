#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
ANSERINI_JAR="${ANSERINI_JAR:-$SCRIPT_DIR/anserini-2.1.1-fatjar.jar}"

if [ ! -f "$ANSERINI_JAR" ]; then
  echo "Error: Anserini fatjar not found at $ANSERINI_JAR"
  echo "Run the install-anserini-fatjar workflow first."
  exit 1
fi

cleanup() {
  echo ""
  echo "Shutting down..."
  kill $BACKEND_PID 2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

echo "=== MS MARCO Passage Search App ==="
echo ""
echo "Starting Anserini REST server on port $BACKEND_PORT..."
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "$BACKEND_PORT" &
BACKEND_PID=$!
sleep 4

echo "Starting Next.js frontend on port $FRONTEND_PORT..."
cd "$SCRIPT_DIR/frontend"
BACKEND_URL="http://localhost:$BACKEND_PORT" PORT="$FRONTEND_PORT" npm run dev -- -p "$FRONTEND_PORT" &
FRONTEND_PID=$!
sleep 4

echo ""
echo "====================================="
echo "  Frontend:  http://localhost:$FRONTEND_PORT"
echo "  Backend:   http://localhost:$BACKEND_PORT"
echo "====================================="
echo ""
echo "Press Ctrl+C to stop both servers."

wait
