# NFCorpus Live Retrieval Diagnostics Workbench
#
# Single-image Docker web service for Render / local Docker. Bundles Anserini
# fatjar (Maven Central) + Python FastAPI app. NFCorpus prebuilt index (~6 MB)
# is downloaded at first startup into /data and reused thereafter.

FROM eclipse-temurin:21-jdk

# Python 3 + curl + tini for clean signal handling.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv curl tini ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pin Anserini fatjar version. Override at build time with --build-arg
# ANSERINI_VERSION=<x.y.z> if needed.
ARG ANSERINI_VERSION=2.1.1
ENV ANSERINI_JAR=/opt/anserini/anserini.jar
RUN mkdir -p /opt/anserini \
 && curl -fL -o "$ANSERINI_JAR" \
      "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar" \
 && test -s "$ANSERINI_JAR"

# Python deps.
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

# App source.
COPY app /app/app

# Runtime cache directory. NFCorpus prebuilt index (~6 MB) lives here under
# $HOME/.cache/pyserini/indexes (HOME redirected by app/anserini.py).
ENV NFCORPUS_DATA_DIR=/data
RUN mkdir -p /data /data/runs /data/logs /data/.cache/pyserini/indexes \
 && chmod -R 777 /data

# Render injects PORT; default to 10000 for local docker.
ENV PORT=10000
EXPOSE 10000

# /health is served immediately; NFCorpus warmup + eval run in the background.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["python3","-m","app.main"]
