# V2.4 Arena Algorithm Compliance Verification Checklist

**Document Version**: V1.0
**Created Date**: 2025-10-07
**Author**: CLI 4 (The Lab)
**Status**: ✅ Production Ready
**Criticality**: ⚠️ **P0 - BLOCKING** - Must pass before Arena mode goes live

---

## Executive Summary

This checklist ensures that the Arena V1-Lite analysis algorithm **strictly complies with Riot Games' Third-Party Application Policy**, specifically the prohibition on providing competitive advantages through data not available in the game client.

**Red Line Compliance Rule**:
> **Arena Augment (增强符文) analysis MUST NOT display or reference win rates, tier rankings, or any predictive/competitive advantage data.**

All analysis must be **retrospective** (post-game only) and focus on **educational feedback** about synergy and tactical choices.

---

## 1. Code-Level Compliance Verification

### 1.1 Data Source Audit

**Checklist**:

- [ ] **No Win Rate Data Access**: Verify that `src/core/scoring/arena_v1_lite.py` does NOT call any win rate APIs or databases
  - ❌ Prohibited: `get_augment_win_rate()`, `fetch_item_tier_list()`
  - ✅ Allowed: Match-V5 API, Timeline API, Static Data Dragon (champion/item names only)

- [ ] **No External Stats APIs**: Verify that Arena analysis does NOT use third-party stats providers (e.g., op.gg, u.gg, lolalytics)
  - ❌ Prohibited: Any API calls to `*.op.gg`, `*.u.gg`, `*.lolalytics.com`
  - ✅ Allowed: Riot official APIs only

- [ ] **Augment Mapping Only**: Verify that `AUGMENT_NAMES` mapping in `arena_v1_lite.py` only contains **ID-to-name translations**, not win rates or tier data
  ```python
  # ✅ Allowed
  AUGMENT_NAMES = {
      "1": "猛攻",
      "2": "韧性",
      # ...
  }

  # ❌ Prohibited
  AUGMENT_WIN_RATES = {
      "1": 0.68,  # ❌ FORBIDDEN
      "2": 0.54,
  }
  ```

**Verification Commands**:
```bash
# Search for forbidden patterns in Arena algorithm
rg --type py "(win_rate|winrate|tier_list|tier_rank|competitive_advantage)" src/core/scoring/arena_v1_lite.py

# Expected result: No matches (exit code 1)
# If matches found, BLOCKING ISSUE - must fix
```

---

### 1.2 Algorithm Logic Review

**Checklist**:

- [ ] **Rule-Based Synergy Only**: Verify that `analyze_arena_augments()` uses **rule-based heuristics** instead of statistical data
  - ✅ Allowed: `if champion in ["Yasuo", "Zed"] and augment == "猛攻": synergy = "刺客英雄配合良好"`
  - ❌ Prohibited: `if augment_win_rate[augment] > 0.65: recommendation = "高胜率符文"`

- [ ] **No Predictive Suggestions**: Verify that `alternative_augment_suggestion` field is **retrospective only**
  - ✅ Allowed: "在本场比赛中，如果在第4回合选择【坚韧】，可能能更好地应对敌方高爆发阵容"
  - ❌ Prohibited: "下场比赛建议选择【猛攻】，该符文胜率68%"

- [ ] **No Tier Rankings**: Verify that algorithm does NOT assign tier rankings to Augments
  - ❌ Prohibited: `augment_tier = "S"`, `augment_rank = 1`

**Verification Code Review**:

Review `src/core/scoring/arena_v1_lite.py:analyze_arena_augments()` function:

```python
# Line 123-234: analyze_arena_augments()
# MUST verify:
# 1. No win rate API calls
# 2. No statistical data lookups
# 3. Only rule-based synergy analysis
# 4. Retrospective suggestions only (if player lost)
```

---

### 1.3 Pydantic Contract Compliance

**Checklist**:

- [ ] **No Win Rate Fields**: Verify that `V23ArenaAugmentAnalysis` Pydantic model does NOT contain win rate fields
  ```python
  # ❌ Prohibited fields
  augment_win_rate: float  # MUST NOT EXIST
  augment_tier: str  # MUST NOT EXIST
  competitive_advantage_score: float  # MUST NOT EXIST
  ```

