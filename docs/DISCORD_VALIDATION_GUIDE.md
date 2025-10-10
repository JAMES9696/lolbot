# Discord Data Validation Guide

**Purpose**: Catch Discord API errors BEFORE sending data in development/testing.

All outbound Discord data (embeds, messages, TTS, webhooks) can be validated locally to prevent common formatting errors, API limit violations, and rendering issues.

---

## Quick Start

### 1. Enable Dev Mode Validation

Add to your `.env` file:

```bash
# Enable validation for ALL Discord data
CHIMERA_DEV_VALIDATE_DISCORD=true

# Optional: Fail fast on validation errors (strict mode)
CHIMERA_DEV_STRICT=true
```

**Behavior**:
- `CHIMERA_DEV_VALIDATE_DISCORD=true`: Logs validation errors/warnings, continues execution
- `CHIMERA_DEV_STRICT=true`: Raises exceptions on validation failures, stops execution

### 2. Test Locally with CLI

```bash
# Test a specific match from database
python scripts/test_discord_embed.py --match-id NA1_4830294840

# Test with mock data
python scripts/test_discord_embed.py --mock

# Run edge case tests
python scripts/test_discord_embed.py --edge-cases

# Test with custom JSON file
python scripts/test_discord_embed.py --json-file my_test_data.json
```

---

## What Gets Validated

### ✅ Automatic Validation (when `CHIMERA_DEV_VALIDATE_DISCORD=true`)

#### 1. **Discord Embeds** (via `DiscordWebhookAdapter`)
- **Title**: Max 256 chars
- **Description**: Max 4096 chars
- **Fields**: Max 25 fields, each with name (256 chars) and value (1024 chars)
- **Footer**: Max 2048 chars
- **Author**: Max 256 chars
- **Total size**: Max 6000 chars across all fields

**Logged output**:
```
✅ Embed validation passed: 2847/6000 chars
⚠️  Warnings:
  - Description near limit: 3900/4096 chars
```

#### 2. **TTS Audio URLs** (via `DiscordAdapter.play_tts_*`)
- **URL length**: Max 2048 chars
- **Protocol**: Should be HTTP/HTTPS
- **Extension**: Should be `.mp3`, `.ogg`, `.wav`, `.m4a`

**Logged output**:
```
✅ TTS URL validation passed: https://cdn.volcengine.com/...
⚠️  Warnings:
  - TTS URL may not be a valid audio file
```

#### 3. **Webhook Payloads** (complete message structure)
- **Content**: Max 2000 chars
- **Components**: Max 5 action rows, max 5 buttons per row
- **Embeds**: Full embed validation (see above)
- **Application ID**: Must be valid snowflake
- **Token**: Must be non-empty

**Logged output**:
```
✅ Webhook payload validation passed: 3245 chars total
```

---

## Manual Validation (Programmatic)

### Example 1: Validate FinalAnalysisReport Data

```python
from src.contracts.analysis_results import FinalAnalysisReport
from src.core.validation import validate_analysis_data

# Your analysis report
report = FinalAnalysisReport(...)

# Validate BEFORE rendering
result = validate_analysis_data(report.model_dump())

if not result.is_valid:
    print(f"❌ Errors: {result.errors}")
if result.warnings:
    print(f"⚠️  Warnings: {result.warnings}")
```

### Example 2: Validate Rendered Embed

```python
from src.core.views.analysis_view import render_analysis_embed
from src.core.validation import validate_embed_strict

# Render embed
embed = render_analysis_embed(analysis_data)

# Validate embed
result = validate_embed_strict(embed)

if not result.is_valid:
    print(f"❌ Embed validation failed:\n{result}")
    # Fix embed before sending
```

### Example 3: Test End-to-End Rendering

```python
from src.core.validation import test_embed_rendering

# One-line validation (data → embed → validation)
success, report = test_embed_rendering(analysis_report.model_dump())

if not success:
    print(f"Failed:\n{report}")
else:
    print(f"Success:\n{report}")
```

