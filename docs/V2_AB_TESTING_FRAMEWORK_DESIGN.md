# V2 Prompt A/B Testing Framework - Technical Design Document

**Document Version**: 1.0
**Author**: CLI 4 (The Lab)
**Date**: 2025-10-06
**Status**: Design Phase
**Related Research**: `notebooks/v2_multi_perspective_narrative.ipynb`

---

## Executive Summary

This document outlines the technical design for an **A/B testing framework** to evaluate and optimize LLM prompt strategies for match analysis narrative generation. The framework will enable data-driven prompt engineering by systematically comparing V1 (single-player) vs. V2 (team-relative) narratives through user feedback and automated metrics.

### Goals

1. **Enable controlled experimentation** of prompt variants without disrupting user experience
2. **Collect quantitative feedback** (user reactions, engagement metrics)
3. **Automate prompt performance analysis** (token costs, latency, quality scores)
4. **Facilitate rapid iteration** on prompt strategies based on data

---

## System Architecture

### High-Level Flow

```
┌──────────────────┐
│ Discord Command  │
│   /analyze       │
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  analyze_match_task (Celery)        │
│  ┌───────────────────────────────┐  │
│  │ 1. Assign Prompt Variant      │  │  ◄─── A/B Assignment Logic
│  │    (based on user_id hash)    │  │
│  └───────────────┬───────────────┘  │
│                  │                   │
│  ┌───────────────▼───────────────┐  │
│  │ 2. Generate Narrative         │  │
│  │    (with selected variant)    │  │
│  └───────────────┬───────────────┘  │
│                  │                   │
│  ┌───────────────▼───────────────┐  │
│  │ 3. Store Metadata             │  │  ◄─── Database Schema Extension
│  │    - prompt_version: "v2_summary"│ │
│  │    - ab_cohort: "B"           │  │
│  │    - variant_id: "v2_20251006"│  │
│  └───────────────┬───────────────┘  │
│                  │                   │
│  ┌───────────────▼───────────────┐  │
│  │ 4. Publish to Discord         │  │
│  │    (with feedback buttons)    │  │  ◄─── Discord Interaction Components
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  User Feedback Collection           │
│  - React with 👍/👎 (quality)       │
│  - React with ��� (very helpful)     │
│  - Click "Report Issue" button      │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Feedback Processing (async)        │
│  - Store feedback event             │  ◄─── feedback_events table
│  - Link to analysis record          │
│  - Track user_id, timestamp         │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Analytics Dashboard                │
│  - Variant performance comparison   │  ◄─── Metrics Aggregation
│  - Statistical significance tests   │
│  - Cost-benefit analysis            │
└─────────────────────────────────────┘
```

---

## Component Design

### 1. A/B Assignment Logic

**Objective**: Deterministically assign users to prompt variants while ensuring:
- **Consistency**: Same user always gets the same variant (no jarring switches)
- **Balance**: ~50/50 split across cohorts
- **Flexibility**: Easy to adjust distribution (e.g., 80/20 for phased rollout)

#### Implementation: Hash-Based Cohort Assignment

