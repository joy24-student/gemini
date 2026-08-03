# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 – builder: compile wheels for all C-extension dependencies
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install only what's needed to compile C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and wheel toolchain
RUN pip install --upgrade pip wheel setuptools

# Copy requirements first (Docker layer caching)
COPY requirements.txt .

# Build wheels — curl_cffi and orjson need compilation
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt \
    # Add server extras
    && pip wheel --no-cache-dir --wheel-dir /wheels \
        fastapi>=0.111.0 \
        "uvicorn[standard]>=0.30.0" \
        websockets>=12.0


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 – runtime: minimal image with pre-built wheels
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Gemini Unofficial API" \
      description="Production-grade unofficial Gemini client REST API server" \
      version="1.0.0"

# Runtime system libs only (curl_cffi needs libcurl)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcurl4 \
        libssl3 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root application user
RUN groupadd --system gemini && useradd --system --gid gemini --no-create-home gemini

WORKDIR /app

# Install pre-built wheels from builder (no internet needed in runtime stage)
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl \
    && rm -rf /wheels

# Copy application source
COPY gemini_client/ ./gemini_client/
COPY api/             ./api/
COPY server.py        ./server.py
COPY setup.py         ./setup.py

# Install the package itself (editable so imports work correctly)
RUN pip install --no-cache-dir -e . --no-deps

# Create writable directories for cookies and memory persistence
RUN mkdir -p /data/memory /data/sessions \
    && chown -R gemini:gemini /app /data

# Drop privileges
USER gemini

# Runtime environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    GEMINI_DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8000 \
    WORKERS=1

VOLUME ["/data"]

EXPOSE 8000

# Health check — hits the /health/live endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

# Default: run the uvicorn ASGI server
CMD ["python", "-m", "uvicorn", "gemini_client.server.app:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", \
     "--loop", "asyncio", \
     "--log-level", "info", \
     "--access-log"]
