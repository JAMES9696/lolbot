# Project Chimera - Project Overview

## Purpose

Project Chimera is an **AI-powered League of Legends Discord bot** that provides deep match analysis using Riot API Match-V5 Timeline data. The bot enables players to:

1. Bind their Riot account to Discord using OAuth (RSO - Riot Sign-On)
2. Request detailed match analysis with AI-generated narratives
3. Get comprehensive scoring across 5 dimensions: Combat, Economic, Vision, Objective, Team Contribution
4. Receive voice narration (TTS) of analysis results (optional)

## Current Phase: V1.2 → V2 Transition

**V1 Status**: ✅ Production-ready backend with RSO integration, basic match analysis, TTS support

**V1.2 Goals** (Current Focus):
- Support RSO production environment validation
- Extend data pipeline from 1 player → 10 players (full team analysis)
- Build A/B testing infrastructure for prompt optimization

**V2 Vision**:
- Team-relative multi-perspective analysis (`/team-analysis`)
- A/B testing framework for prompt engineering
- Advanced analytics and player insights

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│              Discord Bot (Frontend - CLI 1)             │
│         Commands: /bind, /讲道理, /team-analysis       │
└───────────────────────────┬─────────────────────────────┘
                            │
                ┌───────────▼────────────┐
                │   RSO Callback Server  │
                │  (OAuth flow handler)  │
                └───────────┬────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│                  Backend Services (CLI 2)               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Celery Tasks │  │ Match Service│  │ Scoring Algo │ │
│  │  (Async)     │  │  (10 Players)│  │   (V1/V2)    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└───────────────────────────┬─────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌──────▼───────┐  ┌────────▼────────┐
│   PostgreSQL   │  │    Redis     │  │   Riot API      │
│ (User bindings,│  │  (Cache +    │  │ (Match-V5 +     │
│  Match data,   │  │   Celery     │  │  Timeline)      │
│  A/B metadata) │  │   Broker)    │  │                 │
└────────────────┘  └──────────────┘  └─────────────────┘
        │
┌───────▼────────┐  ┌──────────────┐
│  Gemini LLM    │  │  Volcengine  │
│ (AI Narrative) │  │  TTS (Voice) │
└────────────────┘  └──────────────┘
```

## Key Technologies

- **Python 3.12** - Modern type hints and async support
- **Pydantic V2** - Data validation and contracts
- **discord.py 2.3+** - Discord bot framework
- **Cassiopeia** - Riot API client with built-in rate limiting
- **PostgreSQL** - Primary data storage
- **Redis** - Caching and Celery message broker
- **Celery** - Async task queue for long-running analysis
- **SQLAlchemy 2.0** - Async ORM
- **Google Gemini** - LLM for narrative generation
- **Volcengine TTS** - Voice synthesis (optional)

## Project Structure

```
lolbot/
├── src/
│   ├── adapters/         # External service integrations
│   │   ├── database.py       # PostgreSQL adapter
│   │   ├── redis_adapter.py  # Redis client
│   │   ├── rso_adapter.py    # Riot OAuth handler
│   │   ├── riot_api.py       # Riot API client
│   │   ├── discord_adapter.py # Discord bot
│   │   ├── gemini_llm.py     # LLM adapter
│   │   └── tts_adapter.py    # Voice synthesis
│   ├── core/             # Business logic
│   │   ├── scoring/          # Match scoring algorithm
│   │   ├── services/         # Domain services
│   │   └── views/            # Discord UI rendering
│   ├── contracts/        # Pydantic data models
│   │   ├── common.py         # Base models and enums
│   │   ├── timeline.py       # Match timeline structures
│   │   ├── match.py          # Match data models
│   │   └── events.py         # 20+ event types
│   ├── tasks/            # Celery async tasks
│   │   ├── celery_app.py     # Celery configuration
│   │   ├── match_tasks.py    # Match data fetching
│   │   └── analysis_tasks.py # AI analysis pipeline
│   ├── api/              # HTTP endpoints
│   │   └── rso_callback.py   # OAuth callback server
│   ├── config/           # Application settings
│   │   └── settings.py       # Pydantic Settings
│   └── prompts/          # LLM prompt templates
├── tests/                # Test suite
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── docs/                 # Documentation
├── notebooks/            # Data exploration (Jupyter)
├── main.py              # Application entry point
└── pyproject.toml       # Poetry dependencies
```

## Development Philosophy

- **Type Safety First**: 100% MyPy strict mode compliance
- **Async-First**: All I/O operations are async
- **Contract-Driven**: Pydantic models as single source of truth
- **Test Coverage**: Unit + integration tests for critical paths
- **Observability**: Structured logging with correlation IDs
