# Suggested Commands for Development

## Package Management (Poetry)

```bash
# Install dependencies
poetry install

# Add new dependency
poetry add <package-name>

# Update dependencies
poetry update

# Activate virtual environment
poetry shell
```

## Code Quality (Pre-commit Hooks)

```bash
# Install pre-commit hooks
poetry run pre-commit install

# Run hooks manually on all files
poetry run pre-commit run --all-files

# Run specific hook
poetry run pre-commit run ruff --all-files
poetry run pre-commit run mypy --all-files
```

## Linting & Formatting

```bash
# Run ruff linter with auto-fix
poetry run ruff check src/ --fix

# Run ruff formatter
poetry run ruff format src/

# Run MyPy type checking (STRICT MODE)
poetry run mypy src/ --config-file=pyproject.toml

# Alternative: Run mypy on specific file
poetry run mypy src/adapters/database.py
```

## Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage report
poetry run pytest --cov=src --cov-report=term-missing

# Run specific test file
poetry run pytest tests/unit/test_database_adapter.py

# Run async tests (already configured in pytest.ini)
poetry run pytest tests/unit/tasks/test_match_tasks.py

# Run integration tests
poetry run pytest tests/integration/
```

## Running the Application

```bash
# Main Discord bot
poetry run python main.py

# Celery worker (for async tasks)
poetry run celery -A src.tasks.celery_app worker --loglevel=info

# Celery worker with auto-reload (development)
poetry run watchmedo auto-restart --directory=./src --pattern=*.py --recursive -- celery -A src.tasks.celery_app worker --loglevel=debug
```

## Database Operations

```bash
# Create database migration (Alembic)
poetry run alembic revision --autogenerate -m "migration message"

# Apply migrations
poetry run alembic upgrade head

# Rollback migration
poetry run alembic downgrade -1

# View migration history
poetry run alembic history
```

## Development Utilities

```bash
# Run Jupyter notebook for data exploration
poetry run jupyter notebook notebooks/

# Check logs
tail -f chimera_bot.log

# Monitor Redis
redis-cli MONITOR

# PostgreSQL CLI
psql -U user -d lolbot
```

## Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Edit environment variables
# Then fill in:
# - DISCORD_BOT_TOKEN
# - RIOT_API_KEY (Production key for RSO)
# - SECURITY_RSO_CLIENT_ID
# - SECURITY_RSO_CLIENT_SECRET
# - DATABASE_URL
# - REDIS_URL
# - GEMINI_API_KEY (optional)
# - TTS_API_KEY (optional)
```

## Git Workflow

```bash
# Create feature branch
git checkout -b feature/v1.2-team-analysis

# Stage changes
git add .

# Commit (pre-commit hooks will run automatically)
git commit -m "feat: implement 10-player data fetching"

# Push to remote
git push origin feature/v1.2-team-analysis
```

## macOS-Specific (Darwin) Commands

```bash
# Use ripgrep for fast code search
rg "pattern" src/

# Use fd for file finding
fd "database" src/

# Monitor file changes
fswatch -o . | xargs -n1 -I{} echo "Files changed"

# Check running processes
ps aux | grep "celery\|python"

# Kill process by port
lsof -ti:3000 | xargs kill -9
```

## Task Completion Checklist

After implementing a feature:

1. ✅ Run linter: `poetry run ruff check src/ --fix`
2. ✅ Run formatter: `poetry run ruff format src/`
3. ✅ Type check: `poetry run mypy src/`
4. ✅ Run tests: `poetry run pytest --cov=src`
5. ✅ Commit changes (pre-commit will auto-run)
6. ✅ Update documentation if needed
