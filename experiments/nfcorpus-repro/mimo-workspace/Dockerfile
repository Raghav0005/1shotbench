# NFCorpus Retrieval Diagnostics Workbench
# Render-compatible Docker web service
# Uses pre-built base with Java 21 + Python + Anserini fatjar

FROM ghcr.io/lilyjge/pi-bench-anserini-nfcorpus-claude:20260604-195631-698d5dac AS base

# Install Flask dependencies
RUN pip3 install --no-cache-dir --break-system-packages \
    flask==3.1.1 \
    flask-cors==5.0.1 \
    gunicorn==23.0.0

# Set up app directory
WORKDIR /app

# Copy application code
COPY app/ ./app/

# Create data directories for runtime artifacts
RUN mkdir -p /app/data/runs /app/data/evals /app/data/logs

# Environment configuration
ENV PYTHONUNBUFFERED=1
ENV PORT=10000
ENV CACHE_DIR=/app/data
# Point to the pre-installed Anserini fatjar
ENV ANSERINI_JAR=/opt/anserini-2.1.1-fatjar.jar

EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run with startup script
CMD ["bash", "app/start.sh"]
