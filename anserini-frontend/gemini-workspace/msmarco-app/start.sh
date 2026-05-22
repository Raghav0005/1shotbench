#!/bin/bash

# Configuration
export BACKEND_PORT=${BACKEND_PORT:-8080}
export PORT=${FRONTEND_PORT:-3000}
export ANSERINI_BACKEND_URL="http://localhost:${BACKEND_PORT}"

# Ensure we're in the app directory
cd "$(dirname "$0")" || exit

# Path to the anserini fatjar
ANSERINI_JAR="${ANSERINI_JAR:-../anserini-2.1.1-fatjar.jar}"

if [ ! -f "$ANSERINI_JAR" ]; then
    echo "Anserini fatjar not found at $ANSERINI_JAR"
    echo "Please download it first using the install-anserini-fatjar skill."
    exit 1
fi

echo "Starting Anserini REST API server on port $BACKEND_PORT..."
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "$BACKEND_PORT" > backend.log 2>&1 &
BACKEND_PID=$!

echo "Waiting for backend to start..."
sleep 5

echo "Starting Next.js frontend on port $PORT..."
npm run dev &
FRONTEND_PID=$!

# Trap SIGINT to kill background processes
trap "echo 'Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID; exit 0" SIGINT SIGTERM

echo "App is running! Frontend at http://localhost:$PORT"
echo "Press Ctrl+C to stop."

# Wait for background processes
wait
