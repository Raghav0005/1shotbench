#!/usr/bin/env bash
#
# start-frontend.sh — Start the Next.js frontend dev server.
#
# Prerequisites:
#   - Node.js 18+ and npm installed
#   - Run `npm install` in the project root
#
# Usage:
#   bash scripts/start-frontend.sh
#
# Environment variables:
#   FRONTEND_PORT — Port for the Next.js dev server (default: 3000)
#   BACKEND_PORT  — Port of the Anserini REST API (default: 8080)
#   BACKEND_HOST  — Host of the Anserini REST API (default: localhost)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# ---- Check node_modules ----
if [ ! -d node_modules ]; then
  echo "==> Installing npm dependencies..."
  npm install
fi

# ---- Load env ----
if [ -f .env.local ]; then
  set -a; source .env.local; set +a
fi

FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_PORT="${BACKEND_PORT:-8080}"
BACKEND_HOST="${BACKEND_HOST:-localhost}"

echo "============================================"
echo " Starting MS MARCO Passage Search Frontend"
echo "============================================"
echo ""
echo "   Frontend: http://localhost:$FRONTEND_PORT"
echo "   Backend:  http://$BACKEND_HOST:$BACKEND_PORT"
echo ""
echo " Make sure the Anserini REST server is running:"
echo "   bash scripts/start-backend.sh"
echo ""

exec npx next dev -p "$FRONTEND_PORT"
