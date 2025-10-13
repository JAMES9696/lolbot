#!/bin/bash
# Local development startup script for Discord bot

set -e

echo "🚀 Starting Discord Bot (Local Development Mode)..."
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

echo "✅ Environment configured"
echo "🎮 Starting bot..."
echo ""

poetry run python main.py
