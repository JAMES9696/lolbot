# V2 A/B Test Success Criteria Document

**Document Version**: 1.0
**Author**: CLI 4 (The Lab)
**Date**: 2025-10-06
**Status**: Production Ready
**Related Documents**:
- `docs/V2_AB_TESTING_FRAMEWORK_DESIGN.md` (Technical Implementation)
- `docs/V2_TEST_PLAN.md` (Quality Plan)
- `notebooks/v2_multi_perspective_narrative.ipynb` (Research Foundation)

---

## Executive Summary

This document defines the **statistical success criteria** for the V2 team-relative analysis A/B test. It establishes measurable targets, minimum sample size requirements, and decision thresholds to determine whether V2 should be promoted to production default.

**Primary Goal**: Improve user satisfaction with AI-generated match analysis by providing team-relative context.

**Secondary Goals**: Control token costs and maintain acceptable latency.

---

## 1. Primary Metrics (User Satisfaction)

### 1.1 Positive Feedback Rate (Primary Success Metric)

**Definition**: Percentage of analyses receiving positive user reactions (👍 or ⭐).

**Formula**:
```
Positive Feedback Rate = (thumbs_up_count + star_count) / total_analyses_with_feedback
```

**Target**:
- **V2 ≥ V1 + 10 percentage points** (absolute improvement)
- Example: If V1 baseline = 60%, then V2 target = 70%

**Measurement Period**: 3 weeks (Phase 3: 50/50 split)

**Data Source**:
- Table: `feedback_events`
- Query: `src/analytics/queries/variant_performance_comparison.sql`

**Statistical Significance**: p-value < 0.05 (chi-square test)

---

### 1.2 Net Satisfaction Score (Secondary User Metric)

**Definition**: Ratio of positive to total directional feedback (excluding neutral).

**Formula**:
```
Net Satisfaction Score = thumbs_up_count / (thumbs_up_count + thumbs_down_count) × 100%
```

**Target**:
- **V2 ≥ 70%** (absolute threshold)
- **V2 ≥ V1** (relative threshold)

**Acceptable Range**: ≥ 65% (minimum acceptable quality)

**Fallback Criterion**: If V2 < 65%, rollback to V1 immediately

---

### 1.3 Engagement Rate (Feedback Participation)

**Definition**: Percentage of analyses where user provided any feedback.

**Formula**:
```
Engagement Rate = analyses_with_feedback / total_analyses × 100%
```

**Target**:
- **V2 ≥ 15%** (minimum engagement threshold)
- **V2 ≥ V1 - 3 percentage points** (no significant drop in engagement)

**Rationale**: High engagement indicates users find the analysis relevant enough to react. A significant drop suggests confusion or disinterest.

---

## 2. Secondary Metrics (Performance & Cost)

### 2.1 Token Cost Increase (Cost Control)

**Definition**: Percentage increase in LLM token consumption for V2 vs. V1.

**Formula**:
```
Token Cost Increase = (V2_avg_tokens - V1_avg_tokens) / V1_avg_tokens × 100%
```

**Acceptable Range**: **< 30%** (maximum tolerable cost increase)

**Hard Limit**: **< 50%** (emergency rollback threshold)

**Calculation**:
- **V1 Baseline Estimate**: ~800 tokens input (single player score_data)
- **V2 Target Estimate**: ~1,040 tokens input (compressed team summary)
- **Expected Increase**: ~30% based on research findings

**Data Source**:
- Table: `ab_experiment_metadata`
- Fields: `llm_input_tokens`, `llm_output_tokens`, `llm_api_cost_usd`

---

### 2.2 Latency Increase (Performance Control)

**Definition**: Percentage increase in P95 end-to-end processing latency.

**Formula**:
```
Latency Increase = (V2_p95_latency - V1_p95_latency) / V1_p95_latency × 100%
```

**Acceptable Range**: **< 20%** (maximum tolerable latency increase)

**Hard Limit**: **< 35%** (emergency rollback threshold)

**Baseline Assumptions**:
- **V1 P95 Latency**: ~13 seconds (current production metric)
- **V2 Target P95**: ≤ 15.6 seconds (13s × 1.20)

**Measurement**:
- Metric: `chimera_analyze_e2e_latency_seconds{quantile="0.95"}`
- Grafana Dashboard: `/analyze E2E Performance` panel

---

### 2.3 JSON Parsing Failure Rate (Quality Gate)

**Definition**: Percentage of V2 analyses where LLM output fails Pydantic validation.

**Formula**:
```
JSON Parsing Failure Rate = failed_parses / total_v2_analyses × 100%
```

**Acceptable Range**: **< 3%** (tolerable error rate)

**Hard Limit**: **< 5%** (quality concern threshold)