```python
# src/core/ab_testing/variant_assignment.py

import hashlib
from typing import Literal

class PromptVariantAssigner:
    """Assigns prompt variants to users using consistent hashing."""

    def __init__(
        self,
        variant_a_weight: float = 0.5,  # V1 baseline
        variant_b_weight: float = 0.5,  # V2 team-relative
        seed: str = "prompt_ab_2025",  # Change to trigger re-randomization
    ):
        """Initialize assigner with variant weights.

        Args:
            variant_a_weight: Probability of assigning Variant A (0.0-1.0)
            variant_b_weight: Probability of assigning Variant B (0.0-1.0)
            seed: Randomization seed (change to trigger new cohort assignments)
        """
        if abs((variant_a_weight + variant_b_weight) - 1.0) > 0.01:
            raise ValueError("Variant weights must sum to 1.0")

        self.variant_a_weight = variant_a_weight
        self.variant_b_weight = variant_b_weight
        self.seed = seed

    def assign_variant(self, user_id: str) -> Literal["A", "B"]:
        """Assign user to a prompt variant cohort.

        Uses SHA-256 hash of (user_id + seed) to deterministically
        assign cohorts while maintaining balance.

        Args:
            user_id: Discord user ID (unique identifier)

        Returns:
            "A" for V1 baseline, "B" for V2 team-relative
        """
        # Generate deterministic hash
        hash_input = f"{user_id}:{self.seed}".encode("utf-8")
        hash_digest = hashlib.sha256(hash_input).hexdigest()

        # Convert first 8 hex chars to integer (0-4294967295)
        hash_int = int(hash_digest[:8], 16)

        # Normalize to 0.0-1.0 range
        hash_normalized = hash_int / 0xFFFFFFFF

        # Assign based on threshold
        if hash_normalized < self.variant_a_weight:
            return "A"
        else:
            return "B"

    def get_variant_metadata(self, cohort: Literal["A", "B"]) -> dict[str, str]:
        """Get metadata for the assigned variant.

        Args:
            cohort: Assigned cohort ("A" or "B")

        Returns:
            Dictionary with variant metadata:
                - variant_id: Unique identifier (e.g., "v1_baseline")
                - prompt_version: Prompt template version
                - description: Human-readable description
        """
        metadata = {
            "A": {
                "variant_id": "v1_baseline_20251006",
                "prompt_version": "v1",
                "prompt_template": "single_player_analysis",
                "description": "V1 Baseline: Single-player analysis (no team context)",
            },
            "B": {
                "variant_id": "v2_team_summary_20251006",
                "prompt_version": "v2",
                "prompt_template": "team_relative_summary",
                "description": "V2 Team-Relative: Analysis with compressed team statistics",
            },
        }
        return metadata[cohort]


# Usage in Celery task
assigner = PromptVariantAssigner(
    variant_a_weight=0.5,  # 50% V1 baseline
    variant_b_weight=0.5,  # 50% V2 team-relative
    seed="prompt_ab_2025_q4",
)

cohort = assigner.assign_variant(user_id="123456789")
variant_meta = assigner.get_variant_metadata(cohort)
# Result: cohort="B", variant_meta={...}
```

**Configuration Management**:
```python
# src/config/settings.py (add new fields)

# A/B Testing Configuration
ab_testing_enabled: bool = Field(True, alias="AB_TESTING_ENABLED")
ab_variant_a_weight: float = Field(0.5, alias="AB_VARIANT_A_WEIGHT")
ab_variant_b_weight: float = Field(0.5, alias="AB_VARIANT_B_WEIGHT")
ab_testing_seed: str = Field("prompt_ab_2025_q4", alias="AB_TESTING_SEED")
```

---

### 2. Database Schema Extension

#### New Table: `ab_experiment_metadata`

```sql
CREATE TABLE ab_experiment_metadata (
    match_id VARCHAR(255) PRIMARY KEY REFERENCES match_analytics(match_id),
    discord_user_id VARCHAR(255) NOT NULL,  -- User who triggered analysis

    -- A/B Cohort Assignment
    ab_cohort CHAR(1) NOT NULL CHECK (ab_cohort IN ('A', 'B')),  -- "A" or "B"
    variant_id VARCHAR(100) NOT NULL,  -- "v1_baseline_20251006"
    prompt_version VARCHAR(50) NOT NULL,  -- "v1" or "v2"
    prompt_template VARCHAR(100) NOT NULL,  -- Template identifier

    -- Experiment Metadata
    assignment_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ab_seed VARCHAR(100),  -- Seed used for assignment (for reproducibility)

    -- Performance Metrics (auto-populated)
    llm_input_tokens INTEGER,
    llm_output_tokens INTEGER,
    llm_api_cost_usd DECIMAL(10, 6),  -- Calculated cost
    llm_latency_ms INTEGER,
    total_processing_time_ms INTEGER,

    -- Indexes
    INDEX idx_ab_cohort (ab_cohort),
    INDEX idx_variant_id (variant_id),
    INDEX idx_user_cohort (discord_user_id, ab_cohort),
    INDEX idx_timestamp (assignment_timestamp DESC)
);
```

