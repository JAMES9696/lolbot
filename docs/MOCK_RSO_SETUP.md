# Mock RSO Setup Guide

**Created**: 2025-10-06
**Purpose**: Test `/bind` command without Production API Key
**Status**: ✅ **Fully Operational**

---

## 📋 Overview

Mock RSO (Riot Sign-On) adapter allows you to test the complete `/bind` command flow without requiring a Production API Key from Riot Games. This is ideal for:

- **Development testing** before Production Key approval
- **Integration testing** of user binding workflows
- **Demo purposes** with pre-configured test accounts

---

## ✅ Test Results

**All Mock RSO tests passed successfully:**

```
✅ Mock RSO adapter initialization
✅ Binding initiation (/bind command)
✅ OAuth callback simulation
✅ Binding completion
✅ Database persistence
✅ Binding retrieval (/profile command)
✅ Re-binding prevention
```

---

## 🔧 Configuration

### 1. Enable Mock RSO

In `.env`:
```bash
# Mock RSO for Development Testing
MOCK_RSO_ENABLED=true
```

### 2. Architecture

The system uses a **factory pattern** to select the appropriate RSO adapter:

- **`MOCK_RSO_ENABLED=true`**: Uses `MockRSOAdapter` (no Production Key needed)
- **`MOCK_RSO_ENABLED=false`**: Uses `RSOAdapter` (requires Production Key)

**Files involved:**
- `src/adapters/mock_rso_adapter.py` - Mock implementation
- `src/adapters/rso_adapter.py` - Real Riot OAuth implementation
- `src/adapters/rso_factory.py` - Factory to select adapter
- `main.py` - Uses factory to create RSO adapter

---

## 📝 Available Test Accounts

Mock RSO comes with 3 pre-configured test accounts:

| Authorization Code | Game Name | Tag Line | Region | PUUID |
|--------------------|-----------|----------|--------|-------|
| `test_code_1` | FujiShanXia | NA1 | NA | `000...` (78 chars) |
| `test_code_2` | TestPlayer | NA1 | NA | `111...` (78 chars) |
| `test_code_3` | DemoSummoner | KR | KR | `222...` (78 chars) |

**Dynamic accounts:** Any code starting with `test_` will generate a dynamic mock account.

---

## 🚀 Usage

### Method 1: Automated Test Script

Run the comprehensive test script:

```bash
poetry run python test_mock_rso.py
```

**What it tests:**
1. Mock RSO adapter initialization
2. Binding initiation (simulates `/bind`)
3. OAuth callback with mock code
4. Database persistence
5. Binding retrieval (simulates `/profile`)
6. Re-binding prevention

### Method 2: Manual Discord Bot Testing

1. **Start the Discord Bot:**
```bash
poetry run python main.py
```

2. **In Discord, run `/bind`:**
- Bot will generate a mock OAuth URL
- URL format: `http://localhost:3000/mock-oauth?state=...&discord_id=...`

3. **Simulate OAuth Callback:**

Since this is mock mode, you need to manually trigger the callback. You have two options:

**Option A: Direct Service Call (Recommended)**

Create a test script or use Python REPL:

```python
import asyncio
from src.adapters.database import DatabaseAdapter
from src.adapters.redis_adapter import RedisAdapter
from src.adapters.rso_factory import create_rso_adapter
from src.core.services.user_binding_service import UserBindingService

async def complete_binding(discord_id: str, state: str, code: str):
    db = DatabaseAdapter()
    await db.connect()
    redis = RedisAdapter()
    await redis.connect()

    rso = create_rso_adapter(redis_client=redis)
    service = UserBindingService(database=db, rso_adapter=rso)

    result = await service.complete_binding(code=code, state=state)
    print(result)

    await db.disconnect()
    await redis.disconnect()

# Use state from /bind response
asyncio.run(complete_binding(
    discord_id="YOUR_DISCORD_ID",
    state="STATE_FROM_BIND_URL",
    code="test_code_1"
))
```

