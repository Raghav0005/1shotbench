#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration via environment variables
BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
ANSERINI_JAR="${ANSERINI_JAR:-$(ls anserini-*-fatjar.jar 2>/dev/null | head -1)}"

if [ -z "$ANSERINI_JAR" ] || [ ! -f "$ANSERINI_JAR" ]; then
  echo "ERROR: Anserini fatjar not found. Set ANSERINI_JAR or place anserini-*-fatjar.jar in $SCRIPT_DIR"
  exit 1
fi

echo "=== MS MARCO Passage Search App ==="
echo "Backend port:  $BACKEND_PORT"
echo "Frontend port: $FRONTEND_PORT"
echo "Anserini jar:  $ANSERINI_JAR"
echo ""

# Function to clean up background processes
cleanup() {
  echo ""
  echo "Shutting down..."
  [ -n "${BACKEND_PID:-}" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "${FRONTEND_PID:-}" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null
  echo "Done."
}
trap cleanup EXIT INT TERM

# Start Anserini REST API backend
echo "Starting Anserini REST API server on port $BACKEND_PORT..."
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "$BACKEND_PORT" &
BACKEND_PID=$!

# Wait for backend to be ready
echo "Waiting for backend to be ready..."
for i in $(seq 1 30); do
  if curl -sf "http://localhost:${BACKEND_PORT}/v1/msmarco-v1-passage/search?query=test&hits=1" > /dev/null 2>&1; then
    echo "Backend is ready!"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "WARNING: Backend did not become ready within 30 seconds, but continuing..."
  fi
  sleep 1
done

# Start Next.js frontend
echo "Starting Next.js frontend on port $FRONTEND_PORT..."
cd frontend
ANSERINI_BACKEND_URL="http://localhost:${BACKEND_PORT}" \
  PORT="$FRONTEND_PORT" \
  npx next dev &
FRONTEND_PID=$!

echo ""
echo "=== App is running ==="
echo "Frontend: http://localhost:${FRONTEND_PORT}"
echo "Backend:  http://localhost:${BACKEND_PORT}"
echo "Press Ctrl+C to stop."
echo ""

wait
