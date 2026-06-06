#!/bin/bash

# MS MARCO Passage Search Application Startup Script
# This script starts both the Anserini REST API server and the Next.js frontend

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANSERINI_JAR="${ANSERINI_JAR:-${SCRIPT_DIR}/anserini-2.1.1-fatjar.jar}"
ANSERINI_PORT="${ANSERINI_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}MS MARCO Passage Search Application${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if Anserini jar exists
if [ ! -f "$ANSERINI_JAR" ]; then
    echo -e "${RED}Error: Anserini fatjar not found at $ANSERINI_JAR${NC}"
    echo "Please run install-anserini-fatjar skill first or set ANSERINI_JAR"
    exit 1
fi

# Check if Java is available
if ! command -v java &> /dev/null; then
    echo -e "${RED}Error: Java is not installed${NC}"
    exit 1
fi

echo -e "${YELLOW}Configuration:${NC}"
echo "  Anserini JAR: $ANSERINI_JAR"
echo "  Anserini Port: $ANSERINI_PORT"
echo "  Frontend Port: $FRONTEND_PORT"
echo ""

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    if [ ! -z "$ANSERINI_PID" ]; then
        kill $ANSERINI_PID 2>/dev/null || true
        echo -e "${GREEN}✓ Anserini server stopped${NC}"
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
        echo -e "${GREEN}✓ Frontend stopped${NC}"
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# Start Anserini REST server
echo -e "${YELLOW}Starting Anserini REST server on port $ANSERINI_PORT...${NC}"
java -cp "$ANSERINI_JAR" io.anserini.api.RestServer --port "$ANSERINI_PORT" &
ANSERINI_PID=$!

# Wait for Anserini to start
echo -n "Waiting for Anserini server"
for i in {1..30}; do
    if curl -s "http://localhost:$ANSERINI_PORT/" > /dev/null 2>&1; then
        echo ""
        echo -e "${GREEN}✓ Anserini server started successfully${NC}"
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

# Check if Anserini is actually running
if ! curl -s "http://localhost:$ANSERINI_PORT/" > /dev/null 2>&1; then
    echo -e "${RED}Error: Anserini server failed to start${NC}"
    exit 1
fi

# Start Next.js frontend
echo -e "${YELLOW}Starting Next.js frontend on port $FRONTEND_PORT...${NC}"
cd "${SCRIPT_DIR}/search-app"
PORT=$FRONTEND_PORT npm run dev &
FRONTEND_PID=$!

# Wait for frontend to start
echo -n "Waiting for frontend"
for i in {1..30}; do
    if curl -s "http://localhost:$FRONTEND_PORT/" > /dev/null 2>&1; then
        echo ""
        echo -e "${GREEN}✓ Frontend started successfully${NC}"
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Application is running!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Frontend: ${GREEN}http://localhost:$FRONTEND_PORT${NC}"
echo -e "Backend:  ${GREEN}http://localhost:$ANSERINI_PORT${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop both servers${NC}"
echo ""

# Wait for processes
wait
