# Project Chimera - AI-Powered LoL Discord Bot

> 🎮 An intelligent gaming companion and community analyst for League of Legends, powered by Riot Games API, Gemini AI, and advanced data analytics.

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Quality Standards](#quality-standards)
- [Observability](#observability)
- [API Documentation](#api-documentation)
- [Contributing](#contributing)

## Overview

Project Chimera is a sophisticated Discord bot that goes beyond basic data queries. It leverages:

- **Riot Games API (Match-V5 Timeline)** for deep match analysis
- **LLM (Gemini)** for intelligent insights and personality
- **TTS (豆包)** for emotional voice responses
- **PostgreSQL & Redis** for data persistence and caching
- **Hexagonal Architecture** for clean, maintainable code

### Core Features

- 🏆 **Data-driven Post-Match Scoring System**: Comprehensive performance evaluation
- 🧠 **"/讲道理" (AI Data Judge)**: Deep analysis with personality-driven insights
- 🎭 **Emotional TTS Integration**: Context-aware voice responses
- 📊 **Advanced Analytics**: Timeline analysis, pattern recognition, and trend detection

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Discord Users                       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                  Discord Bot Layer                      │
│                   (discord.py)                          │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                Hexagonal Architecture                    │
│  ┌───────────────────────────────────────────────────┐  │
│  │                  Core Domain                      │  │
│  │  • Scoring Algorithm                              │  │
│  │  • Business Logic                                 │  │
│  │  • Permission Management                          │  │
│  └───────────────────────────────────────────────────┘  │
│                         ▲                                │
│                         │                                │
│  ┌──────────────┬───────┴────────┬─────────────────┐   │
│  │   Adapters   │   Contracts    │      Ports      │   │
│  │              │                │                  │   │
│  │ • Riot API   │ • Data Models  │ • Interfaces    │   │
│  │ • LLM/TTS    │ • DTOs         │ • Protocols     │   │
│  │ • Database   │ • Schemas      │                  │   │
│  │ • Redis      │                │                  │   │
│  └──────────────┴────────────────┴─────────────────┘   │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Infrastructure Services                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ PostgreSQL  │  │    Redis    │  │   Celery    │    │
│  │   (Data)    │  │   (Cache)   │  │   (Queue)   │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Poetry (package manager)
- Riot API Key (Production recommended)
- Discord Bot Token

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/your-org/project-chimera.git
cd project-chimera

# Install dependencies with Poetry
poetry install

# Setup pre-commit hooks
poetry run pre-commit install
```

### 2. Configure Environment

Create a `.env` file:

```env
# API Keys
RIOT_API_KEY=RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
DISCORD_BOT_TOKEN=your-discord-bot-token
GEMINI_API_KEY=your-gemini-api-key
TTS_API_KEY=your-doubao-tts-key

# Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=chimera_db
POSTGRES_USER=chimera_user
POSTGRES_PASSWORD=chimera_secure_password_2024

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=chimera_redis_password_2024

# Application Settings
LOG_LEVEL=INFO
ENVIRONMENT=development
```

### 3. Start Infrastructure

```bash
# Start PostgreSQL and Redis
docker-compose up -d

# Verify services are running
docker-compose ps

# Check logs if needed
docker-compose logs -f postgres redis
```

### 4. Run the Bot

```bash
# Activate virtual environment
poetry shell

# Run database migrations (if any)
# python -m src.migrations.migrate

# Start the bot
python -m src.main
```

## Development Setup

### Code Quality Tools

The project enforces strict code quality standards:

```bash
# Format code with Ruff
poetry run ruff format src/ tests/

# Lint code with Ruff
poetry run ruff check src/ tests/ --fix

# Type check with MyPy
poetry run mypy src/

# Run all pre-commit hooks
poetry run pre-commit run --all-files

# Run tests
poetry run pytest
```

### Development Tools Access

When running with `docker-compose --profile dev up`:

- **Adminer** (PostgreSQL UI): <http://localhost:8080>
  - Server: `postgres`
  - Username: `chimera_user`
  - Password: `chimera_secure_password_2024`
  - Database: `chimera_db`

- **Redis Commander**: <http://localhost:8081>
  - Username: `admin`
  - Password: `admin_dev_2024`

## Project Structure

```
project-chimera/
│
├── src/
│   ├── __init__.py
│   ├── core/                   # Domain logic (no external dependencies)
│   │   ├── __init__.py
│   │   ├── observability.py    # llm_debug_wrapper decorator
│   │   ├── scoring.py          # Match scoring algorithms
│   │   └── permissions.py      # Permission management
│   │
│   ├── adapters/               # External service integrations
│   │   ├── __init__.py
│   │   ├── riot_api.py         # Riot API client with rate limiting
│   │   ├── discord_bot.py      # Discord bot implementation
│   │   ├── database.py         # PostgreSQL adapter
│   │   ├── cache.py           # Redis adapter
│   │   ├── llm.py             # Gemini integration
│   │   └── tts.py             # TTS integration
│   │
│   ├── contracts/              # Data contracts and models
│   │   ├── __init__.py
│   │   ├── models.py          # Pydantic models
│   │   └── schemas.py         # Database schemas
│   │
│   └── api/                   # API endpoints (if needed)
│       ├── __init__.py
│       └── endpoints.py
│
├── tests/
│   ├── unit/                  # Unit tests
│   └── integration/           # Integration tests
│
├── infrastructure/
│   └── postgres/
│       └── init.sql          # Database initialization
│
├── docker-compose.yml         # Infrastructure as Code
├── pyproject.toml            # Project configuration
├── .pre-commit-config.yaml   # Pre-commit hooks
└── README.md                 # This file
```

## Quality Standards

### Enforced Principles

- **SOLID**: Single responsibility, open/closed, Liskov substitution, interface segregation, dependency inversion
- **KISS**: Keep it simple, stupid - avoid unnecessary complexity
- **DRY**: Don't repeat yourself - abstract common patterns
- **YAGNI**: You aren't gonna need it - implement only what's required

### Type Safety

All code must pass strict MyPy checks:

```python
# ✅ Good
async def fetch_match(match_id: str) -> MatchData | None:
    ...

# ❌ Bad
async def fetch_match(match_id):  # Missing type hints
    ...
```

### Async Best Practices

```python
# ✅ Good - Proper async context manager
async with RiotAPIAdapter(api_key) as adapter:
    timeline = await adapter.get_match_timeline(match_id)

# ❌ Bad - Blocking in async context
async def bad_example():
    time.sleep(1)  # Never use blocking sleep in async
```

## Observability

### llm_debug_wrapper Decorator

All critical functions and adapters are wrapped with our observability decorator:

```python
from src.core.observability import trace_adapter

@trace_adapter
async def get_match_timeline(self, match_id: str) -> MatchTimeline:
    """This function's inputs, outputs, timing, and errors are automatically logged."""
    ...
```

### Structured Logging Output

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "function_name": "src.adapters.riot_api.get_match_timeline",
  "execution_id": "src.adapters.riot_api.get_match_timeline_1705315845123456",
  "duration_ms": 245.67,
  "args": ["NA1_4812345678"],
  "kwargs": {},
  "result": {
    "match_id": "NA1_4812345678",
    "game_duration": 1823,
    "game_version": "14.1.1"
  }
}
```

## API Documentation

### Core Endpoints

#### `/讲道理` - Deep Match Analysis

Performs comprehensive analysis of a match with AI-powered insights.

**Parameters:**

- `match_id` (required): Riot match identifier
- `summoner_name` (optional): Focus analysis on specific player

**Response:**

- Detailed scoring breakdown
- AI-generated insights
- Emotional tone classification
- Key moments identification

## Contributing

### Development Workflow

1. **Create a feature branch**

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes following our standards**
   - Write tests first (TDD)
   - Ensure all quality checks pass
   - Add appropriate logging with decorators

3. **Run quality checks**

   ```bash
   poetry run pre-commit run --all-files
   poetry run pytest
   ```

4. **Submit a pull request**
   - Clear description of changes
   - Link to related issues
   - Ensure CI/CD passes

### Commit Message Format

```
type(scope): description

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Example:

```
feat(riot-api): implement match timeline caching

- Add Redis caching layer for timeline data
- Implement 1-hour TTL for match data
- Add cache hit/miss metrics

Closes #123
```

## License

This project is proprietary and confidential. All rights reserved.

## Support

For questions or issues:

- Create an issue in the repository
- Contact the development team
- Check the [Wiki](https://github.com/your-org/project-chimera/wiki) for detailed documentation

---

**Built with ❤️ by the Chimera Team**

*"Beyond data, towards understanding"*
