#!/bin/bash
# Startup script for the NFCorpus Retrieval Diagnostics Workbench
# Handles PORT environment variable and starts gunicorn

set -e

PORT="${PORT:-10000}"

echo "Starting NFCorpus Workbench on port $PORT..."

exec python3 -m gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers 2 \
    --timeout 900 \
    --access-logfile - \
    --error-logfile - \
    app.wsgi:application
