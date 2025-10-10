# V1.2 Requirements and Current Implementation Status

## V1.2 Mission (CLI 2 - Backend)

Ensure production environment stability and upgrade data pipeline to support:
1. RSO production validation
2. 10-player team analysis (V2 foundation)
3. A/B testing infrastructure

---

## Core Task 1: RSO Production Validation (P0 - Stability)

### Requirements

**Objective**: Ensure production-grade RSO/OAuth integration is stable and monitored.

**Critical Success Criteria**:
- ✅ Production API key properly configured (from environment)
- ✅ RSO OAuth flow completes successfully (`/bind` command)
- ✅ User bindings persisted to `user_bindings` table (Discord ID + Riot PUUID + Region)
- ✅ Real-time monitoring with structured logs (`llm_debug_wrapper`)

### Current Implementation Status

**Implemented** (V1):
- ✅ `RSOAdapter` class with OAuth flow (`src/adapters/rso_adapter.py`)
- ✅ `RSOCallbackServer` HTTP endpoint for callback handling (`src/api/rso_callback.py`)
- ✅ `DatabaseAdapter.save_user_binding()` method
- ✅ Settings management via Pydantic (`src/config/settings.py`)
- ✅ Mock RSO adapter for development (`src/adapters/mock_rso_adapter.py`)

**Configuration Variables** (in `.env`):
```env
SECURITY_RSO_CLIENT_ID=your_production_client_id
SECURITY_RSO_CLIENT_SECRET=your_production_secret
SECURITY_RSO_REDIRECT_URI=http://your-domain.com:3000/callback
RIOT_API_KEY=your_production_api_key
```

**Monitoring Requirements** (V1.2):
- [ ] Add structured logging to RSO callback handler
- [ ] Add database write confirmation logs
- [ ] Monitor `/riot/account/v1/accounts/me` API call success
- [ ] Track authorization code → access token exchange

**Action Items**:
1. Review `src/api/rso_callback.py` for logging completeness
2. Ensure `DatabaseAdapter.save_user_binding()` logs success/failure
3. Add correlation ID tracking for RSO flow
4. Test with production credentials in staging environment

---

## Core Task 2: V2 Team Data Fetching (10 Players + MatchTimeline)

### Requirements

**Objective**: Extend data pipeline from single-player analysis to full team (10 players).

**Data Flow**:
```
User triggers /team-analysis
  ↓
Celery Task: analyze_team_task (NEW)
  ↓
1. Fetch Match Details (Match-V5 API)
   - Extract 10 player PUUIDs
  ↓
2. Fetch MatchTimeline for all 10 players (parallel/batch)
   - Match-V5 Timeline API
  ↓
3. Calculate scores for all 10 players
   - Use existing scoring algorithm
  ↓
4. Store results in PostgreSQL (JSONB fields)
  ↓
5. Generate team-relative analysis (LLM)
  ↓
6. Publish to Discord with feedback buttons
```

### Current Implementation Status

**Existing Components** (V1):
- ✅ `fetch_match_history` Celery task (`src/tasks/match_tasks.py`)
- ✅ `DatabaseAdapter.save_match_data()` - stores match data with JSONB
- ✅ `RiotAPIAdapter` - basic Match-V5 integration (`src/adapters/riot_api.py`)
- ✅ Scoring algorithm for single player (`src/core/scoring/calculator.py`)
- ✅ Contracts for MatchTimeline (`src/contracts/timeline.py`)

**Missing Components** (V1.2):
- [ ] `analyze_team_task` Celery task (NEW)
- [ ] Batch fetching logic for 10 players
- [ ] Cassiopeia integration (recommended for rate limiting)
- [ ] Team summary calculation function
- [ ] Extended database schema for team analysis results

**API Rate Limiting Strategy**:
- **Production Key Quota**: 500 requests per 10 seconds
- **Solution**: Use Cassiopeia client with built-in rate limiting
- **Retry Logic**: Honor `Retry-After` header on 429 responses

**Action Items**:
1. Create `src/tasks/analysis_tasks.py` with `analyze_team_task`
2. Implement parallel MatchTimeline fetching (10 players)
3. Extend `DatabaseAdapter` with team analysis storage methods
4. Add Cassiopeia client wrapper in `RiotAPIAdapter`
5. Write integration test for 10-player data pipeline

---

## Core Task 3: A/B Testing Infrastructure

### Requirements

**Objective**: Enable data-driven prompt engineering through controlled experimentation.

