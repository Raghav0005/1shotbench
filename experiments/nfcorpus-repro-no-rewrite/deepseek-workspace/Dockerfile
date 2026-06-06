FROM python:3.12-slim

# Install Java 21
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        openjdk-21-jdk-headless \
        curl \
        jq \
    && rm -rf /var/lib/apt/lists/*

# Verify Java
RUN java -version

WORKDIR /app

# Copy application
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ templates/
COPY static/ static/

# Create data directory for Anserini downloads and caches
# Mount a Render persistent disk at /app/data if desired
RUN mkdir -p /app/data

ENV WORK_DIR=/app
ENV ANSERINI_JAR=/app/anserini-2.1.1-fatjar.jar

# The fatjar may be pre-downloaded or downloaded at startup
# Pre-download in the image to speed up cold starts
RUN curl -fL -o /app/anserini-2.1.1-fatjar.jar \
    "https://repo1.maven.org/maven2/io/anserini/anserini/2.1.1/anserini-2.1.1-fatjar.jar"

# Verify fatjar exists
RUN test -f /app/anserini-2.1.1-fatjar.jar

# Smoke test (downloads CACM on first run - triggers Anserini cache)
# Run as a separate layer so it can be cached
RUN java -cp /app/anserini-2.1.1-fatjar.jar \
    io.anserini.search.SearchCollection \
    -threads 1 \
    -index cacm \
    -topics cacm \
    -output /app/run.cacm.bm25.txt \
    -hits 1000 \
    -bm25

# NFCorpus pre-built index warm-up (triggers download during build)
RUN java -cp /app/anserini-2.1.1-fatjar.jar \
    io.anserini.cli.Search \
    --index beir-v1.0.0-nfcorpus.flat \
    --query blood \
    --hits 1 \
    --trec

EXPOSE 10000

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 2 --timeout 300 --preload app:app"]
