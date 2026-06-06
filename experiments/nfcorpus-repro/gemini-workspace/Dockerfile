FROM mcr.microsoft.com/playwright:v1.40.1-jammy AS e2e
# We don't necessarily need to run e2e in the docker image by default,
# but using a node image with java is good.

FROM node:20-bullseye
# Install Java 21
RUN apt-get update && \
    apt-get install -y wget apt-transport-https gnupg ca-certificates && \
    wget -O - https://packages.adoptium.net/artifactory/api/gpg/key/public | apt-key add - && \
    echo "deb https://packages.adoptium.net/artifactory/deb $(awk -F= '/^VERSION_CODENAME/{print$2}' /etc/os-release) main" | tee /etc/apt/sources.list.d/adoptium.list && \
    apt-get update && \
    apt-get install -y temurin-21-jdk curl jq && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package*.json ./
RUN npm install

COPY . .

# Download Anserini fatjar
RUN ./download_fatjar.sh

# Run initial setup / caching for NFCorpus
RUN ./setup_nfcorpus.sh

ENV PORT=10000
EXPOSE 10000
CMD ["npm", "start"]