**Components**:
1. **User Cohort Assignment** - Hash-based deterministic assignment (A/B)
2. **Database Schema** - Store experiment metadata and feedback
3. **Feedback Collection** - Discord buttons for user reactions
4. **Analytics Queries** - Compare variant performance

### Database Schema (NEW Tables)

#### 1. `ab_experiment_metadata`
```sql
CREATE TABLE ab_experiment_metadata (
    match_id VARCHAR(255) PRIMARY KEY,
    discord_user_id VARCHAR(255) NOT NULL,
    ab_cohort CHAR(1) CHECK (ab_cohort IN ('A', 'B')),
    variant_id VARCHAR(100),
    prompt_version VARCHAR(50),
    prompt_template VARCHAR(100),
    assignment_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    llm_input_tokens INTEGER,
    llm_output_tokens INTEGER,
    llm_api_cost_usd DECIMAL(10, 6),
    llm_latency_ms INTEGER
);
```

#### 2. `feedback_events`
```sql
CREATE TABLE feedback_events (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(255) REFERENCES match_analytics(match_id),
    discord_user_id VARCHAR(255),
    feedback_type VARCHAR(50),  -- "thumbs_up", "thumbs_down", "star"
    feedback_value INTEGER,
    ab_cohort CHAR(1),
    variant_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (match_id, discord_user_id, feedback_type)
);
```

### Current Implementation Status

**Existing Components**:
- ✅ Database adapter with JSONB support
- ✅ Discord UI rendering (`src/core/views/analysis_view.py`)
- ✅ Celery task infrastructure

**Missing Components** (V1.2):
- [ ] `PromptVariantAssigner` class (hash-based cohort assignment)
- [ ] Database migrations for new tables
- [ ] `AnalysisFeedbackView` Discord UI component (buttons)
- [ ] `DatabaseAdapter.record_feedback_event()` method
- [ ] `DatabaseAdapter.store_ab_experiment_metadata()` method
- [ ] A/B settings in `src/config/settings.py`
- [ ] Integration with `analyze_team_task`

**A/B Testing Flow**:
```python
# In analyze_team_task
assigner = PromptVariantAssigner(seed="2025_q4")
cohort = assigner.assign_variant(user_id)  # "A" or "B"

if cohort == "A":
    narrative = await gemini.generate_v1_narrative(score)
else:
    narrative = await gemini.generate_v2_team_narrative(score, team_summary)

# Store metadata
await db.store_ab_experiment_metadata(
    match_id=match_id,
    discord_user_id=user_id,
    ab_cohort=cohort,
    variant_id=f"v{cohort}_20251006"
)
```

**Action Items**:
1. Create `src/core/ab_testing/variant_assignment.py`
2. Create Alembic migrations for new tables
3. Implement Discord feedback buttons in `src/core/views/`
4. Extend `DatabaseAdapter` with A/B methods
5. Add A/B configuration to settings
6. Write analytics SQL queries for variant comparison

---

## Implementation Priority

### Week 1-2: RSO Production Validation + Database Schema
1. Enhance RSO monitoring and logging
2. Create database migrations for A/B tables
3. Test RSO flow with production credentials

### Week 3-4: Team Data Fetching Pipeline
1. Implement `analyze_team_task` Celery task
2. Add Cassiopeia rate limiting
3. Batch fetch MatchTimeline for 10 players
4. Team summary calculation function

### Week 5-6: A/B Testing Infrastructure
1. Implement cohort assignment logic
2. Create Discord feedback UI components
3. Integrate A/B flow into analysis task
4. Build analytics dashboard queries

---

## Success Metrics

### RSO Validation
- ✅ 100% successful OAuth flows in production
- ✅ User bindings persisted without errors
- ✅ Zero authorization failures

### Team Analysis
- ✅ 10-player data fetched in < 30 seconds
- ✅ Rate limit compliance (no 429 errors)
- ✅ Scoring algorithm works for all players

### A/B Testing
- ✅ 50/50 cohort split achieved
- ✅ Feedback collection rate > 15%
- ✅ Statistical significance achieved (500+ samples per variant)
- ✅ Variant performance tracked and queryable

---

## Known Dependencies

- **Riot Production API Key**: Required for RSO OAuth
- **Cassiopeia Library**: Recommended for rate limiting
- **PostgreSQL**: JSONB support for complex data
- **Redis**: Celery message broker
- **Discord Bot Permissions**: Manage messages, reactions, webhooks