**Mitigation Strategy**:
- Failures trigger automatic retry with stricter prompt
- Persistent failures (>5%) activate fallback to V1 for affected users

**Data Source**:
- Logs: `src.adapters.gemini_llm ERROR "Failed to parse LLM output"`
- Monitoring: Sentry error aggregation

---

## 3. Minimum Detectable Effect (MDE) & Sample Size

### 3.1 Statistical Power Requirements

**Confidence Level**: 95% (α = 0.05)

**Statistical Power**: 80% (β = 0.20)

**Test Type**: Two-proportion z-test (for Positive Feedback Rate)

---

### 3.2 Sample Size Calculation

**Assumptions**:
- **V1 Baseline Positive Feedback Rate**: 60% (p₁)
- **V2 Target Positive Feedback Rate**: 70% (p₂)
- **MDE (Minimum Detectable Effect)**: 10 percentage points

**Formula** (Simplified):
```
n = 2 × [(z_α/2 + z_β)² × p(1-p)] / (p₂ - p₁)²

Where:
- p = (p₁ + p₂) / 2 = 0.65
- z_α/2 = 1.96 (95% confidence)
- z_β = 0.84 (80% power)
```

**Calculated Sample Size**:
- **n = 382 analyses per variant** (total: 764 analyses)

**Practical Considerations**:
- **Target Sample Size**: **500 analyses per variant** (total: 1,000)
- **Rationale**: Buffer for dropouts, non-feedback cases, and conservative estimation

**Engagement Adjustment**:
- If engagement rate = 15%, need **500 / 0.15 = 3,334 total analyses** to collect 500 feedback events per variant

---

### 3.3 Experiment Duration Estimate

**Current Production Volume**: ~200 `/analyze` requests per week (estimated)

**Phase 3 Configuration**: 50/50 A/B split

**Expected Feedback Volume**:
- Total analyses per week: 200
- Feedback events per week (15% engagement): 30
- Feedback per variant per week: 15

**Estimated Duration**:
- To reach 500 feedback events per variant: **500 / 15 = 33 weeks** ❌ **TOO LONG**

**Revised Strategy (Phased Approach)**:

#### **Phase 2 (Limited Rollout): 2 Weeks**
- **Split**: 80% V1, 20% V2
- **Minimum Sample**: 100 feedback events per variant
- **Goal**: Early signal detection and risk mitigation

#### **Phase 3 (Full Rollout): 3 Weeks**
- **Split**: 50% V1, 50% V2
- **Target Sample**: 200-300 feedback events per variant
- **Goal**: Statistical significance with acceptable confidence

**Total Experiment Duration**: **5 weeks** (Phase 2 + Phase 3)

**Early Stopping Rules**:
- If V2 satisfaction < 50% in Phase 2 → Immediate rollback
- If V2 cost > 50% increase in Phase 2 → Investigate and pause

---

## 4. Decision Matrix

### 4.1 V2 Promotion Criteria (All Must Be Met)

| Criterion | Threshold | Status Check |
|-----------|-----------|--------------|
| **Positive Feedback Rate** | V2 ≥ V1 + 10pp | ✅ Required |
| **Net Satisfaction Score** | V2 ≥ 70% | ✅ Required |
| **Statistical Significance** | p-value < 0.05 | ✅ Required |
| **Token Cost Increase** | < 30% | ✅ Required |
| **Latency Increase** | < 20% | ✅ Required |
| **JSON Parsing Failure Rate** | < 3% | ✅ Required |
| **Engagement Rate** | V2 ≥ V1 - 3pp | ✅ Required |

**Decision**: If all criteria met → **Promote V2 to 100% default**

---

### 4.2 V2 Partial Success (Conditional Promotion)

**Scenario**: V2 shows improvement but exceeds cost/latency thresholds.

**Criteria**:
- Positive Feedback Rate: V2 ≥ V1 + 5pp (relaxed from 10pp)
- Net Satisfaction Score: V2 ≥ 70%
- Statistical Significance: p-value < 0.05
- **BUT**: Cost increase 30-50% OR Latency increase 20-35%

**Decision**:
1. **Optimize V2 prompt** to reduce token usage (1 week sprint)
2. **Gradual rollout**: 80% V2, 20% V1 (cost control)
3. **Re-evaluate** in 2 weeks

---

### 4.3 V2 Rollback Criteria (Immediate Action Required)

**Trigger Conditions** (Any of the following):

| Condition | Action |
|-----------|--------|
| Net Satisfaction Score < 65% | ❌ Immediate rollback to V1 |
| JSON Parsing Failure Rate > 5% | ❌ Immediate rollback to V1 |
| Token Cost Increase > 50% | ❌ Immediate rollback to V1 |
| Latency Increase > 35% | ❌ Immediate rollback to V1 |
| User complaints > 10 per week | ⚠️ Investigate + possible rollback |

