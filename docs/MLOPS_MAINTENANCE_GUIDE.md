# Project Chimera MLOps Maintenance Guide

**Document Version**: V1.0
**Created Date**: 2025-10-07
**Author**: CLI 4 (The Lab)
**Status**: ✅ Production Ready
**Target Audience**: Maintenance Team, DevOps, SRE

---

## Executive Summary

This guide provides comprehensive instructions for maintaining Project Chimera's AI/LLM infrastructure. It covers LLM adapter management, prompt versioning, monitoring, troubleshooting, and operational procedures.

**Key Responsibilities**:
- Monitor LLM API health and performance
- Manage prompt versions and rollbacks
- Handle JSON parsing failures
- Optimize LLM costs and latency
- Ensure compliance with Riot Games policies

**Critical Metrics**:
- JSON Parsing Success Rate: Target ≥ 98%
- LLM Response Time (P95): Target ≤ 5 seconds
- LLM Cost per Analysis: Target ≤ $0.05
- Compliance Violation Rate: Target = 0%

---

## 1. System Architecture Overview

### 1.1 AI/LLM Component Map

```
┌─────────────────────────────────────────────────────────────┐
│                   CLI 2: Backend Orchestrator               │
│                   (analyze_team_task)                       │
└───────────────┬─────────────────────────────────────────────┘
                │
                ├─ Mode Detection (v23_multi_mode_analysis)
                │  └─ detect_game_mode(queue_id) → GameMode
                │
                ├─ Scoring Algorithms
                │  ├─ SR: V2.2 Evidence-Grounded
                │  ├─ ARAM: V1-Lite (aram_v1_lite.py)
                │  └─ Arena: V1-Lite (arena_v1_lite.py) ⚠️ Compliance-Critical
                │
                ├─ LLM Adapter (src/adapters/gemini_llm.py)
                │  ├─ Model: gemini-2.0-flash-exp (default)
                │  ├─ Fallback: gemini-2.5-pro (if Flash fails)
                │  ├─ Prompt Injection: Dynamic variable replacement
                │  └─ Output Validation: JSON schema enforcement
                │
                ├─ Prompt Templates (src/prompts/)
                │  ├─ v22_sr_evidence_grounded.txt (SR)
                │  ├─ v23_aram_analysis.txt (ARAM)
                │  └─ v23_arena_analysis.txt (Arena) ⚠️ Compliance-Critical
                │
                └─ Observability (src/core/observability.py)
                   ├─ Structlog: Structured logging
                   ├─ Sentry: Error tracking
                   └─ Metrics: LLM performance tracking
```

### 1.2 Data Flow

```
User → Discord → CLI 3 → Celery Task Queue → CLI 2
                                                  │
                                                  ├─ Riot API (Match-V5, Timeline)
                                                  ├─ Scoring Algorithm (Python)
                                                  ├─ LLM Adapter (Gemini)
                                                  │   ├─ Load Prompt Template
                                                  │   ├─ Inject Variables
                                                  │   ├─ Call Gemini API
                                                  │   └─ Parse JSON Response
                                                  │
                                                  └─ Pydantic Validation
                                                      └─ Discord Response
```

---

## 2. LLM Adapter Management

### 2.1 Configuration

**File**: `src/adapters/gemini_llm.py`

**Environment Variables**:

```bash
# Gemini API Configuration
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.0-flash-exp  # Default model
GEMINI_FALLBACK_MODEL=gemini-2.5-pro  # Fallback for critical failures
GEMINI_TEMPERATURE=0.3  # Lower = more deterministic
GEMINI_MAX_OUTPUT_TOKENS=2048  # Max response length
GEMINI_TIMEOUT=10  # API timeout in seconds

# Fallback Configuration (V2.4)
GEMINI_REVIEW_FALLBACK_PRO=1  # Enable Flash→Pro fallback
GEMINI_FALLBACK_THRESHOLD=0.7  # Confidence threshold for fallback

# Rate Limiting
GEMINI_RATE_LIMIT_RPM=60  # Requests per minute
GEMINI_RATE_LIMIT_TPM=100000  # Tokens per minute
```

**Model Selection Strategy**:

