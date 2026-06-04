# syntax=docker/dockerfile:1.6
#
# NFCorpus Live Retrieval Diagnostics Workbench.
#
# Render contract: container binds 0.0.0.0:$PORT (default 10000).
# Cache directory for the Anserini prebuilt index lives under /data, which
# can be mapped to a Render persistent disk when available.

FROM eclipse-temurin:21-jdk AS base

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        curl ca-certificates jq tini \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Default Anserini version. Override at build time with:
#   docker build --build-arg ANSERINI_VERSION=2.1.1 .
ARG ANSERINI_VERSION=2.1.1
ENV ANSERINI_VERSION=${ANSERINI_VERSION}

# Download the released Anserini fatjar from Maven Central. This follows the
# install-anserini-fatjar skill's documented download step.
RUN curl -fL \
      -o /opt/anserini-${ANSERINI_VERSION}-fatjar.jar \
      "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar" \
 && test -f /opt/anserini-${ANSERINI_VERSION}-fatjar.jar

ENV ANSERINI_JAR=/opt/anserini-${ANSERINI_VERSION}-fatjar.jar

# Python dependencies for the Flask app.
COPY requirements.txt /app/requirements.txt
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r /app/requirements.txt
ENV PATH="/opt/venv/bin:${PATH}"

# Application source.
COPY app /app/app
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Persistent cache root. Mount a Render disk here to keep the NFCorpus index
# warm across deploys.
ENV APP_CACHE_DIR=/data \
    PYSERINI_CACHE=/data/pyserini-cache \
    ANSERINI_REST_PORT=8081 \
    PORT=10000
RUN mkdir -p /data /root/.cache

# The Anserini fatjar resolves the prebuilt-index cache via the user's home
# `.cache` directory. Symlink it to /data so cached indexes persist when a
# Render disk is mounted at /data.
RUN ln -sfn /data/pyserini-cache /root/.cache/pyserini

EXPOSE 10000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/entrypoint.sh"]
