FROM python:3.12-slim

WORKDIR /app

# Install essential system libraries (curl for healthchecks, postgresql-client for pg_isready)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code (excluding files defined in .dockerignore)
COPY . .

# Ensure startup script has Linux line endings and is executable
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

# Create dedicated non-root user and required runtime directories
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data/audio && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["./start.sh"]
