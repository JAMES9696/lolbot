# MyPy Static Check Resolution Plan

## P3 Phase Analysis: Type Safety Convergence

**Date**: 2025-10-06
**Status**: 104 MyPy errors identified
**Priority**: Medium (does not block P3 deliverables)

## Error Categories

### 1. Pydantic Settings Configuration Errors (60+ errors)
**Root Cause**: `src/config/settings.py:104` - Settings instantiation without env vars

```python
# Current (Line 104):
settings = Settings()  # MyPy expects all required fields

# Fix Strategy:
settings = Settings(_env_file=".env", _env_file_encoding="utf-8")
```

**Impact**: Low - Runtime works correctly with Pydantic's env loading
**Resolution**: Update `settings.py` to explicitly pass `_env_file` parameter

### 2. Import Unfollowed Errors (15+ errors)
**Root Cause**: MyPy `strict = true` + `disallow_any_unimported = true`

**Affected Modules**:
- `structlog` (not in mypy stubs)
- Port classes being marked as `Any` due to import paths

**Fix Strategy**:
```ini
# mypy.ini
[mypy-structlog.*]
ignore_missing_imports = True

[mypy-src.core.ports]
follow_imports = "normal"
```

**Impact**: Medium - Affects adapter type safety
**Resolution**: Add type stubs or ignore specific imports

### 3. Pydantic Model Missing Fields (20+ errors)
**Root Cause**: Pydantic models with optional fields not provided in constructors

**Example**: `src/contracts/user_binding.py` - `RiotAccount`, `UserBinding`

**Fix Strategy**:
1. Use `Field(default=None)` for optional fields
2. Update constructors to use keyword arguments with defaults

**Impact**: Low - Pydantic handles defaults at runtime
**Resolution**: Add explicit defaults or use `model_validate()` instead of direct instantiation

### 4. No-Any-Return Errors (10+ errors)
**Root Cause**: `ddragon_adapter.py` returning untyped dict/str from JSON parsing

**Fix Strategy**:
```python
# Before:
async def get_champion_name(self, champion_id: int) -> str | None:
    data = self._cache.get("champions")  # Returns Any
    return data.get("champions", {}).get(str(champion_id), {}).get("name")

# After:
async def get_champion_name(self, champion_id: int) -> str | None:
    data: dict[str, Any] | None = self._cache.get("champions")
    if data and isinstance(data, dict):
        champions: dict[str, Any] = data.get("champions", {})
        champion_data: dict[str, Any] = champions.get(str(champion_id), {})
        name = champion_data.get("name")
        return name if isinstance(name, str) else None
    return None
```

**Impact**: Medium - Affects type inference downstream
**Resolution**: Add explicit type annotations for JSON parsing

## Recommended Approach

### Phase 1: Quick Wins (Immediate)
1. **Fix Settings Instantiation** (1 file, 60+ errors resolved)
   - Update `src/config/settings.py:104` to use `_env_file`

2. **Add Missing Import Ignores** (mypy.ini, 15+ errors resolved)
   ```ini
   [mypy-structlog.*]
   ignore_missing_imports = True
   ```

### Phase 2: Type Safety Improvements (P4 Phase)
1. **DDragon Adapter Refactoring**
   - Add explicit type annotations for JSON parsing
   - Use TypedDict for DDragon API responses

2. **Pydantic Model Defaults**
   - Update all Pydantic models with explicit defaults
   - Use `model_validate()` for dict-to-model conversion

### Phase 3: Strict Mode Refinement (P5 Phase)
1. **Create Type Stubs**
   - Generate `.pyi` stub files for untyped third-party libraries
   - Use `stubgen` for automatic stub generation

2. **Port Interface Typing**
   - Ensure all port implementations have full type coverage
   - Remove `Any` types from adapter interfaces

## MyPy Configuration Tuning

### Current Configuration Issues

```ini
# mypy.ini
[tool.mypy]
strict = true  # Too aggressive for incremental adoption
disallow_any_unimported = true  # Blocks third-party libraries without stubs
```

### Recommended Progressive Strictness

```ini
# Phase 1: Basic Type Safety
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
# disallow_any_unimported = false  # Relax for third-party libs
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
mypy_path = "src"
namespace_packages = false

# Phase 2: Add strictness incrementally per module
[tool.mypy-src.core.scoring.*]
strict = true  # New modules start strict

[tool.mypy-src.adapters.*]
disallow_any_unimported = false  # Adapters deal with untyped APIs

# Ignore untyped third-party libraries
[mypy-structlog.*]
ignore_missing_imports = True

[mypy-celery.*]
ignore_missing_imports = True
```

## P3 Phase Decision

**Recommendation**: **Defer comprehensive MyPy fixes to P4 Phase**

**Rationale**:
1. **P3 Core Deliverables Achieved**:
   - ✅ V1 Scoring Algorithm (100% type-safe, 0 MyPy errors)
   - ✅ Unit Tests (23/23 passing)
   - ✅ Task Queue Monitoring (implemented)
   - ✅ Health Check Guide (documented)

2. **MyPy Errors Do Not Block P3**:
   - Errors are in legacy adapters (`ddragon`, `rso`, `config`)
   - New scoring module passes MyPy with `strict = true`
   - Runtime behavior unaffected

3. **Optimal Fix Timing**:
   - P4 Phase includes LLM/TTS adapter implementation
   - Can apply strict typing standards to new adapters
   - Incremental migration of legacy adapters

## Action Items for P4 Phase

### High Priority
- [ ] Fix `settings.py` instantiation (5 min fix, 60 errors resolved)
- [ ] Add `structlog` import ignore (2 min fix, 5 errors resolved)

### Medium Priority
- [ ] Refactor DDragon adapter with explicit types
- [ ] Add Pydantic model defaults for optional fields
- [ ] Update MyPy config for progressive strictness

### Low Priority
- [ ] Generate type stubs for third-party libraries
- [ ] Achieve 100% MyPy compliance across entire codebase

## Monitoring Strategy

**Weekly MyPy Compliance Tracking**:
```bash
# Track error count trend
poetry run mypy src --show-error-codes 2>&1 | rg "Found \d+ errors" | tee -a logs/mypy_history.log
```

**Quality Gate for New Code**:
- All new modules in `src/core/` must pass `mypy --strict`
- Adapter changes require MyPy compliance (warnings allowed)

---

**Conclusion**: P3 Phase successfully established type-safe foundation with scoring module. Comprehensive MyPy compliance deferred to P4 Phase for systematic resolution alongside new adapter development.
