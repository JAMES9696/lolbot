"""Core scoring calculation logic - Pure domain functions with zero I/O.

SOLID Compliance:
- Single Responsibility: Each function calculates one dimension
- Open/Closed: Extensible via new dimension calculators
- Interface Segregation: Small, focused function signatures
- Dependency Inversion: Depends on MatchTimeline abstraction, not adapters

CRITICAL: This module MUST NOT contain any:
- Riot API calls
- Database operations
- File I/O
- Network requests
All I/O operations belong in adapters layer.
"""

import logging
from collections import defaultdict
from typing import Any

import numpy as np

from src.contracts.timeline import MatchTimeline
from src.core.scoring.models import MatchAnalysisOutput, PlayerScore

logger = logging.getLogger(__name__)

_CONVERSION_LOOKAHEAD_MS = 120_000
_PERSONAL_OBJECTIVE_WEIGHT = 0.6
_TEAM_CONVERSION_WEIGHT = 0.4
_CONVERSION_RATE_WEIGHT = 0.7
_CONVERSION_VOLUME_WEIGHT = 0.3
_CONVERSION_VOLUME_NORMALIZER = 6.0


def calculate_combat_efficiency(timeline: MatchTimeline, participant_id: int) -> dict[str, float]:
    """Calculate combat efficiency metrics.

    Returns:
        Dict with normalized scores (0-1) for:
        - kda_score: Kill/Death/Assist ratio normalized
        - damage_efficiency: Damage per 1000 gold
        - kill_participation: Team kill participation %
    """
    # Extract kill/death/assist from timeline events
    kills = 0
    deaths = 0
    assists = 0

    for frame in timeline.info.frames:
        for event in frame.events:
            if event.get("type") == "CHAMPION_KILL":
                if event.get("killerId") == participant_id:
                    kills += 1
                if event.get("victimId") == participant_id:
                    deaths += 1
                if participant_id in event.get("assistingParticipantIds", []):
                    assists += 1

    # Calculate KDA (prevent division by zero)
    kda = (kills + assists) / max(deaths, 1)
    kda_score = min(kda / 10, 1.0)  # Normalize to 0-1, cap at KDA=10

    # Kill participation using timeline helper method
    kill_participation = timeline.get_kill_participation(participant_id)
    kill_participation_score = kill_participation / 100  # Convert % to 0-1

    # Damage efficiency from last frame
    last_frame = timeline.info.frames[-1]
    participant_frame = last_frame.participant_frames.get(str(participant_id))

    damage_efficiency = 0.0
    if participant_frame:
        damage_to_champs = participant_frame.damage_stats.total_damage_done_to_champions
        gold_spent = participant_frame.total_gold

        # Damage per 1000 gold (normalize around 1000 damage/1k gold baseline)
        damage_efficiency_raw = damage_to_champs / max(gold_spent / 1000, 1)
        damage_efficiency = min(damage_efficiency_raw / 1000, 1.0)

    return {
        "kda_score": kda_score,
        "kill_participation": kill_participation_score,
        "damage_efficiency": damage_efficiency,
        "raw_kda": kda,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
    }


def calculate_economic_management(timeline: MatchTimeline, participant_id: int) -> dict[str, float]:
    """Calculate economic management metrics.

    Returns:
        Dict with normalized scores for:
        - cs_efficiency: CS per minute normalized
        - gold_lead: Gold advantage vs opponent team average
        - item_timing: Major item purchase rate
    """
    last_frame = timeline.info.frames[-1]
    participant_frame = last_frame.participant_frames.get(str(participant_id))

    if not participant_frame:
        return {
            "cs_efficiency": 0.0,
            "gold_lead": 0.5,
            "item_timing": 0.5,
            "cs_per_min": 0.0,
            "total_gold": 0,
            "gold_difference": 0,
        }

    # CS/min calculation
    game_duration_min = last_frame.timestamp / 60000  # ms to minutes
    total_cs = participant_frame.minions_killed + participant_frame.jungle_minions_killed
    cs_per_min = total_cs / max(game_duration_min, 1)

    # CS efficiency (normalize around 10 CS/min as perfect)
    cs_efficiency = min(cs_per_min / 10, 1.0)

    # Gold lead/deficit vs opponent team
    team_id = 100 if participant_id <= 5 else 200
    opponent_team_ids = range(6, 11) if team_id == 100 else range(1, 6)

    opponent_gold_values: list[int] = []
    for opp_id in opponent_team_ids:
        opp_frame = last_frame.participant_frames.get(str(opp_id))
        if opp_frame:
            opponent_gold_values.append(opp_frame.total_gold)

    avg_opponent_gold = (
        np.mean(opponent_gold_values).item()
        if opponent_gold_values
        else participant_frame.total_gold
    )
    gold_difference = participant_frame.total_gold - avg_opponent_gold

    # Normalize gold lead (-5000 to +5000 range)
    gold_lead_score = (gold_difference + 5000) / 10000
    gold_lead_score = max(0.0, min(1.0, gold_lead_score))

    # Item timing analysis
    major_item_purchases = 0
    for frame in timeline.info.frames:
        for event in frame.events:
            if (
                event.get("type") == "ITEM_PURCHASED"
                and event.get("participantId") == participant_id
            ):
                item_id = event.get("itemId", 0)
                # Major items have IDs >= 3000
                if item_id >= 3000:
                    major_item_purchases += 1

    # Normalize (expect 2-4 major items)
    item_timing_score = min(major_item_purchases / 4, 1.0)

    return {
        "cs_efficiency": cs_efficiency,
        "gold_lead": gold_lead_score,
        "item_timing": item_timing_score,
        "cs_per_min": cs_per_min,
        "total_cs": int(total_cs),
        "total_gold": participant_frame.total_gold,
        "gold_difference": gold_difference,
    }