### Example 4: Validate Custom Message Payload

```python
from src.core.validation import validate_message_payload

payload = {
    "content": "Match analysis complete!",
    "embeds": [embed.to_dict()],
    "components": [
        {
            "type": 1,  # Action row
            "components": [
                {"type": 2, "style": 3, "label": "有用", "custom_id": "..."},
                # ... more buttons
            ],
        }
    ],
}

result = validate_message_payload(payload)

if not result.is_valid:
    print(f"❌ Invalid payload: {result.errors}")
```

---

## Common Validation Errors

### Error: "Description exceeds limit: 4200/4096 chars"

**Cause**: AI narrative + ASCII card + metadata exceeds Discord's 4096 char limit.

**Fix**:
1. Shorten AI narrative (enforce `max_length=1900` in Pydantic model)
2. Simplify ASCII card layout
3. Use `_clamp()` helper in view renderer

### Error: "Field[3] value exceeds limit: 1100/1024"

**Cause**: Detailed stats field is too long.

**Fix**:
1. Use shorter stat labels
2. Remove less critical stats
3. Split into multiple fields

### Error: "Total embed size exceeds limit: 6200/6000"

**Cause**: Cumulative text across all embed fields is too large.

**Fix**:
1. Remove optional fields (e.g., timeline references)
2. Use shorter footer text
3. Consider splitting into multiple messages

### Warning: "TTS URL may not be a valid audio file"

**Cause**: URL doesn't end with `.mp3`, `.ogg`, `.wav`, or `.m4a`.

**Fix**:
1. Ensure TTS adapter returns proper file extension
2. Verify CDN serves correct MIME type
3. Test URL manually in browser

---

## Integration Points

### Where Validation Happens

| Component | Validation Type | Trigger |
|-----------|----------------|---------|
| `DiscordWebhookAdapter.publish_match_analysis()` | Data + Embed + Payload | Before webhook PATCH |
| `DiscordAdapter.play_tts_in_voice_channel()` | TTS URL | Before FFmpeg playback |
| `scripts/test_discord_embed.py` | All | Manual CLI test |

### Validation Flow Diagram

```
User Request
    ↓
Analysis Task
    ↓
[1] FinalAnalysisReport (Pydantic validation)
    ↓
[2] validate_analysis_data() ← DEV MODE
    ↓
render_analysis_embed()
    ↓
[3] validate_embed_strict() ← DEV MODE
    ↓
Build webhook payload
    ↓
[4] validate_webhook_delivery() ← DEV MODE
    ↓
Send to Discord API
```

---

## Testing Checklist

### Before Committing New Features

```bash
# 1. Enable validation
export CHIMERA_DEV_VALIDATE_DISCORD=true
export CHIMERA_DEV_STRICT=true

# 2. Test with real data
python scripts/test_discord_embed.py --match-id <recent_match>

# 3. Test edge cases
python scripts/test_discord_embed.py --edge-cases

# 4. Check logs for warnings
grep "⚠️" logs/bot.log

# 5. Run integration tests
pytest tests/integration/test_discord_webhook_adapter.py -v
```

### CI/CD Integration

Add to `.github/workflows/quality-gate.yml`:

```yaml
- name: Discord Data Validation
  run: |
    export CHIMERA_DEV_VALIDATE_DISCORD=true
    export CHIMERA_DEV_STRICT=true
    python scripts/test_discord_embed.py --mock
    python scripts/test_discord_embed.py --edge-cases
```

---

## Discord API Limits Reference

### Embed Limits

| Field | Limit | Enforcement |
|-------|-------|-------------|
| Title | 256 chars | Hard (API rejection) |
| Description | 4096 chars | Hard |
| Fields | 25 fields | Hard |
| Field name | 256 chars | Hard |
| Field value | 1024 chars | Hard |
| Footer | 2048 chars | Hard |
| Author | 256 chars | Hard |
| **Total** | **6000 chars** | **Hard** |

### Message Limits