- [ ] **Compliance Docstrings**: Verify that model docstrings include compliance warnings
  ```python
  class V23ArenaAugmentAnalysis(BaseModel):
      """Arena Augment analysis.

      CRITICAL COMPLIANCE NOTE:
      Per Riot Games policy, this analysis MUST NOT display Augment win rates.
      """
  ```

**Verification Commands**:
```bash
# Search for forbidden fields in Arena contracts
rg --type py "(win_rate|winrate|tier|rank|advantage)" src/contracts/v23_multi_mode_analysis.py

# Manual review: Check V23ArenaAugmentAnalysis model
# Expected: No win rate/tier fields
```

---

## 2. Prompt-Level Compliance Verification

### 2.1 Prompt Template Audit

**Checklist**:

- [ ] **Compliance Warnings**: Verify that `src/prompts/v23_arena_analysis.txt` contains **multiple compliance warnings**
  - Must include: "⚠️ 关键合规要求（CRITICAL COMPLIANCE REQUIREMENT）"
  - Must include: "根据Riot Games政策，本分析严禁显示增强符文的胜率数据"

- [ ] **Forbidden Content Section**: Verify that prompt includes **explicit list of prohibited content**
  ```
  ❌ 禁止提及以下违反Riot Games政策的内容：
  - 增强符文的胜率数据（如"【猛攻】胜率68%"）
  - 增强符文的tier排名（如"T1级符文"、"S级符文"）
  - 基于胜率的预测性符文建议
  ```

- [ ] **Compliance Checklist**: Verify that prompt includes **5-point compliance checklist** for LLM to follow
  ```
  合规性检查清单：
  1. ❌ 是否提及任何符文的胜率数字？
  2. ❌ 是否提及符文的tier排名？
  3. ❌ 是否提供未来比赛的预测性符文建议？
  4. ✅ 分析是否基于英雄协同性和战术配合？
  5. ✅ 建议是否明确标注为"基于本场赛后分析"？
  ```

**Verification Commands**:
```bash
# Verify compliance warnings exist in prompt
grep -c "CRITICAL COMPLIANCE" src/prompts/v23_arena_analysis.txt
# Expected: >= 1

grep -c "严禁显示增强符文的胜率" src/prompts/v23_arena_analysis.txt
# Expected: >= 1

grep -c "合规性检查清单" src/prompts/v23_arena_analysis.txt
# Expected: >= 1
```

---

### 2.2 LLM Output Constraints

**Checklist**:

- [ ] **Output Format Enforcement**: Verify that prompt enforces **JSON Schema** output format
  - Must specify: `analysis_summary: str` and `improvement_suggestions: list[str]`
  - Must NOT allow: `augment_win_rates: dict` or `tier_rankings: list`

- [ ] **Example Analysis Review**: Verify that prompt's **example analysis** does NOT contain forbidden content
  ```
  # ✅ Good example (from prompt)
  "你选择的【猛攻】符文与你的刺客英雄配合良好，提升了爆发伤害"

  # ❌ Bad example (MUST NOT appear in prompt)
  "【猛攻】符文胜率68%，建议下场继续选择"
  ```

**Verification Method**:

Manually review `src/prompts/v23_arena_analysis.txt` lines 100-150 (example section):
- ✅ Examples must demonstrate compliant analysis
- ❌ Examples must NOT contain win rates, tier rankings, or predictive suggestions

---

## 3. Test-Level Compliance Verification

### 3.1 Automated Compliance Tests

**Checklist**:

- [ ] **Forbidden Pattern Detection**: Verify that test suite includes **regex-based forbidden pattern detection**
  ```python
  # tests/unit/test_arena_compliance.py
  def test_arena_augment_analysis_no_win_rates():
      """Test Arena Augment analysis does NOT contain win rate data."""
      report = generate_arena_analysis_report(...)

      augment_text = report.augment_analysis.augment_synergy_with_champion

      # Forbidden patterns
      forbidden_patterns = [
          r"\d+%",  # Any percentage number (likely win rate)
          r"胜率",
          r"win\s*rate",
          r"tier\s*[1-5]",
          r"[SABCDF]\s*级",  # Tier rankings
          r"下场.*选择",  # Predictive suggestions
      ]

      for pattern in forbidden_patterns:
          assert not re.search(pattern, augment_text, re.IGNORECASE), \
              f"Arena Augment analysis contains forbidden pattern: {pattern}"
  ```

