# NFCorpus Live Retrieval Diagnostics Workbench
# A single Docker web service suitable for Render. Listens on 0.0.0.0:$PORT
# (Render injects PORT; we default to 10000). The runtime is OpenJDK 21 + Python
# 3.12, with Anserini pre-downloaded at build time so that the first request is
# fast and the container is fully usable immediately after start.

FROM eclipse-temurin:21-jdk-jammy AS anserini
# Pre-fetch the Anserini fatjar at build time. The image only contains the jar,
# not the index or qrels, so the resulting layer stays small (<120 MB).
ARG ANSERINI_VERSION=2.1.1
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fL -o /opt/anserini-fatjar.jar \
        "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar" \
 && test -s /opt/anserini-fatjar.jar

FROM eclipse-temurin:21-jdk-jammy
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install Python 3.12 and curl. We keep the JDK as the default runtime so that
# `java -cp /opt/anserini-fatjar.jar ...` works directly from PATH.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3-pip curl ca-certificates \
 && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m pip install --break-system-packages --upgrade pip

WORKDIR /app

# Copy Python requirements first for better layer caching.
COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --break-system-packages -r /app/requirements.txt

# Copy the application code.
COPY nfcorpus_app /app/nfcorpus_app
COPY README.md /app/README.md

# Pre-staged Anserini fatjar from the builder stage.
COPY --from=anserini /opt/anserini-fatjar.jar /opt/anserini-fatjar.jar
ENV ANSERINI_JAR=/opt/anserini-fatjar.jar

# Data directory holds run files, evaluator output, and command logs. On
# Render, mount a persistent disk here to keep artifacts across deploys.
RUN mkdir -p /app/data
ENV NFCORPUS_DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1
ENV PORT=10000
EXPOSE 10000

# Run as a non-root user for safety.
RUN useradd --create-home --shell /bin/bash appuser \
 && chown -R appuser:appuser /app
USER appuser

CMD ["sh", "-c", "gunicorn --workers 1 --threads 4 --bind 0.0.0.0:${PORT} --access-logfile - --error-logfile - nfcorpus_app:app"]
