from __future__ import annotations

from typing import Any


def _find_frame_at_or_after(frames: list[dict[str, Any]], ms: int) -> dict | None:
    for fr in frames:
        if int(fr.get("timestamp", 0)) >= ms:
            return fr
    return frames[-1] if frames else None


def _cs_from_frame_participant(pf: dict[str, Any]) -> int:
    return int(pf.get("minions_killed", 0)) + int(pf.get("jungle_minions_killed", 0))


def _participant_team_from_details(
    match_details: dict[str, Any], participant_id: int
) -> int | None:
    try:
        parts = match_details["info"].get("participants", [])
        for p in parts:
            if int(p.get("participantId", 0)) == int(participant_id):
                return int(p.get("teamId", 0))
    except Exception:
        return None
    return None


def extract_sr_enrichment(
    timeline_data: dict[str, Any],
    match_details: dict[str, Any],
    participant_id: int,
) -> dict[str, Any]:
    """Extract SR-focused enrichment metrics for LLM/view.

    Returns keys:
      - cs_at_10, cs_at_15
      - ward_rate_per_min
      - post_kill_objective_conversions (count)
      - team_kills_considered (count)
      - conversion_rate (0.0-1.0)
      - objective_breakdown: {towers, drakes, heralds, barons}
      - gold/xp diffs vs lane opponent at 10/15: gold_diff_10, xp_diff_10, gold_diff_15, xp_diff_15
    """
    info = (timeline_data or {}).get("info", {})
    frames: list[dict[str, Any]] = info.get("frames", []) or []
    last_ts = int(frames[-1].get("timestamp", 0)) if frames else 0
    duration_min = max(last_ts / 60000.0, 1.0)

    # CS milestones
    cs10 = cs15 = 0
    fr10 = _find_frame_at_or_after(frames, 10 * 60000)
    fr15 = _find_frame_at_or_after(frames, 15 * 60000)
    if fr10:
        pf10 = fr10.get("participantFrames", {}).get(str(participant_id), {})
        cs10 = _cs_from_frame_participant(pf10)
    if fr15:
        pf15 = fr15.get("participantFrames", {}).get(str(participant_id), {})
        cs15 = _cs_from_frame_participant(pf15)

    # Lane opponent resolution from Details API
    parts = match_details.get("info", {}).get("participants", []) if match_details else []
    me = next((p for p in parts if int(p.get("participantId", 0)) == int(participant_id)), None)
    my_team = int(me.get("teamId", 0)) if me else None
    my_lane = str(me.get("individualPosition", "")) if me else ""

    opponent_id = None
    if me:
        opp = next(
            (
                p
                for p in parts
                if int(p.get("teamId", 0)) != my_team
                and str(p.get("individualPosition", "")) == my_lane
            ),
            None,
        )
        if opp is None:
            # Fallback: enemy with same lane reported by 'teamPosition'
            opp = next(
                (
                    p
                    for p in parts
                    if int(p.get("teamId", 0)) != my_team
                    and str(p.get("teamPosition", "")) == str(me.get("teamPosition", ""))
                ),
                None,
            )
        if opp is None:
            # Last resort: enemy mid (common proxy)
            opp = next(
                (
                    p
                    for p in parts
                    if int(p.get("teamId", 0)) != my_team
                    and str(p.get("individualPosition", "")) in ("MIDDLE", "MID")
                ),
                None,
            )
        if opp:
            opponent_id = int(opp.get("participantId", 0))

    # Gold/XP diffs at 10/15
    gold_diff_10 = xp_diff_10 = gold_diff_15 = xp_diff_15 = 0

    def _gx(fr: dict[str, Any], pid: int) -> tuple[int, int]:
        pf = fr.get("participantFrames", {}).get(str(pid), {}) if fr else {}
        return int(pf.get("total_gold", 0)), int(pf.get("xp", 0))

    if opponent_id:
        if fr10:
            my_g10, my_x10 = _gx(fr10, participant_id)
            op_g10, op_x10 = _gx(fr10, opponent_id)
            gold_diff_10 = my_g10 - op_g10
            xp_diff_10 = my_x10 - op_x10
        if fr15:
            my_g15, my_x15 = _gx(fr15, participant_id)
            op_g15, op_x15 = _gx(fr15, opponent_id)
            gold_diff_15 = my_g15 - op_g15
            xp_diff_15 = my_x15 - op_x15

    # Wards per minute
    ward_rate = 0.0
    if me:
        try:
            wp = int(me.get("wardsPlaced", 0))
            ward_rate = wp / duration_min
        except Exception:
            pass

    # Objective conversion within 120s after our team kills, with breakdown
    conv_count = 0
    team_kills = 0
    breakdown = {"towers": 0, "drakes": 0, "heralds": 0, "barons": 0}

    def _bump(e2: dict[str, Any]):
        t = e2.get("type")
        if t == "BUILDING_KILL":
            if str(e2.get("buildingType")) == "TOWER_BUILDING":
                breakdown["towers"] += 1
        elif t == "ELITE_MONSTER_KILL":
            m = str(e2.get("monsterType", ""))
            if m == "DRAGON":
                breakdown["drakes"] += 1
            elif m == "BARON_NASHOR":
                breakdown["barons"] += 1
            elif m in ("RIFTHERALD", "HORDE_RIFTHERALD"):
                breakdown["heralds"] += 1

    try:
        team_id = my_team
        if team_id:
            # Flatten events
            events: list[dict[str, Any]] = []
            for fr in frames:
                for ev in fr.get("events", []) or []:
                    if isinstance(ev, dict):
                        events.append(ev)
            events.sort(key=lambda e: int(e.get("timestamp", 0)))

            our_part_ids = {
                int(p.get("participantId", 0)) for p in parts if int(p.get("teamId", 0)) == team_id
            }

            for i, ev in enumerate(events):
                if ev.get("type") == "CHAMPION_KILL" and int(ev.get("killerId", 0)) in our_part_ids:
                    team_kills += 1
                    t0 = int(ev.get("timestamp", 0))
                    t1 = t0 + 120_000
                    converted = False
                    j = i + 1
                    while j < len(events) and int(events[j].get("timestamp", 0)) <= t1:
                        e2 = events[j]
                        et = e2.get("type")
                        if et == "BUILDING_KILL":
                            if int(e2.get("teamId", 0)) == team_id:
                                converted = True
                                _bump(e2)
                                break
                        elif et == "ELITE_MONSTER_KILL":
                            if int(e2.get("killerId", 0)) in our_part_ids:
                                converted = True
                                _bump(e2)
                                break
                        j += 1
                    if converted:
                        conv_count += 1
    except Exception:
        pass

    rate = (conv_count / team_kills) if team_kills > 0 else 0.0

    # Preferred conversion path suggestion (simple ordering by counts)
    order = sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)
    preferred_path = (
        ">".join([k[:2].capitalize() for k, v in order if v > 0])
        if any(v > 0 for _, v in order)
        else "None"
    )

    return {
        "cs_at_10": int(cs10),
        "cs_at_15": int(cs15),
        "ward_rate_per_min": float(round(ward_rate, 2)),
        "post_kill_objective_conversions": int(conv_count),
        "team_kills_considered": int(team_kills),
        "conversion_rate": float(round(rate, 3)),
        "objective_breakdown": breakdown,
        "preferred_conversion_path": preferred_path,
        "gold_diff_10": int(gold_diff_10),
        "xp_diff_10": int(xp_diff_10),
        "gold_diff_15": int(gold_diff_15),
        "xp_diff_15": int(xp_diff_15),
        "duration_min": float(round(duration_min, 1)),
    }
