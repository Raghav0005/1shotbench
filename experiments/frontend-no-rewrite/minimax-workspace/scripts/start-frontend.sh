#!/usr/bin/env bash
# Start the Next.js dev server on the configured frontend port.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

# Load .env if it exists so BACKEND_PORT / FRONTEND_PORT are honored.
if [ -f "${ROOT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "${ROOT_DIR}/.env"
  set +a
fi

FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_PORT="${BACKEND_PORT:-8080}"

if [ ! -d "${ROOT_DIR}/node_modules" ]; then
  echo "Installing npm dependencies..."
  npm install --no-audit --no-fund
fi

echo "Starting Next.js frontend on http://localhost:${FRONTEND_PORT}"
echo "Backend expected at http://localhost:${BACKEND_PORT}"
echo

exec npx next dev -p "${FRONTEND_PORT}"
