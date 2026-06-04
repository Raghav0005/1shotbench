FROM python:3.11-slim

# Install Java 21
RUN apt-get update && apt-get install -y \
    openjdk-21-jre-headless \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY server.py .
COPY templates/ ./templates/
COPY static/ ./static/

# Create runtime directories
RUN mkdir -p cache runs logs

# Environment variables
ENV PORT=10000
ENV ANSERINI_REST_PORT=8080

# Expose port
EXPOSE 10000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:10000/health || exit 1

# Run the application
CMD ["python3", "server.py"]