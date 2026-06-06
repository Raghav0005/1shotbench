#!/bin/bash
# Convenience script to start both backend and frontend

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

echo "=========================================="
echo "MS MARCO Passage Search App"
echo "=========================================="
echo "Backend port: $BACKEND_PORT"
echo "Frontend port: $FRONTEND_PORT"
echo ""

# Check if Java is available
if ! command -v java &> /dev/null; then
    echo "Error: Java not found. Please install Java 21."
    exit 1
fi

# Check if Node is available
if ! command -v node &> /dev/null; then
    echo "Error: Node.js not found. Please install Node.js 18+."
    exit 1
fi

# Check if the fatjar exists
ANSERINI_VERSION="${ANSERINI_VERSION:-2.1.1}"
ANSERINI_JAR="${ANSERINI_JAR:-$SCRIPT_DIR/anserini-${ANSERINI_VERSION}-fatjar.jar}"

if [ ! -f "$ANSERINI_JAR" ]; then
    echo "Error: Anserini fatjar not found at $ANSERINI_JAR"
    echo "Please download it first."
    exit 1
fi

echo "Starting backend server on port $BACKEND_PORT..."
"$SCRIPT_DIR/start-backend.sh" &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

echo "Backend started with PID $BACKEND_PID"
echo "Starting frontend on port $FRONTEND_PORT..."
cd "$SCRIPT_DIR" && npm run dev &
FRONTEND_PID=$!

echo ""
echo "=========================================="
echo "Both servers are starting!"
echo "Backend: http://localhost:$BACKEND_PORT"
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo "=========================================="
echo ""
echo "Press Ctrl+C to stop both servers"

# Wait for either process to exit
trap "echo 'Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

wait $BACKEND_PID $FRONTEND_PID