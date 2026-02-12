FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps (gcc for C extensions, libpq-dev for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency file first for caching
COPY pyproject.toml .

# Install Python dependencies
RUN pip install --no-cache-dir .

# Copy application code
COPY . .

# Environment defaults
ENV IB_HOST=host.docker.internal
ENV IB_PORT=4001
ENV IB_CLIENT_ID=1
ENV IB_READ_ONLY=true
ENV LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('${IB_HOST}', int('${IB_PORT}'))); s.close()" || exit 1

EXPOSE 8000

CMD ["python", "mcp_server.py"]
