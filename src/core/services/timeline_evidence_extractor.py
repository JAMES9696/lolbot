import logging
from typing import Any

from src.contracts.v2_1_timeline_evidence import (
    V2_1_TimelineEvidence,
    WardControlEvidence,
    WardPlacementEvent,
    CombatEvidence,
    ChampionKillEvent,
    AbilityUsage,
)

logger = logging.getLogger(__name__)


def _fmt_ts(ms: int) -> str:
    m = max(0, int(ms // 60000))
    s = max(0, int((ms % 60000) // 1000))
    return f"{m}:{s:02d}"


def _label(x: int, y: int) -> str | None:
    try:
        if 9000 <= x <= 10500 and 3500 <= y <= 5000:
            return "Dragon Pit"
        if 4000 <= x <= 5500 and 10000 <= y <= 11500:
            return "Baron Pit"
        if 6000 <= x <= 9000 and 6000 <= y <= 9000:
            return "Mid Lane"
        if 2000 <= x <= 4000 and 10000 <= y <= 13000:
            return "Top Lane"
        if 10000 <= x <= 13000 and 2000 <= y <= 4000:
            return "Bot Lane"
    except Exception:
        return None
    return None


def extract_ward_control_evidence(
    timeline_data: dict[str, Any],
    target_participant_id: int,
) -> WardControlEvidence:
    total_placed = 0
    control_placed = 0
    destroyed = 0
    events: list[WardPlacementEvent] = []

    try:
        frames = timeline_data.get("info", {}).get("frames", [])
        for frame in frames:
            for ev in frame.get("events", []):
                et = ev.get("type")
                if et == "WARD_PLACED" and ev.get("creatorId") == target_participant_id:
                    total_placed += 1
                    wt = ev.get("wardType") or "SIGHT_WARD"
                    if wt == "CONTROL_WARD":
                        control_placed += 1
                    pos = ev.get("position", {}) or {}
                    x = int(pos.get("x", 0) or 0)
                    y = int(pos.get("y", 0) or 0)
                    ts = int(ev.get("timestamp", 0) or 0)
                    events.append(
                        WardPlacementEvent(
                            timestamp_ms=ts,
                            timestamp_display=_fmt_ts(ts),
                            ward_type=str(wt),
                            position_x=x,
                            position_y=y,
                            position_label=_label(x, y),
                        )
                    )
                    if len(events) > 5:
                        events.pop(0)
                elif et == "WARD_KILL" and ev.get("killerId") == target_participant_id:
                    destroyed += 1
    except Exception as e:
        logger.warning(f"Error extracting ward control evidence: {e}")
        return WardControlEvidence(
            total_wards_placed=0,
            control_wards_placed=0,
            wards_destroyed=0,
            critical_objective_wards=0,
            ward_events=[],
        )

    critical = sum(1 for e in events if (e.position_label or "").startswith(("Dragon", "Baron")))
    return WardControlEvidence(
        total_wards_placed=total_placed,
        control_wards_placed=control_placed,
        wards_destroyed=destroyed,
        critical_objective_wards=critical,
        ward_events=events,
    )


def extract_combat_evidence(
    timeline_data: dict[str, Any],
    target_participant_id: int,
) -> CombatEvidence:
    kills = deaths = assists = solo = 0
    early_flash = 0
    kill_events: list[ChampionKillEvent] = []

    try:
        frames = timeline_data.get("info", {}).get("frames", [])
        all_events = [ev for f in frames for ev in f.get("events", [])]

        for ev in all_events:
            if ev.get("type") != "CHAMPION_KILL":
                continue
            killer = int(ev.get("killerId", 0) or 0)
            victim = int(ev.get("victimId", 0) or 0)
            assists_ids = [int(a) for a in (ev.get("assistingParticipantIds") or [])]
            pos = ev.get("position", {}) or {}
            x = int(pos.get("x", 0) or 0)
            y = int(pos.get("y", 0) or 0)
            ts = int(ev.get("timestamp", 0) or 0)

            is_killer = killer == target_participant_id
            is_victim = victim == target_participant_id
            is_assist = target_participant_id in assists_ids

            if is_killer:
                kills += 1
                if not assists_ids:
                    solo += 1
            if is_victim:
                deaths += 1
            if is_assist:
                assists += 1

            if not (is_killer or is_victim or is_assist):
                continue

            abilities: list[AbilityUsage] = []
            for oe in all_events:
                t2 = int(oe.get("timestamp", 0) or 0)
                if abs(t2 - ts) > 10000:
                    continue
                if (
                    oe.get("type") == "SUMMONER_SPELL_USED"
                    and int(oe.get("participantId", 0) or 0) == target_participant_id
                ):
                    spell_id = int(oe.get("spellId", 0) or 0)
                    if spell_id == 4:  # Flash
                        before_death_ms = (ts - t2) if is_victim and t2 < ts else None
                        if before_death_ms is not None and before_death_ms < 5000:
                            early_flash += 1
                        abilities.append(
                            AbilityUsage(
                                ability_type="FLASH",
                                used_by_victim=is_victim,
                                timestamp_before_death_ms=before_death_ms,
                            )
                        )

            kill_events.append(
                ChampionKillEvent(
                    timestamp_ms=ts,
                    timestamp_display=_fmt_ts(ts),
                    victim_participant_id=victim,
                    killer_participant_id=killer,
                    was_target_player_victim=is_victim,
                    was_target_player_killer=is_killer,
                    was_target_player_assist=is_assist,
                    kill_bounty=None,
                    abilities_used=abilities,
                    position_x=x,
                    position_y=y,
                    position_label=_label(x, y),
                )
            )
            if len(kill_events) > 5:
                kill_events.pop(0)

    except Exception as e:
        logger.warning(f"Error extracting combat evidence: {e}")
        return CombatEvidence(
            total_kills=0,
            total_deaths=0,
            total_assists=0,
            solo_kills=0,
            early_flash_usage_count=0,
            kill_events=[],
        )

    return CombatEvidence(
        total_kills=kills,
        total_deaths=deaths,
        total_assists=assists,
        solo_kills=solo,
        early_flash_usage_count=early_flash,
        kill_events=kill_events,
    )


def extract_timeline_evidence(
    timeline_data: dict[str, Any],
    target_participant_id: int,
    match_id: str,
) -> V2_1_TimelineEvidence:
    try:
        ward = extract_ward_control_evidence(timeline_data, target_participant_id)
        combat = extract_combat_evidence(timeline_data, target_participant_id)
        return V2_1_TimelineEvidence(
            match_id=match_id,
            target_player_participant_id=target_participant_id,
            ward_control_evidence=ward,
            combat_evidence=combat,
        )
    except Exception as e:
        logger.warning(f"Error extracting timeline evidence: {e}")
        return V2_1_TimelineEvidence(
            match_id=match_id,
            target_player_participant_id=target_participant_id,
            ward_control_evidence=WardControlEvidence(
                total_wards_placed=0,
                control_wards_placed=0,
                wards_destroyed=0,
                critical_objective_wards=0,
                ward_events=[],
            ),
            combat_evidence=CombatEvidence(
                total_kills=0,
                total_deaths=0,
                total_assists=0,
                solo_kills=0,
                early_flash_usage_count=0,
                kill_events=[],
            ),
        )