def calculate_objective_control(timeline: MatchTimeline, participant_id: int) -> dict[str, Any]:
    """Calculate objective control metrics.

    Returns:
        Dict with normalized scores for:
        - epic_monster_participation: Dragon/Baron/Herald participation
        - tower_participation: Tower/Building destruction participation
        - objective_setup: Combined objective control quality (personal + team conversions)
    """
    epic_monsters = 0
    tower_kills = 0
    total_epic_monsters = 0
    total_towers = 0
    team_kills = 0
    team_conversions = 0

    team_id = 100 if participant_id <= 5 else 200
    team_participant_ids = list(range(1, 6)) if team_id == 100 else list(range(6, 11))
    conversion_events: list[dict[str, Any]] = []

    def _event_timestamp(ev: dict[str, Any]) -> int:
        """Best-effort timestamp extraction with graceful fallback."""
        ts = ev.get("timestamp")
        if ts is None:
            ts = ev.get("realTimestamp")
        try:
            return int(ts) if ts is not None else 0
        except (TypeError, ValueError):
            return 0

    def _conversion_bucket(ev: dict[str, Any]) -> str | None:
        """Map objective events to canonical bucket names."""
        et = ev.get("type")
        if et == "BUILDING_KILL":
            building_type = str(ev.get("buildingType", ""))
            if building_type == "TOWER_BUILDING":
                return "towers"
            if building_type == "INHIBITOR_BUILDING":
                return "inhibitors"
        elif et == "ELITE_MONSTER_KILL":
            monster_type = str(ev.get("monsterType", ""))
            if monster_type == "DRAGON":
                return "drakes"
            if monster_type == "BARON_NASHOR":
                return "barons"
            if monster_type in ("RIFTHERALD", "HORDE_RIFTHERALD"):
                return "heralds"
            if monster_type in ("HORDE", "VOIDGRUB"):
                return "voidgrubs"
            if monster_type in ("ATAKHAN", "RUINOUS_ATAKHAN", "VORACIOUS_ATAKHAN"):
                return "atakhans"
        return None

    conversion_breakdown: dict[str, int] = defaultdict(int)

    for frame in timeline.info.frames:
        for event in frame.events:
            # Epic monster kills
            if event.get("type") == "ELITE_MONSTER_KILL":
                killer_id = event.get("killerId", 0)
                if killer_id in team_participant_ids:
                    total_epic_monsters += 1
                    if killer_id == participant_id:
                        epic_monsters += 1

            # Tower/Building kills
            elif event.get("type") == "BUILDING_KILL":
                killer_id = event.get("killerId", 0)
                assisting_ids = event.get("assistingParticipantIds", [])

                if killer_id in team_participant_ids:
                    total_towers += 1
                    if killer_id == participant_id or participant_id in assisting_ids:
                        tower_kills += 1

            if event.get("type") in {"CHAMPION_KILL", "BUILDING_KILL", "ELITE_MONSTER_KILL"}:
                conversion_events.append(event)

    conversion_events.sort(key=_event_timestamp)

    for index, event in enumerate(conversion_events):
        if event.get("type") != "CHAMPION_KILL":
            continue

        killer_id = int(event.get("killerId", 0))
        if killer_id not in team_participant_ids:
            continue

        team_kills += 1
        window_end = _event_timestamp(event) + _CONVERSION_LOOKAHEAD_MS
        probe = index + 1

        while probe < len(conversion_events):
            candidate = conversion_events[probe]
            candidate_ts = _event_timestamp(candidate)
            if candidate_ts > window_end:
                break

            c_type = candidate.get("type")
            bucket = _conversion_bucket(candidate)
            if bucket:
                if c_type == "BUILDING_KILL":
                    if int(candidate.get("teamId", 0)) != team_id:
                        conversion_breakdown[bucket] += 1
                        team_conversions += 1
                        break
                elif (
                    c_type == "ELITE_MONSTER_KILL"
                    and int(candidate.get("killerId", 0)) in team_participant_ids
                ):
                    conversion_breakdown[bucket] += 1
                    team_conversions += 1
                    break
            probe += 1

    # Calculate participation rates
    epic_monster_participation = epic_monsters / max(total_epic_monsters, 1)
    tower_participation = tower_kills / max(total_towers, 1)

    # Combined objective setup score (personal + team conversion health)
    personal_score = (epic_monster_participation + tower_participation) / 2
    conversion_rate = team_conversions / team_kills if team_kills > 0 else 0.0
    conversion_volume = (
        min(team_conversions / _CONVERSION_VOLUME_NORMALIZER, 1.0) if team_conversions > 0 else 0.0
    )
    team_conversion_score = (
        conversion_rate * _CONVERSION_RATE_WEIGHT + conversion_volume * _CONVERSION_VOLUME_WEIGHT
    )
    objective_setup = (
        personal_score * _PERSONAL_OBJECTIVE_WEIGHT
        + team_conversion_score * _TEAM_CONVERSION_WEIGHT
    )

    return {
        "epic_monster_participation": epic_monster_participation,
        "tower_participation": tower_participation,
        "objective_setup": objective_setup,
        "epic_monsters": epic_monsters,
        "tower_kills": tower_kills,
        "personal_objective_score": personal_score,
        "team_conversion_rate": conversion_rate,
        "team_conversion_score": team_conversion_score,
        "team_post_kill_conversions": team_conversions,
        "team_kills_considered": team_kills,
        "team_conversion_volume": conversion_volume,
        "team_conversion_breakdown": dict(conversion_breakdown),
    }


