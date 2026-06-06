FROM python:3.12-slim

# Install Java 21 (Temurin)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget ca-certificates gnupg \
  && mkdir -p /etc/apt/keyrings \
  && curl -fsSL https://packages.adoptium.net/artifactory/api/gpg/key/public \
     | gpg --dearmor -o /etc/apt/keyrings/adoptium.gpg \
  && echo "deb [signed-by=/etc/apt/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $(awk -F= '/^VERSION_CODENAME/{print $2}' /etc/os-release) main" \
     > /etc/apt/sources.list.d/adoptium.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends temurin-21-jdk \
  && rm -rf /var/lib/apt/lists/*

# Install jq for optional registry filtering
RUN apt-get update && apt-get install -y --no-install-recommends jq && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY templates/ templates/
COPY static/ static/
COPY run.py .

# Download Anserini fatjar at build time
ARG ANSERINI_VERSION=2.1.1
RUN curl -fL -o anserini-${ANSERINI_VERSION}-fatjar.jar \
    "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar"

ENV ANSERINI_JAR=/app/anserini-${ANSERINI_VERSION}-fatjar.jar
ENV DATA_DIR=/app/data
ENV HOST=0.0.0.0
ENV PORT=10000

# Pre-create data dir
RUN mkdir -p /app/data

EXPOSE ${PORT}

CMD ["python", "run.py"]
