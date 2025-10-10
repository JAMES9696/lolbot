# P3 → CLI 1 Integration Checklist

**Purpose**: Quick checklist for CLI 1 developers integrating the P3 backend engine for `/讲道理` command.

**Date**: 2025-10-06
**Phase**: P3 Complete → CLI 1 Integration Ready
**Status**: ✅ All P3 deliverables verified

---

## Prerequisites Verification

### 1. Environment Setup
- [ ] Celery installed: `pip install celery[redis]`
- [ ] Redis running: `redis-cli ping` → `PONG`
- [ ] Database initialized: Check `match_analytics` table exists
- [ ] Worker process started: `celery -A src.tasks.celery_app worker --loglevel=info`

**Quick Test**:
```bash
# Terminal 1: Start Redis
redis-server

# Terminal 2: Start Celery Worker
cd /path/to/lolbot
celery -A src.tasks.celery_app worker --loglevel=info

# Terminal 3: Check worker status
celery -A src.tasks.celery_app inspect active
```

---

## Integration Steps

### Step 1: Import Task Contracts
```python
from src.contracts.analysis_task import (
    AnalysisTaskPayload,
    AnalysisTaskResult
)
from src.tasks.analysis_tasks import analyze_match_task
```

### Step 2: Create Task Payload (CLI 1 → CLI 2)
```python
from datetime import datetime, UTC

payload = AnalysisTaskPayload(
    puuid="abc123...",  # 78-char PUUID
    match_id="NA1_4567890123",
    interaction_token="discord_webhook_token_here",  # For P4
    region="na1",
    requested_by_discord_id="123456789012345678",
    requested_at=datetime.now(UTC)
)
```

### Step 3: Submit Task to Queue
```python
# Option A: Fire and forget
task = analyze_match_task.delay(payload.model_dump())

# Option B: Get result (blocks until complete)
result = analyze_match_task.apply_async(
    args=[payload.model_dump()],
    countdown=0  # Execute immediately
).get(timeout=300)  # 5 min timeout

# Option C: Track task ID for later retrieval
task = analyze_match_task.apply_async(args=[payload.model_dump()])
task_id = task.id  # Store this for status checks
```

### Step 4: Handle Results
```python
if result['success']:
    print(f"✅ Analysis complete for {result['match_id']}")
    print(f"Score data saved: {result['score_data_saved']}")
    print(f"Total duration: {result['total_duration_ms']}ms")
else:
    print(f"❌ Analysis failed at stage: {result['error_stage']}")
    print(f"Error: {result['error_message']}")
```

---

## Database Queries (Discord Bot)

### Query 1: Get Latest Analysis for Player
```python
from src.adapters.database import DatabaseAdapter

db = DatabaseAdapter()

# Get most recent analysis
result = await db.get_analysis_result(match_id="NA1_4567890123")

if result:
    score_data = result['score_data']  # JSON object
    player_scores = score_data['player_scores']  # List of 10 players

    for player in player_scores:
        print(f"{player['summoner_name']}: {player['total_score']:.1f}")
```

### Query 2: Get Player's Recent Analyses
```sql
-- Execute via DatabaseAdapter raw query
SELECT
    ma.match_id,
    ma.score_data->'player_scores' AS scores,
    ma.created_at,
    ma.processing_duration_ms
FROM match_analytics ma
WHERE ma.puuid = $1
ORDER BY ma.created_at DESC
LIMIT 10;
```

### Query 3: Find Top Performers in Match
```sql
-- Query JSONB score data
SELECT
    ma.match_id,
    jsonb_array_elements(ma.score_data->'player_scores')->>'summoner_name' AS player,
    (jsonb_array_elements(ma.score_data->'player_scores')->>'total_score')::float AS score
FROM match_analytics ma
WHERE ma.match_id = $1
ORDER BY score DESC;
```

---

## Error Handling Patterns

### Pattern 1: Graceful Degradation
```python
try:
    task = analyze_match_task.delay(payload.model_dump())
    await interaction.followup.send("⏳ Analysis queued! Check back in 30 seconds.")
except Exception as e:
    logger.error(f"Failed to queue task: {e}")
    await interaction.followup.send("❌ Backend unavailable. Try again later.")
```

### Pattern 2: Status Polling
```python
from celery.result import AsyncResult

task_id = "stored_from_step3"
result_obj = AsyncResult(task_id, app=celery_app)

if result_obj.ready():
    result = result_obj.get()
    # Process result
elif result_obj.failed():
    print(f"Task failed: {result_obj.info}")
else:
    print("Task still processing...")
```

