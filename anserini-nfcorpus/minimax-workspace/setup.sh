#!/bin/bash
# NFCorpus Diagnostics Workbench - Setup Script
# Downloads Anserini fatjar and prepares NFCorpus environment

set -e

WORKSPACE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKSPACE_DIR"

echo "=== NFCorpus Diagnostics Workbench Setup ==="

# Create directories
mkdir -p cache runs logs

# Check Java
echo "Checking Java..."
if ! command -v java &> /dev/null; then
    echo "ERROR: Java is not installed. Please install Java 21+"
    exit 1
fi

java_version=$(java -version 2>&1 | head -1)
echo "Found: $java_version"

# Download Anserini fatjar if not present
ANSERINI_JAR="${ANSERINI_JAR:-${WORKSPACE_DIR}/anserini-fatjar.jar}"

if [ ! -f "$ANSERINI_JAR" ]; then
    echo "Downloading Anserini fatjar..."

    # Get latest version
    ANSERINI_VERSION=$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml \
        | sed -n 's:.*<release>\(.*\)</release>.*:\1:p')

    if [ -z "$ANSERINI_VERSION" ]; then
        echo "ERROR: Could not determine latest Anserini version"
        exit 1
    fi

    echo "Latest Anserini version: $ANSERINI_VERSION"

    curl -fL -o "$ANSERINI_JAR" \
        "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"
else
    echo "Anserini fatjar already present: $ANSERINI_JAR"
fi

export ANSERINI_JAR

# Verify fatjar with CACM smoke test
echo "Running Anserini smoke test..."
java -cp "$ANSERINI_JAR" io.anserini.search.SearchCollection \
    -index cacm \
    -topics cacm \
    -output cache/test-run.txt \
    -hits 1000 \
    -bm25 \
    -threads 1

echo "Evaluating smoke test..."
java -cp "$ANSERINI_JAR" io.anserini.eval.TrecEval \
    -c \
    -m map \
    -m P.30 \
    cacm \
    cache/test-run.txt

echo ""
echo "=== Setup Complete ==="
echo "Run: python3 server.py"
echo "Then open: http://localhost:10000"