- [ ] **Compliance Test Coverage**: Verify that test suite includes:
  - ✅ Unit test for `analyze_arena_augments()` compliance
  - ✅ Integration test for end-to-end Arena analysis compliance
  - ✅ LLM output validation test (checks final JSON output from Gemini)

**Verification Commands**:
```bash
# Run compliance tests
pytest tests/unit/test_arena_compliance.py -v

# Expected: All tests pass (exit code 0)
# If any test fails, BLOCKING ISSUE
```

---

### 3.2 Manual Test Cases

**Test Case 1: Augment Synergy Analysis**

**Input**:
- Player: Yasuo (Assassin)
- Augments: ["猛攻", "韧性", "疾行"]
- Partner: Malphite (Tank)

**Expected Output**:
- ✅ "【猛攻】与你的刺客英雄配合良好，提升了爆发伤害"
- ✅ "你的队友使用坦克英雄，配合你的输出型符文，形成了攻防平衡"

**Forbidden Output**:
- ❌ "【猛攻】符文胜率68%"
- ❌ "【猛攻】是T1级符文"
- ❌ "下场比赛建议继续选择【猛攻】"

---

**Test Case 2: Alternative Augment Suggestion (Loss Scenario)**

**Input**:
- Player: Ezreal (ADC)
- Match Result: Loss (4th place)
- Augments: ["猛攻", "疾行", "生命窃取"]

**Expected Output**:
- ✅ "在本场比赛中，如果在后期回合选择更多防御型符文（如【韧性】或【坚韧】），可能能更好地应对敌方的高爆发阵容"
- ✅ **Must include**: "基于赛后分析的建议"

**Forbidden Output**:
- ❌ "下场比赛建议选择【坚韧】，该符文在当前版本胜率更高"
- ❌ "根据统计数据，【韧性】在ADC英雄中胜率达到72%"

---

**Test Case 3: Win Scenario (No Alternative Suggestion)**

**Input**:
- Player: Zed (Assassin)
- Match Result: Win (1st place)
- Augments: ["猛攻", "疾行", "生命窃取"]

**Expected Output**:
- ✅ `alternative_augment_suggestion: null` (no suggestion needed for wins)
- ✅ Positive feedback on Augment choices

**Forbidden Output**:
- ❌ Any win rate or tier ranking data

---

## 4. Integration-Level Compliance Verification

### 4.1 CLI 2 (Backend) Integration Review

**Checklist**:

- [ ] **Strategy Pattern Implementation**: Verify that `ArenaStrategy` class uses compliant algorithm
  ```python
  # src/core/strategies/arena_strategy.py (假设位置)
  class ArenaStrategy(AnalysisStrategy):
      def analyze(self, match_data, timeline_data, player_puuid):
          # MUST call compliant arena_v1_lite functions
          return generate_arena_analysis_report(...)
  ```

- [ ] **No Fallback to Stats APIs**: Verify that CLI 2 does NOT have fallback logic to stats APIs when Arena analysis fails
  - ❌ Prohibited: `if arena_analysis_fails: return fetch_arena_stats_from_opgg()`

- [ ] **Metric Applicability Enforcement**: Verify that CLI 2 correctly applies `MetricApplicability` preset for Arena
  ```python
  # Must disable Economy, Vision, Objectives for Arena
  arena_preset = METRIC_APPLICABILITY_PRESETS["Arena"]
  assert arena_preset.economy_enabled is False
  assert arena_preset.vision_enabled is False
  ```

**Verification Method**:

Pair programming session with CLI 2 to review:
1. `ArenaStrategy` implementation
2. Mode detection → strategy selection flow
3. No forbidden API calls in Arena code path

---

### 4.2 CLI 3 (Discord) Integration Review

**Checklist**:

