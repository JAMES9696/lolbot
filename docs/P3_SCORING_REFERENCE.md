# V1 Scoring System Quick Reference

**Version**: 1.0
**Date**: 2025-10-06
**Purpose**: Display guide for Discord bot UI integration

---

## Five Dimensions Overview

| Dimension | Weight | Range | Interpretation |
|-----------|--------|-------|----------------|
| **Combat Efficiency** | 30% | 0-100 | KDA, damage output, kill participation |
| **Economic Management** | 25% | 0-100 | CS/min, gold lead, item timing |
| **Objective Control** | 25% | 0-100 | Epic monsters, tower kills |
| **Vision Control** | 10% | 0-100 | Ward placement/clearing, vision denial |
| **Team Contribution** | 10% | 0-100 | Assist ratio, teamfight presence |
| **Total Score** | 100% | 0-100 | Weighted sum of all dimensions |

---

## Score Interpretation

### Total Score Tiers
```
95-100: 🏆 Legendary (S+)
85-94:  ⭐ Outstanding (S)
75-84:  💎 Excellent (A)
65-74:  ✨ Good (B)
50-64:  ⚡ Average (C)
35-49:  📉 Below Average (D)
0-34:   ❌ Poor (F)
```

### Per-Dimension Ranges
```
90-100: Exceptional
75-89:  Strong
60-74:  Solid
40-59:  Needs Improvement
0-39:   Critical Weakness
```

---

## Discord Embed Templates

### Template 1: Simple Player Card
```python
from discord import Embed, Color

def create_player_card(player_score: dict) -> Embed:
    """Create a simple player performance card."""
    total = player_score['total_score']
    tier = get_score_tier(total)

    embed = Embed(
        title=f"{tier['emoji']} {player_score['summoner_name']}",
        description=f"**Total Score**: {total:.1f}/100 ({tier['rank']})",
        color=tier['color']
    )

    embed.add_field(
        name="⚔️ Combat",
        value=f"{player_score['combat_efficiency']:.1f}/100",
        inline=True
    )
    embed.add_field(
        name="💰 Economy",
        value=f"{player_score['economic_management']:.1f}/100",
        inline=True
    )
    embed.add_field(
        name="🎯 Objectives",
        value=f"{player_score['objective_control']:.1f}/100",
        inline=True
    )
    embed.add_field(
        name="👁️ Vision",
        value=f"{player_score['vision_control']:.1f}/100",
        inline=True
    )
    embed.add_field(
        name="🤝 Teamplay",
        value=f"{player_score['team_contribution']:.1f}/100",
        inline=True
    )

    return embed

def get_score_tier(score: float) -> dict:
    """Map score to tier with emoji and color."""
    if score >= 95: return {'rank': 'S+', 'emoji': '🏆', 'color': Color.gold()}
    if score >= 85: return {'rank': 'S', 'emoji': '⭐', 'color': Color.purple()}
    if score >= 75: return {'rank': 'A', 'emoji': '💎', 'color': Color.blue()}
    if score >= 65: return {'rank': 'B', 'emoji': '✨', 'color': Color.green()}
    if score >= 50: return {'rank': 'C', 'emoji': '⚡', 'color': Color.light_gray()}
    if score >= 35: return {'rank': 'D', 'emoji': '📉', 'color': Color.orange()}
    return {'rank': 'F', 'emoji': '❌', 'color': Color.red()}
```

### Template 2: Detailed Analysis Card
```python
def create_detailed_card(player_score: dict, raw_metrics: dict) -> Embed:
    """Create detailed performance card with raw metrics."""
    embed = create_player_card(player_score)  # Use simple card as base

    # Add raw metrics section
    embed.add_field(
        name="📊 Combat Metrics",
        value=(
            f"KDA: {raw_metrics['kda']:.2f}\n"
            f"Kill Participation: {raw_metrics['kill_participation']:.1%}\n"
            f"Damage Share: {raw_metrics['damage_share']:.1%}"
        ),
        inline=False
    )

    embed.add_field(
        name="📊 Economic Metrics",
        value=(
            f"CS/min: {raw_metrics['cs_per_min']:.1f}\n"
            f"Gold/min: {raw_metrics['gold_per_min']:.0f}\n"
            f"Gold Lead @ 10min: {raw_metrics['gold_diff_10']:+.0f}"
        ),
        inline=False
    )

    return embed
```

