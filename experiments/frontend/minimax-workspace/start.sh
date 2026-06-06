#!/usr/bin/env bash
# Launch the Anserini REST backend and the Next.js frontend together.
#
# Port configuration (all optional):
#   ANSERINI_PORT  - port for the Anserini REST server (default 8080)
#   PORT           - port for the Next.js frontend (default 3000)
#   ANSERINI_JAR   - path to the Anserini fatjar
#                    (default ../anserini-2.1.1-fatjar.jar relative to the
#                    frontend directory, or the resolved jar in the repo root)
#   ANSERINI_URL   - full base URL of the Anserini REST server. If set, this
#                    overrides ANSERINI_PORT when the frontend talks to the
#                    backend.

set -euo pipefail

# Resolve the repo root (one level up from the directory containing this script).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
ANSERINI_PORT="${ANSERINI_PORT:-8080}"
FRONTEND_PORT="${PORT:-3000}"

# Pick the Anserini fatjar. Prefer a jar next to this script, otherwise
# fall back to whatever the operator set in ANSERINI_JAR.
if [[ -z "${ANSERINI_JAR:-}" ]]; then
  if [[ -f "$SCRIPT_DIR/anserini-2.1.1-fatjar.jar" ]]; then
    ANSERINI_JAR="$SCRIPT_DIR/anserini-2.1.1-fatjar.jar"
  else
    echo "ERROR: Could not find anserini-*-fatjar.jar. Set ANSERINI_JAR." >&2
    exit 1
  fi
fi

if [[ ! -f "$ANSERINI_JAR" ]]; then
  echo "ERROR: ANSERINI_JAR does not exist: $ANSERINI_JAR" >&2
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Installing Next.js dependencies (first run only)..."
  (cd "$FRONTEND_DIR" && npm install --no-audit --no-fund)
fi

# Start the Anserini REST backend.
ANSERINI_PID_FILE="$(mktemp -t anserinirest.XXXXXX)"
echo "Starting Anserini REST backend on port $ANSERINI_PORT..."
( cd "$SCRIPT_DIR" && nohup java -cp "$ANSERINI_JAR" \
    io.anserini.api.RestServer --port "$ANSERINI_PORT" \
    > anserini-rest.log 2>&1 & echo $! > "$ANSERINI_PID_FILE" )

cleanup() {
  if [[ -f "$ANSERINI_PID_FILE" ]]; then
    local pid
    pid="$(cat "$ANSERINI_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "Stopping Anserini REST backend (pid $pid)..."
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$ANSERINI_PID_FILE"
  fi
}
trap cleanup EXIT INT TERM

# Wait for the backend to accept connections.
echo "Waiting for Anserini REST backend to be ready..."
for i in {1..30}; do
  if curl -sS -o /dev/null "http://localhost:${ANSERINI_PORT}/v1/msmarco-v1-passage/search?query=test&hits=1"; then
    echo "Anserini REST backend is ready."
    break
  fi
  if [[ "$i" -eq 30 ]]; then
    echo "ERROR: Anserini REST backend did not become ready in time." >&2
    echo "Check anserini-rest.log for details." >&2
    exit 1
  fi
  sleep 2
done

# Export the backend URL so the Next.js server-side routes can reach it.
export ANSERINI_PORT
export ANSERINI_URL="${ANSERINI_URL:-http://localhost:${ANSERINI_PORT}}"
export PORT="$FRONTEND_PORT"

echo "Starting Next.js frontend on port $FRONTEND_PORT..."
echo "Open http://localhost:${FRONTEND_PORT} in your browser."
echo "Press Ctrl+C to stop both services."
echo

cd "$FRONTEND_DIR"
exec npx next dev --port "$FRONTEND_PORT"
