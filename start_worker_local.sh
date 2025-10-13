#!/bin/bash
# Local development startup script for Celery worker

set -e

echo "⚙️  Starting Celery Worker (Local Development Mode)..."
echo "📦 Using Poetry environment"
echo "🗄️  Database: localhost:5432"
echo "📮 Redis: localhost:6379"
echo ""

# Load environment variables from .env
export $(grep -v '^#' .env | xargs)

# Override Docker-specific URLs for local development
export DATABASE_URL="postgresql://chimera_user:chimera_secure_password_2024@localhost:5432/chimera_db"
export REDIS_URL="redis://:chimera_redis_password_2024@localhost:6379"
export CELERY_BROKER_URL="redis://:chimera_redis_password_2024@localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://:chimera_redis_password_2024@localhost:6379/1"

# Prometheus multiproc directory
export PROMETHEUS_MULTIPROC_DIR="./.prom_multiproc"
mkdir -p $PROMETHEUS_MULTIPROC_DIR

echo "✅ Environment configured"
echo "⚙️  Starting worker with 4 concurrency..."
echo ""

poetry run celery -A src.tasks.celery_app worker \
  --loglevel=info \
  --concurrency=4 \
  --hostname=local_worker@%h \
  --queues=matches,ai,default \
  --max-tasks-per-child=1000 \
  --time-limit=300 \
  --soft-time-limit=240
