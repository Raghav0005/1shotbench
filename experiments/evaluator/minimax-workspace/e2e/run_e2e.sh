#!/usr/bin/env bash
# Launch the Anserini Prebuilt Index Evaluator end-to-end.
#
# 1. Find / install the Anserini fatjar following the
#    ``install-anserini-fatjar`` skill.
# 2. Start the Flask backend in the background.
# 3. Run the Playwright e2e browser test.
# 4. Stop the backend on exit.
#
# Usage::
#
#     ./e2e/run_e2e.sh           # start server, run test, stop server
#     E2E_BASE_URL=… ./run_e2e.sh  # override base URL (e.g. for CI)

set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKSPACE"

PORT="${PORT:-5555}"
HOST="${HOST:-127.0.0.1}"
E2E_BASE_URL="${E2E_BASE_URL:-http://${HOST}:${PORT}}"
LOG_FILE="$WORKSPACE/server.log"
PID_FILE="$WORKSPACE/server.pid"

cleanup() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" || true
      sleep 0.5
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi
}
trap cleanup EXIT

# Locate a fatjar. The skill says: download the latest Anserini fatjar from
# Maven Central, then set ``ANSERINI_JAR`` to the downloaded file.
if ! ls anserini-*-fatjar.jar >/dev/null 2>&1; then
  echo "[run_e2e] no anserini-*-fatjar.jar found; installing via install-anserini-fatjar" >&2
  ANSERINI_VERSION="$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml \
    | sed -n 's:.*<release>\(.*\)</release>.*:\1:p')"
  test -n "$ANSERINI_VERSION"
  echo "[run_e2e] downloading anserini-${ANSERINI_VERSION}-fatjar.jar" >&2
  curl -fL -o "anserini-${ANSERINI_VERSION}-fatjar.jar" \
    "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"
fi

# Start the backend in the background.
echo "[run_e2e] starting backend on ${E2E_BASE_URL}" >&2
PORT="$PORT" HOST="$HOST" \
  nohup python3 "$WORKSPACE/app/server.py" >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
echo "[run_e2e] backend PID $(cat "$PID_FILE")" >&2

# Wait for /api/health to come up.
deadline=$((SECONDS + 90))
while (( SECONDS < deadline )); do
  if curl -fsS "${E2E_BASE_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -fsS "${E2E_BASE_URL}/api/health" >/dev/null 2>&1; then
  echo "[run_e2e] backend failed to start; tail of $LOG_FILE:" >&2
  tail -50 "$LOG_FILE" >&2
  exit 1
fi

# Make sure we can run the Playwright Python bindings.
PYTHON="${PYTHON:-python3}"
if ! "$PYTHON" -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
  for alt in /opt/miniconda3/bin/python3 /usr/local/bin/python3; do
    if [[ -x "$alt" ]] && "$alt" -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
      PYTHON="$alt"
      break
    fi
  done
fi

echo "[run_e2e] running Playwright e2e with $PYTHON" >&2
E2E_BASE_URL="$E2E_BASE_URL" "$PYTHON" "$WORKSPACE/e2e/test_app.py"
