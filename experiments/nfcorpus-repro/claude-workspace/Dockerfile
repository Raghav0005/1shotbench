# NFCorpus Live Retrieval Diagnostics Workbench
#
# Single-image Render-compatible container.
# - Java 21 (Temurin) + Python 3.11
# - Anserini fatjar downloaded at first start (Maven Central, ~110 MB)
# - NFCorpus prebuilt index (~7 MB) auto-fetched by Anserini on first search
#
# The container binds 0.0.0.0:$PORT (default 10000 per Render convention) and
# exposes /health for the Render health check.

FROM eclipse-temurin:21-jdk-jammy

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=10000 \
    HOST=0.0.0.0 \
    WORKBENCH_CACHE_DIR=/data/cache \
    ANSERINI_VERSION=2.1.1 \
    ANSERINI_REST_PORT=18099

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip curl ca-certificates jq tini \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 100 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY app/ ./app/

# /data is the Render persistent-disk mount point; runtime cache lives here.
RUN mkdir -p /data/cache && chmod -R 0777 /data

EXPOSE 10000

# Health check uses the documented /health endpoint.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "python -m uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-10000}"]
