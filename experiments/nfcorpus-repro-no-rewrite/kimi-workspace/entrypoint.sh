#!/bin/sh
# Start gunicorn using the PORT environment variable (default 10000)
exec gunicorn --bind "0.0.0.0:${PORT:-10000}" --workers 1 --threads 4 --timeout 300 app:app
