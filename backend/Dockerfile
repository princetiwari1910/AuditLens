# AuditLens Backend Production Dockerfile
FROM python:3.11-slim

# Install system dependencies: ffmpeg, OpenCV native libraries, build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ app/
COPY scripts/ scripts/

# Default persistent data directory volume
ENV DATA_DIR=/app/data
ENV PROVIDER_MODE=meta
ENV DEMO_MODE=live
ENV FRAME_FPS=1
ENV CORS_ORIGINS=*
# CORS_ORIGINS is read from the environment at runtime (e.g. Render, Railway, local dev)
# Mount persistent disk at /app/data for SQLite and uploaded audit files across restarts
VOLUME ["/app/data"]

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Start Uvicorn ASGI server with proxy forwarding
# Critical: disable response buffering for SSE streaming in production
# (e.g. Render/Railway: set CORS_ORIGINS from env; proxy must also set proxy_buffering off)

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
