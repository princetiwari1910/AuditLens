# Deployment Guide

## Render

```yaml
services:
  backend:
    type: web_service
    env: python
    buildCommand: ./backend/build.sh  # or: dockerfilePath: ./backend/Dockerfile
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port 8000
    envVars:
      DATA_DIR: /var/data
      PROVIDER_MODE: mock
      CORS_ORIGINS: https://yourdomain.com,http://localhost:5173
      MODEL_API_KEY: ${secrets.MODEL_API_KEY}
    dockerfilePath: ./backend/Dockerfile
    # Persistent disk 5GB+ at /var/data for SQLite + uploads
    # Ensure proxy_buffering off in your Render dashboard for SSE
```

## Railway

```yaml
# railway.json
{
  "services": {
    "backend": {
      "name": "auditlens",
      "dockerfile": "./backend/Dockerfile",
      "runCommand": "uvicorn app.main:app --host 0.0.0.0 --port 8000",
      "env": {
        "DATA_DIR": "/data",
        "PROVIDER_MODE": "mock",
        "CORS_ORIGINS": "https://yourdomain.com,http://localhost:5173",
        "MODEL_API_KEY": "${MODEL_API_KEY}"
      }
    }
  }
}
```

## Render/Railway SSE Fix

When running behind a reverse proxy (Render, Railway, Cloudflare, Nginx), **disable response buffering** so Server-Sent Events (SSE) stream in real time:

```nginx
location /api/audits/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding off;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
}
```

In Render dashboard: set `CORS_ORIGINS` env var. In Railway: same.

## Data Persistence

Both Render and Railway offer **persistent disks** that survive container restarts. Mount at `/app/data` (Dockerfile) or `/data` (docker-compose) and set `DATA_DIR` accordingly.

Example Render persistent disk:
- 5 GB+ storage
- Mount path: `/var/data`
- Environment variable: `DATA_DIR=/var/data`

## Development Quickstart (Docker Compose)

```bash
docker compose up --build
```
Mounts `./data` to `/data` with persistent SQLite and file uploads, and configures `CORS_ORIGINS=*`.

## Health Check

Endpoint: `GET /api/health`

Response shows only `provider_mode` and `demo_mode` — **never** any API key material.

```json
{
  "provider_mode": "mock",
  "demo_mode": "replay",
  "message": "OK"
}
```
