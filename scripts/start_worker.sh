#!/usr/bin/env bash
# Celery worker startup script for Project Chimera
# This script starts a Celery worker with production-ready configuration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Celery Worker for Project Chimera${NC}"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Please create .env from .env.example and configure your settings"
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

# Check required environment variables
if [ -z "$CELERY_BROKER_URL" ]; then
    echo -e "${RED}Error: CELERY_BROKER_URL not set${NC}"
    exit 1
fi

# Default worker settings
WORKER_NAME="${WORKER_NAME:-chimera_worker}"
CONCURRENCY="${WORKER_CONCURRENCY:-4}"
LOGLEVEL="${WORKER_LOGLEVEL:-info}"
QUEUE="${WORKER_QUEUE:-matches,ai,default}"

echo -e "${YELLOW}Worker Configuration:${NC}"
echo "  Name: $WORKER_NAME"
echo "  Concurrency: $CONCURRENCY"
echo "  Log Level: $LOGLEVEL"
echo "  Queues: $QUEUE"
echo ""

# Configure Prometheus multiprocess directory for Celery workers if not set
if [ -z "$PROMETHEUS_MULTIPROC_DIR" ]; then
  export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-.prom_multiproc}"
fi

# Ensure directory exists and is clean (per prometheus_client docs)
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
find "$PROMETHEUS_MULTIPROC_DIR" -type f -name '*.db' -maxdepth 1 -print -delete >/dev/null 2>&1 || true
echo "Using PROMETHEUS_MULTIPROC_DIR=$PROMETHEUS_MULTIPROC_DIR"

# Start Celery worker
celery -A src.tasks.celery_app worker \
    --loglevel="$LOGLEVEL" \
    --concurrency="$CONCURRENCY" \
    --hostname="$WORKER_NAME@%h" \
    --queues="$QUEUE" \
    --max-tasks-per-child=1000 \
    --time-limit=300 \
    --soft-time-limit=240 \
    --autoscale=10,3 \
    --without-gossip \
    --without-mingle \
    --without-heartbeat