| Scenario | Model | Rationale |
|----------|-------|-----------|
| **Default** | `gemini-2.0-flash-exp` | Fast, cost-effective, good quality |
| **Fallback** | `gemini-2.5-pro` | Higher quality, used when Flash fails |
| **Critical (Arena)** | `gemini-2.5-pro` (optional) | Compliance-critical analysis |

---

### 2.2 Prompt Template Management

**Location**: `src/prompts/`

**Versioning Scheme**:
- `v22_sr_evidence_grounded.txt` → Version 2.2, Summoner's Rift
- `v23_aram_analysis.txt` → Version 2.3, ARAM
- `v23_arena_analysis.txt` → Version 2.3, Arena

**Prompt Structure** (Universal Pattern):

```
[1. Role Definition]
你是一位专业的{mode}模式分析教练

[2. Mode Characteristics]
{mode}模式特点：
- 特点1
- 特点2

[3. Input Data]
## 玩家表现数据
{summoner_name}, {champion_name}, {overall_score}, ...

[4. Task Requirements]
请为玩家生成{mode}模式专用分析

[5. Output Format (JSON Schema)]
```json
{
  "analysis_summary": "...",
  "improvement_suggestions": [...]
}
```

[6. Analysis Focus]
具体分析要点...

[7. Prohibited Content]
❌ 禁止提及以下内容...

[8. Examples]
良好示例 vs 不良示例
```

**Prompt Loading**:

```python
# src/adapters/gemini_llm.py
def load_prompt_template(mode: str) -> str:
    """Load prompt template for specified mode."""
    prompt_map = {
        "SR": "src/prompts/v22_sr_evidence_grounded.txt",
        "ARAM": "src/prompts/v23_aram_analysis.txt",
        "Arena": "src/prompts/v23_arena_analysis.txt",
    }

    with open(prompt_map[mode], "r", encoding="utf-8") as f:
        return f.read()


def inject_variables(template: str, **variables) -> str:
    """Inject variables into prompt template."""
    return template.format(**variables)
```

**Example Usage**:

```python
# In CLI 2's analyze_team_task
template = load_prompt_template("ARAM")
prompt = inject_variables(
    template,
    summoner_name="Player1",
    champion_name="Ezreal",
    overall_score=85.3,
    teamfight_metrics_json=json.dumps(teamfight_metrics.dict()),
    build_adaptation_json=json.dumps(build_adaptation.dict()),
    # ... other variables
)

response = gemini_adapter.generate(prompt)
```

---

### 2.3 Prompt Versioning & Rollback

**Version Control**: All prompts are stored in Git (under `src/prompts/`)

**Rollback Procedure**:

1. **Identify Issue**:
   - Monitor Sentry for JSON parsing failures
   - Check user feedback for quality issues

2. **Rollback Decision**:
   - If JSON parsing success rate < 95% for 24 hours: **Rollback**
   - If user reports > 5 critical quality issues: **Investigate + Rollback**

3. **Execute Rollback**:
   ```bash
   # Revert prompt file to previous version
   git log src/prompts/v23_aram_analysis.txt
   git checkout <commit-hash> src/prompts/v23_aram_analysis.txt

   # Commit rollback
   git commit -m "Rollback ARAM prompt to v23.1 due to parsing failures"
   git push

   # Deploy
   ./deploy.sh production
   ```

4. **Post-Rollback**:
   - Monitor metrics for 24 hours
   - Investigate root cause of original issue
   - Fix issue in new prompt version

**Versioning Best Practices**:

- **Semantic Versioning**: `v{major}.{minor}.{patch}`
  - Major: Algorithm redesign (e.g., V1 → V2)
  - Minor: Feature addition (e.g., V2.2 → V2.3)
  - Patch: Bug fixes (e.g., V2.3.0 → V2.3.1)

- **Change Log**: Maintain `PROMPT_CHANGELOG.md` in `src/prompts/`
  ```markdown
  # Prompt Change Log

  ## v23_aram_analysis.txt

  ### V2.3.1 (2025-10-08)
  - Fixed: JSON parsing issue with multi-line suggestions
  - Updated: Example analysis to clarify build adaptation

  ### V2.3.0 (2025-10-07)
  - Initial: ARAM V1-Lite prompt
  ```

---

### 2.4 JSON Parsing & Validation

**Critical Metric**: JSON Parsing Success Rate ≥ 98%

**Pydantic Schema Enforcement**:

