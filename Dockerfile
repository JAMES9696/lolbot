# 蔚-上城人 Discord Bot - Production Dockerfile
# Multi-stage build for optimized image size

# Stage 1: Builder
FROM python:3.11.10-slim AS builder

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.2 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_VIRTUALENVS_CREATE=true

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install dependencies (without dev dependencies)
RUN poetry install --no-dev --no-root --no-interaction --no-ansi

# Stage 2: Runtime
FROM python:3.11.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app:/app/src" \
    PATH="/app/.venv/bin:$PATH"

# Install runtime dependencies (FFmpeg, libopus for voice features)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libopus-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user (non-root for security)
RUN useradd -m -u 1000 -s /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Copy application code
COPY --chown=appuser:appuser . .

# Create necessary directories
RUN mkdir -p logs static/audio static/builds ddragon_cache opgg_cache .prom_multiproc && \
    chown -R appuser:appuser logs static ddragon_cache opgg_cache .prom_multiproc

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Default command (will be overridden in docker-compose)
CMD ["python", "main.py"]