**Rollback Procedure**:
1. Set `AB_VARIANT_B_WEIGHT=0.0` in environment config
2. Deploy within 15 minutes
3. Notify development team via Discord CI webhook
4. Post-mortem analysis within 48 hours

---

### 4.4 V2 Inconclusive Results (Extended Testing)

**Scenario**: Results show marginal improvement but lack statistical significance.

**Criteria**:
- Positive Feedback Rate: V2 ≥ V1 + 3pp (below 10pp target)
- Statistical Significance: 0.05 < p-value < 0.10 (trend but not significant)
- All secondary metrics within acceptable range

**Decision**:
1. **Extend Phase 3 by 2 weeks** to collect 200 additional samples per variant
2. **Refine V2 prompt** based on qualitative user feedback
3. **Iterate prompt template** (Variant D) and re-test

---

## 5. Data Collection & Monitoring Plan

### 5.1 Real-Time Monitoring (Grafana Dashboards)

**Dashboard**: `V2 A/B Test Monitoring`

**Panels** (Updated Hourly):
1. **Feedback Comparison**: Bar chart of thumbs_up/thumbs_down/star by variant
2. **Satisfaction Trend**: Line chart of Net Satisfaction Score over time
3. **Cost Metrics**: Stacked area chart of token consumption (input/output) by variant
4. **Latency Distribution**: Histogram of P50/P95/P99 latency by variant
5. **Sample Size Progress**: Gauge showing current vs. target feedback count

**Alert Rules**:
- V2 satisfaction < 65% for 24 hours → Slack notification
- V2 cost > 40% increase for 48 hours → Email escalation
- JSON parsing failure rate > 3% for 12 hours → PagerDuty alert

---

### 5.2 Weekly Statistical Analysis (Jupyter Notebook)

**Notebook**: `notebooks/v2_ab_test_analysis.ipynb`

**Automated Reports** (Every Monday):
1. **Sample Size Progress**: Current feedback count vs. target
2. **Chi-Square Test Results**: Statistical significance calculation
3. **Confidence Intervals**: 95% CI for positive feedback rate difference
4. **Cost-Benefit Analysis**: User satisfaction gain vs. token cost increase
5. **Qualitative Insights**: Random sample of 10 V2 narratives (manual review)

**Distribution**:
- Auto-generated PDF report → Slack `#v2-ab-testing` channel
- Jupyter Notebook archived in `docs/reports/v2_ab_test_week_N.ipynb`

---

### 5.3 Post-Experiment Analysis (End of Phase 3)

**Deliverables** (End of Week 5):