#### New Table: `feedback_events`

```sql
CREATE TABLE feedback_events (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(255) NOT NULL REFERENCES match_analytics(match_id),
    discord_user_id VARCHAR(255) NOT NULL,

    -- Feedback Type
    feedback_type VARCHAR(50) NOT NULL,  -- "thumbs_up", "thumbs_down", "star", "report"
    feedback_value INTEGER,  -- For 1-5 star ratings
    feedback_comment TEXT,  -- Optional user comment

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    interaction_id VARCHAR(255),  -- Discord interaction ID for deduplication

    -- Link to A/B experiment
    ab_cohort CHAR(1),  -- Denormalized for faster queries
    variant_id VARCHAR(100),  -- Denormalized

    -- Indexes
    INDEX idx_match_feedback (match_id),
    INDEX idx_user_feedback (discord_user_id),
    INDEX idx_feedback_type (feedback_type),
    INDEX idx_variant_feedback (variant_id, feedback_type),
    UNIQUE (match_id, discord_user_id, feedback_type)  -- Prevent duplicate reactions
);
```

#### Extend `match_analytics` Table

```sql
-- Add columns to existing table (migration)
ALTER TABLE match_analytics
ADD COLUMN ab_cohort CHAR(1),  -- Denormalized for convenience
ADD COLUMN prompt_version VARCHAR(50);  -- "v1", "v2", etc.

CREATE INDEX idx_match_ab_cohort ON match_analytics(ab_cohort);
CREATE INDEX idx_match_prompt_version ON match_analytics(prompt_version);
```

---

### 3. Discord Feedback Collection

#### Interactive Message Components

```python
# src/core/views/analysis_view.py (extend existing render_analysis_embed)

import discord

def render_analysis_embed_with_feedback(
    analysis_data: dict[str, Any],
    ab_cohort: str | None = None,
) -> tuple[discord.Embed, discord.ui.View]:
    """Render analysis embed with feedback collection buttons.

    Args:
        analysis_data: FinalAnalysisReport dictionary
        ab_cohort: A/B cohort identifier ("A" or "B") for tracking

    Returns:
        Tuple of (Embed, View with feedback buttons)
    """
    # Generate existing embed
    embed = render_analysis_embed(analysis_data)

    # Add A/B testing footer note (subtle)
    if ab_cohort:
        current_footer = embed.footer.text if embed.footer else ""
        embed.set_footer(
            text=f"{current_footer}\n📊 AI 分析版本: {ab_cohort}",
            icon_url=embed.footer.icon_url if embed.footer else None,
        )

    # Create feedback button view
    view = AnalysisFeedbackView(
        match_id=analysis_data["match_id"],
        ab_cohort=ab_cohort or "unknown",
    )

    return embed, view


class AnalysisFeedbackView(discord.ui.View):
    """Interactive feedback collection view."""

    def __init__(self, match_id: str, ab_cohort: str):
        super().__init__(timeout=None)  # Persistent buttons
        self.match_id = match_id
        self.ab_cohort = ab_cohort

    @discord.ui.button(label="👍 有帮助", style=discord.ButtonStyle.success, custom_id="feedback_helpful")
    async def thumbs_up_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle thumbs up feedback."""
        await self._record_feedback(interaction, "thumbs_up", value=1)

    @discord.ui.button(label="👎 不准确", style=discord.ButtonStyle.secondary, custom_id="feedback_not_helpful")
    async def thumbs_down_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle thumbs down feedback."""
        await self._record_feedback(interaction, "thumbs_down", value=-1)

    @discord.ui.button(label="⭐ 非常有用", style=discord.ButtonStyle.primary, custom_id="feedback_star")
    async def star_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle star (very helpful) feedback."""
        await self._record_feedback(interaction, "star", value=2)

    async def _record_feedback(
        self,
        interaction: discord.Interaction,
        feedback_type: str,
        value: int,
    ):
        """Record feedback event in database."""
        from src.adapters.database import get_database

        db = get_database()

        try:
            await db.record_feedback_event(
                match_id=self.match_id,
                discord_user_id=str(interaction.user.id),
                feedback_type=feedback_type,
                feedback_value=value,
                ab_cohort=self.ab_cohort,
                interaction_id=str(interaction.id),
            )

            # Acknowledge feedback
            await interaction.response.send_message(
                "✅ 感谢您的反馈！这将帮助我们改进 AI 分析质量。",
                ephemeral=True,
            )

        except Exception as e:
            logger.error(f"Failed to record feedback: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ 反馈提交失败，请稍后重试。",
                ephemeral=True,
            )
```