```python
# src/contracts/v23_multi_mode_analysis.py
class V23ARAMAnalysisReport(BaseModel):
    """ARAM analysis report with strict JSON schema."""

    analysis_summary: str = Field(
        ...,
        min_length=100,
        max_length=800,
        description="分析总结（100-800字）"
    )

    improvement_suggestions: list[str] = Field(
        ...,
        min_items=1,
        max_items=3,
        description="改进建议（1-3条，每条50-150字）"
    )

    # Validation
    @field_validator("improvement_suggestions")
    @classmethod
    def validate_suggestion_length(cls, v: list[str]) -> list[str]:
        """Validate each suggestion is 50-150 characters."""
        for suggestion in v:
            if not (50 <= len(suggestion) <= 150):
                raise ValueError(f"Suggestion length must be 50-150 chars: {len(suggestion)}")
        return v
```

**Parsing Flow**:

```python
# src/adapters/gemini_llm.py
def parse_llm_response(response: str, schema: type[BaseModel]) -> BaseModel:
    """Parse LLM response and validate against Pydantic schema."""

    try:
        # Step 1: Extract JSON from response (may contain markdown code fences)
        json_match = re.search(r"```json\n(.*?)\n```", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response  # Assume plain JSON

        # Step 2: Parse JSON
        data = json.loads(json_str)

        # Step 3: Validate with Pydantic
        return schema(**data)

    except json.JSONDecodeError as e:
        # Log parsing failure
        logger.error(
            "JSON parsing failed",
            extra={
                "response": response[:500],
                "error": str(e),
                "schema": schema.__name__,
            }
        )
        sentry_sdk.capture_exception(e)
        raise

    except ValidationError as e:
        # Log validation failure
        logger.error(
            "Pydantic validation failed",
            extra={
                "data": data,
                "errors": e.errors(),
                "schema": schema.__name__,
            }
        )
        sentry_sdk.capture_exception(e)
        raise
```

**Common JSON Parsing Issues**:

| Issue | Symptom | Fix |
|-------|---------|-----|
| **Extra Text** | LLM adds text before/after JSON | Update prompt: "仅输出JSON，不要添加任何解释性文本" |
| **Markdown Fences** | Response wrapped in ` ```json ... ``` ` | Extract JSON using regex (implemented above) |
| **Truncated JSON** | Response exceeds `max_output_tokens` | Increase `GEMINI_MAX_OUTPUT_TOKENS` or shorten prompt |
| **Schema Mismatch** | LLM uses wrong field names | Add examples in prompt showing exact JSON structure |

---

## 3. Monitoring & Observability

### 3.1 Key Metrics

**LLM Performance Metrics** (tracked in Grafana/Sentry):

| Metric | Target | Alert Threshold | Action |
|--------|--------|-----------------|--------|
| **JSON Parsing Success Rate** | ≥ 98% | < 95% for 24h | Investigate prompt/model issue |
| **LLM Response Time (P95)** | ≤ 5s | > 10s for 1h | Check Gemini API status, consider caching |
| **LLM Cost per Analysis** | ≤ $0.05 | > $0.10 | Optimize prompt length, switch to Flash |
| **Compliance Violation Rate** | 0% | > 0 | **IMMEDIATE**: Disable feature, investigate |
| **API Error Rate** | < 1% | > 5% for 30min | Check Gemini API status, enable fallback |

**Structlog Example**:

```python
# src/core/observability.py
logger.info(
    "LLM analysis completed",
    extra={
        "match_id": match_id,
        "mode": game_mode.mode,
        "llm_model": "gemini-2.0-flash-exp",
        "llm_response_time_ms": 3450,
        "llm_tokens_input": 1250,
        "llm_tokens_output": 450,
        "llm_cost_usd": 0.032,
        "json_parsing_success": True,
    }
)
```

---

### 3.2 Sentry Configuration

**Error Tracking**:

```python
# src/core/observability.py
import sentry_sdk

sentry_sdk.init(
    dsn="your_sentry_dsn_here",
    environment="production",
    traces_sample_rate=0.1,  # 10% of transactions
    profiles_sample_rate=0.1,  # 10% of transactions
)

# Custom context for LLM errors
sentry_sdk.set_context("llm", {
    "model": "gemini-2.0-flash-exp",
    "prompt_version": "v23_aram_analysis",
    "temperature": 0.3,
})
```