def calculate_vision_control(timeline: MatchTimeline, participant_id: int) -> dict[str, float]:
    """Calculate vision and map control metrics.

    Returns:
        Dict with normalized scores for:
        - ward_placement_rate: Wards per minute
        - ward_clear_efficiency: Enemy wards destroyed
        - vision_score: Combined vision control quality
    """
    wards_placed = 0
    wards_killed = 0

    for frame in timeline.info.frames:
        for event in frame.events:
            if event.get("type") == "WARD_PLACED" and event.get("creatorId") == participant_id:
                wards_placed += 1
            elif event.get("type") == "WARD_KILL" and event.get("killerId") == participant_id:
                wards_killed += 1

    # Wards per minute
    last_frame = timeline.info.frames[-1]
    game_duration_min = last_frame.timestamp / 60000
    wards_per_min = wards_placed / max(game_duration_min, 1)

    # Normalize (expect 1-2 wards/min for good vision)
    ward_placement_rate = min(wards_per_min / 2, 1.0)

    # Ward clear efficiency (normalize around 10 wards cleared)
    ward_clear_efficiency = min(wards_killed / 10, 1.0)

    # Combined vision score
    vision_score = (ward_placement_rate + ward_clear_efficiency) / 2

    return {
        "ward_placement_rate": ward_placement_rate,
        "ward_clear_efficiency": ward_clear_efficiency,
        "vision_score": vision_score,
        "wards_placed": wards_placed,
        "wards_killed": wards_killed,
    }


def calculate_team_contribution(timeline: MatchTimeline, participant_id: int) -> dict[str, float]:
    """Calculate team contribution metrics.

    Returns:
        Dict with normalized scores for:
        - assist_ratio: Assists relative to total kills+assists
        - teamfight_presence: Teamfight participation quality
        - objective_assists: Assists on epic objectives
    """
    # Reuse combat metrics for assists
    combat = calculate_combat_efficiency(timeline, participant_id)
    assists = combat["assists"]
    kills = combat["kills"]

    # Assist ratio
    assist_ratio = assists / max(kills + assists, 1)

    # Objective assists
    objective_assists = 0
    for frame in timeline.info.frames:
        for event in frame.events:
            if event.get("type") in ["ELITE_MONSTER_KILL", "BUILDING_KILL"]:
                assisting_ids = event.get("assistingParticipantIds", [])
                if participant_id in assisting_ids:
                    objective_assists += 1

    # Normalize (expect 3-5 objective assists per game)
    objective_assist_score = min(objective_assists / 5, 1.0)

    # Teamfight presence approximated by assist ratio
    teamfight_presence = assist_ratio

    return {
        "assist_ratio": assist_ratio,
        "teamfight_presence": teamfight_presence,
        "objective_assists": objective_assist_score,
        "total_assists": assists,
        "objective_assist_count": objective_assists,
    }


