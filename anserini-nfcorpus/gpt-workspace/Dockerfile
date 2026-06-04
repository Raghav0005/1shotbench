FROM eclipse-temurin:21-jre-jammy

ARG ANSERINI_VERSION=2.1.1
ENV ANSERINI_VERSION=${ANSERINI_VERSION}
ENV ANSERINI_JAR=/opt/anserini/anserini-${ANSERINI_VERSION}-fatjar.jar
ENV PORT=10000
ENV DATA_DIR=/var/data/nfcorpus-workbench

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
  && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/* \
  && mkdir -p /opt/anserini /var/data/nfcorpus-workbench \
  && curl -fL -o "$ANSERINI_JAR" "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"

WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev
COPY src ./src
COPY public ./public
COPY README.md ./README.md

EXPOSE 10000
CMD ["npm", "start"]