### Template 3: Team Comparison
```python
def create_team_comparison(match_result: dict) -> Embed:
    """Create team-based score comparison."""
    blue_team = [p for p in match_result['player_scores'] if p['team_id'] == 100]
    red_team = [p for p in match_result['player_scores'] if p['team_id'] == 200]

    blue_avg = sum(p['total_score'] for p in blue_team) / 5
    red_avg = sum(p['total_score'] for p in red_team) / 5

    winner = "Blue Team" if blue_avg > red_avg else "Red Team"
    embed = Embed(
        title=f"Team Analysis - {winner} Victory",
        color=Color.blue() if winner == "Blue Team" else Color.red()
    )

    # Blue team scores
    blue_scores = "\n".join([
        f"{p['summoner_name']}: {p['total_score']:.1f}"
        for p in sorted(blue_team, key=lambda x: x['total_score'], reverse=True)
    ])
    embed.add_field(
        name=f"🔵 Blue Team (Avg: {blue_avg:.1f})",
        value=blue_scores,
        inline=True
    )

    # Red team scores
    red_scores = "\n".join([
        f"{p['summoner_name']}: {p['total_score']:.1f}"
        for p in sorted(red_team, key=lambda x: x['total_score'], reverse=True)
    ])
    embed.add_field(
        name=f"🔴 Red Team (Avg: {red_avg:.1f})",
        value=red_scores,
        inline=True
    )

    return embed
```

---

## Data Structure Reference

### Player Score Object
```python
{
    "participant_id": 1,
    "summoner_name": "PlayerName",
    "champion_name": "Ahri",
    "team_id": 100,  # 100=Blue, 200=Red
    "role": "MIDDLE",

    # Scores (0-100)
    "total_score": 78.5,
    "combat_efficiency": 85.2,
    "economic_management": 72.3,
    "objective_control": 68.9,
    "vision_control": 55.4,
    "team_contribution": 82.1,

    # Raw metrics (for detailed view)
    "raw_metrics": {
        # Combat
        "kills": 8,
        "deaths": 2,
        "assists": 12,
        "kda": 10.0,
        "kill_participation": 0.625,  # 62.5%
        "damage_share": 0.28,  # 28%

        # Economy
        "cs_per_min": 8.5,
        "gold_per_min": 425,
        "gold_diff_10": 350,  # +350 gold @ 10min

        # Objectives
        "tower_kills": 2,
        "epic_monster_kills": 1,
        "baron_kills": 0,
        "dragon_kills": 1,

        # Vision
        "wards_placed": 18,
        "wards_cleared": 5,
        "control_wards_purchased": 3,
        "vision_score": 42,

        # Team
        "teamfight_participation": 0.85,  # 85%
        "assist_ratio": 0.6  # Assists / (Kills + Assists)
    }
}
```

### Match Result Object
```python
{
    "match_id": "NA1_4567890123",
    "algorithm_version": "v1",
    "calculated_at": "2025-10-06T12:34:56Z",
    "processing_duration_ms": 1250.5,

    "player_scores": [
        # ... 10 player score objects (see above)
    ],

    "match_insights": {
        "winning_team": 100,  # Blue team
        "game_duration_seconds": 1845,  # 30:45
        "highest_scorer": {
            "summoner_name": "PlayerName",
            "score": 92.3
        },
        "mvp_candidate": {
            "summoner_name": "PlayerName",
            "reason": "Highest total score with strong all-around performance"
        }
    }
}
```

---

## Display Recommendations

### 1. Immediate Response (3s)
```
⏳ Analyzing match NA1_4567890123...
This will take about 30 seconds.
```

### 2. Progress Update (Optional)
```
📊 Fetched match data (5/10 players analyzed)
```

### 3. Final Result (30s)
```
✅ Analysis complete!

[Player Card Embed - see templates above]

💡 Powered by V1 Scoring Algorithm
```

### 4. Error Handling
```
❌ Analysis failed: Rate limit exceeded
⏳ Retrying in 60 seconds... (Attempt 2/3)

---

❌ Analysis failed: Match not found
Please check the match ID and try again.
```

---

## Score Weighting Justification

### Why 30% Combat?
Combat is the most visible aspect of performance and directly correlates with player impact in teamfights and skirmishes. KDA, damage output, and kill participation are primary indicators of mechanical skill and decision-making.

### Why 25% Economy?
Economic advantage translates to item power spikes and map pressure. CS/min, gold generation, and item timing determine a player's ability to scale and influence the game state.

### Why 25% Objectives?
League of Legends is won through objectives, not kills. Dragon souls, Baron buffs, and tower gold are critical win conditions. This dimension rewards strategic play over stat padding.