def calculate_growth_curve(timeline: MatchTimeline, participant_id: int) -> dict[str, float]:
    """Calculate growth curve metrics (level/experience advantage).

    Returns:
        Dict with normalized scores for:
        - level_lead: Level advantage vs opponent team average
        - xp_efficiency: Experience gain efficiency
        - early_game_power: First 15min growth performance
    """
    last_frame = timeline.info.frames[-1]
    participant_frame = last_frame.participant_frames.get(str(participant_id))

    if not participant_frame:
        return {
            "level_lead": 0.5,
            "xp_efficiency": 0.5,
            "early_game_power": 0.5,
            "final_level": 0,
            "xp_lead": 0,
        }

    # Get opponent team average level/xp
    team_id = 100 if participant_id <= 5 else 200
    opponent_team_ids = range(6, 11) if team_id == 100 else range(1, 6)

    opponent_levels = []
    opponent_xp = []
    for opp_id in opponent_team_ids:
        opp_frame = last_frame.participant_frames.get(str(opp_id))
        if opp_frame:
            opponent_levels.append(opp_frame.level)
            opponent_xp.append(opp_frame.xp)

    avg_opponent_level = (
        np.mean(opponent_levels).item() if opponent_levels else participant_frame.level
    )
    avg_opponent_xp = np.mean(opponent_xp).item() if opponent_xp else participant_frame.xp

    # Level lead (-3 to +3 range)
    level_difference = participant_frame.level - avg_opponent_level
    level_lead_score = (level_difference + 3) / 6
    level_lead_score = max(0.0, min(1.0, level_lead_score))

    # XP efficiency (normalize around ±5000 xp)
    xp_difference = participant_frame.xp - avg_opponent_xp
    xp_efficiency = (xp_difference + 5000) / 10000
    xp_efficiency = max(0.0, min(1.0, xp_efficiency))

    # Early game power (level at 15min)
    early_game_level = 0
    fifteen_min_timestamp = 15 * 60000  # 15 minutes in ms
    for frame in reversed(timeline.info.frames):
        if frame.timestamp <= fifteen_min_timestamp:
            early_frame = frame.participant_frames.get(str(participant_id))
            if early_frame:
                early_game_level = early_frame.level
                break

    # Normalize (expect level 10-13 at 15min)
    early_game_power = (early_game_level - 8) / 7  # Level 8-15 range
    early_game_power = max(0.0, min(1.0, early_game_power))

    return {
        "level_lead": level_lead_score,
        "xp_efficiency": xp_efficiency,
        "early_game_power": early_game_power,
        "final_level": participant_frame.level,
        "xp_lead": xp_difference,
    }


def calculate_tankiness(timeline: MatchTimeline, participant_id: int) -> dict[str, float]:
    """Calculate tankiness/frontline performance metrics.

    Returns:
        Dict with normalized scores for:
        - damage_taken_ratio: Damage absorbed vs dealt
        - frontline_value: Tank effectiveness score
        - durability: Health pool & resistances efficiency
    """
    last_frame = timeline.info.frames[-1]
    participant_frame = last_frame.participant_frames.get(str(participant_id))

    if not participant_frame:
        return {
            "damage_taken_ratio": 0.5,
            "frontline_value": 0.5,
            "durability": 0.5,
            "total_damage_taken": 0,
            "damage_taken_to_dealt_ratio": 0.0,
        }

    damage_taken = participant_frame.damage_stats.total_damage_taken
    damage_dealt = participant_frame.damage_stats.total_damage_done_to_champions

    # Damage taken ratio (higher = more frontline)
    # Tanks typically take 1.5-3x damage compared to damage dealt
    damage_ratio = damage_taken / max(damage_dealt, 1)
    damage_taken_ratio = min(damage_ratio / 3, 1.0)

    # Frontline value (combine damage taken + resistances)
    armor = participant_frame.champion_stats.armor
    magic_resist = participant_frame.champion_stats.magic_resist
    avg_resistance = (armor + magic_resist) / 2

    # High resistance + high damage taken = good tank
    resistance_score = min(avg_resistance / 200, 1.0)
    damage_absorption_score = min(damage_taken / 30000, 1.0)
    frontline_value = (resistance_score + damage_absorption_score) / 2

    # Durability (health pool efficiency)
    health_max = participant_frame.champion_stats.health_max
    durability = min(health_max / 3000, 1.0)

    return {
        "damage_taken_ratio": damage_taken_ratio,
        "frontline_value": frontline_value,
        "durability": durability,
        "total_damage_taken": damage_taken,
        "damage_taken_to_dealt_ratio": damage_ratio,
    }


def calculate_damage_composition(timeline: MatchTimeline, participant_id: int) -> dict[str, float]:
    """Calculate damage type distribution metrics.

    Returns:
        Dict with normalized scores for:
        - damage_diversity: Balance of physical/magic/true damage
        - damage_focus: Consistency of damage type (0=mixed, 1=focused)
        - burst_potential: Peak damage in single frame
    """
    last_frame = timeline.info.frames[-1]
    participant_frame = last_frame.participant_frames.get(str(participant_id))

    if not participant_frame:
        return {
            "damage_diversity": 0.5,
            "damage_focus": 0.5,
            "burst_potential": 0.5,
            "physical_damage_percent": 0.0,
            "magic_damage_percent": 0.0,
            "true_damage_percent": 0.0,
        }

    phys_dmg = participant_frame.damage_stats.physical_damage_done_to_champions
    magic_dmg = participant_frame.damage_stats.magic_damage_done_to_champions
    true_dmg = participant_frame.damage_stats.true_damage_done_to_champions
    total_dmg = phys_dmg + magic_dmg + true_dmg

    if total_dmg == 0:
        return {
            "damage_diversity": 0.5,
            "damage_focus": 0.5,
            "burst_potential": 0.5,
            "physical_damage_percent": 0.0,
            "magic_damage_percent": 0.0,
            "true_damage_percent": 0.0,
        }

    # Calculate percentages
    phys_percent = (phys_dmg / total_dmg) * 100
    magic_percent = (magic_dmg / total_dmg) * 100
    true_percent = (true_dmg / total_dmg) * 100

    # Damage diversity (high when balanced, low when focused)
    # Shannon entropy-like measure
    probs = [p / 100 for p in [phys_percent, magic_percent, true_percent] if p > 0]
    diversity = -sum(p * np.log2(p + 1e-10) for p in probs) / np.log2(3)

    # Damage focus (inverse of diversity)
    damage_focus = 1.0 - diversity

    # Burst potential (find max damage spike between frames)
    max_damage_spike = 0
    prev_total = 0
    for frame in timeline.info.frames:
        current_frame = frame.participant_frames.get(str(participant_id))
        if current_frame:
            current_total = current_frame.damage_stats.total_damage_done_to_champions
            spike = current_total - prev_total
            max_damage_spike = max(max_damage_spike, spike)
            prev_total = current_total

    # Normalize burst (expect 500-3000 damage spikes)
    burst_potential = min(max_damage_spike / 3000, 1.0)

    return {
        "damage_diversity": diversity,
        "damage_focus": damage_focus,
        "burst_potential": burst_potential,
        "physical_damage_percent": phys_percent,
        "magic_damage_percent": magic_percent,
        "true_damage_percent": true_percent,
    }