#### Database Adapter Extension

```python
# src/adapters/database.py (add new method)

async def record_feedback_event(
    self,
    match_id: str,
    discord_user_id: str,
    feedback_type: str,
    feedback_value: int,
    ab_cohort: str,
    interaction_id: str,
) -> bool:
    """Record user feedback event for A/B testing analysis.

    Args:
        match_id: Match ID the feedback relates to
        discord_user_id: User who provided feedback
        feedback_type: Type of feedback (thumbs_up, thumbs_down, star)
        feedback_value: Numeric value (1, -1, 2)
        ab_cohort: A/B cohort assignment
        interaction_id: Discord interaction ID (for deduplication)

    Returns:
        True if feedback recorded successfully
    """
    query = """
        INSERT INTO feedback_events (
            match_id, discord_user_id, feedback_type, feedback_value,
            ab_cohort, interaction_id, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        ON CONFLICT (match_id, discord_user_id, feedback_type) DO UPDATE
        SET feedback_value = EXCLUDED.feedback_value,
            created_at = NOW()
    """

    try:
        await self.pool.execute(
            query,
            match_id,
            discord_user_id,
            feedback_type,
            feedback_value,
            ab_cohort,
            interaction_id,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to record feedback event: {e}", exc_info=True)
        return False
```

---

### 4. Celery Task Integration

#### Modified `analyze_match_task` with A/B Logic

```python
# src/tasks/analysis_tasks.py (STAGE 4 modification)

from src.core.ab_testing.variant_assignment import PromptVariantAssigner

@celery_app.task(bind=True)
async def analyze_match_task(
    self,
    match_id: str,
    application_id: str,
    interaction_token: str,
    discord_user_id: str,  # NEW: Required for A/B assignment
):
    """Match analysis task with A/B testing support."""

    # ... STAGES 1-3: Data retrieval and scoring (unchanged)

    # ==================== STAGE 4: A/B ASSIGNMENT ====================
    logger.info(f"[STAGE 4] A/B variant assignment for user {discord_user_id}")

    # Initialize assigner from settings
    assigner = PromptVariantAssigner(
        variant_a_weight=settings.ab_variant_a_weight,
        variant_b_weight=settings.ab_variant_b_weight,
        seed=settings.ab_testing_seed,
    )

    # Assign cohort
    ab_cohort = assigner.assign_variant(discord_user_id)
    variant_meta = assigner.get_variant_metadata(ab_cohort)

    logger.info(
        f"User {discord_user_id} assigned to cohort {ab_cohort} "
        f"(variant: {variant_meta['variant_id']})"
    )

    # ==================== STAGE 5: LLM GENERATION (VARIANT-AWARE) ====================
    logger.info(f"[STAGE 5] Generating narrative with {variant_meta['prompt_template']}")

    # Select prompt template based on cohort
    if ab_cohort == "A":
        # V1 Baseline: Single-player analysis
        narrative_result = await gemini.generate_narrative_v1(
            score_data=score_data,
            match_result=match_result,
        )
    else:
        # V2 Team-Relative: Use team summary statistics
        team_summary = _calculate_team_summary(all_players_scores)
        narrative_result = await gemini.generate_narrative_v2_with_team(
            target_player_score=score_data,
            team_summary=team_summary,
            match_result=match_result,
        )

    # ==================== STAGE 6: METADATA STORAGE ====================
    # Store A/B experiment metadata
    await db.store_ab_experiment_metadata(
        match_id=match_id,
        discord_user_id=discord_user_id,
        ab_cohort=ab_cohort,
        variant_id=variant_meta["variant_id"],
        prompt_version=variant_meta["prompt_version"],
        prompt_template=variant_meta["prompt_template"],
        llm_input_tokens=narrative_result.get("input_tokens"),
        llm_output_tokens=narrative_result.get("output_tokens"),
        llm_latency_ms=narrative_result.get("latency_ms"),
        ab_seed=settings.ab_testing_seed,
    )

    # ... STAGE 7: Webhook delivery (with feedback buttons)
    embed, feedback_view = render_analysis_embed_with_feedback(
        analysis_data=final_report.model_dump(),
        ab_cohort=ab_cohort,
    )

    # Publish via webhook with interactive components
    await webhook_adapter.publish_match_analysis_with_feedback(
        application_id=application_id,
        interaction_token=interaction_token,
        embed=embed,
        view=feedback_view,
    )
```

