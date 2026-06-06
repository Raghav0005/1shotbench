# NFCorpus Live Retrieval Diagnostics Workbench
# Deployable as a single Docker web service on Render.

FROM eclipse-temurin:21-jre

# Install Python and pip
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifest and install Python packages
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY templates/ templates/

# Pre-download Anserini fatjar during build so startup is faster
ARG ANSERINI_VERSION=2.1.1
ENV ANSERINI_VERSION=${ANSERINI_VERSION}
ENV ANSERINI_JAR=/app/cache/anserini-${ANSERINI_VERSION}-fatjar.jar
ENV CACHE_DIR=/app/cache
ENV RUNS_DIR=/app/cache/runs
ENV JAVA_OPTS="--enable-native-access=ALL-UNNAMED --add-modules jdk.incubator.vector"
ENV PORT=10000
ENV BLOCKING_SETUP=1

RUN mkdir -p /app/cache/runs && \
    curl -fL -o /app/cache/anserini-${ANSERINI_VERSION}-fatjar.jar \
    "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"

# Verify the jar was downloaded
RUN test -f /app/cache/anserini-${ANSERINI_VERSION}-fatjar.jar

EXPOSE 10000

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Use gunicorn for production HTTP serving, respecting $PORT
CMD ["/app/entrypoint.sh"]