**Alert Rules** (configured in Sentry):

1. **JSON Parsing Failure** (P1):
   - Condition: > 10 failures in 1 hour
   - Action: Email + Slack alert to on-call engineer

2. **Compliance Violation** (P0 - CRITICAL):
   - Condition: Any Arena Augment win rate detected
   - Action: **Auto-disable feature** + PagerDuty alert

3. **High LLM Latency** (P2):
   - Condition: P95 latency > 10s for 1 hour
   - Action: Slack alert to SRE team

---

### 3.3 Grafana Dashboards

**LLM Health Dashboard**:

```
┌─────────────────────────────────────────────────────────────┐
│ Project Chimera - LLM Health                                │
├─────────────────────────────────────────────────────────────┤
│ JSON Parsing Success Rate (24h)                             │
│ ████████████████████████████████████ 98.5%                  │
│                                                               │
│ LLM Response Time (P95, 1h)                                  │
│ ████████████████████ 4.2s                                    │
│                                                               │
│ LLM Cost per Analysis (24h avg)                              │
│ $0.038                                                        │
│                                                               │
│ Compliance Violations (7d)                                   │
│ 0 ✅                                                          │
└─────────────────────────────────────────────────────────────┘
```

**Queries** (Prometheus):

```promql
# JSON Parsing Success Rate
sum(rate(llm_parsing_success_total[1h])) /
sum(rate(llm_parsing_attempts_total[1h]))

# LLM Response Time P95
histogram_quantile(0.95, rate(llm_response_time_seconds_bucket[1h]))

# LLM Cost per Analysis
sum(rate(llm_cost_usd_total[24h])) /
sum(rate(llm_analysis_total[24h]))
```

---

## 4. Operational Procedures

### 4.1 Prompt Update Procedure

**When to Update Prompts**:
- JSON parsing success rate < 98% for 3+ days
- User feedback indicates quality issues
- New compliance requirements (e.g., Riot policy change)
- Feature additions (e.g., new analysis dimensions)

**Update Workflow**:

1. **Draft New Prompt** (in separate branch):
   ```bash
   git checkout -b prompt-update-aram-v2.3.1
   vim src/prompts/v23_aram_analysis.txt
   ```

2. **Test on Staging**:
   ```bash
   # Deploy to staging
   ./deploy.sh staging

   # Run 100 test analyses
   pytest tests/integration/test_aram_llm_output.py --count=100

   # Check metrics
   - JSON parsing success rate: ____%
   - Average response time: ____s
   - User feedback (manual review): ____
   ```

3. **A/B Test (Optional for Major Changes)**:
   ```python
   # Split traffic 50/50 between old and new prompt
   if random.random() < 0.5:
       prompt = load_prompt_template("ARAM")  # Old
   else:
       prompt = load_prompt_template("ARAM_v2.3.1")  # New

   # Track metrics separately
   ```

4. **Deploy to Production**:
   ```bash
   git commit -m "Update ARAM prompt to v2.3.1: Improve JSON parsing"
   git push origin prompt-update-aram-v2.3.1

   # Code review + approval
   gh pr create --title "ARAM Prompt v2.3.1"

   # Merge + deploy
   git checkout main
   git merge prompt-update-aram-v2.3.1
   ./deploy.sh production
   ```

5. **Monitor Post-Deployment** (24-48 hours):
   - Watch JSON parsing success rate
   - Review Sentry for new errors
   - Check user feedback in Discord

---

### 4.2 Model Switching Procedure

**When to Switch Models**:
- Gemini API releases new model version
- Cost optimization (e.g., Flash → Flash 2.0)
- Quality improvement (e.g., Flash → Pro for critical modes)

**Switching Workflow**:

1. **Update Environment Variable**:
   ```bash
   # staging
   export GEMINI_MODEL=gemini-2.5-pro

   # Restart services
   systemctl restart celery-worker
   ```

2. **Test on Staging** (same as prompt update):
   - Run 100 test analyses
   - Check metrics: parsing rate, latency, cost

3. **Deploy to Production** (if tests pass):
   ```bash
   # Update production config
   vim .env.production
   # GEMINI_MODEL=gemini-2.5-pro

   # Deploy
   ./deploy.sh production
   ```

