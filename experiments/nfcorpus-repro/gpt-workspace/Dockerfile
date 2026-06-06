FROM eclipse-temurin:21-jre-jammy

ARG ANSERINI_VERSION=2.1.1
ENV ANSERINI_VERSION=${ANSERINI_VERSION}
ENV ANSERINI_JAR=/opt/anserini/anserini-${ANSERINI_VERSION}-fatjar.jar
ENV PORT=10000
ENV NFCORPUS_CACHE_DIR=/data/nfcorpus-workbench

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl ca-certificates python3 \
  && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/anserini /data/nfcorpus-workbench \
  && curl -fL -o "$ANSERINI_JAR" \
    "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar" \
  && test -f "$ANSERINI_JAR"

WORKDIR /app
COPY app ./app
COPY README.md ./README.md

EXPOSE 10000
CMD ["python3", "app/server.py"]
