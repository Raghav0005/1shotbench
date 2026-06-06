#!/usr/bin/env bash
# Start the Next.js frontend. Defaults match the PRD: port 3000, backend on :8080.
set -euo pipefail

cd "$(dirname "$0")/frontend"

if [[ ! -d node_modules ]]; then
  echo "Installing frontend dependencies..."
  npm install --no-audit --no-fund
fi

export ANSERINI_BASE_URL="${ANSERINI_BASE_URL:-http://localhost:${ANSERINI_PORT:-8080}}"
export ANSERINI_INDEX="${ANSERINI_INDEX:-msmarco-v1-passage}"
export FRONTEND_PORT="${FRONTEND_PORT:-3000}"

echo "Starting Next.js on :$FRONTEND_PORT (backend: $ANSERINI_BASE_URL, index: $ANSERINI_INDEX)"
exec npx next dev -p "$FRONTEND_PORT"