| Field | Limit | Enforcement |
|-------|-------|-------------|
| Content | 2000 chars | Hard |
| Embeds | 10 per message | Hard |
| Components | 5 action rows | Hard |
| Buttons per row | 5 buttons | Hard |

### Other Limits

- **Interaction token TTL**: 15 minutes
- **Webhook rate limit**: 30 requests/minute per webhook
- **TTS rate limit**: Varies by provider (Gemini: 600 RPM)

---

## Troubleshooting

### "Validation passes locally but fails in Discord"

**Possible causes**:
1. Unicode encoding differences (emoji rendering)
2. Mobile vs desktop client rendering
3. ANSI escape codes in code blocks

**Solutions**:
1. Use plain text code blocks (no `ansi` language tag)
2. Test on multiple Discord clients
3. Check for invisible Unicode characters

### "Validation warnings but message sends successfully"

**Expected behavior**: Warnings are informational, not errors.

**Action**: Review warnings and optimize if near limits.

### "DEV_STRICT mode breaks production"

**Never enable in production**:
```bash
# ❌ DO NOT DO THIS IN PRODUCTION
CHIMERA_DEV_STRICT=true

# ✅ Use validation without strict mode
CHIMERA_DEV_VALIDATE_DISCORD=true
CHIMERA_DEV_STRICT=false  # or omit
```

---

## Best Practices

### 1. **Always validate in development**
```bash
# .env.development
CHIMERA_DEV_VALIDATE_DISCORD=true
CHIMERA_DEV_STRICT=true
```

### 2. **Test with real match data**
```bash
# Get recent match ID from logs
grep "match_id" logs/bot.log | tail -1

# Test with that match
python scripts/test_discord_embed.py --match-id <MATCH_ID>
```

### 3. **Monitor validation warnings in production**
```bash
# Check for near-limit warnings
grep "near limit" logs/bot.log

# Review and optimize if frequent
```

### 4. **Use Pydantic constraints proactively**
```python
class FinalAnalysisReport(BaseModel):
    ai_narrative_text: str = Field(
        ...,
        max_length=1900,  # Leave buffer for other embed content
        description="LLM-generated narrative"
    )
```

### 5. **Create regression tests for edge cases**
```python
# tests/test_discord_validation.py

def test_long_narrative_rejection():
    """Ensure ultra-long narratives are rejected."""
    report = FinalAnalysisReport(
        ai_narrative_text="x" * 5000,  # Should fail
        ...
    )
    result = validate_analysis_data(report.model_dump())
    assert not result.is_valid
```

---

## FAQ

**Q: Do I need to enable validation in production?**
A: No. Validation is for development/testing only. Production should rely on Pydantic model constraints and robust error handling.

**Q: What's the performance impact of validation?**
A: Negligible (<5ms per validation). All checks are in-memory string operations.

**Q: Can I customize validation rules?**
A: Yes. Edit `src/core/validation/discord_embed_validator.py` to adjust limits or add custom checks.

**Q: What if Discord changes their API limits?**
A: Update `DISCORD_LIMITS` in `discord_embed_validator.py` and `MESSAGE_LIMITS` in `discord_message_validator.py`.

---

## Related Documentation

- [Discord API Limits](https://discord.com/developers/docs/resources/channel#embed-limits)
- [Pydantic Validation](https://docs.pydantic.dev/latest/concepts/validators/)
- [Project Chimera Testing Guide](./RUNBOOKS.md#testing)

---

## Summary

✅ **What you get:**
- **Pre-flight validation** for all Discord data
- **Detailed error messages** with specific fixes
- **CLI testing tool** for manual verification
- **Automatic logging** of validation results
- **Fail-fast mode** for strict development

✅ **How to use:**
1. Set `CHIMERA_DEV_VALIDATE_DISCORD=true` in `.env`
2. Run `python scripts/test_discord_embed.py --mock`
3. Check logs for validation results
4. Fix any errors before committing

✅ **Best practice:**
- Enable in development/testing
- Disable in production
- Monitor warnings regularly
- Test with real data before deploying
