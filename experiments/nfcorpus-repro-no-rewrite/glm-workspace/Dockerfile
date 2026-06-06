FROM eclipse-temurin:21-jdk

# Install Python and pip
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip python3-venv curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application
COPY app/ ./app/

# Data directory for Anserini artifacts, indexes, runs
RUN mkdir -p /app/data
ENV DATA_DIR=/app/data

# Render provides PORT; default to 10000
ENV PORT=10000

EXPOSE 10000

CMD ["python3", "app/server.py"]
