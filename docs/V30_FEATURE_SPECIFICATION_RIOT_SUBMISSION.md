# Project Chimera V3.0 Feature Specification

**Submission to Riot Games Developer Relations Team**

**Document Version**: V1.0
**Submission Date**: 2025-10-07
**Application Name**: Project Chimera
**Riot Application ID**: TBD (pending registration)
**Developer**: [Your Organization Name]
**Contact**: [Your Email]
**Developer Portal URL**: https://developer.riotgames.com

---

## Executive Summary

Project Chimera is an **educational post-game analysis tool** for League of Legends players, providing AI-powered feedback to help them understand their performance and improve their gameplay skills. We are submitting this V3.0 feature specification to request **compliance pre-approval** for our planned real-time analysis capabilities.

**Key Points**:
- ✅ **Current Status (V2.3)**: Production-ready post-game analysis for SR, ARAM, and Arena modes
- ✅ **Compliance Track Record**: Zero policy violations; strict adherence to Riot's Third-Party Application Policy
- ⚠️ **V3.0 Vision**: Real-time in-game analysis (if permitted) to provide educational feedback during gameplay
- 🔒 **Compliance Commitment**: All V3.0 features will strictly adhere to Riot's prohibition on competitive advantages

**Request**:
We respectfully request Riot Games' review and guidance on the following V3.0 features to ensure full compliance with your Third-Party Application Policy before implementation.

---

## 1. Application Background

### 1.1 Project Chimera Overview

**Mission**: Empower League of Legends players to learn and improve through personalized, AI-powered post-game analysis.

**Current Capabilities (V2.3)**:
- **Post-Game Analysis**: Analyzes completed matches using Match-V5 and Timeline APIs
- **Multi-Mode Support**: Summoner's Rift (V2.2), ARAM (V1-Lite), Arena (V1-Lite)
- **Educational Focus**: Provides actionable feedback on combat, teamplay, vision, economy, and objectives
- **Compliance-First Design**: Explicitly prohibits win rate predictions, tier rankings, and competitive advantage data

**User Base**: Discord-integrated bot serving [X] active users across [Y] servers

**Data Sources (Current)**:
- Riot Match-V5 API (post-game data only)
- Riot Timeline API (detailed event logs)
- Riot Data Dragon (static champion/item data)

---

### 1.2 Compliance Track Record (V1.0 - V2.3)

**Policy Adherence**:
- ✅ **No Competitive Advantages**: All analysis is retrospective; no real-time decision-making assistance
- ✅ **No Forbidden Data**: No win rate predictions, hidden information, or tier rankings (especially for Arena Augments)
- ✅ **Official APIs Only**: Exclusively uses Riot-provided APIs; no third-party stats scrapers
- ✅ **Rate Limiting Compliance**: Respects all API rate limits and uses production API keys

**Compliance Measures Implemented**:
1. **Code-Level Safeguards**: Forbidden pattern detection in Arena Augment analysis
2. **Prompt-Level Constraints**: LLM prompts explicitly prohibit competitive advantage suggestions
3. **Automated Testing**: Compliance test suite validates all outputs for policy violations
4. **Production Monitoring**: Sentry alerts configured for compliance violations

**Incidents**: Zero policy violations reported since launch (2025-09-25 to present)

---

## 2. V3.0 Feature Proposal: Real-Time Educational Analysis

### 2.1 Feature Vision

**Goal**: Provide **educational, non-intrusive feedback** during gameplay to help players learn in real-time, similar to a coach observing and providing tips.

**Core Principle**:
> "V3.0 will ONLY provide information that is already visible to the player in the game client. We will NOT create competitive advantages through hidden data or predictive analytics."

**Example Use Cases**:

✅ **Allowed (Educational)**:
- "You have placed 0 wards in the last 5 minutes. Consider placing a ward for map vision." (Visible in game: ward count)
- "Your CS is 45 at 10 minutes. The average for your rank is 60-70 CS. Focus on last-hitting minions." (Visible in game: CS count)
- "You have not participated in the last 2 teamfights. Consider joining your team for objectives." (Visible in game: minimap)