---

## Analytics & Reporting

### Metrics Dashboard Queries

#### 1. Variant Performance Comparison

```sql
-- Overall feedback comparison by variant
SELECT
    ab.variant_id,
    ab.ab_cohort,
    COUNT(DISTINCT ab.match_id) AS total_analyses,

    -- Feedback metrics
    COUNT(DISTINCT CASE WHEN fe.feedback_type = 'thumbs_up' THEN fe.id END) AS thumbs_up_count,
    COUNT(DISTINCT CASE WHEN fe.feedback_type = 'thumbs_down' THEN fe.id END) AS thumbs_down_count,
    COUNT(DISTINCT CASE WHEN fe.feedback_type = 'star' THEN fe.id END) AS star_count,

    -- Engagement rate
    (COUNT(DISTINCT fe.match_id)::FLOAT / COUNT(DISTINCT ab.match_id)) * 100 AS feedback_rate_pct,

    -- Net satisfaction score
    (COUNT(DISTINCT CASE WHEN fe.feedback_type = 'thumbs_up' THEN fe.id END)::FLOAT /
     NULLIF(COUNT(DISTINCT CASE WHEN fe.feedback_type IN ('thumbs_up', 'thumbs_down') THEN fe.id END), 0)) * 100 AS satisfaction_pct,

    -- Cost metrics
    AVG(ab.llm_api_cost_usd) AS avg_cost_usd,
    SUM(ab.llm_api_cost_usd) AS total_cost_usd,

    -- Latency metrics
    AVG(ab.llm_latency_ms) AS avg_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ab.llm_latency_ms) AS p95_latency_ms

FROM ab_experiment_metadata ab
LEFT JOIN feedback_events fe ON ab.match_id = fe.match_id
WHERE ab.assignment_timestamp >= NOW() - INTERVAL '7 days'
GROUP BY ab.variant_id, ab.ab_cohort
ORDER BY ab.variant_id;
```

#### 2. Statistical Significance Test (Chi-Square)

```python
# src/analytics/ab_test_analysis.py

from scipy.stats import chi2_contingency
import pandas as pd

async def calculate_statistical_significance(
    variant_a_positive: int,
    variant_a_negative: int,
    variant_b_positive: int,
    variant_b_negative: int,
) -> dict[str, float]:
    """Calculate statistical significance of A/B test results.

    Uses chi-square test for independence.

    Args:
        variant_a_positive: Positive feedback count for Variant A
        variant_a_negative: Negative feedback count for Variant A
        variant_b_positive: Positive feedback count for Variant B
        variant_b_negative: Negative feedback count for Variant B

    Returns:
        Dictionary with:
            - chi2_statistic: Chi-square test statistic
            - p_value: P-value (< 0.05 indicates significant difference)
            - significant: Boolean indicating statistical significance
    """
    # Construct contingency table
    observed = [
        [variant_a_positive, variant_a_negative],
        [variant_b_positive, variant_b_negative],
    ]

    # Perform chi-square test
    chi2, p_value, dof, expected = chi2_contingency(observed)

    return {
        "chi2_statistic": chi2,
        "p_value": p_value,
        "degrees_of_freedom": dof,
        "significant": p_value < 0.05,
        "confidence_level": (1 - p_value) * 100,
    }


# Usage example
result = await calculate_statistical_significance(
    variant_a_positive=120,  # V1 thumbs up
    variant_a_negative=30,   # V1 thumbs down
    variant_b_positive=180,  # V2 thumbs up
    variant_b_negative=20,   # V2 thumbs down
)
# Result: {"p_value": 0.012, "significant": True, ...}
# Interpretation: V2 performs significantly better than V1 (p < 0.05)
```