### Why 10% Vision?
Vision control is essential for macro play but harder to quantify. Ward placement, clearing, and control ward usage demonstrate map awareness and team utility.

### Why 10% Team Contribution?
League is a team game. Assist ratios and teamfight participation highlight players who enable their team's success rather than solo carry attempts.

---

## Advanced Usage

### Custom Thresholds (Optional)
```python
# For competitive analysis, you might want stricter tiers
COMPETITIVE_TIERS = {
    'S+': 98,  # Near-perfect
    'S': 90,
    'A': 80,
    'B': 70,
    'C': 60,
    'D': 45,
    'F': 0
}
```

### Dimensional Highlights
```python
def find_strengths_weaknesses(player_score: dict) -> dict:
    """Identify player's best and worst dimensions."""
    dimensions = {
        'Combat': player_score['combat_efficiency'],
        'Economy': player_score['economic_management'],
        'Objectives': player_score['objective_control'],
        'Vision': player_score['vision_control'],
        'Teamplay': player_score['team_contribution']
    }

    return {
        'strength': max(dimensions.items(), key=lambda x: x[1]),
        'weakness': min(dimensions.items(), key=lambda x: x[1])
    }

# Example output:
# strength: ('Combat', 92.5)
# weakness: ('Vision', 45.2)
```

### Role-Based Comparisons (Future Enhancement)
```python
# Compare player to role averages (requires historical data)
ROLE_AVERAGES = {
    'TOP': {'combat': 65, 'economy': 70, 'objectives': 60, 'vision': 55, 'team': 62},
    'JUNGLE': {'combat': 62, 'economy': 58, 'objectives': 75, 'vision': 65, 'team': 70},
    'MIDDLE': {'combat': 72, 'economy': 75, 'objectives': 55, 'vision': 50, 'team': 65},
    'BOTTOM': {'combat': 70, 'economy': 80, 'objectives': 50, 'vision': 45, 'team': 60},
    'UTILITY': {'combat': 50, 'economy': 45, 'objectives': 58, 'vision': 75, 'team': 78}
}
```

---

## Testing Display Logic

### Mock Data Generator
```python
def generate_mock_player_score(name: str = "TestPlayer") -> dict:
    """Generate realistic mock score for UI testing."""
    import random

    return {
        "participant_id": 1,
        "summoner_name": name,
        "champion_name": "Ahri",
        "team_id": 100,
        "role": "MIDDLE",
        "total_score": round(random.uniform(50, 95), 1),
        "combat_efficiency": round(random.uniform(60, 95), 1),
        "economic_management": round(random.uniform(55, 90), 1),
        "objective_control": round(random.uniform(45, 85), 1),
        "vision_control": round(random.uniform(40, 80), 1),
        "team_contribution": round(random.uniform(50, 90), 1),
        "raw_metrics": {
            "kills": random.randint(0, 15),
            "deaths": random.randint(0, 8),
            "assists": random.randint(0, 20),
            "cs_per_min": round(random.uniform(4.0, 10.0), 1),
            "gold_per_min": random.randint(300, 550),
            "wards_placed": random.randint(5, 30),
            "vision_score": random.randint(20, 80)
        }
    }

# Test all tier colors
for score in [98, 88, 78, 68, 58, 42, 25]:
    mock_player = generate_mock_player_score()
    mock_player['total_score'] = score
    embed = create_player_card(mock_player)
    # Visual inspection of embed colors/formatting
```

---

## FAQ

### Q: How often should scores be recalculated?
**A**: Scores are immutable once calculated. They represent a snapshot of match performance. If the algorithm is updated (v2), historical scores remain on v1.

### Q: Can I compare scores across patches?
**A**: Not recommended. Game balance changes (e.g., item reworks, dragon soul changes) affect what constitutes "good" performance. Compare within the same patch window.

### Q: What if a player has 0 score in a dimension?
**A**: This indicates critical underperformance in that area (e.g., 0% kill participation, 0 wards placed). Display as `0.0/100` with appropriate warnings.

### Q: How do I handle incomplete match data?
**A**: If Riot API returns incomplete timeline data, the task will fail at the `fetch` stage with `error_stage: "fetch"`. No score will be generated. Retry the task when data is available.

---

**Ready for UI Integration**: All score data structures and display templates verified.

**Next**: See `P3_CLI1_INTEGRATION_CHECKLIST.md` for backend integration steps.