4. **Cost Monitoring**:
   - Track cost increase (Pro is ~10x more expensive than Flash)
   - If cost > $0.10/analysis: Consider reverting or optimizing prompt

---

### 4.3 Incident Response: JSON Parsing Failures

**Scenario**: JSON parsing success rate drops below 95%

**Response Procedure**:

1. **Immediate Actions** (within 30 minutes):
   - Check Sentry for error patterns
   - Identify which mode/prompt is affected (SR/ARAM/Arena)
   - Sample 10 failed responses manually

2. **Root Cause Analysis** (within 2 hours):
   - **Prompt Issue**: LLM not following JSON format
   - **Model Issue**: Gemini API behavior change
   - **Schema Issue**: Pydantic validation too strict

3. **Mitigation** (within 4 hours):
   - **Quick Fix**: Add JSON extraction fallback (already implemented)
   - **Prompt Fix**: Add stricter output format instructions
   - **Model Rollback**: Switch to previous model version if Gemini update caused issue

4. **Long-Term Fix** (within 1 week):
   - Update prompt with clearer JSON format instructions
   - Add more examples to prompt
   - Consider schema relaxation if validation too strict

**Example Sentry Query**:
```python
# Find recent JSON parsing failures
sentry_sdk.search_events(
    query="error.type:JSONDecodeError",
    timeframe="24h",
    limit=100
)
```

---

### 4.4 Compliance Incident Response

**Scenario**: Arena Augment analysis contains forbidden content (win rates, tier rankings)

**Response Procedure** (⚠️ P0 - CRITICAL):

1. **Immediate Actions** (within 5 minutes):
   ```bash
   # Disable Arena analysis feature
   export ENABLE_ARENA_ANALYSIS=False
   systemctl restart celery-worker

   # Post Discord announcement
   # "Arena 分析功能因技术问题暂时不可用，我们正在修复"
   ```

2. **Investigation** (within 1 hour):
   - Review Sentry log for violation details
   - Identify root cause:
     - LLM hallucination (added win rate data not in prompt)
     - Prompt injection (user manipulated input)
     - Code bug (algorithm accidentally accessed win rate API)

3. **Fix** (within 24 hours):
   - **LLM Hallucination**: Add stronger compliance warnings in prompt
   - **Prompt Injection**: Sanitize user inputs
   - **Code Bug**: Fix code, add regression test

4. **Re-Deployment** (after fix verified):
   - Deploy to staging
   - Run compliance test suite (see V2.4 Compliance Checklist)
   - Manual verification (10+ test cases)
   - Re-enable in production
   - Monitor for 48 hours

5. **Post-Incident**:
   - Write post-mortem report
   - Update compliance checklist if needed
   - Notify Riot Games if violation reached users (transparency)

---

## 5. Cost Optimization

### 5.1 LLM Cost Breakdown

**Gemini Pricing** (as of 2025-10-07):

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Use Case |
|-------|----------------------|------------------------|----------|
| **Flash Exp** | $0.075 | $0.30 | Default (fast, cheap) |
| **Pro** | $1.25 | $5.00 | Fallback (high quality) |

**Typical Analysis Cost**:

```
ARAM Analysis Example:
- Input tokens: 1,250 (prompt + data)
- Output tokens: 450 (analysis_summary + suggestions)

Flash Cost:
= (1,250 / 1,000,000) * $0.075 + (450 / 1,000,000) * $0.30
= $0.00009375 + $0.000135
= $0.00023 (≈ $0.0002)

Monthly Cost (10,000 analyses):
= $0.0002 * 10,000
= $2.00
```

**Cost Optimization Strategies**:

1. **Prompt Length Reduction**:
   - Remove unnecessary examples
   - Use abbreviated field names in JSON input
   - Target: Reduce input tokens by 20% (1,250 → 1,000)

2. **Caching** (for static data):
   - Cache champion/item data (Data Dragon)
   - Cache prompt templates (avoid re-loading)
   - Target: Reduce input tokens by 10%

3. **Batch Processing**:
   - Analyze multiple players in single LLM call (if possible)
   - Target: Reduce cost per analysis by 30%

4. **Model Selection**:
   - Use Flash for 95% of analyses
   - Use Pro only for critical failures or compliance-sensitive modes (Arena)
   - Target: Keep average cost < $0.05/analysis

