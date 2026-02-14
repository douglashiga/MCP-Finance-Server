FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps (gcc for C extensions, libpq-dev for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files required to build/install package
COPY pyproject.toml README.md ./
COPY mcp_server.py exchange_map.json ./
COPY core ./core
COPY services ./services
COPY dataloader ./dataloader

# Install Python dependencies
RUN pip install --no-cache-dir .

# Environment defaults
ENV IB_HOST=host.docker.internal
ENV IB_PORT=4001
ENV IB_CLIENT_ID=1
ENV IB_READ_ONLY=true
ENV LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,socket,sys; ib_enabled=os.getenv('IB_ENABLED','true').lower() in {'1','true','yes','on'}; \
ib_enabled or sys.exit(0); \
host=os.getenv('IB_HOST','127.0.0.1'); port=int(os.getenv('IB_PORT','4001')); \
s=socket.socket(); s.settimeout(2); s.connect((host, port)); s.close()" || exit 1

EXPOSE 8000

CMD ["mcp-finance"]