❌ **Prohibited (Competitive Advantage)**:
- "Enemy jungler's ultimate is on cooldown for 35 seconds. Push now." (Hidden information)
- "Enemy support has 75 gold. They cannot afford wards yet." (Hidden information)
- "This team composition has a 68% win rate against yours." (Predictive analytics)

---

### 2.2 Technical Implementation Plan

#### Data Source: Live Client Data API

**API**: `https://127.0.0.1:2999/liveclientdata/allgamedata`

**Rationale**:
- ✅ **Official Riot API**: Provided and documented by Riot Games
- ✅ **Client-Visible Data Only**: API returns only data visible in the game client (player's own stats, visible enemy positions, etc.)
- ✅ **Local-Only**: API runs on localhost; no remote data exposure

**Data Fields We Plan to Use**:

| Category | Field | Visible in Game? | Use Case |
|----------|-------|------------------|----------|
| **Player Stats** | `level`, `currentGold`, `totalGold` | ✅ Yes (HUD) | Educational feedback on economy |
| **Player Stats** | `creepScore` | ✅ Yes (HUD) | CS benchmarking vs rank average |
| **Player Stats** | `wardScore` | ✅ Yes (Tab menu) | Vision control education |
| **Game Time** | `gameTime` | ✅ Yes (Clock) | Time-based milestone reminders |
| **Active Player** | `championStats` | ✅ Yes (HUD) | Ability cooldown reminders |
| **Minimap Events** | `events` (visible only) | ✅ Yes (Minimap) | Objective participation tracking |

**Data Fields We Will NOT Use**:

| Category | Field | Why Prohibited |
|----------|-------|----------------|
| **Enemy Hidden Data** | `currentGold` (enemy) | ❌ Not visible in game (competitive advantage) |
| **Enemy Hidden Data** | `abilityCD` (enemy) | ❌ Not visible in game (competitive advantage) |
| **Enemy Hidden Data** | `itemSlots` (enemy, if hidden) | ❌ Not visible in game (competitive advantage) |

---

#### Analysis Triggers

**Real-Time Feedback Triggers** (all based on visible data):

1. **CS Benchmark Alerts** (Every 5 minutes):
   - If `creepScore` < (rank_average * 0.8): "Your CS is below average for your rank. Focus on last-hitting."
   - Threshold: Visible player CS vs public rank benchmarks (not opponent-specific)

2. **Vision Reminders** (Every 3 minutes):
   - If `wardScore` == 0 in last 5 min: "Consider placing wards for map vision."
   - Threshold: Based on player's own ward count (visible in Tab menu)

3. **Objective Participation Reminders** (On objective spawn):
   - If player far from objective (>5000 units) when drake/baron spawns: "Objective spawning soon. Consider rotating."
   - Threshold: Based on player's position (visible on minimap)

4. **Death Analysis** (Post-death, if spectate mode available):
   - Analyze player's death event: "You were caught out alone. Stay closer to team."
   - Threshold: Based on player's death events (visible in death recap)

**Frequency Limits**:
- Max 1 alert per category per 5 minutes (avoid spam)
- User-configurable: Can disable specific alert categories

---

#### Compliance Safeguards

**Technical Safeguards**:

1. **No Hidden Data Access**:
   ```python
   # Forbidden: Accessing enemy hidden stats
   if data["allPlayers"][enemy_index]["currentGold"] < 300:  # ❌ FORBIDDEN
       alert("Enemy cannot buy wards")

   # Allowed: Accessing player's own visible stats
   if data["activePlayer"]["creepScore"] < 50:  # ✅ ALLOWED
       alert("Your CS is below average")
   ```

2. **No Predictive Analytics**:
   ```python
   # Forbidden: Win rate predictions
   win_probability = calculate_win_rate(team_comp, enemy_comp)  # ❌ FORBIDDEN

   # Allowed: Educational benchmarks
   avg_cs_for_rank = get_public_rank_benchmark(player_rank)  # ✅ ALLOWED
   ```

3. **Delayed Feedback** (Optional):
   - Introduce 30-second delay for non-critical feedback to avoid "automatic assistant" feel
   - Preserve educational intent, avoid "auto-pilot" experience

**Prompt-Level Safeguards**:

```
System Prompt for Real-Time Analysis:

You are an educational League of Legends coach. Your role is to provide
feedback based ONLY on information visible to the player in the game client.

STRICT RULES:
1. NEVER provide information about enemy hidden stats (gold, cooldowns, item timings)
2. NEVER predict outcomes or suggest "optimal plays" based on win rates
3. ONLY provide educational reminders about the player's own performance
4. Frame all feedback as learning opportunities, not commands

Example Allowed Feedback:
- "Your CS is 45 at 10 minutes. The average for Gold rank is 65. Focus on last-hitting."
- "You have not placed wards in 5 minutes. Consider buying and placing wards."

Example Forbidden Feedback:
- "Enemy jungler's ultimate is on cooldown. Push now." (Hidden information)
- "Your team has 72% win rate with this strategy." (Predictive analytics)
```

---

### 2.3 User Experience Design

#### Feedback Delivery Methods

**Option 1: Discord Bot Notifications** (Preferred for initial launch):
- User enables `/live-analysis` in Discord
- Bot polls Live Client Data API (with user consent)
- Sends educational tips to user's Discord DM during game
- **Pros**: Non-intrusive, doesn't overlay game
- **Cons**: Requires alt-tabbing to view

**Option 2: In-Game Overlay** (Future consideration, requires additional approval):
- Lightweight overlay with educational tips
- **Compliance Concern**: May be considered intrusive; requires Riot approval
- **Status**: Not included in V3.0 initial proposal

**Frequency & Intrusiveness**:
- Max 3-5 tips per game (non-spammy)
- User can disable/enable specific tip categories
- No audio alerts (avoid distraction)

---

### 2.4 Privacy & Security

**Data Handling**:
- ✅ **Local-Only API Access**: Live Client Data API is localhost-only; no remote data transmission
- ✅ **No Sensitive Data Storage**: Real-time tips are ephemeral; not stored in database
- ✅ **User Consent Required**: Users must explicitly opt-in via `/live-analysis enable`

**Account Security**:
- ✅ **No Account Credentials**: Live Client Data API requires no login; read-only
- ✅ **No Game Client Modification**: Purely API-based; no memory reading or injection

---

## 3. Compliance Risk Assessment & Mitigation

### 3.1 Identified Risks

| Risk | Severity | Mitigation Strategy |
|------|----------|---------------------|
| **Hidden Data Exposure** | 🔴 High | Technical safeguard: Whitelist only visible data fields; block enemy hidden stats |
| **Predictive Analytics Creep** | 🔴 High | Prompt-level constraint: LLM explicitly prohibited from win rate predictions |
| **User Over-Reliance** | 🟡 Medium | Frequency limiting: Max 3-5 tips/game; emphasize educational intent in UI |
| **Overlay Intrusiveness** | 🟡 Medium | V3.0 uses Discord DMs only; in-game overlay deferred pending Riot approval |
| **API Abuse** | 🟢 Low | Rate limiting: Poll Live Client API at 10-second intervals (not real-time spam) |

---

### 3.2 Compliance Boundaries (Red Lines)

**We WILL NOT**:
1. ❌ Provide enemy hidden information (gold, cooldowns, item timings)
2. ❌ Predict match outcomes or suggest "optimal plays" based on win rates
3. ❌ Automate decision-making (e.g., "auto-ward here" overlays)
4. ❌ Display Arena Augment win rates or tier rankings (existing V2.3 compliance)
5. ❌ Modify game client memory or inject code

**We WILL**:
1. ✅ Provide educational feedback based on player's own visible stats
2. ✅ Offer learning opportunities (e.g., "Your CS is below average for your rank")
3. ✅ Respect user consent (opt-in only, can disable anytime)
4. ✅ Use official Riot APIs exclusively
5. ✅ Maintain full transparency with Riot via this pre-approval process

---

### 3.3 V2.2/V2.3 Research-Based Risk Mitigation

**Lessons Learned from V2.3 Arena Compliance**:

1. **Explicit Prohibition Lists**:
   - V2.3 Arena prompts include "Forbidden Content" sections
   - V3.0 will extend this to real-time analysis prompts

2. **Automated Compliance Testing**:
   - V2.3 uses regex-based forbidden pattern detection
   - V3.0 will add real-time output validation before user delivery

3. **Incident Response Plan**:
   - V2.3 established kill-switch for compliance violations
   - V3.0 will use `ENABLE_LIVE_ANALYSIS=False` feature flag for instant disable

**V3.0-Specific Enhancements**:

```python
# Real-Time Compliance Validator (new for V3.0)
def validate_live_analysis_output(tip: str) -> bool:
    """Validate real-time tip for compliance before delivery."""

    # Forbidden patterns (same as V2.3 + real-time specific)
    forbidden_patterns = [
        r"enemy.*gold",
        r"enemy.*cooldown",
        r"enemy.*ultimate.*\d+\s*seconds",
        r"win.*rate.*\d+%",
        r"push.*now",  # Suggests real-time decision
        r"optimal.*play",
    ]

    for pattern in forbidden_patterns:
        if re.search(pattern, tip, re.IGNORECASE):
            sentry_sdk.capture_message(
                f"V3.0 COMPLIANCE VIOLATION: {pattern}",
                level="error"
            )
            return False  # Block delivery

    return True  # Safe to deliver
```

---

## 4. Comparison with Existing Third-Party Tools

### 4.1 Competitive Landscape

| Tool | Real-Time Analysis | Compliance Status | Competitive Advantage? |
|------|-------------------|-------------------|------------------------|
| **Blitz.gg** | ✅ Yes (champion counters, rune suggestions) | ✅ Approved (presumably) | ⚠️ Moderate (predictive data) |
| **Mobalytics** | ✅ Yes (performance tracking) | ✅ Approved (presumably) | ⚠️ Moderate (tier lists) |
| **OP.GG** | ❌ No (post-game only) | ✅ Approved | ✅ Low (retrospective) |
| **Project Chimera V2.3** | ❌ No (post-game only) | ✅ Compliant | ✅ Low (educational) |
| **Project Chimera V3.0** | ✅ Yes (educational tips) | ⏳ Pending Riot Approval | ✅ Low (visible data only) |

**Differentiation**:
- **Blitz/Mobalytics**: Focus on pre-game optimization (runes, builds) + win rate data
- **Project Chimera V3.0**: Focus on in-game learning (educational tips) + no win rate data

**Compliance Advantage**:
- We explicitly avoid tier lists and win rate predictions (unlike some competitors)
- We use official APIs exclusively (no web scraping)
- We maintain full transparency with Riot via this pre-approval process

---

### 4.2 Why V3.0 is Different

**Educational Philosophy**:
- **Blitz**: "Here's the best build for this matchup" (prescriptive)
- **Project Chimera**: "Your CS is below average. Practice last-hitting." (educational)

**Data Transparency**:
- **Blitz**: Uses aggregated win rate data (may create meta pressure)
- **Project Chimera**: Uses player's own visible stats only (no meta influence)

**Compliance-First Design**:
- **Blitz**: Real-time champion counters (borderline competitive advantage)
- **Project Chimera**: Real-time skill reminders (purely educational)

---

## 5. Monetization & Commercial Use (Future)

**Current Status**: Project Chimera is currently **free and non-commercial**.

**Future Monetization Plans** (subject to Riot approval):

1. **Premium Features** (Paid Tier):
   - Advanced post-game analysis (deeper insights)
   - Personalized coaching recommendations (AI-generated learning paths)
   - **Note**: Premium features will NOT include real-time analysis unless explicitly approved by Riot

2. **Sponsorship/Advertising**:
   - Potential Discord bot sponsorships (e.g., "Powered by [Partner]")
   - **Note**: Will require written Riot approval per Third-Party Application Policy

**Commitment**:
- ✅ We will notify Riot Games of any monetization plans before implementation
- ✅ We will seek written approval for commercial features
- ✅ We will not gate compliance-critical features behind paywalls

---

## 6. Technical Specifications

### 6.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User (In-Game)                          │
└───────────────┬─────────────────────────────────────────────┘
                │
                ├─ Live Client Data API (localhost:2999)
                │  └─ Exposes: Player stats, visible events
                │
                ├─ Project Chimera Backend (CLI 2)
                │  ├─ Poll Live Client API (10-second interval)
                │  ├─ Analyze visible data (CS, wards, participation)
                │  ├─ Generate educational tips (LLM)
                │  └─ Validate compliance (forbidden pattern check)
                │
                ├─ Discord Bot (CLI 3)
                │  └─ Send tips to user's DM (non-intrusive)
                │
                └─ Compliance Monitoring (Sentry)
                   └─ Alert on forbidden pattern detection
```

### 6.2 API Usage

**Live Client Data API**:
- **Endpoint**: `https://127.0.0.1:2999/liveclientdata/allgamedata`
- **Polling Frequency**: Every 10 seconds (not real-time spam)
- **Rate Limiting**: Local API (no Riot rate limits apply)
- **Authentication**: None required (read-only, localhost)

**Match-V5 API** (post-game only):
- **Endpoint**: `https://{region}.api.riotgames.com/lol/match/v5/matches/{matchId}`
- **Rate Limiting**: Respects Riot production limits (20 req/sec, 100 req/2min)
- **Authentication**: Production API key

**Data Dragon** (static data):
- **Endpoint**: `https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json`
- **Caching**: Static data cached for 24 hours (reduce load)

---

### 6.3 System Requirements

**User Requirements**:
- Windows 10/11 or macOS 10.15+
- League of Legends client installed
- Discord account (for bot notifications)

**Backend Requirements**:
- Python 3.11+
- Celery + Redis (task queue)
- PostgreSQL 15+ (match data storage)
- Gemini 2.0 Flash API (LLM)

---

## 7. Testing & Quality Assurance

### 7.1 Compliance Testing Strategy

**Pre-Launch Testing**:

1. **Automated Compliance Tests** (CI/CD):
   - Regex-based forbidden pattern detection (see V2.4 Compliance Checklist)
   - Test cases for hidden data exposure scenarios
   - Test cases for predictive analytics detection

2. **Manual Review**:
   - CLI 4 (Algorithm Designer) reviews all LLM prompts
   - CLI 2 (Backend) reviews all Live Client API integrations
   - CLI 3 (SRE) reviews all Discord message templates

3. **Closed Beta Testing**:
   - 10-20 trusted users test V3.0 real-time analysis
   - Manual review of all delivered tips for compliance
   - User feedback on educational value vs intrusiveness

**Success Criteria**:
- ✅ Zero forbidden pattern detections in 100+ test cases
- ✅ Zero user reports of competitive advantage features
- ✅ 90%+ user satisfaction with educational value

---

### 7.2 Ongoing Monitoring

**Production Monitoring**:

1. **Sentry Compliance Alerts**:
   - Alert on forbidden pattern detection in real-time tips
   - Alert on Live Client API access errors
   - Alert on LLM prompt injection attempts

2. **User Feedback Channels**:
   - Discord `/feedback` command for user reports
   - Monthly user surveys on feature value
   - Public GitHub issue tracker for bug reports

3. **Quarterly Riot Policy Reviews**:
   - Review Riot Developer Portal for policy updates
   - Update compliance checks accordingly
   - Re-run full test suite after policy changes

---

## 8. Rollout Plan

### 8.1 Phased Rollout

**Phase 1: Closed Beta** (2 weeks after Riot approval):
- 20 invited users
- Discord DM notifications only
- Limited tip categories (CS, vision only)
- Heavy manual monitoring

**Phase 2: Open Beta** (4 weeks after Riot approval):
- 500 users (opt-in via Discord)
- Add objective participation tips
- Automated compliance monitoring active
- Weekly compliance reports to Riot (if requested)

**Phase 3: General Availability** (8 weeks after Riot approval):
- All Project Chimera users
- Full feature set enabled
- Quarterly compliance audits

**Kill-Switch Plan**:
- Feature flag: `ENABLE_LIVE_ANALYSIS=False`
- Can disable within 5 minutes via environment variable
- Discord announcement template pre-written

---

### 8.2 Success Metrics

**Educational Impact**:
- **Metric**: % users showing improved CS/vision scores after using V3.0
- **Target**: 20% improvement in tracked metrics over 30 days

**User Engagement**:
- **Metric**: % users enabling `/live-analysis` feature
- **Target**: 40% of active users opt-in

**Compliance**:
- **Metric**: # of compliance violations detected
- **Target**: Zero violations (threshold for feature disable)

---

## 9. Contact & Support

### 9.1 Developer Information

**Organization**: [Your Organization Name]
**Primary Contact**: [Your Name], [Your Role]
**Email**: [Your Email]
**Discord**: [Your Discord Handle]
**GitHub**: [Your GitHub Repo URL]

### 9.2 Riot Developer Portal Registration

**Application ID**: TBD (pending registration)
**Application Name**: Project Chimera
**Application Type**: Discord Bot + Web Service
**APIs Used**: Match-V5, Timeline, Live Client Data, Data Dragon

### 9.3 Support Channels

**User Support**: Discord server `/support` command
**Bug Reports**: GitHub Issues
**Compliance Inquiries**: [Your Email] (direct to Riot Developer Relations)

---

## 10. Appendices

### Appendix A: Riot Games Third-Party Application Policy Excerpts

> "Third-party applications must not provide players with a competitive advantage through the use of data that is not available within the game client."

**Our Interpretation**:
- ✅ Live Client Data API provides "data available within the game client"
- ✅ Our analysis is based on visible player stats only
- ❌ We do not expose enemy hidden data (gold, cooldowns, etc.)

**Compliance Alignment**:
- V3.0 features are designed to stay within "data available within the game client" boundary
- All tips are educational, not prescriptive
- No predictive analytics or win rate data

---

### Appendix B: Example Real-Time Tips

**CS Benchmark Tip**:
```
💡 Educational Tip: CS Benchmark

Your CS: 45 at 10:00
Average for Gold IV: 65 CS

Tips:
- Focus on last-hitting minions under tower
- Avoid trading when cannon wave arrives
- Practice CS drills in Practice Tool

This tip is based on your own visible CS count and public rank benchmarks.
```

**Vision Reminder Tip**:
```
💡 Educational Tip: Vision Control

You have not placed wards in the last 5 minutes.

Tips:
- Place wards in river bushes for jungle vision
- Use Control Wards to deny enemy vision
- Check your ward count in the Tab menu

This tip is based on your own visible ward score.
```

**Objective Participation Tip**:
```
💡 Educational Tip: Objective Participation

Dragon spawning in 30 seconds. You are farming top lane.

Tips:
- Consider rotating to dragon pit if your team is grouping
- Ping your team if you cannot make it
- Balance wave management with objective timing

This tip is based on your visible position on the minimap.
```

---

### Appendix C: Comparison Table: V2.3 vs V3.0

| Feature | V2.3 (Current) | V3.0 (Proposed) |
|---------|----------------|-----------------|
| **Analysis Timing** | Post-game only | Real-time + post-game |
| **Data Source** | Match-V5 + Timeline | Live Client Data + Match-V5 |
| **Feedback Delivery** | Discord embed (after game) | Discord DM (during game) |
| **User Opt-In** | Automatic (all users) | Explicit opt-in (`/live-analysis enable`) |
| **Compliance Risk** | Low (retrospective) | Medium (real-time, requires approval) |
| **Educational Value** | High (detailed post-game) | Very High (immediate learning) |

---

## 11. Conclusion

Project Chimera V3.0 represents our commitment to **educational excellence** while maintaining **strict compliance** with Riot Games' Third-Party Application Policy. We have designed V3.0 with the following principles:

1. **Transparency**: Full disclosure of features and data usage
2. **Compliance-First**: Technical and prompt-level safeguards against policy violations
3. **Educational Focus**: Empowering players to learn, not automating their decisions
4. **User Consent**: Opt-in model with clear controls

We respectfully request Riot Games' review and guidance on this specification. We are committed to working collaboratively with Riot to ensure V3.0 meets all compliance requirements before launch.

**Next Steps**:
1. Riot Developer Relations team review this specification
2. Feedback/guidance on compliance boundaries
3. Written approval or revision requests
4. Closed beta launch (pending approval)

**Thank you for your consideration.**

---

**Submission Checklist**:
- [x] Feature specification completed
- [x] Compliance risk assessment included
- [x] Comparison with existing tools provided
- [x] Technical architecture documented
- [x] Rollout plan defined
- [x] Contact information provided
- [ ] Submitted via Riot Developer Portal messaging system
- [ ] Await Riot Developer Relations response

**Document Status**: ✅ Ready for Submission
**Last Updated**: 2025-10-07
