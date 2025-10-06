# Project Chimera - LoL Discord Bot

An AI-powered League of Legends Discord bot with deep match analysis capabilities.

## Architecture

This project follows hexagonal architecture with clear separation of concerns:

- **Core**: Business logic and domain models
- **Adapters**: External integrations (Riot API, Database, etc.)
- **Contracts**: Pydantic models for data validation
- **API**: Discord bot interfaces

## Setup

1. Install dependencies:
```bash
poetry install
```

2. Configure environment variables in `.env`:
```
RIOT_API_KEY=your_production_key
DISCORD_TOKEN=your_bot_token
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
```

3. Run the bot:
```bash
poetry run python -m src.main
```

## Development

- Run tests: `poetry run pytest`
- Type checking: `poetry run mypy src`
- Linting: `poetry run ruff check src`
- Formatting: `poetry run black src`
