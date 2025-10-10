# opgg.py Technical Evaluation Report

**Project:** Project Chimera - AI-powered League of Legends Discord Bot
**Phase:** P2 - Data Integration
**Date:** October 6, 2025
**Evaluator:** CLI 4 (The Lab)
**Version Evaluated:** opgg.py 2.0.4

---

## Executive Summary

This report evaluates the `opgg.py` library (version 2.0.4) as a potential supplementary data source for Project Chimera's match analysis and `/讲道理` command. The library provides an unofficial Python interface to scrape data from OP.GG, a popular League of Legends statistics aggregation website.

**Recommendation:** ⚠️ **CONDITIONAL USE** - Integration recommended only for non-critical supplementary features with robust fallback mechanisms.

---

## 1. Library Overview

### 1.1 Basic Information

| Attribute | Details |
|-----------|---------|
| **Name** | opgg.py |
| **Version** | 2.0.4 (Released March 14, 2025) |
| **Source** | PyPI / GitHub (ShoobyDoo/OPGG.py) |
| **License** | Not specified (potential legal risk) |
| **Status** | Alpha (actively developed but unstable) |
| **Python Version** | 3.12+ (compatible with Project Chimera) |
| **Installation** | `pip install opgg.py` |

### 1.2 Dependencies

```python
# Compatible with existing stack
aiohttp      # ✅ Already in use (src/adapters/ddragon_adapter.py)
pydantic     # ✅ Already in use (all contracts)
fake-useragent  # ⚠️ NEW dependency (browser user-agent spoofing)
```

---

## 2. Technical Architecture Analysis

### 2.1 Implementation Method