**Option B: HTTP Callback (Manual)**

If you want to test the actual HTTP callback endpoint:

```bash
curl "http://localhost:3000/callback?code=test_code_1&state=STATE_FROM_BIND_URL"
```

4. **Verify with `/profile`:**
- Discord bot will show your bound account

---

## 🔄 Switching Between Mock and Real RSO

### Development Mode (Mock RSO)

`.env`:
```bash
MOCK_RSO_ENABLED=true
```

**Pros:**
- No Production API Key needed
- Instant testing
- Repeatable test scenarios

**Cons:**
- Not real Riot OAuth
- Can't validate actual Riot accounts

### Production Mode (Real RSO)

`.env`:
```bash
MOCK_RSO_ENABLED=false
SECURITY_RSO_CLIENT_ID=your_production_client_id
SECURITY_RSO_CLIENT_SECRET=your_production_client_secret
```

**Pros:**
- Real Riot OAuth flow
- Validates actual player accounts

**Cons:**
- Requires Production API Key approval
- Requires public callback URL

---

## 🐛 Troubleshooting

### Issue: "Mock RSO is enabled" warning not appearing

**Solution:** Check that `.env` has `MOCK_RSO_ENABLED=true` and restart the bot.

### Issue: Validation errors (PUUID too short, summoner name too long)

**Solution:** This was fixed in the current implementation. Mock accounts now use:
- **PUUID**: Exactly 78 characters (Riot standard)
- **Game Name**: Max 16 characters (Riot standard, no spaces)

### Issue: State token invalid/expired

**Solution:** State tokens expire after 10 minutes (TTL=600s). Generate a new `/bind` URL if expired.

### Issue: Database connection errors

**Solution:** Ensure PostgreSQL and Redis are running:

```bash
docker ps | grep chimera
```

Expected output:
```
chimera-postgres (port 5432)
chimera-redis (port 6379)
```

---

## 📊 Implementation Details

### Mock PUUID Generation

```python
# Pre-configured accounts use simple patterns
puuid="0" * 78  # test_code_1
puuid="1" * 78  # test_code_2
puuid="2" * 78  # test_code_3

# Dynamic accounts use UUID-based generation
mock_puuid = (uuid4().hex + uuid4().hex + uuid4().hex)[:78]
```

### Mock OAuth URL Format

```
http://localhost:3000/mock-oauth?state={STATE}&discord_id={DISCORD_ID}&region={REGION}
```

**Parameters:**
- `state`: CSRF protection token (stored in Redis, 10-min TTL)
- `discord_id`: Discord user ID
- `region`: Riot region (e.g., "na1")

### State Validation Flow

1. User runs `/bind` → generates `state` token
2. Token stored in Redis: `rso:state:{state}` → `{discord_id}` (TTL: 600s)
3. OAuth callback validates `state` → retrieves `discord_id`
4. Token deleted after use (one-time token)

---

## 🎯 Next Steps

1. ✅ **Mock RSO Setup Complete**
2. ⏳ **Wait for Production API Key Approval** (1-3 business days)
3. ⏳ **Configure Real RSO OAuth** (once approved)
4. ✅ **Test `/bind` in Discord** (ready with mock)
5. ⏳ **Deploy to Production** (switch to real RSO)

---

## 📝 Related Documentation

- [`docs/RIOT_PORTAL_CONFIG_ALIGNMENT.md`](./RIOT_PORTAL_CONFIG_ALIGNMENT.md) - RSO OAuth requirements
- [`docs/PRODUCTION_API_KEY_APPLICATION.md`](./PRODUCTION_API_KEY_APPLICATION.md) - Production Key application
- [`docs/FINAL_TEST_SUMMARY.md`](./FINAL_TEST_SUMMARY.md) - Overall testing summary

---

**Status**: ✅ **Mock RSO Ready for Testing**
**Created**: 2025-10-06
**Last Updated**: 2025-10-06
