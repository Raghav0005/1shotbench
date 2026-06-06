# NFCorpus Live Retrieval Diagnostics Workbench
# Render-compatible Docker web service
FROM eclipse-temurin:21-jdk

# Install Python and pip
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip python3-venv curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/workbench

# Copy requirements and install Python deps
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/

# Runtime data directory
RUN mkdir -p /opt/workbench/data

# Environment
ENV WORKBENCH_HOME=/opt/workbench
ENV ANSERINI_VERSION=2.1.1
ENV PORT=10000
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD curl -f http://localhost:${PORT}/health || exit 1

# Start the application
CMD ["python3", "app/server.py"]