---

### 5.2 Latency Optimization

**Target**: P95 latency ≤ 5 seconds

**Optimization Strategies**:

1. **Prompt Length Reduction**:
   - Shorter prompts → faster LLM processing
   - Current: ~1,250 tokens input → Target: ~1,000 tokens

2. **Output Token Limiting**:
   ```python
   GEMINI_MAX_OUTPUT_TOKENS=1500  # Down from 2048
   ```
   - Shorter responses → faster generation

3. **Parallel LLM Calls** (if multiple modes):
   ```python
   # Analyze SR and ARAM in parallel
   with ThreadPoolExecutor(max_workers=2) as executor:
       sr_future = executor.submit(analyze_sr, match_data)
       aram_future = executor.submit(analyze_aram, match_data)

       sr_result = sr_future.result()
       aram_result = aram_future.result()
   ```

4. **Async LLM Calls**:
   ```python
   # Use Gemini async API
   response = await gemini_adapter.generate_async(prompt)
   ```

---

## 6. Troubleshooting Guide

### 6.1 Common Issues

#### Issue 1: JSON Parsing Failures

**Symptoms**:
- Sentry errors: `JSONDecodeError`
- User receives: "分析过程中发生错误"

**Diagnosis**:
```bash
# Check Sentry for recent failures
sentry-cli events list --query "error.type:JSONDecodeError" --limit 10

# Sample failed responses
tail -n 100 /var/log/celery/worker.log | grep "JSON parsing failed"
```

**Fixes**:
1. **Prompt Issue**: Update prompt with stricter JSON format instructions
2. **Model Issue**: Switch to Pro model temporarily
3. **Schema Issue**: Relax Pydantic validation

---

#### Issue 2: High LLM Latency

**Symptoms**:
- P95 latency > 10 seconds
- User complaints about slow analysis

**Diagnosis**:
```bash
# Check Grafana dashboard
# Or query Prometheus:
histogram_quantile(0.95, rate(llm_response_time_seconds_bucket[1h]))
```

**Fixes**:
1. **Prompt Length**: Reduce input tokens
2. **Output Tokens**: Lower `max_output_tokens`
3. **Model Switch**: Use Flash instead of Pro
4. **Gemini API Status**: Check https://status.cloud.google.com

---

#### Issue 3: Compliance Violation Detected

**Symptoms**:
- Sentry alert: "COMPLIANCE VIOLATION: Arena analysis contains forbidden pattern"
- Feature auto-disabled

**Diagnosis**:
```bash
# Check Sentry log
sentry-cli events show <event-id>

# Sample violation text
grep "COMPLIANCE VIOLATION" /var/log/celery/worker.log
```

**Fixes**:
1. **LLM Hallucination**: Add stronger compliance warnings in prompt
2. **Code Bug**: Review Arena algorithm for forbidden API calls
3. **Test Suite**: Run compliance test suite to identify gaps

---

### 6.2 Debugging Tools

**CLI Commands**:

```bash
# Test LLM adapter locally
python -c "
from src.adapters.gemini_llm import GeminiAdapter
adapter = GeminiAdapter()
response = adapter.generate('Test prompt')
print(response)
"

# Test prompt template loading
python -c "
from src.adapters.gemini_llm import load_prompt_template
prompt = load_prompt_template('ARAM')
print(prompt[:500])  # First 500 chars
"

# Test JSON parsing
python -c "
from src.contracts.v23_multi_mode_analysis import V23ARAMAnalysisReport
import json
data = json.loads('{...}')  # Your JSON here
report = V23ARAMAnalysisReport(**data)
print(report)
"
```

**Sentry Commands**:

```bash
# Install Sentry CLI
brew install sentry-cli

# List recent events
sentry-cli events list --project project-chimera

# Show event details
sentry-cli events show <event-id>

# Search events
sentry-cli events search "error.type:JSONDecodeError" --limit 10
```

---

## 7. Maintenance Checklist

### 7.1 Daily Tasks

- [ ] Check Grafana dashboard for metric anomalies
- [ ] Review Sentry for new errors (should be < 10/day)
- [ ] Monitor Discord for user feedback
- [ ] Check LLM cost (should be < $50/day for 1,000 analyses)

