#!/bin/bash
# Start the Anserini REST API server

ANSERINI_VERSION="${ANSERINI_VERSION:-2.1.1}"
ANSERINI_JAR="${ANSERINI_JAR:-./anserini-${ANSERINI_VERSION}-fatjar.jar}"
PORT="${BACKEND_PORT:-8080}"

if [ ! -f "$ANSERINI_JAR" ]; then
    echo "Error: Anserini fatjar not found at $ANSERINI_JAR"
    echo "Please download it first or set ANSERINI_JAR environment variable"
    exit 1
fi

echo "Starting Anserini REST API server on port $PORT..."
echo "JAR: $ANSERINI_JAR"
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "$PORT"