---

## Deployment & Rollout Strategy

### Phase 1: Development Testing (1 week)

- Deploy A/B framework to staging environment
- Test cohort assignment logic with synthetic users
- Verify database schema and migrations
- Validate feedback collection with Discord test server

**Success Criteria**:
- ✅ 100% cohort assignment consistency (same user → same cohort)
- ✅ Feedback buttons functional and data persisted
- ✅ No performance regression (latency < 2% increase)

---

### Phase 2: Limited Production Rollout (2 weeks)

- Enable A/B testing for **20% of production users**
- Use 80/20 split: 80% V1 (safe baseline), 20% V2 (experimental)
- Monitor for errors and user complaints
- Collect minimum 100 feedback events per variant

**Configuration**:
```env
AB_TESTING_ENABLED=true
AB_VARIANT_A_WEIGHT=0.8  # 80% V1 baseline
AB_VARIANT_B_WEIGHT=0.2  # 20% V2 team-relative
AB_TESTING_SEED=prompt_ab_2025_q4_phase2
```

**Monitoring Alerts**:
- Error rate > 1% for V2 variant → Rollback
- Feedback satisfaction < 50% for V2 → Investigate
- API cost increase > 50% for V2 → Cost review

---

### Phase 3: Full 50/50 Rollout (3 weeks)

- Increase to 50/50 split after Phase 2 validation
- Collect 500+ feedback events per variant
- Run statistical significance tests weekly

**Decision Criteria** (after 3 weeks):
1. **V2 Wins**: Satisfaction ≥ V1 + 10% AND cost increase < 30% → **Promote V2 to default**
2. **V1 Wins**: V2 shows no significant improvement → **Keep V1 as default**
3. **Inconclusive**: Extend testing 2 more weeks or refine V2 prompt

---

### Phase 4: Continuous Optimization (Ongoing)

- Test new prompt variants (V3, V4) against current champion
- Implement multi-armed bandit algorithm for dynamic allocation
- Automate weekly A/B reports to Slack/Email

---

## Success Metrics & KPIs

### Primary Metrics (User Satisfaction)

| Metric | Target (V2 vs. V1) | Measurement |
|--------|-------------------|-------------|
| **Positive Feedback Rate** | ≥ +10% | (thumbs_up + star) / total_feedback |
| **Net Satisfaction Score** | ≥ 70% | thumbs_up / (thumbs_up + thumbs_down) |
| **Engagement Rate** | ≥ 15% | users_giving_feedback / total_analyses |

### Secondary Metrics (Technical Performance)

| Metric | Acceptable Range | Measurement |
|--------|------------------|-------------|
| **Token Cost Increase** | < 30% | (V2_avg_cost - V1_avg_cost) / V1_avg_cost |
| **Latency Increase** | < 20% | (V2_p95_latency - V1_p95_latency) / V1_p95_latency |
| **Error Rate** | < 1% | failed_analyses / total_analyses |

### Decision Matrix

```
IF satisfaction_improvement ≥ 10% AND cost_increase < 30%:
    → Promote V2 to 100% default

ELIF satisfaction_improvement ≥ 5% AND cost_increase < 15%:
    → Gradually ramp V2 to 80% (optimize costs first)

ELIF satisfaction_improvement < 0%:
    → Rollback to V1, refine V2 prompt

ELSE:
    → Extend testing period (inconclusive results)
```

---

## Implementation Checklist

