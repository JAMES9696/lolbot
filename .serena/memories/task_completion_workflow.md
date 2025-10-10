# Task Completion Workflow

## Standard Development Workflow

When completing any development task, follow this sequence:

### 1. Implementation Phase

1. **Read existing code** before making changes
   - Use `get_symbols_overview` for file structure
   - Use `find_symbol` with `include_body=True` for implementation details
   - Never modify code without understanding current implementation

2. **Make code changes**
   - Use symbolic editing tools (`replace_symbol_body`, `insert_after_symbol`)
   - Use regex-based editing (`replace_regex`) for small changes
   - Maintain consistent indentation and style

3. **Update tests** if applicable
   - Add unit tests for new functions
   - Update integration tests for API changes
   - Ensure async tests use `pytest.mark.asyncio`

### 2. Code Quality Checks (Automated via Pre-commit)

**IMPORTANT**: Pre-commit hooks run automatically on `git commit`. If they fail, fix issues and re-commit.

```bash
# Manual pre-commit run (recommended before committing)
poetry run pre-commit run --all-files
```

The hooks will automatically:
1. **Remove trailing whitespace**
2. **Fix end-of-file issues**
3. **Validate YAML/JSON/TOML files**
4. **Run ruff linter** (`--fix` auto-fixes issues)
5. **Run ruff formatter** (formats code)
6. **Run mypy type checker** (strict mode)

### 3. Manual Verification Steps

Even with pre-commit hooks, manually verify:

```bash
# 1. Type checking (strict mode)
poetry run mypy src/ --config-file=pyproject.toml

# Expected: Success: no issues found in X source files

# 2. Run relevant tests
poetry run pytest tests/unit/test_your_feature.py -v

# Expected: All tests pass

# 3. Integration test (if applicable)
poetry run pytest tests/integration/ -v
```

### 4. Functional Testing

For backend changes involving:

**RSO/OAuth**:
```bash
# Start bot and test /bind command
poetry run python main.py
# In Discord: /bind
# Verify OAuth flow completes and user is stored in DB
```

**Celery Tasks**:
```bash
# Terminal 1: Start Celery worker
poetry run celery -A src.tasks.celery_app worker --loglevel=info

# Terminal 2: Start bot
poetry run python main.py

# In Discord: /讲道理
# Monitor Celery logs for task execution
```

**Database Changes**:
```bash
# Create migration
poetry run alembic revision --autogenerate -m "add ab_testing tables"

# Review generated migration in alembic/versions/
# Apply migration
poetry run alembic upgrade head

# Verify schema
psql -U user -d lolbot -c "\dt"
```

### 5. Documentation Updates

Update relevant docs when:
- Adding new features → Update README.md
- Changing API → Update docstrings
- Modifying config → Update .env.example
- Adding tables → Document schema in memory

### 6. Git Commit

```bash
# Stage changes
git add .

# Commit (pre-commit hooks run automatically)
git commit -m "feat: implement 10-player team analysis"

# If pre-commit fails, fix issues and re-run
git add .
git commit -m "feat: implement 10-player team analysis"
```

### 7. Final Checklist

Before marking task as complete:

- [ ] ✅ Code compiles without errors
- [ ] ✅ All pre-commit hooks pass
- [ ] ✅ MyPy strict mode passes (no type errors)
- [ ] ✅ Unit tests pass with >80% coverage
- [ ] ✅ Integration tests pass (if applicable)
- [ ] ✅ Manual functional testing successful
- [ ] ✅ Documentation updated
- [ ] ✅ Changes committed to git
- [ ] ✅ No sensitive data (API keys, tokens) in code

## Common Issues & Resolutions

### MyPy Errors

**Duplicate module discovery**:
```
error: Source file found twice under different module names
```
**Fix**: Ensure imports use `from src.module` (not `from module`)

**Missing type stubs**:
```
error: Library stubs not installed for "discord"
```
**Fix**: Add to `.pre-commit-config.yaml` under mypy `additional_dependencies`

### Ruff Errors

**Import sorting issues**:
```bash
# Auto-fix with ruff
poetry run ruff check src/ --fix
```

**Line too long**:
```bash
# Auto-format with ruff
poetry run ruff format src/
```

### Test Failures

**Async test not running**:
```python
# Ensure decorator is present
@pytest.mark.asyncio
async def test_my_async_function():
    pass
```

**Database connection errors in tests**:
```python
# Use test database or mock
@pytest.fixture
async def db_adapter():
    adapter = DatabaseAdapter()
    # Use test database URL
    await adapter.connect()
    yield adapter
    await adapter.disconnect()
```

## Performance Considerations

When implementing new features:

1. **Database queries**: Use connection pooling (already configured)
2. **Riot API calls**: Respect rate limits (use Cassiopeia built-in handling)
3. **Celery tasks**: Set appropriate timeouts (`CELERY_TASK_TIME_LIMIT`)
4. **LLM calls**: Monitor token usage and costs
5. **Memory usage**: Avoid loading entire datasets into memory

## Observability

Add structured logging for important operations:

```python
logger.info(
    "Team analysis started",
    extra={
        "match_id": match_id,
        "player_count": len(players),
        "correlation_id": correlation_id,
    }
)
```

Use `@llm_debug_wrapper` for LLM-related functions to track:
- Input/output tokens
- Latency
- Cost
- Error rates