def calculate_survivability(timeline: MatchTimeline, participant_id: int) -> dict[str, float]:
    """Calculate survivability/death quality metrics.

    Returns:
        Dict with normalized scores for:
        - death_positioning: Death location quality (0=bad, 1=good)
        - survival_time_ratio: % of game time alive
        - health_management: Effective HP usage
    """
    # Count deaths
    combat_metrics = calculate_combat_efficiency(timeline, participant_id)
    deaths = combat_metrics["deaths"]

    # Calculate survival time (approximation: game_time - death_count * avg_respawn)
    last_frame = timeline.info.frames[-1]
    game_duration_sec = last_frame.timestamp / 1000
    avg_respawn_time = 30  # Simplified: ~30s average respawn

    time_dead = deaths * avg_respawn_time
    survival_time = game_duration_sec - time_dead
    survival_time_ratio = survival_time / max(game_duration_sec, 1)
    survival_time_ratio = max(0.0, min(1.0, survival_time_ratio))

    # Death positioning score (simplified: fewer deaths = better positioning)
    # In production, would analyze death locations vs team positions
    death_score = max(0.0, 1.0 - (deaths / 10))

    # Health management (use health regen + lifesteal efficiency)
    participant_frame = last_frame.participant_frames.get(str(participant_id))
    health_management = 0.5
    if participant_frame:
        lifesteal = participant_frame.champion_stats.lifesteal
        omnivamp = participant_frame.champion_stats.omnivamp
        healing = lifesteal + omnivamp
        health_management = min(healing / 50, 1.0)  # Normalize around 50% healing

    return {
        "death_positioning": death_score,
        "survival_time_ratio": survival_time_ratio,
        "health_management": health_management,
        "total_deaths": deaths,
        "estimated_time_alive": survival_time,
    }


def calculate_cc_contribution(
    timeline: MatchTimeline,
    participant_id: int,
    *,
    participant_data: dict[str, Any] | None = None,
    game_duration_ms: float | None = None,
) -> dict[str, float]:
    """Calculate crowd control contribution metrics.

    Returns:
        Dict with normalized scores for:
        - cc_duration: Total time enemies spent controlled
        - cc_efficiency: CC time per minute
        - cc_setup: CC contribution to teamfights/objectives
    """
    frames = timeline.info.frames or []
    last_frame = frames[-1] if frames else None
    participant_frame = (
        last_frame.participant_frames.get(str(participant_id)) if last_frame else None
    )

    timeline_cc_time_ms = float(getattr(participant_frame, "time_enemy_spent_controlled", 0) or 0)

    def _as_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    fallback_seconds = None
    if participant_data:
        fallback_seconds = _as_float(
            participant_data.get("timeCCingOthers") or participant_data.get("totalTimeCCDealt")
        )

    cc_time_ms = timeline_cc_time_ms
    fallback_used = False
    if cc_time_ms <= 0 and fallback_seconds and fallback_seconds > 0:
        cc_time_ms = fallback_seconds * 1000.0
        fallback_used = True

    if game_duration_ms is None:
        game_duration_ms = float(last_frame.timestamp or 0) if last_frame else None

    time_played = _as_float(participant_data.get("timePlayed")) if participant_data else None
    if (
        fallback_used
        and time_played
        and time_played > 0
        or (not game_duration_ms or game_duration_ms <= 0)
        and time_played
        and time_played > 0
    ):
        game_duration_ms = time_played * 1000.0

    cc_time_sec = cc_time_ms / 1000.0
    game_duration_min = (
        (game_duration_ms / 60000.0) if game_duration_ms and game_duration_ms > 0 else 0.0
    )
    cc_per_min = cc_time_sec / max(game_duration_min, 1.0) if cc_time_sec > 0 else 0.0

    cc_duration = min(cc_time_sec / 60.0, 1.0)
    cc_efficiency = min(cc_per_min / 10.0, 1.0)
    cc_setup = cc_efficiency  # Placeholder until we correlate CC with objectives

    if fallback_used:
        logger.debug(
            "cc_metrics_fallback_used",
            extra={
                "participant_id": participant_id,
                "cc_time_sec": round(cc_time_sec, 1),
                "game_duration_min": round(game_duration_min, 2),
            },
        )

    return {
        "cc_duration": cc_duration,
        "cc_efficiency": cc_efficiency,
        "cc_setup": cc_setup,
        # Keep milliseconds here for downstream raw_stats (converted there)
        "total_cc_time": cc_time_ms,
        "cc_per_min": cc_per_min,
    }


