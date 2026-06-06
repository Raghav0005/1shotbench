#!/usr/bin/env bash
set -euo pipefail

# Render injects PORT; default to 10000 to satisfy the PRD contract when run
# locally with `docker run`.
export PORT="${PORT:-10000}"
export ANSERINI_REST_PORT="${ANSERINI_REST_PORT:-8081}"
export APP_CACHE_DIR="${APP_CACHE_DIR:-/data}"
mkdir -p "${APP_CACHE_DIR}"

if [[ -z "${ANSERINI_JAR:-}" || ! -f "${ANSERINI_JAR}" ]]; then
  echo "[entrypoint] ANSERINI_JAR not set or missing (${ANSERINI_JAR:-unset})" >&2
  exit 1
fi

echo "[entrypoint] starting on 0.0.0.0:${PORT}"
echo "[entrypoint] cache dir: ${APP_CACHE_DIR}"
echo "[entrypoint] anserini jar: ${ANSERINI_JAR}"
echo "[entrypoint] anserini rest port (internal): ${ANSERINI_REST_PORT}"

cd /app
exec python3 -m app.server
