# P3 Quick Reference Card

**Print this or keep it open during development!**

---

## Task Submission (1 Liner)

```python
from src.tasks.analysis_tasks import analyze_match_task
from src.contracts.analysis_task import AnalysisTaskPayload

task = analyze_match_task.delay(AnalysisTaskPayload(
    puuid="...", match_id="...", interaction_token="...",
    region="na1", requested_by_discord_id="...", requested_at=datetime.now(UTC)
).model_dump())
```

---

## Result Interpretation

```python
result = task.get(timeout=300)  # Block until complete

if result['success']:
    print(f"✅ Total time: {result['total_duration_ms']}ms")
    print(f"Score saved: {result['score_data_saved']}")
else:
    print(f"❌ Failed at: {result['error_stage']}")
    print(f"Error: {result['error_message']}")
```

---

## Score Tiers

| Score | Tier | Emoji |
|-------|------|-------|
| 95-100 | S+ | 🏆 |
| 85-94 | S | ⭐ |
| 75-84 | A | 💎 |
| 65-74 | B | ✨ |
| 50-64 | C | ⚡ |
| 35-49 | D | 📉 |
| 0-34 | F | ❌ |

---

## Score Dimensions

| Name | Weight | Measures |
|------|--------|----------|
| Combat | 30% | KDA, damage, kills |
| Economy | 25% | CS, gold, items |
| Objectives | 25% | Dragons, Baron, towers |
| Vision | 10% | Wards, control |
| Team | 10% | Assists, teamfights |

---

## Database Query

```python
from src.adapters.database import DatabaseAdapter

db = DatabaseAdapter()
result = await db.get_analysis_result("NA1_4567890123")

if result:
    scores = result['score_data']['player_scores']
    mvp = max(scores, key=lambda p: p['total_score'])
    print(f"MVP: {mvp['summoner_name']} - {mvp['total_score']:.1f}")
```

---

## Error Types

| Error | Behavior | Action |
|-------|----------|--------|
| `RateLimitError` | Auto-retry 3x | Wait, task will retry |
| `RiotAPIError` | No retry | Check API key |
| `ValidationError` | No retry | Fix payload data |
| `DatabaseError` | No retry | Check connection |

---

## Worker Commands

```bash
# Start worker
celery -A src.tasks.celery_app worker --loglevel=info

# Check status
celery -A src.tasks.celery_app inspect active

# Purge queue
celery -A src.tasks.celery_app purge
```

---

## Performance Targets

| Operation | Target | Typical |
|-----------|--------|---------|
| Fetch | <2s | 1.2s |
| Score | <100ms | 50ms |
| Save | <200ms | 120ms |
| **Total** | **<3s** | **1.5s** |

---

## Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Task not running | Worker offline | Start celery worker |
| "No module celery" | Missing dep | `pip install celery[redis]` |
| "Connection refused" | Redis offline | `redis-server` |
| "Rate limit exceeded" | 429 from Riot | Normal, auto-retries |

---

## File Locations

```
src/tasks/analysis_tasks.py      → Main task
src/contracts/analysis_task.py   → Payload/Result
src/adapters/database.py          → match_analytics table
src/core/scoring/calculator.py   → V1 algorithm
docs/P3_CLI1_INTEGRATION_CHECKLIST.md → Full guide
```

---

## Discord Embed Template

```python
from discord import Embed, Color

def create_score_card(player_score):
    embed = Embed(
        title=f"{player_score['summoner_name']}",
        description=f"**Score**: {player_score['total_score']:.1f}/100",
        color=Color.gold() if player_score['total_score'] >= 85 else Color.blue()
    )
    embed.add_field(name="⚔️ Combat", value=f"{player_score['combat_efficiency']:.1f}", inline=True)
    embed.add_field(name="💰 Economy", value=f"{player_score['economic_management']:.1f}", inline=True)
    embed.add_field(name="🎯 Objectives", value=f"{player_score['objective_control']:.1f}", inline=True)
    return embed
```

---

## Testing Command

```bash
python3 -c "
from src.tasks.analysis_tasks import analyze_match_task
from src.contracts.analysis_task import AnalysisTaskPayload
from datetime import datetime, UTC

payload = AnalysisTaskPayload(
    puuid='test_puuid_78chars_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    match_id='NA1_4567890123',
    interaction_token='test',
    region='na1',
    requested_by_discord_id='999999999999999999',
    requested_at=datetime.now(UTC)
)

result = analyze_match_task.delay(payload.model_dump()).get(timeout=300)
print('✅ Success!' if result['success'] else f'❌ Failed: {result[\"error_message\"]}')
"
```

---

## Next Steps (P4)

1. Implement `src/adapters/gemini_llm.py`
2. Extend `analyze_match_task` with LLM stage
3. Add Discord webhook response using `interaction_token`

---

**P3 Status**: ✅ PRODUCTION READY (26/26 checks passed)

**Questions?** See `docs/P3_CLI1_INTEGRATION_CHECKLIST.md`