### 7.2 Weekly Tasks

- [ ] Review JSON parsing success rate (should be ≥ 98%)
- [ ] Review LLM latency trends (P95 should be ≤ 5s)
- [ ] Sample 10 random analyses for quality check
- [ ] Review Riot Games Developer Portal for policy updates

### 7.3 Monthly Tasks

- [ ] Review prompt performance (consider updates)
- [ ] Review model performance (consider upgrades)
- [ ] Cost optimization review (identify savings)
- [ ] Compliance audit (sample 50 Arena analyses)

### 7.4 Quarterly Tasks

- [ ] Full prompt review and update
- [ ] Model evaluation (test new Gemini models)
- [ ] Security audit (check for prompt injection vulnerabilities)
- [ ] Riot Games policy review (update compliance checklist)

---

## 8. Emergency Contacts

### 8.1 Internal Contacts

| Role | Name | Contact | Responsibility |
|------|------|---------|----------------|
| **CLI 4 (Algorithm Designer)** | TBD | TBD | Prompt design, compliance |
| **CLI 2 (Backend Engineer)** | TBD | TBD | LLM adapter, API integration |
| **CLI 3 (SRE)** | TBD | TBD | Monitoring, incident response |
| **On-Call Engineer** | TBD | PagerDuty | 24/7 incident response |

### 8.2 External Contacts

| Service | Contact | Use Case |
|---------|---------|----------|
| **Gemini Support** | https://cloud.google.com/support | API issues, model behavior |
| **Sentry Support** | support@sentry.io | Monitoring issues |
| **Riot Developer Relations** | https://developer.riotgames.com/support | Compliance questions |

---

## 9. Appendices

### Appendix A: LLM Adapter Code Reference

**File**: `src/adapters/gemini_llm.py`

**Key Functions**:

```python
class GeminiAdapter:
    """Adapter for Google Gemini API."""

    def __init__(self, model: str = "gemini-2.0-flash-exp"):
        self.model = model
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def generate(self, prompt: str, temperature: float = 0.3) -> str:
        """Generate response from Gemini API."""
        response = self.client.generate_content(
            prompt=prompt,
            config={
                "temperature": temperature,
                "max_output_tokens": int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", 2048)),
            }
        )
        return response.text

    def generate_with_fallback(self, prompt: str) -> str:
        """Generate with Flash, fallback to Pro if fails."""
        try:
            return self.generate(prompt, model="gemini-2.0-flash-exp")
        except Exception as e:
            logger.warning("Flash failed, falling back to Pro", extra={"error": str(e)})
            return self.generate(prompt, model="gemini-2.5-pro")
```

---

### Appendix B: Prompt Variable Reference

**ARAM Prompt Variables**:

```python
{
    "summoner_name": str,
    "champion_name": str,
    "match_result": Literal["victory", "defeat"],
    "overall_score": float,
    "teamfight_metrics_json": str,  # JSON string
    "build_adaptation_json": str,   # JSON string
    "combat_score": float,
    "teamplay_score": float,
}
```

**Arena Prompt Variables**:

```python
{
    "summoner_name": str,
    "champion_name": str,
    "partner_summoner_name": str,
    "partner_champion_name": str,
    "final_placement": int,
    "overall_score": float,
    "rounds_played": int,
    "rounds_won": int,
    "round_performances_json": str,  # JSON string
    "augment_analysis_json": str,    # JSON string
    "combat_score": float,
    "duo_synergy_score": float,
}
```

---

### Appendix C: JSON Schema Examples

**ARAM Analysis Output**:

```json
{
  "analysis_summary": "本场ARAM比赛你的整体表现优秀...",
  "improvement_suggestions": [
    "在团战中保持后排站位...",
    "优先攻击敌方ADC和法师...",
    "考虑购买水银鞋替换攻速鞋..."
  ]
}
```

**Arena Analysis Output**:

```json
{
  "analysis_summary": "本场Arena比赛你的最终排名为第3名...",
  "improvement_suggestions": [
    "在面对排名靠前的队伍时...",
    "在队友石头人大招进场后...",
    "在落后回合选择符文时..."
  ]
}
```

---

**Document Status**: ✅ Production Ready
**Last Updated**: 2025-10-07
**Next Review**: Monthly (first review: 2025-11-07)
