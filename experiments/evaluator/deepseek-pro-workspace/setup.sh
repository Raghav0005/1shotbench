#!/usr/bin/env bash
#
# Setup script for the Anserini Prebuilt Index Evaluator.
#
# Usage:
#   bash setup.sh
#
# This script:
# 1. Checks for Java 21+
# 2. Downloads the Anserini fatjar from Maven Central
# 3. Runs the CACM smoke test to verify the setup
# 4. Installs Python dependencies
# 5. Installs Playwright for e2e tests (optional)
#

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 1. Check Java ──
echo ""
info "Checking Java…"
if ! command -v java &>/dev/null; then
    error "Java not found. Please install JDK 21+."
    exit 1
fi

JAVA_VERSION=$(java -version 2>&1 | head -1 || true)
echo "  $JAVA_VERSION"

JAVA_MAJOR=$(java -version 2>&1 | grep -oP 'version "\d+' | grep -oP '\d+' || echo "0")
if [ "$JAVA_MAJOR" -lt 21 ]; then
    warn "Java major version is $JAVA_MAJOR. Anserini recommends JDK 21+."
    warn "The evaluator may not work correctly."
fi

# ── 2. Download Anserini fatjar ──
echo ""
info "Checking Anserini fatjar…"

# Check if ANSERINI_JAR is already set and file exists
if [ -n "${ANSERINI_JAR:-}" ] && [ -f "$ANSERINI_JAR" ]; then
    info "Using existing ANSERINI_JAR: $ANSERINI_JAR"
else
    # Look for existing fatjar in current dir
    EXISTING_JAR=$(ls anserini-*-fatjar.jar 2>/dev/null | head -1 || true)
    if [ -n "$EXISTING_JAR" ]; then
        info "Found existing fatjar: $EXISTING_JAR"
        export ANSERINI_JAR="$SCRIPT_DIR/$EXISTING_JAR"
    else
        info "Downloading latest Anserini fatjar from Maven Central…"

        # Get latest version
        ANSERINI_VERSION=$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml \
            | sed -n 's:.*<release>\(.*\)</release>.*:\1:p' || echo "")

        if [ -z "$ANSERINI_VERSION" ]; then
            error "Could not determine latest Anserini version from Maven Central."
            error "Please set ANSERINI_JAR manually to a downloaded fatjar path."
            exit 1
        fi

        info "Latest version: $ANSERINI_VERSION"

        JAR_FILE="anserini-${ANSERINI_VERSION}-fatjar.jar"
        if [ -f "$JAR_FILE" ]; then
            info "Fatjar already downloaded: $JAR_FILE"
        else
            info "Downloading $JAR_FILE…"
            curl -fL -o "$JAR_FILE" \
                "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"
        fi

        export ANSERINI_JAR="$SCRIPT_DIR/$JAR_FILE"
    fi
fi

info "ANSERINI_JAR=$ANSERINI_JAR"

# ── 3. Smoke test ──
echo ""
info "Running CACM smoke test…"

SMOKE_OUTPUT="run.cacm.bm25.smoke.txt"

java -cp "$ANSERINI_JAR" io.anserini.search.SearchCollection \
    -threads 1 \
    -index cacm \
    -topics cacm \
    -output "$SMOKE_OUTPUT" \
    -hits 1000 \
    -bm25

if [ -f "$SMOKE_OUTPUT" ]; then
    LINE_COUNT=$(wc -l < "$SMOKE_OUTPUT")
    info "Smoke test passed. Run file: $SMOKE_OUTPUT ($LINE_COUNT lines)"

    # Verify with TrecEval
    EVAL_OUTPUT=$(java -cp "$ANSERINI_JAR" io.anserini.eval.TrecEval \
        -c -m map -m P.30 cacm "$SMOKE_OUTPUT" 2>&1 || true)

    if echo "$EVAL_OUTPUT" | grep -q "map.*0\.3123"; then
        info "Evaluation verified: MAP 0.3123 ✓"
    else
        warn "Could not verify MAP 0.3123. Got:"
        echo "$EVAL_OUTPUT" | head -5
    fi
else
    error "Smoke test failed: $SMOKE_OUTPUT not created"
    error "Check that Java 21+ is installed and the fatjar is valid."
    exit 1
fi

# ── 4. Python dependencies ──
echo ""
info "Checking Python dependencies…"

if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    error "Python 3 not found. Please install Python 3.8+."
    exit 1
fi

# Install Flask if not present
if ! $PYTHON -c "import flask" 2>/dev/null; then
    info "Installing Flask…"
    $PYTHON -m pip install flask
else
    info "Flask is available"
fi

# ── 5. Playwright (optional) ──
echo ""
info "Checking Playwright for e2e tests…"

if command -v npx &>/dev/null; then
    if [ -f "package.json" ]; then
        info "Installing Node dependencies…"
        npm install
    fi
    if ! npx playwright --version &>/dev/null 2>&1; then
        warn "Playwright not installed. Run: npm install && npx playwright install chromium"
    else
        info "Playwright is available"
    fi
else
    warn "Node.js/npx not found. Skipping Playwright setup."
    warn "To run e2e tests, install Node.js and run: npm install && npx playwright install chromium"
fi

# ── Done ──
echo ""
info "══ Setup complete ══"
echo ""
echo "To start the evaluator:"
echo "  ANSERINI_JAR=\"$ANSERINI_JAR\" python3 server.py"
echo ""
echo "To run the e2e test (after starting the server):"
echo "  npx playwright test test_e2e.mjs  # or: node test_e2e.mjs"
echo ""