### Backend (2 weeks)

- [ ] Implement `PromptVariantAssigner` class
- [ ] Add A/B configuration to `settings.py`
- [ ] Create database migration for new tables
- [ ] Extend `analyze_match_task` with A/B logic
- [ ] Implement V2 prompt template with team summary
- [ ] Add database methods for metadata storage
- [ ] Write unit tests for assignment logic

### Frontend (Discord Integration) (1 week)

- [ ] Create `AnalysisFeedbackView` Discord UI component
- [ ] Extend `render_analysis_embed_with_feedback`
- [ ] Implement feedback event handlers
- [ ] Add feedback storage database methods
- [ ] Test feedback buttons in Discord test server

### Analytics (1 week)

- [ ] Write SQL queries for variant comparison dashboard
- [ ] Implement statistical significance calculator
- [ ] Create weekly automated A/B report script
- [ ] Set up monitoring alerts (error rate, satisfaction)
- [ ] Build internal Grafana dashboard

### Documentation (3 days)

- [ ] Update `docs/volcengine_tts_setup.md` with V2 prompt examples
- [ ] Create A/B testing runbook for operations team
- [ ] Document rollback procedures
- [ ] Write user-facing changelog (if V2 promoted)

---

## Risk Mitigation

### Risk 1: User Confusion from Variant Differences

**Scenario**: User asks friend about analysis, sees different style
**Mitigation**:
- Add subtle footer note: "📊 AI 分析版本: A/B"
- Internal FAQ for support team explaining A/B testing
- Ensure both variants maintain high quality baseline

### Risk 2: Data Bias from Self-Selection

**Scenario**: Only highly engaged users provide feedback
**Mitigation**:
- Track engagement rate as secondary metric
- Require minimum sample size (500+ per variant)
- Consider passive metrics (e.g., re-analysis requests)

### Risk 3: Token Cost Explosion

**Scenario**: V2 costs 2× more than expected
**Mitigation**:
- Set hard limit: AB_VARIANT_B_WEIGHT=0.2 (20% max)
- Monitor daily cost dashboard
- Auto-disable V2 if weekly budget exceeded

### Risk 4: LLM Hallucinations in Team Comparisons

**Scenario**: V2 generates factually incorrect comparisons
**Mitigation**:
- Add JSON schema validation for team summary inputs
- Spot-check 10 random V2 outputs daily for accuracy
- Provide "Report Inaccuracy" button for user feedback

---

## Appendix: Example Prompt Templates

### V1 Baseline Prompt (Existing)

```python
# src/prompts/v1_single_player.txt

你是一位专业的英雄联盟分析教练。请根据以下数据为玩家生成一段中文评价：

**玩家数据**:
{score_data_json}

**比赛结果**: {match_result}

要求：
1. 200字左右的中文叙事
2. 基于五个维度（战斗、经济、视野、目标、团队配合）评价
3. 突出优势和改进点
4. 语气鼓励但客观
```

### V2 Team-Relative Prompt (New)

```python
# src/prompts/v2_team_relative_summary.txt

你是一位专业的英雄联盟分析教练。请根据以下数据为目标玩家生成一段**团队相对**的中文评价：

**目标玩家数据**:
{target_player_score_json}

**团队统计摘要**:
{team_summary_json}

**比赛结果**: {match_result}

要求：
1. 200字左右的中文叙事
2. 使用团队统计摘要进行对比分析（"你的战斗评分高于队伍平均15%"）
3. 突出相对排名（"在队伍中排名第X"）
4. 提供具体改进建议（对比队友强项）
5. 语气鼓励但客观

输出格式示例：
"在这场{match_result}中，你的{champion_name}在经济维度表现卓越，经济评分{economy_score}高于队伍平均{economy_avg}约{pct_diff}%，在队伍中排名第{economy_rank}。..."
```

---

**Document Status**: ✅ **Design Complete - Ready for Implementation**
**Next Steps**: Backend implementation (2 weeks sprint)
**Owner**: CLI 4 (The Lab) → CLI 2 (Backend) for execution
