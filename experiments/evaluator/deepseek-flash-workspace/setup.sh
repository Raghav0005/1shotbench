#!/usr/bin/env bash
#
# Setup script for Anserini Prebuilt Index Evaluator
#
# This script:
# 1. Checks for Java 21+
# 2. Checks for Node.js
# 3. Installs npm dependencies
# 4. Downloads the Anserini fatjar
# 5. Runs the CACM smoke test
# 6. Starts the app and runs Playwright e2e tests
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Anserini Prebuilt Index Evaluator Setup ==="
echo "Workspace: $SCRIPT_DIR"
echo ""

# Step 1: Check Java
echo "--- Checking Java ---"
if ! command -v java &>/dev/null; then
    echo "ERROR: Java not found. Please install JDK 21."
    exit 1
fi
JAVA_VER=$(java -version 2>&1 | head -1 | sed 's/[^0-9.]//g' | cut -d. -f1)
echo "Java version: $(java -version 2>&1 | head -1)"
if [ "$JAVA_VER" -lt 21 ]; then
    echo "ERROR: Java 21+ required, found version $JAVA_VER"
    exit 1
fi
echo "Java OK"
echo ""

# Step 2: Check Node.js
echo "--- Checking Node.js ---"
if ! command -v node &>/dev/null; then
    echo "ERROR: Node.js not found. Please install Node.js 18+."
    exit 1
fi
echo "Node.js version: $(node --version)"
echo "Node OK"
echo ""

# Step 3: Install npm dependencies
echo "--- Installing npm dependencies ---"
cd "$SCRIPT_DIR"
npm install
echo "npm dependencies installed"
echo ""

# Step 4: Download Anserini fatjar
echo "--- Installing Anserini fatjar ---"
node setup/install-fatjar.js
echo ""

# Step 5: Clean old CACM smoke test artifacts from previous runs
echo "--- Cleaning old artifacts ---"
rm -f "$SCRIPT_DIR"/run.cacm.bm25.txt "$SCRIPT_DIR"/eval.cacm.bm25.txt
rm -rf "$SCRIPT_DIR"/runs "$SCRIPT_DIR"/evals
echo "Done"
echo ""

# Step 6: Install Playwright browsers
echo "--- Installing Playwright browsers ---"
npx playwright install chromium 2>/dev/null || true
echo ""

echo "=== Setup complete ==="
echo ""
echo "To start the app:"
echo "  cd $SCRIPT_DIR && npm start"
echo ""
echo "To run e2e tests:"
echo "  cd $SCRIPT_DIR && npm test"
echo ""
echo "Then open http://localhost:3000"