### Pattern 3: Retry Detection
```python
result = analyze_match_task.apply_async(args=[payload.model_dump()]).get()

if not result['success'] and result['error_message'] == "Rate limit exceeded":
    # Task will auto-retry up to 3 times with exponential backoff
    # Check task status later
    await interaction.followup.send(
        "⏳ Riot API rate limited. Analysis will retry automatically."
    )
```

---

## Testing Workflow

### Manual Test (No Discord)
```python
# test_p3_integration.py
import asyncio
from datetime import datetime, UTC
from src.contracts.analysis_task import AnalysisTaskPayload
from src.tasks.analysis_tasks import analyze_match_task

async def test_analysis():
    payload = AnalysisTaskPayload(
        puuid="test_puuid_78chars_long_string_here_abc123xyz789_test_puuid_suffix",
        match_id="NA1_4567890123",
        interaction_token="test_token",
        region="na1",
        requested_by_discord_id="999999999999999999",
        requested_at=datetime.now(UTC)
    )

    result = analyze_match_task.delay(payload.model_dump()).get(timeout=300)
    print(result)

if __name__ == "__main__":
    asyncio.run(test_analysis())
```

### Expected Output (Success)
```json
{
  "success": true,
  "match_id": "NA1_4567890123",
  "score_data_saved": true,
  "timeline_cached": true,
  "fetch_duration_ms": 1250.5,
  "scoring_duration_ms": 45.2,
  "save_duration_ms": 120.8,
  "total_duration_ms": 1416.5,
  "error_message": null,
  "error_stage": null
}
```

### Expected Output (Rate Limit - Auto-Retry)
```json
{
  "success": false,
  "match_id": "NA1_4567890123",
  "error_stage": "fetch",
  "error_message": "Rate limit exceeded (Retry-After: 120s)",
  "fetch_duration_ms": 500.0
}
```
**Note**: Task will automatically retry after 120 seconds (Riot's Retry-After header).

---

## Observability

### View Structured Logs
```bash
# All logs are JSON-formatted (non-TTY) or colored (TTY)
tail -f /var/log/celery/worker.log | jq '.event'

# Filter for specific execution
tail -f /var/log/celery/worker.log | jq 'select(.execution_id | contains("analyze_match_task"))'
```

### Key Log Events
1. **Task Entry**: `Executing async function: src.tasks.analysis_tasks.analyze_match_task`
2. **Fetch Start**: `operation: riot_api_fetch`
3. **Scoring Complete**: `Successfully executed: src.core.scoring.calculator.generate_llm_input`
4. **Save Complete**: `Successfully executed: src.adapters.database.DatabaseAdapter.save_analysis_result`
5. **Task Exit**: `Successfully executed: src.tasks.analysis_tasks.analyze_match_task`

### Performance Metrics
All durations are automatically logged:
- `fetch_duration_ms`: Riot API call time
- `scoring_duration_ms`: V1 algorithm execution time
- `save_duration_ms`: Database write time
- `total_duration_ms`: End-to-end task time

---

## Common Issues

### Issue 1: "No module named 'celery'"
**Solution**: Install Celery worker dependencies
```bash
pip install celery[redis] asyncpg cassiopeia
```

### Issue 2: "Connection refused (Redis)"
**Solution**: Start Redis server
```bash
redis-server
# Or via Homebrew service
brew services start redis
```

### Issue 3: "match_analytics table does not exist"
**Solution**: Initialize database schema
```bash
python -c "
import asyncio
from src.adapters.database import DatabaseAdapter
asyncio.run(DatabaseAdapter().initialize_schema())
"
```

### Issue 4: "Task timeout after 300 seconds"
**Solution**: Increase timeout or check worker logs for errors
```python
result = analyze_match_task.apply_async(
    args=[payload.model_dump()]
).get(timeout=600)  # Increase to 10 minutes
```

### Issue 5: "Rate limit exceeded (429)"
**Solution**: This is expected! Task will auto-retry with exponential backoff.
- 1st retry: 60s delay
- 2nd retry: 120s delay
- 3rd retry: 240s delay

Check Celery worker logs for retry status.

---

## Next Steps (P4 Preview)

Once P4 is complete, the workflow will extend to:

1. **LLM Narrative Generation**: Gemini analyzes score data → generates narrative
2. **Discord Webhook Response**: Uses `interaction_token` to send async response
3. **Optional TTS**: Generates audio file for voice channels

**CLI 1 Changes Required for P4**:
- Store `interaction_token` from Discord interaction
- Handle webhook response delivery
- Display LLM narrative in embed format

---

## Support

- **P3 Documentation**: See `docs/P3_COMPLETION_SUMMARY.md`
- **Architecture Guide**: See `docs/ARCHITECTURE.md`
- **Scoring Algorithm**: See `src/core/scoring/README.md`

**Ready for Production**: ✅ All P3 components verified and documented.
