#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Configurable ports ---
BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

# --- Find fatjar ---
ANSERINI_JAR="$(ls anserini-*-fatjar.jar 2>/dev/null | head -1)"
if [ -z "$ANSERINI_JAR" ]; then
  echo "ERROR: No anserini-*-fatjar.jar found in $SCRIPT_DIR"
  echo "Run the install steps first (see README.md)."
  exit 1
fi

echo "=== MS MARCO Passage Search App ==="
echo "Anserini jar:   $ANSERINI_JAR"
echo "Backend port:   $BACKEND_PORT"
echo "Frontend port:  $FRONTEND_PORT"
echo ""

# --- Start Anserini REST Server ---
echo "Starting Anserini REST server on port $BACKEND_PORT..."
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "$BACKEND_PORT" &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait for backend to be ready
echo "Waiting for backend to be ready..."
for i in $(seq 1 30); do
  if curl -s "http://localhost:${BACKEND_PORT}/v1/msmarco-v1-passage/search?query=test&hits=1" > /dev/null 2>&1; then
    echo "Backend is ready!"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "ERROR: Backend did not become ready in 30 seconds."
    kill $BACKEND_PID 2>/dev/null
    exit 1
  fi
  sleep 2
done

# --- Start Next.js Frontend ---
echo ""
echo "Starting Next.js frontend on port $FRONTEND_PORT..."
cd frontend
ANSERINI_BACKEND_URL="http://localhost:${BACKEND_PORT}" PORT="$FRONTEND_PORT" npx next dev --port "$FRONTEND_PORT" &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

echo ""
echo "=== App is running ==="
echo "Frontend:  http://localhost:${FRONTEND_PORT}"
echo "Backend:   http://localhost:${BACKEND_PORT}"
echo ""
echo "Press Ctrl+C to stop both servers."

cleanup() {
  echo ""
  echo "Shutting down..."
  kill $FRONTEND_PID 2>/dev/null
  kill $BACKEND_PID 2>/dev/null
  wait
  echo "Done."
}
trap cleanup EXIT INT TERM

wait
