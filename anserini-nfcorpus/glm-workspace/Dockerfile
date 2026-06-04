FROM eclipse-temurin:21-jdk AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app/requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

COPY app/ .
COPY run.sh .
RUN chmod +x run.sh

ENV PORT=10000
ENV ANSERINI_VERSION=2.1.1
ENV DATA_DIR=/app/data
ENV CACHE_DIR=/app/data/cache

RUN mkdir -p ${DATA_DIR} ${CACHE_DIR}

EXPOSE ${PORT}

CMD ["./run.sh"]
