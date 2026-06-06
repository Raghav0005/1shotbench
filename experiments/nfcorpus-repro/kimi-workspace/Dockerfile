FROM python:3.11-slim

# Install Java 21 and curl
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-21-jdk curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Verify Java
RUN java -version

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY static/ static/

# Create cache directory for Anserini artifacts
RUN mkdir -p /app/cache

# Environment
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

# Expose port (informational)
EXPOSE 10000

# Run the Flask app via gunicorn for production, respecting the PORT env var
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-10000} --timeout 300 --workers 1 --threads 4 app:app"]
