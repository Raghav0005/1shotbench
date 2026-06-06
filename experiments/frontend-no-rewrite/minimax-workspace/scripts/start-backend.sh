#!/usr/bin/env bash
# Start the Anserini REST server used as the search backend.
# Honors BACKEND_HOST and BACKEND_PORT env vars (defaults: localhost:8080).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Pick the first anserini-*-fatjar.jar in the repo root, in case the version changes.
ANSERINI_JAR="$(ls -1 "${ROOT_DIR}"/anserini-*-fatjar.jar 2>/dev/null | head -n 1 || true)"
if [ -z "${ANSERINI_JAR}" ] || [ ! -f "${ANSERINI_JAR}" ]; then
  echo "Error: could not find an anserini-*-fatjar.jar in ${ROOT_DIR}." >&2
  echo "Run the install-anserini-fatjar skill first to download it." >&2
  exit 1
fi
export ANSERINI_JAR

if ! command -v java >/dev/null 2>&1; then
  echo "Error: java is not on PATH. Anserini requires Java 21." >&2
  exit 1
fi

BACKEND_HOST="${BACKEND_HOST:-localhost}"
BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

mkdir -p "${ROOT_DIR}/logs"

echo "Starting Anserini REST server on ${BACKEND_HOST}:${BACKEND_PORT}..."
echo "Frontend (when started) will be at http://localhost:${FRONTEND_PORT}"
echo "Logs: ${ROOT_DIR}/logs/anserini-rest.log"
echo

# exec so signals (e.g. Ctrl-C from `npm run dev`) propagate to the JVM.
exec java -cp "${ANSERINI_JAR}" io.anserini.api.RestServer \
  --host "${BACKEND_HOST}" \
  --port "${BACKEND_PORT}"
