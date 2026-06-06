#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/frontend"

FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_PORT="${BACKEND_PORT:-8080}"

echo "Starting Next.js frontend on port $FRONTEND_PORT (backend port $BACKEND_PORT) ..."
BACKEND_PORT="$BACKEND_PORT PORT="$FRONTEND_PORT" exec npx next dev --port "$FRONTEND_PORT"
