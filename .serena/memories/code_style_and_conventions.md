# Code Style and Conventions

## Python Version & Type Hints

- **Python 3.12+** required
- **Modern type syntax**: Use `Type | None` instead of `Optional[Type]`
- **Strict typing**: All functions must have type annotations
- **MyPy strict mode**: 100% compliance required
- **No `Any` types**: Use specific types or `TypeVar` for generics

### Type Annotation Examples

```python
# ✅ Correct - Modern syntax
def get_user(user_id: str) -> User | None:
    pass

# ❌ Wrong - Old Optional syntax
def get_user(user_id: str) -> Optional[User]:
    pass

# ✅ Container types must be fully annotated
def process_scores(scores: list[float]) -> dict[str, int]:
    pass

# ❌ Wrong - Bare containers
def process_scores(scores: list) -> dict:
    pass

# ✅ All __init__ methods must return None
def __init__(self, name: str) -> None:
    self.name = name
```

## Async/Await Patterns

- **All I/O operations**: Must be async
- **Database calls**: `await db.method()`
- **HTTP requests**: Use `aiohttp` or `httpx`
- **Redis operations**: Use async client

```python
# ✅ Correct async pattern
async def fetch_match(match_id: str) -> MatchData:
    async with aiohttp.ClientSession() as session:
        response = await session.get(f"/match/{match_id}")
        return await response.json()

# ❌ Wrong - Sync I/O in async function
async def fetch_match(match_id: str) -> MatchData:
    response = requests.get(f"/match/{match_id}")  # BLOCKING!
    return response.json()
```

## Pydantic V2 Models

- **Use Pydantic V2 syntax**: `Field`, `model_validator`, `computed_field`
- **Frozen models**: Use `frozen=True` for immutable data
- **Strict validation**: Enable `strict=True` where appropriate
- **Field aliases**: Use for API field name mapping

```python
from pydantic import BaseModel, Field, computed_field

class PlayerScore(BaseModel, frozen=True):
    """Immutable player score data."""

    player_id: str = Field(..., description="Riot PUUID")
    combat_score: float = Field(..., ge=0.0, le=100.0)
    economic_score: float = Field(..., ge=0.0, le=100.0)

    @computed_field
    @property
    def overall_score(self) -> float:
        """Calculate weighted average score."""
        return (self.combat_score * 0.3 + self.economic_score * 0.25)
```

## Naming Conventions

### Files and Modules
- **Snake_case**: `database_adapter.py`, `match_tasks.py`
- **Descriptive names**: Avoid abbreviations unless standard (e.g., `api`, `db`)

### Classes
- **PascalCase**: `DatabaseAdapter`, `MatchTimeline`, `RSOAdapter`
- **Suffix patterns**:
  - `*Adapter` - External service integrations
  - `*Service` - Business logic services
  - `*Task` - Celery tasks
  - `*Port` - Interface protocols

### Functions and Variables
- **Snake_case**: `fetch_match_data()`, `user_binding`
- **Verb-noun pattern**: `get_user()`, `save_match()`, `calculate_score()`
- **Private methods**: Prefix with `_` (e.g., `_initialize_schema()`)

### Constants
- **SCREAMING_SNAKE_CASE**: `MAX_RETRIES = 3`, `DEFAULT_TIMEOUT = 30`

## Import Organization (isort + ruff)

```python
# Standard library
import asyncio
import logging
from typing import Any

# Third-party
import discord
from pydantic import BaseModel, Field
from redis import asyncio as aioredis

# Local imports (absolute from src)
from src.adapters.database import DatabaseAdapter
from src.contracts.match import MatchTimeline
from src.core.scoring.calculator import ScoreCalculator
```

**Important**: Use absolute imports from `src`, NOT relative imports:
- ✅ `from src.adapters.database import DatabaseAdapter`
- ❌ `from ..adapters.database import DatabaseAdapter`

## Error Handling

- **Specific exceptions**: Catch specific exception types, not bare `except:`
- **Context logging**: Log exceptions with `exc_info=True`
- **Re-raise when appropriate**: Don't swallow exceptions silently

```python
# ✅ Correct error handling
try:
    result = await db.get_match(match_id)
except asyncpg.PostgresError as e:
    logger.error(f"Database error fetching match {match_id}: {e}", exc_info=True)
    raise
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    raise

# ❌ Wrong - Bare except and silent failure
try:
    result = await db.get_match(match_id)
except:
    pass  # Silent failure!
```

## Logging Standards

- **Use structured logging**: Include context (match_id, user_id, etc.)
- **Appropriate log levels**:
  - `DEBUG` - Detailed flow information
  - `INFO` - Important milestones
  - `WARNING` - Unexpected but handled
  - `ERROR` - Failures requiring attention
- **No sensitive data**: Don't log API keys, tokens, passwords

```python
# ✅ Structured logging with context
logger.info(
    f"Starting match analysis",
    extra={
        "match_id": match_id,
        "user_id": user_id,
        "correlation_id": correlation_id,
    }
)

# ❌ Wrong - Unstructured and contains secret
logger.info(f"API call with key {api_key}")
```

## Docstrings

- **Google-style docstrings**: For public functions and classes
- **Type hints preferred**: Docstrings supplement, not replace type hints
- **Include examples**: For complex functions

```python
async def calculate_team_summary(
    player_scores: list[PlayerScore],
) -> TeamSummary:
    """Calculate statistical summary for all players in a match.

    Computes mean, median, and rankings across all scoring dimensions
    to provide context for individual player performance.

    Args:
        player_scores: List of PlayerScore objects for all 10 players

    Returns:
        TeamSummary containing aggregated statistics

    Example:
        >>> scores = [PlayerScore(...), PlayerScore(...)]
        >>> summary = await calculate_team_summary(scores)
        >>> print(summary.avg_combat_score)
        72.5
    """
    pass
```

## Testing Standards

- **Test file naming**: `test_*.py` (e.g., `test_database_adapter.py`)
- **Async test functions**: Use `pytest-asyncio` with `asyncio_mode = "auto"`
- **Mocking**: Use `pytest-mock` for external dependencies
- **Assertions**: Use descriptive assertion messages

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_save_user_binding_success(db_adapter: DatabaseAdapter):
    """Test successful user binding storage."""
    # Arrange
    user_id = "123456789"
    puuid = "test-puuid-123"

    # Act
    result = await db_adapter.save_user_binding(user_id, puuid, "na1")

    # Assert
    assert result is True, "save_user_binding should return True on success"
```

## Configuration Management

- **Pydantic Settings**: All config from environment variables
- **No hardcoded secrets**: Use `.env` files (not committed)
- **Type-safe settings**: Use `Field` with validation

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    discord_bot_token: str = Field(..., alias="DISCORD_BOT_TOKEN")
    riot_api_key: str = Field(..., alias="RIOT_API_KEY")
    database_url: str = Field(..., alias="DATABASE_URL")

    class Config:
        env_file = ".env"
        case_sensitive = False
```

## Code Quality Tools

1. **Ruff** - Linting and formatting (replaces black + isort + flake8)
2. **MyPy** - Static type checking (strict mode)
3. **pytest** - Testing with async support
4. **pre-commit** - Automated quality checks

**Pre-commit hooks** run automatically on commit:
- Trailing whitespace removal
- YAML/JSON/TOML validation
- Ruff linting + formatting
- MyPy type checking (strict)