def calculate_total_score(
    timeline: MatchTimeline, participant_id: int, participant_data: dict[str, Any] | None = None
) -> PlayerScore:
    """Calculate comprehensive player performance score.

    This function implements the V1 scoring algorithm with 10-dimensional analysis.
    It now supports dual-source validation: Timeline API + Match-V5 Details API.

    Dual-Source Strategy:
    - Timeline API: Frame-by-frame gameplay data (gold, damage, position)
    - Match-V5 Details: Accurate end-game statistics (KDA, vision, match result)
    - Cross-validation: Log warnings when data sources disagree

    Args:
        timeline: Parsed match timeline from Timeline API
        participant_id: Target participant ID (1-10)
        participant_data: Optional Match-V5 Details participant object for accuracy

    Returns:
        PlayerScore with all dimension scores and metadata
    """

    def _safe_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    # Calculate all dimensions
    combat = calculate_combat_efficiency(timeline, participant_id)
    economic = calculate_economic_management(timeline, participant_id)
    vision = calculate_vision_control(timeline, participant_id)
    objective = calculate_objective_control(timeline, participant_id)
    teamplay = calculate_team_contribution(timeline, participant_id)
    growth = calculate_growth_curve(timeline, participant_id)
    tankiness = calculate_tankiness(timeline, participant_id)
    damage_comp = calculate_damage_composition(timeline, participant_id)
    survivability = calculate_survivability(timeline, participant_id)
    frames = timeline.info.frames or []
    last_frame = frames[-1] if frames else None

    cc_contrib = calculate_cc_contribution(
        timeline,
        participant_id,
        participant_data=participant_data,
        game_duration_ms=float(last_frame.timestamp) if last_frame else None,
    )

    # Aggregate stats for raw_stats dictionary
    total_cs = economic.get("total_cs", 0)
    # growth calculator currently does not expose total_xp; keep 0 for raw_stats (view hides it)
    total_xp = growth.get("total_xp", 0)

    # Get last frame participant data
    participant_frame = (
        last_frame.participant_frames.get(str(participant_id)) if last_frame else None
    )

    if not participant_frame:
        logger.warning("No participant frame found for participant %d", participant_id)
        damage_dealt_to_champs = 0
        damage_taken_raw = 0
        physical_dmg = 0
        magic_dmg = 0
        true_dmg = 0
    else:
        damage_dealt_to_champs = participant_frame.damage_stats.total_damage_done_to_champions
        damage_taken_raw = participant_frame.damage_stats.total_damage_taken
        physical_dmg = participant_frame.damage_stats.physical_damage_done_to_champions
        magic_dmg = participant_frame.damage_stats.magic_damage_done_to_champions
        true_dmg = participant_frame.damage_stats.true_damage_done_to_champions

    # ===== DUAL-SOURCE VALIDATION: Timeline vs Match-V5 Details =====
    # Extract KDA from both sources for cross-validation
    timeline_kills = combat.get("kills", 0)
    timeline_deaths = combat.get("deaths", 0)
    timeline_assists = combat.get("assists", 0)

    if participant_data:
        details_kills = participant_data.get("kills", 0)
        details_deaths = participant_data.get("deaths", 0)
        details_assists = participant_data.get("assists", 0)

        # Cross-validation: Warn if data sources disagree
        kda_mismatch = (
            timeline_kills != details_kills
            or timeline_deaths != details_deaths
            or timeline_assists != details_assists
        )

        if kda_mismatch:
            logger.warning(
                "🔍 KDA MISMATCH DETECTED | Participant %d | "
                "Timeline: %d/%d/%d | Details: %d/%d/%d | "
                "Using Details API (more accurate)",
                participant_id,
                timeline_kills,
                timeline_deaths,
                timeline_assists,
                details_kills,
                details_deaths,
                details_assists,
            )

        # Prioritize Match-V5 Details for accuracy
        accurate_kills = details_kills
        accurate_deaths = details_deaths
        accurate_assists = details_assists
        accurate_kda = (accurate_kills + accurate_assists) / max(accurate_deaths, 1)
    else:
        # Fallback to Timeline API if Details unavailable
        logger.info(
            "ℹ️  Match-V5 Details unavailable for participant %d, using Timeline API KDA",
            participant_id,
        )
        accurate_kills = timeline_kills
        accurate_deaths = timeline_deaths
        accurate_assists = timeline_assists
        accurate_kda = combat["raw_kda"]

    # Round gold difference to avoid long float tails from numpy means
    _gold_diff_val = economic["gold_difference"]
    try:
        _gold_diff_int = int(round(float(_gold_diff_val)))
    except Exception:
        _gold_diff_int = int(_gold_diff_val) if isinstance(_gold_diff_val, int) else 0

    cc_total_time_ms = _safe_float(cc_contrib.get("total_cc_time")) or 0.0
    cc_time_seconds = cc_total_time_ms / 1000.0
    cc_per_min_value = _safe_float(cc_contrib.get("cc_per_min")) or 0.0
    cc_score_value: float | None = None
    if participant_data:
        challenges = participant_data.get("challenges") or {}
        cc_score_value = _safe_float(
            challenges.get("crowdControlScore") or participant_data.get("crowdControlScore")
        )

    raw_stats = {
        # Basic combat (from Match-V5 Details for accuracy)
        "kills": accurate_kills,
        "deaths": accurate_deaths,
        "assists": accurate_assists,
        "kda": accurate_kda,
        # Economic
        "cs": total_cs,
        "cs_per_min": economic["cs_per_min"],
        "gold": economic.get("total_gold", 0),
        "gold_diff": _gold_diff_int,
        # Damage
        "damage_dealt": damage_dealt_to_champs,
        "damage_taken": damage_taken_raw,
        "damage_physical": physical_dmg,
        "damage_magic": magic_dmg,
        "damage_true": true_dmg,
        # Vision & Control (from calculated values and Match-V5 Details)
        "wards_placed": vision.get("wards_placed", 0),
        "wards_killed": vision.get("wards_killed", 0),
        "vision_score": participant_data.get("visionScore", 0) if participant_data else 0,
        "detector_wards_placed": participant_data.get("detectorWardsPlaced", 0)
        if participant_data
        else 0,
        "cc_time": cc_time_seconds,
        "cc_per_min": cc_per_min_value,
        "cc_score": cc_score_value if cc_score_value is not None else 0.0,
        # Growth
        "level": growth.get("final_level", 0),
        "xp": total_xp,
        # Objectives
        "turret_kills": objective.get("tower_kills", 0),
        "epic_monsters": objective.get("epic_monsters", 0),
        "objective_personal_score": float(objective.get("personal_objective_score", 0.0)),
        "objective_team_conversion_rate": float(objective.get("team_conversion_rate", 0.0)),
        "objective_team_conversions": int(objective.get("team_post_kill_conversions", 0)),
        "objective_team_conversion_breakdown": objective.get("team_conversion_breakdown", {}),
        # Multi-kills & Sprees (from Match-V5 Details)
        "double_kills": participant_data.get("doubleKills", 0) if participant_data else 0,
        "triple_kills": participant_data.get("tripleKills", 0) if participant_data else 0,
        "quadra_kills": participant_data.get("quadraKills", 0) if participant_data else 0,
        "penta_kills": participant_data.get("pentaKills", 0) if participant_data else 0,
        "killing_sprees": participant_data.get("killingSprees", 0) if participant_data else 0,
        "largest_killing_spree": participant_data.get("largestKillingSpree", 0)
        if participant_data
        else 0,
        "largest_multi_kill": participant_data.get("largestMultiKill", 0)
        if participant_data
        else 0,
        # Position & Role (from Match-V5 Details)
        "team_position": participant_data.get("teamPosition", "") if participant_data else "",
        "individual_position": participant_data.get("individualPosition", "")
        if participant_data
        else "",
        "lane": participant_data.get("lane", "") if participant_data else "",
        "role": participant_data.get("role", "") if participant_data else "",
        # Tankiness & Survivability (from Match-V5 Details)
        "damage_self_mitigated": participant_data.get("damageSelfMitigated", 0)
        if participant_data
        else 0,
    }

    # Calculate final dimension scores by averaging sub-metrics (convert to 0-100 scale)
    combat_score = (
        (combat["kda_score"] + combat["kill_participation"] + combat["damage_efficiency"]) / 3 * 100
    )
    economy_score = (
        (economic["cs_efficiency"] + economic["gold_lead"] + economic["item_timing"]) / 3 * 100
    )
    vision_score = (vision["ward_placement_rate"] + vision["ward_clear_efficiency"]) / 2 * 100
    objective_score = float(objective.get("objective_setup", 0.0)) * 100
    teamplay_score = (
        (teamplay["assist_ratio"] + teamplay["teamfight_presence"] + teamplay["objective_assists"])
        / 3
        * 100
    )
    growth_score = (
        (growth["level_lead"] + growth["xp_efficiency"] + growth["early_game_power"]) / 3 * 100
    )
    tankiness_score = (
        (tankiness["damage_taken_ratio"] + tankiness["frontline_value"] + tankiness["durability"])
        / 3
        * 100
    )
    damage_comp_score = (
        (
            damage_comp["damage_diversity"]
            + damage_comp["damage_focus"]
            + damage_comp["burst_potential"]
        )
        / 3
        * 100
    )
    survivability_score = (
        (
            survivability["death_positioning"]
            + survivability["survival_time_ratio"]
            + survivability["health_management"]
        )
        / 3
        * 100
    )
    cc_contrib_score = (
        (cc_contrib["cc_duration"] + cc_contrib["cc_efficiency"] + cc_contrib["cc_setup"]) / 3 * 100
    )

    # Calculate final weighted score (10 dimensions)
    weights = {
        "combat": 0.15,  # Core
        "economy": 0.15,  # Core
        "objective": 0.15,  # Core
        "vision": 0.10,  # Secondary
        "teamplay": 0.10,  # Secondary
        "growth": 0.10,  # Advanced
        "tankiness": 0.10,  # Advanced
        "damage_comp": 0.05,  # Advanced
        "survivability": 0.05,  # Advanced
        "cc_contrib": 0.05,  # Advanced
    }

    total_score = (
        combat_score * weights["combat"]
        + economy_score * weights["economy"]
        + vision_score * weights["vision"]
        + objective_score * weights["objective"]
        + teamplay_score * weights["teamplay"]
        + growth_score * weights["growth"]
        + tankiness_score * weights["tankiness"]
        + damage_comp_score * weights["damage_comp"]
        + survivability_score * weights["survivability"]
        + cc_contrib_score * weights["cc_contrib"]
    )
    dominance_bonus = max(0.0, combat_score - teamplay_score) * 0.2
    total_score = min(100.0, total_score + dominance_bonus)

    if total_score >= 80:
        emotion_tag = "excited"
    elif total_score >= 60:
        emotion_tag = "positive"
    elif total_score >= 40:
        emotion_tag = "neutral"
    else:
        emotion_tag = "concerned"

    dimension_scores = [
        ("combat", combat_score),
        ("economy", economy_score),
        ("objective", objective_score),
        ("vision", vision_score),
        ("teamplay", teamplay_score),
        ("growth", growth_score),
        ("tankiness", tankiness_score),
        ("damage_composition", damage_comp_score),
        ("survivability", survivability_score),
        ("crowd_control", cc_contrib_score),
    ]
    sorted_dims = sorted(dimension_scores, key=lambda item: item[1], reverse=True)
    top_strengths = [name for name, _ in sorted_dims[:2]]
    weakest_dims = [name for name, _ in sorted(dimension_scores, key=lambda item: item[1])[:2]]

    # Map computed dimension scores to PlayerScore schema
    # Note: PlayerScore expects "*_efficiency"/"*_management" for核心5维，值域0-100
    # 其余5维同样为0-100。
    return PlayerScore(
        participant_id=participant_id,
        total_score=total_score,
        # Core dimensions (0-100)
        combat_efficiency=combat_score,
        economic_management=economy_score,
        objective_control=objective_score,
        vision_control=vision_score,
        team_contribution=teamplay_score,
        # Extended dimensions (0-100)
        growth_score=growth_score,
        tankiness_score=tankiness_score,
        damage_composition_score=damage_comp_score,
        survivability_score=survivability_score,
        cc_contribution_score=cc_contrib_score,
        # Raw metrics required by schema
        kda=accurate_kda,
        cs_per_min=economic["cs_per_min"],
        gold_difference=economic["gold_difference"],
        # Convert to percentage for prompt consistency
        kill_participation=float(combat.get("kill_participation", 0.0)) * 100.0,
        raw_stats=raw_stats,
        emotion_tag=emotion_tag,
        strengths=top_strengths,
        improvements=weakest_dims,
    )