- [ ] **Discord Embed Formatting**: Verify that Discord embed does NOT display forbidden data
  ```python
  # src/adapters/discord_adapter.py
  def format_arena_analysis_embed(report: V23ArenaAnalysisReport):
      # ✅ Display: Augment names
      # ✅ Display: Synergy analysis
      # ❌ Display: Win rates, tier rankings
  ```

- [ ] **User-Visible Output Audit**: Manually test `/jiangli` command in Discord and verify:
  - ✅ Augment names displayed
  - ✅ Synergy analysis displayed
  - ❌ No win rates
  - ❌ No tier rankings
  - ❌ No predictive suggestions

**Verification Method**:

Discord E2E test:
```python
# tests/integration/test_discord_arena_compliance.py
@pytest.mark.asyncio
async def test_discord_arena_embed_compliance(discord_client):
    """Test Discord Arena embed does not contain forbidden content."""
    interaction = await discord_client.send_command(
        "/jiangli",
        player_name="TestPlayer",
        match_number=1  # Arena match
    )

    embed = interaction.response.embeds[0]
    embed_text = str(embed.to_dict())

    # Forbidden patterns
    assert "胜率" not in embed_text
    assert "tier" not in embed_text.lower()
    assert "下场比赛" not in embed_text
```

---

## 5. Production Monitoring & Alerting

### 5.1 Sentry Compliance Monitoring

**Checklist**:

- [ ] **Forbidden Pattern Alerts**: Configure Sentry to alert on forbidden pattern detection in Arena analysis
  ```python
  # src/core/observability.py
  def validate_arena_analysis_compliance(report: V23ArenaAnalysisReport):
      """Validate Arena analysis output for compliance violations."""
      augment_text = report.augment_analysis.augment_synergy_with_champion

      forbidden_patterns = [r"\d+%", r"胜率", r"tier"]

      for pattern in forbidden_patterns:
          if re.search(pattern, augment_text, re.IGNORECASE):
              sentry_sdk.capture_message(
                  f"COMPLIANCE VIOLATION: Arena analysis contains forbidden pattern: {pattern}",
                  level="error",
                  extras={"match_id": report.match_id, "text": augment_text}
              )
              raise ComplianceViolationError(f"Forbidden pattern detected: {pattern}")
  ```

- [ ] **LLM Output Validation Hook**: Add validation hook **before** Discord response
  ```python
  # In CLI 2's analyze_team_task
  if game_mode.mode == "Arena":
      report = generate_arena_analysis_report(...)
      validate_arena_analysis_compliance(report)  # ⚠️ BLOCKING
      return report
  ```

**Expected Behavior**:
- ✅ If compliance violation detected: Log to Sentry + Raise exception + Return error to user
- ✅ User sees: "分析过程中发生错误，请联系管理员"
- ✅ Admin receives: Sentry alert with violation details

---

### 5.2 Post-Launch Compliance Audit

**Checklist**:

- [ ] **Weekly Manual Audit**: Sample 10 Arena analysis outputs per week and manually review for compliance
  - Review: Augment synergy text
  - Review: Alternative suggestion text (if present)
  - Review: Discord embed content

- [ ] **User Report Monitoring**: Monitor Discord for user reports of suspicious content
  - Watch for: Screenshots of win rate displays
  - Watch for: User feedback mentioning "tier lists" or "predicted win rates"

- [ ] **Quarterly Riot Policy Review**: Review Riot Games Developer Portal for policy updates
  - URL: https://developer.riotgames.com/policies
  - Update compliance checks if policy changes

---

## 6. Compliance Verification Sign-Off

**Pre-Launch Checklist** (MUST be completed before Arena mode goes live):

- [ ] **Code-Level Compliance** (Section 1): All checks passed
- [ ] **Prompt-Level Compliance** (Section 2): All checks passed
- [ ] **Test-Level Compliance** (Section 3): All tests passed
- [ ] **Integration-Level Compliance** (Section 4): CLI 2/3 review completed
- [ ] **Monitoring Setup** (Section 5): Sentry alerts configured

**Sign-Off**:

| Role | Name | Date | Signature |
|------|------|------|-----------|
| CLI 4 (Algorithm Designer) | ___________ | ___________ | ___________ |
| CLI 2 (Backend Integration) | ___________ | ___________ | ___________ |
| CLI 3 (SRE/Discord Integration) | ___________ | ___________ | ___________ |
| Project Lead | ___________ | ___________ | ___________ |