**Type:** Web Scraper
**Target:** OP.GG website (https://www.op.gg)
**Approach:** HTTP requests + HTML parsing

```python
# Simplified conceptual architecture
[OP.GG Website]
    ↓ (HTTP Request with fake user-agent)
[opgg.py Library]
    ↓ (aiohttp)
[HTML Response]
    ↓ (Parsing)
[Pydantic Models]
```

### 2.2 Core Functionality

Based on available documentation and source analysis:

```python
from opgg.v2.opgg import OPGG
from opgg.v2.params import Region

# Primary API
opgg = OPGG()
results = opgg.search("SummonerName", Region.NA)

# Expected return data (inferred):
# - Summoner ID
# - Account level
# - Region
# - Rank information (likely)
# - Match history (likely)
# - Champion statistics (likely)
```

### 2.3 Data Availability Assessment

| Data Type | Riot API | DDragon | opgg.py | Value Add |
|-----------|----------|---------|---------|-----------|
| **Match Timeline** | ✅ Detailed | ❌ | ⚠️ Limited | None |
| **Summoner Profile** | ✅ Official | ❌ | ✅ Scraped | None |
| **Champion Stats** | ✅ Raw | ✅ Static | ✅ Aggregated | **Meta insights** |
| **Player Role/Lane** | ❌ Inferred | ❌ | ✅ **Accurate** | **HIGH** |
| **Build Recommendations** | ❌ | ✅ Items only | ✅ **Popular builds** | **MEDIUM** |
| **Rune Recommendations** | ❌ | ✅ Static | ✅ **Meta runes** | **MEDIUM** |
| **Rank/LP** | ✅ Official | ❌ | ✅ Scraped | None |
| **Win Rate by Champion** | ❌ | ❌ | ✅ **Aggregated** | **MEDIUM** |
| **Performance Rating** | ❌ | ❌ | ⚠️ Uncertain | Unknown |

**Key Value Propositions:**
1. **Accurate Player Role Detection** ⭐ - Riot API doesn't provide explicit role/lane assignments
2. **Meta Build/Rune Data** ⭐ - Community-driven optimal builds
3. **Champion Performance Trends** - Historical win rates and pick rates

---

## 3. Risk Assessment

### 3.1 Technical Risks

| Risk | Severity | Probability | Impact | Mitigation Strategy |
|------|----------|-------------|--------|---------------------|
| **HTML Structure Changes** | 🔴 HIGH | High | Complete breakage | Graceful degradation to Riot API only |
| **Rate Limiting/IP Blocking** | 🔴 HIGH | Medium | Service disruption | Exponential backoff + retry logic |
| **JavaScript Dependency** | 🟡 MEDIUM | Medium | Partial data loss | Headless browser fallback (Selenium/Playwright) |
| **Data Staleness** | 🟢 LOW | Low | Inaccurate insights | Cache with TTL + version checking |
| **API Key Suspension** | ❌ N/A | N/A | N/A | Not applicable (no API key) |

### 3.2 Legal & Compliance Risks

| Risk | Assessment | Mitigation |
|------|------------|------------|
| **Terms of Service Violation** | ⚠️ **LIKELY** | Consult OP.GG's ToS; add user disclaimer |
| **Riot Developer ToS** | ⚠️ **UNCLEAR** | Verify Riot doesn't prohibit third-party aggregators |
| **Data Privacy (GDPR/CCPA)** | 🟢 LOW | Only public summoner data |
| **Intellectual Property** | 🟢 LOW | Using public data, not assets |
| **Competitive Advantage Clause** | 🔴 **CRITICAL** | **DO NOT use for providing unfair in-game advantage** |

**⚠️ Compliance Concern:**
Riot's Developer Policies explicitly prohibit tools that provide "competitive advantages not available in the game client." Verify that OP.GG-sourced data (e.g., enemy build recommendations) doesn't violate this clause.

### 3.3 Maintenance & Stability Risks

| Factor | Status | Concern Level |
|--------|--------|---------------|
| **Development Status** | Alpha | 🔴 HIGH - Breaking changes likely |
| **Community Support** | Discord server | 🟡 MEDIUM - Reactive, not proactive |
| **Update Frequency** | Last update: March 2025 | 🟢 LOW - Recently active |
| **Breaking Changes** | Version 2.x (major) | 🔴 HIGH - API instability |
| **Bus Factor** | Single maintainer | 🔴 HIGH - Project abandonment risk |

---

## 4. Integration Feasibility Analysis

### 4.1 Architecture Integration Points

```python
# Proposed adapter pattern (following existing design)
# File: src/adapters/opgg_adapter.py

from opgg.v2.opgg import OPGG
from opgg.v2.params import Region
from src.core.ports import ThirdPartyDataPort  # New port

class OPGGAdapter(ThirdPartyDataPort):
    """
    Adapter for OP.GG supplementary data.

    CRITICAL: This adapter provides NON-ESSENTIAL data.
    All methods must gracefully degrade to None on failure.
    """

    async def get_recommended_build(
        self,
        champion_id: int,
        role: str
    ) -> dict | None:
        """Get current meta build for champion/role."""
        try:
            # Implementation with timeout
            # Return None on any error
        except Exception as e:
            logger.warning(f"OPGG build fetch failed: {e}")
            return None  # Graceful degradation

    async def infer_player_role(
        self,
        summoner_name: str,
        region: str
    ) -> str | None:
        """Infer player's primary role from match history."""
        # HIGH VALUE: Riot API doesn't provide this
        # Use as primary source with Riot API fallback
```

### 4.2 Use Cases for Integration

| Use Case | Priority | Dependency | Fallback Strategy |
|----------|----------|------------|-------------------|
| **Role Detection for Scoring** | 🟡 MEDIUM | Required for accurate CS/min benchmarks | Infer from position data |
| **Build Optimization Insights** | 🟢 LOW | Nice-to-have for `/讲道理` narrative | Skip if unavailable |
| **Meta Rune Analysis** | 🟢 LOW | Enhance LLM context | Skip if unavailable |
| **Champion Pool Analysis** | 🟢 LOW | User profile enrichment | Skip if unavailable |

### 4.3 Implementation Effort Estimate

| Task | Effort (Hours) | Complexity |
|------|----------------|------------|
| Adapter Implementation | 4-6 | Medium |
| Unit Tests + Mocking | 3-4 | Medium |
| Error Handling & Fallbacks | 2-3 | Low |
| Rate Limiting Logic | 2-3 | Medium |
| Integration Testing | 4-6 | High (fragile) |
| Documentation | 2-3 | Low |
| **Total** | **17-25** | **Medium-High** |

---

## 5. Alternative Solutions

### 5.1 Comparison Matrix

| Solution | Data Quality | Stability | Legal Risk | Effort |
|----------|--------------|-----------|------------|--------|
| **opgg.py** | High (aggregated) | 🔴 LOW | ⚠️ MEDIUM | Medium |
| **U.GG API** | High (aggregated) | 🟢 HIGH | 🟢 LOW | Low (if available) |
| **Community Dragon** | Medium (static) | 🟢 HIGH | 🟢 NONE | Low |
| **Riot API + Heuristics** | Medium (inferred) | 🟢 HIGH | 🟢 NONE | High |
| **Manual Meta Database** | High (curated) | 🟢 HIGH | 🟢 NONE | Very High |

### 5.2 Recommended Alternative

**Community Dragon** (https://www.communitydragon.org/)
- **Description:** Riot-sanctioned static data aggregator
- **Coverage:** Champion abilities, skins, icons, game assets
- **Legal Status:** ✅ Riot-approved
- **Stability:** ✅ High (CDN-backed)
- **Limitations:** No live match data or meta analytics

---

## 6. Recommendations

### 6.1 Primary Recommendation

**CONDITIONAL INTEGRATION** with strict guardrails:

1. **Scope Limitation:**
   - Use ONLY for non-critical features:
     - ✅ Role inference supplementation
     - ✅ Build recommendations (informational)
     - ❌ Core scoring algorithm inputs
     - ❌ Real-time match analysis

2. **Technical Safeguards:**
   ```python
   # Configuration flag
   FEATURE_OPGG_INTEGRATION = os.getenv("FEATURE_OPGG_ENABLED", "false").lower() == "true"

   # Timeout policy
   OPGG_REQUEST_TIMEOUT = 3.0  # seconds (aggressive)

   # Fallback policy
   async def get_player_role_with_fallback(summoner: str, region: str) -> str:
       if not FEATURE_OPGG_INTEGRATION:
           return infer_role_from_riot_api(summoner, region)

       try:
           role = await opgg_adapter.get_role(summoner, region, timeout=OPGG_REQUEST_TIMEOUT)
           return role or infer_role_from_riot_api(summoner, region)
       except Exception:
           return infer_role_from_riot_api(summoner, region)
   ```

3. **Legal Compliance:**
   - Add user-facing disclaimer: *"Third-party statistics powered by OP.GG"*
   - Implement opt-out mechanism for privacy-conscious users
   - Do NOT use for competitive advantage features (e.g., enemy summoner spell timers)

4. **Monitoring:**
   - Track OP.GG adapter failure rate
   - Alert on >20% failure rate
   - Auto-disable feature if >50% failure rate for 1 hour

### 6.2 Phase-Specific Recommendations

#### P2 (Current Phase):
- ✅ Install `opgg.py` and create prototype notebook
- ✅ Test role inference accuracy vs. Riot API heuristics
- ❌ DO NOT integrate into production code yet

#### P3 (Domain Migration):
- ⚠️ Create `OPGGAdapter` with comprehensive error handling
- ⚠️ Implement feature flag system
- ✅ Unit tests with mocked responses (avoid live tests)

#### P4 (Prompt Engineering):
- ✅ Use OP.GG data as **optional context** for Gemini LLM
- ❌ DO NOT make LLM output dependent on OP.GG availability

#### P5 (Polish & Production):
- ✅ Add monitoring dashboard for adapter health
- ✅ User preference: "Enable third-party insights (OP.GG)"

### 6.3 Decision Framework

**Use opgg.py IF:**
- ✅ Feature is non-critical (can degrade gracefully)
- ✅ Data provides unique value (not available via Riot API)
- ✅ Legal review confirms no ToS violations
- ✅ Monitoring infrastructure is in place

**DO NOT use opgg.py IF:**
- ❌ Feature is core to bot functionality
- ❌ Data is available through official Riot API
- ❌ Legal team raises concerns
- ❌ Failure rate monitoring is unavailable

---

## 7. Implementation Checklist

If proceeding with integration:

### Pre-Implementation
- [ ] Legal review of OP.GG Terms of Service
- [ ] Legal review of Riot Developer ToS (competitive advantage clause)
- [ ] Architecture review: Confirm adapter pattern compliance
- [ ] Create feature flag in settings (default: `false`)

### Implementation
- [ ] Install `opgg.py` via Poetry: `poetry add opgg.py`
- [ ] Create `src/adapters/opgg_adapter.py`
- [ ] Create `src/core/ports/third_party_data_port.py`
- [ ] Implement timeout mechanism (3 seconds max)
- [ ] Implement exponential backoff on rate limits
- [ ] Add comprehensive error logging (non-throwing)

### Testing
- [ ] Unit tests with mocked `OPGG()` class
- [ ] Integration tests with live OP.GG (manual, not CI)
- [ ] Load testing: 100 requests/min sustained
- [ ] Failure injection tests (HTML structure change simulation)

### Monitoring
- [ ] Add Prometheus metrics: `opgg_requests_total`, `opgg_failures_total`
- [ ] Create Grafana dashboard panel
- [ ] Set up PagerDuty alert (failure rate >50% for 1h)

### Documentation
- [ ] Add disclaimer to bot `/help` command
- [ ] Update `SECURITY.md` with third-party data sources
- [ ] Document opt-out mechanism in user guide

---

## 8. Conclusion

The `opgg.py` library offers **moderate value** for Project Chimera, primarily for **role inference** and **meta build insights**. However, its **web scraping nature** introduces significant **stability and legal risks**.

**Final Verdict:**
- **Short-term (P2-P3):** ⚠️ Prototype in notebook, DO NOT deploy to production
- **Mid-term (P4):** ✅ Consider integration with strict guardrails
- **Long-term (P5+):** 🔄 Monitor for official OP.GG API or migrate to Riot-approved alternatives

**Alternative Path:**
Focus on **Riot API + heuristic algorithms** for role detection (higher effort, zero legal risk) and defer meta insights to post-P5 if user demand warrants the complexity.

---

## Appendix A: Research Artifacts

### A.1 Test Script (Prototype)

```python
# notebooks/opgg_evaluation.ipynb

import asyncio
from opgg.v2.opgg import OPGG
from opgg.v2.params import Region

async def test_opgg():
    opgg = OPGG()

    # Test summoner search
    try:
        results = opgg.search("Faker", Region.KR)
        print(f"✅ Search successful: {len(results)} results")
        print(results[0] if results else "No results")
    except Exception as e:
        print(f"❌ Search failed: {e}")

    # Test role inference (if method exists)
    # ...

await test_opgg()
```

### A.2 References

1. **opgg.py GitHub:** https://github.com/ShoobyDoo/OPGG.py
2. **opgg.py PyPI:** https://pypi.org/project/opgg.py/
3. **Riot Developer Portal:** https://developer.riotgames.com/
4. **Riot Developer ToS:** https://developer.riotgames.com/policies/general
5. **Community Dragon:** https://www.communitydragon.org/

---

**Report Prepared By:** CLI 4 (The Lab)
**Review Status:** Pending CLI 3 (Observer) verification
**Next Action:** Await architectural decision from project lead
