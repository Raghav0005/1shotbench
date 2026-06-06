# Multi-stage build for NFCorpus Live Retrieval Diagnostics Workbench

# Stage 1: Build / prepare environment
FROM python:3.11-slim-bookworm AS base

# Install Java 21 and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jdk-headless \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY static/ static/

# Pre-download Anserini fatjar during build to speed up startup
ARG ANSERINI_VERSION=2.1.1
RUN mkdir -p .cache && \
    curl -fL -o .cache/anserini-${ANSERINI_VERSION}-fatjar.jar \
    https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar

ENV ANSERINI_VERSION=${ANSERINI_VERSION}
ENV CACHE_DIR=/app/.cache
ENV DATA_DIR=/app/data
ENV INDEX_DIR=/app/indexes
ENV RUNS_DIR=/app/runs
ENV PORT=10000

EXPOSE 10000

# At runtime, the app will verify the fatjar, download NFCorpus, build the index,
# run evaluation, and start serving HTTP.
CMD ["python", "app.py"]