**Approval Status**: ⏳ Pending / ✅ Approved / ❌ Rejected

---

## 7. Incident Response Plan

### 7.1 Compliance Violation Detected

**If a compliance violation is detected in production**:

1. **Immediate Actions** (within 1 hour):
   - ✅ Disable Arena analysis feature (feature flag: `ENABLE_ARENA_ANALYSIS=False`)
   - ✅ Post Discord announcement: "Arena 分析功能因技术问题暂时不可用，我们正在修复"
   - ✅ Create P0 incident in incident management system

2. **Investigation** (within 4 hours):
   - ✅ Review Sentry logs for violation details
   - ✅ Identify root cause (code bug, LLM hallucination, prompt issue)
   - ✅ Assess severity (single case vs systematic issue)

3. **Remediation** (within 24 hours):
   - ✅ Fix root cause (code patch, prompt update, LLM retry logic)
   - ✅ Add regression test to prevent recurrence
   - ✅ Conduct code review with CLI 2/3

4. **Re-Deployment** (after fix verified):
   - ✅ Deploy fix to staging
   - ✅ Run full compliance test suite
   - ✅ Manual verification on staging
   - ✅ Re-enable feature in production
   - ✅ Monitor for 48 hours

---

### 7.2 Riot Games Policy Change

**If Riot Games updates their Third-Party Application Policy**:

1. **Notification Channels**:
   - ✅ Monitor: https://developer.riotgames.com/policies
   - ✅ Subscribe: Riot Developer Portal newsletter
   - ✅ Join: Riot Developer Discord community

2. **Response Protocol**:
   - ✅ Review policy change within 7 days
   - ✅ Assess impact on Arena analysis
   - ✅ Update compliance checklist if needed
   - ✅ Update code/prompts/tests if needed
   - ✅ Re-run full compliance verification

---

## 8. Reference Materials

### 8.1 Riot Games Official Policies

- **Third-Party Application Policy**: https://developer.riotgames.com/policies/general
- **Terms of Service**: https://www.riotgames.com/en/terms-of-service
- **Developer Portal**: https://developer.riotgames.com

### 8.2 Internal Documentation

- **V2.3 Arena V1-Lite Algorithm**: `src/core/scoring/arena_v1_lite.py`
- **V2.3 Arena Prompt**: `src/prompts/v23_arena_analysis.txt`
- **V2.3 Multi-Mode Contracts**: `src/contracts/v23_multi_mode_analysis.py`
- **Project Chimera AI System Design**: `docs/PROJECT_CHIMERA_AI_SYSTEM_DESIGN.md`

### 8.3 Compliance Test Suite

- **Unit Tests**: `tests/unit/test_arena_compliance.py`
- **Integration Tests**: `tests/integration/test_discord_arena_compliance.py`
- **E2E Tests**: `tests/e2e/test_arena_full_flow_compliance.py`

---

## Appendix A: Forbidden Pattern Regex Library

```python
# Complete list of forbidden patterns for automated detection
FORBIDDEN_PATTERNS = [
    # Win Rate Patterns
    r"\d+\.?\d*%",  # Any percentage (e.g., "68%", "72.5%")
    r"\d+\.?\d*\s*百分比",
    r"胜率",
    r"win\s*rate",
    r"winrate",

    # Tier Ranking Patterns
    r"tier\s*[1-5]",
    r"[SABCDEF]\s*级",
    r"[SABCDEF]\s*tier",
    r"God\s*tier",
    r"Meta\s*pick",

    # Predictive Suggestion Patterns
    r"下场.*选择",
    r"建议.*选择.*胜率",
    r"推荐.*高胜率",
    r"Next\s*game.*choose",
    r"should\s*pick.*win\s*rate",

    # Competitive Advantage Patterns
    r"竞争优势",
    r"competitive\s*advantage",
    r"hidden\s*information",
    r"opponent.*cooldown",
    r"enemy.*ultimate.*timer",
]
```

---

**Document Status**: ✅ Production Ready
**Last Updated**: 2025-10-07
**Next Review**: Before Arena Mode Launch
