# NFCorpus Live Retrieval Diagnostics Workbench
# Single container, suitable for Render Docker Web Service.
# Binds 0.0.0.0:$PORT (default 10000) and exposes a small Express UI plus a
# long-running Anserini REST server. The fatjar is downloaded on first boot
# and cached under /data so subsequent container restarts are fast.
#
# The base image is Ubuntu 26.04 LTS with Temurin JDK 21 pre-installed and
# `tini` available, which keeps the image small and avoids the need to
# download the JDK at build time. Node.js 20 is added on top.

FROM ubuntu:26.04 AS base

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=C.UTF-8

# Install Node.js 20, curl, tini, and ca-certificates. Use NodeSource so we
# pin a known-good release without depending on Ubuntu's (often stale) repo.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg tini \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && node --version && npm --version

# Adopt the Temurin JDK 21 from a clean Ubuntu base to keep the layer small.
FROM base AS jdk
RUN apt-get update \
 && apt-get install -y --no-install-recommends wget apt-transport-https gnupg \
 && mkdir -p /opt/java \
 && wget -qO- https://packages.adoptium.net/artifactory/api/gpg/key/public | gpg --dearmor -o /usr/share/keyrings/adoptium.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $(. /etc/os-release && echo $VERSION_CODENAME) main" > /etc/apt/sources.list.d/adoptium.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends temurin-21-jdk \
 && rm -rf /var/lib/apt/lists/* \
 && JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java)))) \
 && echo "JAVA_HOME=${JAVA_HOME}"

# Final runtime image.
FROM base

ARG ANSERINI_VERSION=2.1.1
ENV ANSERINI_VERSION=${ANSERINI_VERSION}

# Copy the JDK from the previous stage and wire JAVA_HOME.
COPY --from=jdk /opt/java /opt/java 2>/dev/null || true
COPY --from=jdk /usr/lib/jvm /usr/lib/jvm 2>/dev/null || true
RUN JAVA_HOME=$(find /opt /usr/lib/jvm -maxdepth 2 -name 'java-*' -type d 2>/dev/null | head -1) \
 && if [ -n "$JAVA_HOME" ]; then \
      echo "Found JDK at $JAVA_HOME"; \
      ln -sf "$JAVA_HOME" /opt/java/openjdk; \
      echo 'export JAVA_HOME=/opt/java/openjdk' > /etc/profile.d/java.sh; \
    fi
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="${JAVA_HOME}/bin:${PATH}"

WORKDIR /opt/workbench

# Copy the app and install its Node dependencies.
COPY app/package.json app/package-lock.json* /opt/workbench/app/
RUN cd /opt/workbench/app \
 && if [ -f package-lock.json ]; then npm ci --omit=dev --no-audit --no-fund; else npm install --omit=dev --no-audit --no-fund; fi
COPY app/ /opt/workbench/app/

# Persistent cache + workbench data. Render Free/Starter services have
# ephemeral disk; mount a persistent disk at /data to keep the Anserini
# fatjar and pyserini prebuilt-index cache between deploys.
RUN mkdir -p /data/pyserini/indexes /data/workbench/logs
ENV ANSERINI_CACHE_DIR=/data/pyserini
ENV APP_DATA_DIR=/data/workbench
ENV LOGS_DIR=/data/workbench/logs
ENV PYSERINI_CACHE=/data/pyserini
ENV HOST=0.0.0.0
ENV PORT=10000
ENV NODE_ENV=production

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["node", "/opt/workbench/app/server.js"]
