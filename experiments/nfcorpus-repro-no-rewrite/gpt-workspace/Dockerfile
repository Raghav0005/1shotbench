FROM eclipse-temurin:21-jre-jammy

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
  && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json ./
COPY server.js ./
COPY public ./public
COPY README.md ./README.md

ENV NODE_ENV=production
ENV PORT=10000
ENV APP_CACHE_DIR=/data/nfcorpus-workbench
RUN mkdir -p /data/nfcorpus-workbench && chmod -R 777 /data

EXPOSE 10000
CMD ["node", "server.js"]
