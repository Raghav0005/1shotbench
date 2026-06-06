FROM eclipse-temurin:21-jre

# Install curl (needed for fatjar download during build), python3, and pip
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash anserini

WORKDIR /app

# Copy application code
COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

# Download Anserini fatjar
RUN ANSERINI_VERSION="$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml \
      | sed -n 's:.*<release>\(.*\)</release>.*:\1:p')" \
    && echo "Downloading Anserini ${ANSERINI_VERSION}" \
    && curl -fL -o "anserini-${ANSERINI_VERSION}-fatjar.jar" \
       "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar" \
    && echo "Anserini fatjar downloaded."

COPY app.py ans_worker.py ./

# Create cache directories
RUN mkdir -p /app/cache && chown -R anserini:anserini /app

# Switch to non-root
USER anserini

# Expose port
EXPOSE 10000

# Set default PORT env
ENV PORT=10000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1

CMD python3 -m gunicorn --bind "0.0.0.0:${PORT}" --timeout 300 --workers 1 app:app