def analyze_full_match(
    timeline: MatchTimeline, match_details: dict[str, Any] | None = None
) -> list[PlayerScore]:
    """Analyze all 10 participants in a match.

    Args:
        timeline: Match timeline data
        match_details: Optional Match-V5 Details data for additional fields (e.g., vision_score)

    Returns:
        List of PlayerScore objects sorted by total score (descending)
    """
    scores: list[PlayerScore] = []

    # Build participant lookup map from match_details for vision_score
    participant_data_map: dict[int, dict[str, Any]] = {}
    if match_details and "info" in match_details:
        participants = match_details["info"].get("participants", [])
        for p in participants:
            participant_id = p.get("participantId")
            if participant_id:
                participant_data_map[int(participant_id)] = p

    for participant_id in range(1, 11):
        try:
            participant_data = participant_data_map.get(participant_id)
            score = calculate_total_score(
                timeline, participant_id, participant_data=participant_data
            )
            scores.append(score)
        except Exception as e:
            # Log error but continue processing other participants
            print(f"⚠️  Error calculating score for participant {participant_id}: {e}")

    # Sort by total score (highest first)
    scores.sort(key=lambda x: x.total_score, reverse=True)

    return scores


def generate_llm_input(
    timeline: MatchTimeline, match_details: dict[str, Any] | None = None
) -> MatchAnalysisOutput:
    """Generate structured output for LLM consumption.

    Args:
        timeline: Match timeline data
        match_details: Optional Match-V5 Details data for additional fields (e.g., vision_score)

    Returns:
        MatchAnalysisOutput with MVP identification and team statistics
    """
    scores = analyze_full_match(timeline, match_details)

    # Calculate team averages
    blue_scores = [s.total_score for s in scores if s.participant_id <= 5]
    red_scores = [s.total_score for s in scores if s.participant_id > 5]

    last_frame = timeline.info.frames[-1]
    game_duration = last_frame.timestamp / 60000  # ms to minutes

    return MatchAnalysisOutput(
        match_id=timeline.metadata.match_id,
        game_duration_minutes=game_duration,
        player_scores=scores,
        mvp_id=scores[0].participant_id if scores else 1,
        team_blue_avg_score=np.mean(blue_scores).item() if blue_scores else 0.0,
        team_red_avg_score=np.mean(red_scores).item() if red_scores else 0.0,
    )
