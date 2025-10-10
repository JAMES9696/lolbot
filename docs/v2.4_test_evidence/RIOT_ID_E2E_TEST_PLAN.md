# Riot ID E2E Test Plan (No RSO Required)

**Date**: 2025-10-07
**Session**: V2.5 E2E Testing - Riot ID Parameter Flow
**Bot Version**: Project Chimera 0.1.0
**Environment**: Development (Personal API Key)

---

## Executive Summary

This test validates the **riot_id parameter fallback path** that allows users to analyze matches **without RSO binding**, using only the Personal Development API Key.

### Key Features Tested
1. ✅ Riot ID parsing (`GameName#TAG`)
2. ✅ Account-V1 PUUID resolution
3. ✅ HTTP Match-V5 match history fetch
4. ✅ Async analysis task dispatch
5. ✅ Webhook delivery (deferred → PATCH)

---

## Prerequisites

- ✅ Bot running (PID 32694)
- ✅ Personal API Key: `RGAPI-590d27b2-b0f1-43ad-ad19-70682562daae`
- ✅ Redis + PostgreSQL + Celery operational
- ✅ Discord commands synced globally

---

## Test Commands

### 1. Individual Match Analysis
```
/analyze match_index:1 riot_id:FujiShanXia#NA1
```

**Expected Flow**:
1. ⏳ Deferred response within 3 seconds
2. 🔍 Account-V1 resolves `FujiShanXia#NA1` → PUUID
3. 📊 Match-V5 fetches match IDs (regional routing: `americas`)
4. 🔄 Celery task analyzes match data
5. 📨 Webhook PATCH updates original message (~30-60s)

**Success Criteria**:
- No "未找到该 Riot ID" error
- Match history count > 0
- Final embed displays analysis results

---

### 2. Team Analysis
```
/team-analyze match_index:1 riot_id:FujiShanXia#NA1
```

**Expected Flow**:
1. ⏳ Deferred response within 3 seconds
2. 🔍 Account-V1 resolves PUUID
3. 📊 Match-V5 fetches match IDs
4. 👥 Celery analyzes all 5 players
5. 📄 Paginated view with team rankings (~60-90s)

**Success Criteria**:
- Mode-aware UI (SR shows vision, ARAM hides vision)
- All 5 players analyzed with relative rankings
- Navigation buttons functional

---

## Known Issues & Mitigations

### Issue 1: Cassiopeia MatchHistory Kwargs Error
**Symptom**: `MatchHistory.__get_query_from_kwargs__() missing 'continent' and 'puuid'`

**Mitigation**: Replaced with HTTP Match-V5 direct call in `riot_api.py:224-271`

---

### Issue 2: Mock PUUID No Match Data
**Symptom**: "当前共有 0 场历史记录" when using bound Mock account

**Mitigation**: Use `riot_id` parameter to query real accounts

---

### Issue 3: Rate Limiting (429)
**Symptom**: `RateLimitError` with Retry-After header

**Mitigation**:
- Personal Key limits: 20 req/s, 100 req/2min
- Bot implements automatic retry with exponential backoff
- If hit, wait suggested duration and retry

---

## Log Monitoring

### Key Log Patterns

**Successful PUUID Resolution**:
```
Account-V1 resolved FujiShanXia#NA1 → {puuid}
```

**Match History Fetch**:
```
Fetched {N} match IDs for {puuid}
```

**Task Dispatch**:
```
Analysis task pushed: user={discord_id}, match={match_id}, task_id={uuid}
```

**Webhook Delivery**:
```
Webhook PATCH completed: {match_id}
```

---

## Regional Routing Map

| Platform | Regional Route | Example Riot ID |
|----------|---------------|-----------------|
| NA1      | americas      | FujiShanXia#NA1 |
| EUW1     | europe        | Player#EUW      |
| KR       | asia          | Player#KR       |
| JP1      | asia          | Player#JP       |
| BR1      | americas      | Player#BR       |

---

## Troubleshooting

### Command Not Showing `riot_id` Parameter
**Solution**: Restart Bot to sync slash commands
```bash
kill <PID>
python -m main
```

### "未找到该 Riot ID"
**Causes**:
- Case sensitivity (use exact case)
- Invalid TAG (must be uppercase: NA1, not na1)
- Non-existent account

**Solution**: Verify Riot ID exists at https://tracker.gg/

### Still Using Bound PUUID
**Cause**: Command executed without `riot_id` parameter

**Solution**: Explicitly provide `riot_id:GameName#TAG`

---

## Test Evidence Location

All screenshots and logs will be archived to:
```
docs/v2.4_test_evidence/RIOT_ID_E2E_*
```

---

## Next Steps After Successful Test

1. ✅ Capture deferred response screenshot
2. ✅ Wait for webhook completion
3. ✅ Capture final analysis embed
4. ✅ Extract relevant log segments
5. ✅ Create completion report

---

**Ready to Execute**: Awaiting user command execution in Discord.