1. **Final Statistical Report** (`docs/V2_AB_TEST_FINAL_REPORT.md`):
   - Hypothesis test results (accept/reject H1)
   - Effect size calculation (Cohen's h)
   - Confidence intervals for all metrics
   - Recommendation for V2 promotion/rollback

2. **Cost-Benefit Analysis** (`docs/V2_COST_BENEFIT_ANALYSIS.md`):
   - Total token cost comparison (V1 vs. V2)
   - Estimated monthly cost impact at 100% V2
   - User satisfaction ROI calculation

3. **Qualitative User Insights** (`docs/V2_USER_FEEDBACK_SUMMARY.md`):
   - Thematic analysis of user comments (if collected)
   - Common praise/complaint patterns
   - Suggestions for V2.1 improvements

---

## 6. Risk Mitigation & Contingency Plans

### 6.1 Risk: Low User Engagement in Feedback

**Scenario**: Engagement rate < 10% → Insufficient sample size in 5 weeks

**Mitigation**:
1. **Phase 2 Intervention**: Add Discord bot reminder message after 24 hours
   - "Did you find the analysis helpful? React with 👍/👎/⭐ to help us improve!"
2. **Incentive Mechanism**: Raffle prize for users who provide feedback (optional)
3. **Extend Experiment Duration**: Add 2 weeks if necessary

---

### 6.2 Risk: V2 Token Cost Exceeds Budget

**Scenario**: Weekly token cost > $100 (budget limit)

**Mitigation**:
1. **Phase 2 Emergency Brake**: Set `AB_VARIANT_B_WEIGHT=0.1` (reduce to 10%)
2. **Prompt Optimization Sprint**: Reduce team summary token count by 20%
3. **Cost Cap Implementation**: Disable V2 for low-engagement users

---

### 6.3 Risk: V2 Generates Factually Incorrect Comparisons

**Scenario**: User reports "LLM said I had highest vision score, but I was last"

**Mitigation**:
1. **Spot-Check Process**: Manually validate 10 random V2 outputs daily
2. **Hallucination Detection**: Add JSON schema constraints for team rank consistency
3. **User Feedback Tracking**: Monitor "report" button clicks for accuracy issues

---

## 7. Success Criteria Summary (One-Page Reference)

### ✅ V2 Promotion (Go-Live)

| Metric | Threshold |
|--------|-----------|
| Positive Feedback Rate | V2 ≥ V1 + 10pp |
| Net Satisfaction Score | V2 ≥ 70% |
| Statistical Significance | p < 0.05 |
| Token Cost Increase | < 30% |
| Latency Increase | < 20% |
| JSON Failure Rate | < 3% |
| Sample Size | ≥ 500 per variant |

**Decision**: Promote V2 to 100% default

---

### ⚠️ V2 Conditional Promotion (Optimize First)

| Metric | Threshold |
|--------|-----------|
| Positive Feedback Rate | V2 ≥ V1 + 5pp |
| Net Satisfaction Score | V2 ≥ 70% |
| Statistical Significance | p < 0.05 |
| Token Cost Increase | 30-50% |
| Latency Increase | 20-35% |

**Decision**: Optimize prompt → Gradual rollout (80% V2)

---

### ❌ V2 Rollback (Return to V1)

| Metric | Threshold |
|--------|-----------|
| Net Satisfaction Score | < 65% |
| JSON Failure Rate | > 5% |
| Token Cost Increase | > 50% |
| Latency Increase | > 35% |

**Decision**: Immediate rollback to V1

---

### 🔄 V2 Extended Testing (Inconclusive)

| Metric | Threshold |
|--------|-----------|
| Positive Feedback Rate | V2 ≥ V1 + 3pp |
| Statistical Significance | 0.05 < p < 0.10 |
| All secondary metrics | Within acceptable range |

**Decision**: Extend testing + refine prompt

---

## Appendix A: Statistical Formulas

### A.1 Chi-Square Test for Positive Feedback Rate

**Null Hypothesis (H₀)**: V2 and V1 have the same positive feedback rate.

**Alternative Hypothesis (H₁)**: V2 has a higher positive feedback rate than V1.

**Contingency Table**:
```
               | Positive | Negative | Total
---------------|----------|----------|-------
V1 (Variant A) | a        | b        | a+b
V2 (Variant B) | c        | d        | c+d
```

**Chi-Square Statistic**:
```
χ² = N × (ad - bc)² / [(a+b)(c+d)(a+c)(b+d)]

Where N = a+b+c+d (total sample size)
```

**Decision Rule**:
- If p-value < 0.05 → Reject H₀ (V2 is significantly better)
- If p-value ≥ 0.05 → Fail to reject H₀ (no significant difference)

---

### A.2 Confidence Interval for Rate Difference

**Positive Feedback Rate Difference**:
```
Δp = p₂ - p₁

Where:
- p₁ = V1 positive feedback rate
- p₂ = V2 positive feedback rate
```

**95% Confidence Interval**:
```
CI = Δp ± 1.96 × SE(Δp)

Where:
SE(Δp) = √[p₁(1-p₁)/n₁ + p₂(1-p₂)/n₂]
```

**Interpretation**:
- If CI lower bound > 0 → V2 is significantly better
- If CI includes 0 → No significant difference

---

## Appendix B: Example Calculation

**Scenario**: After 3 weeks of Phase 3 (50/50 split)

**V1 Results**:
- Total analyses: 600
- Feedback events: 90 (15% engagement)
- Thumbs up + Star: 54
- Thumbs down: 36
- Positive Feedback Rate: 54/90 = **60%**

**V2 Results**:
- Total analyses: 600
- Feedback events: 96 (16% engagement)
- Thumbs up + Star: 70
- Thumbs down: 26
- Positive Feedback Rate: 70/96 = **72.9%**

**Chi-Square Test**:
```
Contingency Table:
           | Positive | Negative | Total
-----------|----------|----------|-------
V1         | 54       | 36       | 90
V2         | 70       | 26       | 96
-----------|----------|----------|-------
Total      | 124      | 62       | 186

χ² = 186 × (54×26 - 70×36)² / (90×96×124×62)
   = 186 × (1404 - 2520)² / (65,222,400)
   = 186 × 1,245,456 / 65,222,400
   = 3.55

p-value ≈ 0.06 (using χ² distribution with df=1)
```

**Decision**:
- p-value (0.06) > 0.05 → **Fail to reject H₀** (not statistically significant)
- Positive Feedback Rate difference: 72.9% - 60% = **12.9pp** (exceeds 10pp target)
- **Conclusion**: Promising trend but **inconclusive** → Extend testing by 2 weeks

---

**Document Status**: ✅ **Production Ready**
**Next Steps**: Deploy A/B testing framework → Begin Phase 2 (Limited Rollout)
**Owner**: CLI 4 (The Lab) → CLI 3 (Observer) for monitoring execution
