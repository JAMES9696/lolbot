from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _log_event(
    event: str, payload: dict[str, Any], *, level: int = logging.INFO, **log_kwargs: Any
) -> None:
    """Emit diagnostics with event name and structured payload even when extra fields are suppressed."""

    data = {"event": event, **payload}
    try:
        serialized = json.dumps(payload, ensure_ascii=False)
    except Exception:
        serialized = str(payload)
    logger.log(level, "%s %s", event, serialized, extra=data, **log_kwargs)


def _find_frame_with_tolerance(
    frames: list[dict[str, Any]],
    target_ms: int,
    *,
    window_ms: int = 15_000,
    require_participants: list[int] | None = None,
) -> tuple[dict | None, dict[str, Any] | None]:
    """Resolve the closest frame to ``target_ms`` within a tolerance window.

    Args:
        frames: List of timeline frames to search
        target_ms: Target timestamp in milliseconds
        window_ms: Maximum allowed deviation from target (default 15s)
        require_participants: Optional list of participant IDs that must have data

    Returns:
        Tuple of (selected_frame, metadata) or (None, None) if no valid frame found
        metadata includes delta_ms, direction, and fallback_reason if applicable
    """

    def _has_participant_data(frame: dict[str, Any], pids: list[int] | None) -> bool:
        """Verify frame contains non-empty participant data."""
        if not frame:
            return False
        participant_frames = frame.get("participant_frames", {})
        if not participant_frames:
            return False
        if pids is None:
            return True
        return all(str(pid) in participant_frames and participant_frames[str(pid)] for pid in pids)

    if not frames:
        return None, None

    # First pass: find closest frame by time
    candidate_after: dict[str, Any] | None = None
    delta_after: int | None = None

    for fr in frames:
        ts = int(fr.get("timestamp", 0))
        if ts >= target_ms:
            candidate_after = fr
            delta_after = ts - target_ms
            break

    # Exact match with valid data
    if (
        candidate_after is not None
        and delta_after == 0
        and _has_participant_data(candidate_after, require_participants)
    ):
        return candidate_after, None

    candidate_before: dict[str, Any] | None = None
    delta_before: int | None = None

    for fr in reversed(frames):
        ts = int(fr.get("timestamp", 0))
        if ts <= target_ms:
            candidate_before = fr
            delta_before = target_ms - ts
            break

    # Select closest frame within window that has valid participant data
    chosen: dict[str, Any] | None = None
    signed_delta: int | None = None
    fallback_reason: str | None = None

    def _maybe_select(frame: dict[str, Any] | None, delta: int | None, direction: str) -> None:
        nonlocal chosen, signed_delta, fallback_reason
        if frame is None or delta is None:
            return
        if abs(delta) > window_ms:
            return

        # Check if frame has required participant data
        if not _has_participant_data(frame, require_participants):
            _log_event(
                "sr_enrichment_frame_missing_participants",
                {
                    "frame_timestamp": frame.get("timestamp"),
                    "target_ms": target_ms,
                    "delta_ms": delta,
                    "direction": direction,
                    "participant_frames_count": len(frame.get("participant_frames", {})),
                    "required_participants": require_participants,
                },
                level=logging.WARNING,
            )
            return

        if chosen is None or abs(delta) < abs(signed_delta if signed_delta is not None else delta):
            chosen = frame
            signed_delta = delta
            if abs(delta) > 0:
                fallback_reason = f"nearest_valid_frame_{direction}_by_{abs(delta)}ms"

    _maybe_select(candidate_after, delta_after, "after")
    if delta_before is not None:
        _maybe_select(candidate_before, -delta_before, "before")

    # If no valid frame found within primary window, expand search
    if chosen is None and require_participants:
        _log_event(
            "sr_enrichment_expanding_frame_search",
            {
                "target_ms": target_ms,
                "initial_window_ms": window_ms,
                "required_participants": require_participants,
                "total_frames": len(frames),
            },
            level=logging.WARNING,
        )

        # DIAGNOSTIC: Check all frames to see why none are valid
        valid_frames_count = 0
        frames_with_any_participants = 0
        frames_with_required_participants = 0

        for fr in frames:
            participant_frames = fr.get("participant_frames", {})
            if participant_frames:
                frames_with_any_participants += 1
                if _has_participant_data(fr, require_participants):
                    valid_frames_count += 1
                    frames_with_required_participants += 1

        _log_event(
            "sr_enrichment_expanded_search_diagnostics",
            {
                "target_ms": target_ms,
                "total_frames": len(frames),
                "frames_with_any_participants": frames_with_any_participants,
                "frames_with_required_participants": frames_with_required_participants,
                "required_participants": require_participants,
                "sample_frame_timestamps": [int(f.get("timestamp", 0)) for f in frames[:5]],
                "sample_frame_participant_counts": [
                    len(f.get("participant_frames", {})) for f in frames[:5]
                ],
            },
            level=logging.WARNING,
        )

        # Expand search to all frames, prioritizing proximity
        for fr in frames:
            ts = int(fr.get("timestamp", 0))
            delta = ts - target_ms
            if _has_participant_data(fr, require_participants) and (
                chosen is None
                or abs(delta) < abs(signed_delta if signed_delta is not None else delta)
            ):
                chosen = fr
                signed_delta = delta
                fallback_reason = f"expanded_search_fallback_by_{abs(delta)}ms"

    if chosen is None:
        return None, None

    metadata: dict[str, Any] = {
        "delta_ms": signed_delta,
        "direction": "after" if signed_delta and signed_delta > 0 else "before",
    }
    if fallback_reason:
        metadata["reason"] = fallback_reason
    return chosen, metadata


def _cs_from_frame_participant(pf: dict[str, Any]) -> int:
    """Aggregate lane + jungle CS from raw timeline frames.

    Riot Timeline API returns camelCase fields (e.g. ``minionsKilled``) while some
    internal fixtures still use snake_case. Accept both to remain resilient across
    data sources and cast to ``int`` defensively."""

    def _value(*keys: str) -> int:
        for key in keys:
            if key in pf and pf[key] is not None:
                try:
                    return int(pf[key])
                except (TypeError, ValueError):
                    continue
        return 0

    lane_cs = _value("minions_killed", "minionsKilled")
    jungle_cs = _value("jungle_minions_killed", "jungleMinionsKilled")
    return lane_cs + jungle_cs


def _frame_has_participants(frame: dict[str, Any] | None, required_ids: list[int]) -> bool:
    if not frame:
        return False
    pf = frame.get("participant_frames") or {}
    if not pf:
        return False
    return all(str(pid) in pf for pid in required_ids)


def _ensure_frame_participants(
    frames: list[dict[str, Any]],
    target_ms: int,
    required_ids: list[int],
    *,
    current_frame: dict[str, Any] | None,
    current_meta: dict[str, Any] | None,
    label: str,
    window_ms: int = 15_000,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return a frame that contains ``required_ids`` within tolerance.

    If the initially selected frame lacks any required participant, search the
    surrounding window for the closest frame containing them and record the
    fallback via diagnostics."""

    required_ids = list({int(pid) for pid in required_ids})

    if current_meta and "reason" not in current_meta:
        current_meta = {**current_meta, "reason": "time_delta"}

    if _frame_has_participants(current_frame, required_ids):
        return current_frame, current_meta

    best_frame: dict[str, Any] | None = None
    best_delta: int | None = None

    for fr in frames:
        ts = int(fr.get("timestamp", 0))
        delta = ts - target_ms
        if abs(delta) > window_ms:
            continue
        if not _frame_has_participants(fr, required_ids):
            continue
        if best_frame is None or abs(delta) < abs(best_delta if best_delta is not None else delta):
            best_frame = fr
            best_delta = delta

    if best_frame is not None:
        meta = {
            "delta_ms": int(best_delta or 0),
            "direction": "after" if (best_delta or 0) >= 0 else "before",
            "reason": "missing_participant",
            "target_ms": int(target_ms),
        }
        _log_event(
            "sr_enrichment_frame_participant_fallback",
            {
                "label": label,
                "target_ms": target_ms,
                "required_ids": required_ids,
                "chosen_timestamp": int(best_frame.get("timestamp", 0)),
                "delta_ms": meta["delta_ms"],
                "direction": meta["direction"],
            },
        )
        return best_frame, meta

    _log_event(
        "sr_enrichment_missing_participant_data",
        {
            "label": label,
            "target_ms": target_ms,
            "required_ids": required_ids,
            "window_ms": window_ms,
        },
        level=logging.WARNING,
    )
    return current_frame, current_meta


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
    cs10: int | None = None
    cs15: int | None = None

    # DIAGNOSTIC: Log frame availability
    _log_event(
        "sr_enrichment_frame_search",
        {
            "total_frames": len(frames),
            "frame_timestamps": [int(f.get("timestamp", 0)) for f in frames[:5]] if frames else [],
            "target_10min_ms": 10 * 60000,
            "target_15min_ms": 15 * 60000,
            "participant_id": participant_id,
        },
    )

    target_10 = 10 * 60000
    target_15 = 15 * 60000

    # Find frames with valid participant data (Phase 1: only player)
    fr10, fr10_meta = _find_frame_with_tolerance(
        frames, target_10, require_participants=[participant_id]
    )
    fr15, fr15_meta = _find_frame_with_tolerance(
        frames, target_15, require_participants=[participant_id]
    )

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

    # Phase 2: Re-find frames if opponent found, requiring both participants
    if opponent_id:
        fr10, fr10_meta = _find_frame_with_tolerance(
            frames, target_10, require_participants=[participant_id, opponent_id]
        )
        fr15, fr15_meta = _find_frame_with_tolerance(
            frames, target_15, require_participants=[participant_id, opponent_id]
        )

    if fr10:
        pf_container = fr10.get("participant_frames", {}) or {}
        pf10 = pf_container.get(str(participant_id)) or {}
        if pf10:
            cs10 = _cs_from_frame_participant(pf10)
    if fr15:
        pf_container = fr15.get("participant_frames", {}) or {}
        pf15 = pf_container.get(str(participant_id)) or {}
        if pf15:
            cs15 = _cs_from_frame_participant(pf15)

    _log_event(
        "sr_enrichment_fr10_result",
        {
            "fr10_found": fr10 is not None,
            "fr10_timestamp": int(fr10.get("timestamp", 0)) if fr10 else None,
            "fr10_has_participant": _frame_has_participants(fr10, [participant_id]),
            "fr10_has_opponent": _frame_has_participants(fr10, [participant_id, opponent_id])
            if opponent_id
            else None,
            "fallback_used": fr10_meta is not None,
            "fallback_delta_ms": (fr10_meta or {}).get("delta_ms"),
            "fallback_direction": (fr10_meta or {}).get("direction"),
            "fallback_reason": (fr10_meta or {}).get("reason"),
        },
    )

    if fr10_meta:
        _log_event(
            "sr_enrichment_fallback_frame",
            {
                "target_label": "10min",
                "target_ms": target_10,
                "resolved_timestamp": int(fr10.get("timestamp", 0)) if fr10 else None,
                "delta_ms": fr10_meta.get("delta_ms"),
                "direction": fr10_meta.get("direction"),
                "participant_id": participant_id,
                "reason": fr10_meta.get("reason"),
            },
        )

    if fr15_meta:
        _log_event(
            "sr_enrichment_fallback_frame",
            {
                "target_label": "15min",
                "target_ms": target_15,
                "resolved_timestamp": int(fr15.get("timestamp", 0)) if fr15 else None,
                "delta_ms": fr15_meta.get("delta_ms"),
                "direction": fr15_meta.get("direction"),
                "participant_id": participant_id,
                "reason": fr15_meta.get("reason"),
            },
        )

    # Gold/XP diffs at 10/15
    gold_diff_10: int | None = None
    xp_diff_10: int | None = None
    gold_diff_15: int | None = None
    xp_diff_15: int | None = None

    def _gx(fr: dict[str, Any], pid: int) -> tuple[int | None, int | None]:
        pf = fr.get("participant_frames", {}).get(str(pid), {}) if fr else {}

        def _stat(*keys: str) -> int | None:
            for key in keys:
                if key in pf and pf[key] is not None:
                    try:
                        return int(pf[key])
                    except (TypeError, ValueError):
                        continue
            return None

        # DIAGNOSTIC: retain structured view of raw frame data for field verification
        _log_event(
            "sr_enrichment_raw_frame_data",
            {
                "participant_id": pid,
                "frame_timestamp": fr.get("timestamp") if fr else None,
                "participant_frame_keys": list(pf.keys()) if pf else [],
                "participant_frame_sample": {
                    k: pf.get(k)
                    for k in ["totalGold", "total_gold", "goldEarned", "xp", "level", "currentGold"]
                }
                if pf
                else {},
                "all_participant_ids": list(fr.get("participant_frames", {}).keys()) if fr else [],
            },
        )

        if not pf:
            return None, None

        gold_val = _stat("total_gold", "totalGold", "gold", "goldEarned")
        xp_val = _stat("xp", "experience", "totalExperience")

        if gold_val is None or xp_val is None:
            _log_event(
                "sr_enrichment_partial_frame_data",
                {
                    "participant_id": pid,
                    "frame_timestamp": fr.get("timestamp") if fr else None,
                    "missing_gold": gold_val is None,
                    "missing_xp": xp_val is None,
                },
                level=logging.WARNING,
            )

        return gold_val, xp_val

    # DIAGNOSTIC: Log opponent matching
    _log_event(
        "sr_enrichment_opponent_matching",
        {
            "participant_id": participant_id,
            "my_team": my_team,
            "my_lane": my_lane,
            "opponent_id": opponent_id,
            "has_fr10": fr10 is not None,
            "has_fr15": fr15 is not None,
        },
    )

    if opponent_id:
        if fr10:
            my_g10, my_x10 = _gx(fr10, participant_id)
            op_g10, op_x10 = _gx(fr10, opponent_id)

            if my_g10 is not None and op_g10 is not None:
                gold_diff_10 = my_g10 - op_g10
            if my_x10 is not None and op_x10 is not None:
                xp_diff_10 = my_x10 - op_x10

            if gold_diff_10 is not None or xp_diff_10 is not None:
                _log_event(
                    "sr_enrichment_gold_xp_diff_10",
                    {
                        "my_gold": my_g10,
                        "op_gold": op_g10,
                        "gold_diff": gold_diff_10,
                        "my_xp": my_x10,
                        "op_xp": op_x10,
                        "xp_diff": xp_diff_10,
                        "fallback_delta_ms": (fr10_meta or {}).get("delta_ms"),
                    },
                )
            else:
                _log_event(
                    "sr_enrichment_gold_xp_diff_10_missing",
                    {
                        "participant_id": participant_id,
                        "opponent_id": opponent_id,
                        "frame_timestamp": int(fr10.get("timestamp", 0)) if fr10 else None,
                    },
                    level=logging.WARNING,
                )
        else:
            _log_event(
                "sr_enrichment_fr10_missing",
                {"participant_id": participant_id, "opponent_id": opponent_id},
            )

        if fr15:
            my_g15, my_x15 = _gx(fr15, participant_id)
            op_g15, op_x15 = _gx(fr15, opponent_id)

            if my_g15 is not None and op_g15 is not None:
                gold_diff_15 = my_g15 - op_g15
            if my_x15 is not None and op_x15 is not None:
                xp_diff_15 = my_x15 - op_x15

            if gold_diff_15 is not None or xp_diff_15 is not None:
                _log_event(
                    "sr_enrichment_gold_xp_diff_15",
                    {
                        "my_gold": my_g15,
                        "op_gold": op_g15,
                        "gold_diff": gold_diff_15,
                        "my_xp": my_x15,
                        "op_xp": op_x15,
                        "xp_diff": xp_diff_15,
                        "fallback_delta_ms": (fr15_meta or {}).get("delta_ms"),
                    },
                )
            else:
                _log_event(
                    "sr_enrichment_gold_xp_diff_15_missing",
                    {
                        "participant_id": participant_id,
                        "opponent_id": opponent_id,
                        "frame_timestamp": int(fr15.get("timestamp", 0)) if fr15 else None,
                    },
                    level=logging.WARNING,
                )
        else:
            _log_event(
                "sr_enrichment_fr15_missing",
                {"participant_id": participant_id, "opponent_id": opponent_id},
            )
    else:
        _log_event(
            "sr_enrichment_no_opponent_found",
            {
                "participant_id": participant_id,
                "my_lane": my_lane,
                "available_lanes": [
                    (p.get("participantId"), p.get("individualPosition"), p.get("teamId"))
                    for p in parts
                ],
            },
        )

    # Wards per minute
    ward_rate = 0.0
    if me:
        try:
            wp = int(me.get("wardsPlaced", 0))
            ward_rate = wp / duration_min
        except Exception:
            pass

    # Objective conversion within 120s after our team kills
    conv_count = 0
    team_kills = 0

    # Total objectives taken by team (entire game) - for display in UI
    total_objectives = {
        "towers": 0,
        "drakes": 0,
        "heralds": 0,
        "barons": 0,
        "inhibitors": 0,
        "voidgrubs": 0,
        "atakhans": 0,
    }

    # Conversion objectives (within 120s window) - for conversion rate calculation
    conversion_objectives = {
        "towers": 0,
        "drakes": 0,
        "heralds": 0,
        "barons": 0,
        "inhibitors": 0,
        "voidgrubs": 0,
        "atakhans": 0,
    }

    def _count_objective(e2: dict[str, Any], target_dict: dict[str, int]):
        """Count objective in the target dictionary."""
        t = e2.get("type")
        if t == "BUILDING_KILL":
            building_type = str(e2.get("buildingType", ""))
            if building_type == "TOWER_BUILDING":
                target_dict["towers"] += 1
            elif building_type == "INHIBITOR_BUILDING":
                target_dict["inhibitors"] += 1
        elif t == "ELITE_MONSTER_KILL":
            m = str(e2.get("monsterType", ""))
            if m == "DRAGON":
                target_dict["drakes"] += 1
            elif m == "BARON_NASHOR":
                target_dict["barons"] += 1
            elif m in ("RIFTHERALD", "HORDE_RIFTHERALD"):
                target_dict["heralds"] += 1
            elif m in ("HORDE", "VOIDGRUB"):  # S14 Voidgrubs
                target_dict["voidgrubs"] += 1
            elif m in ("ATAKHAN", "RUINOUS_ATAKHAN", "VORACIOUS_ATAKHAN"):  # S15 Atakhan
                target_dict["atakhans"] += 1

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

            # First pass: count ALL objectives taken by team (for display)
            _log_event(
                "sr_enrichment_events_diagnostic",
                {
                    "total_events": len(events),
                    "sample_events": [
                        {
                            "type": ev.get("type"),
                            "timestamp": ev.get("timestamp"),
                            "teamId": ev.get("teamId"),
                            "team_id": ev.get("team_id"),
                            "buildingType": ev.get("buildingType"),
                            "building_type": ev.get("building_type"),
                            "monsterType": ev.get("monsterType"),
                            "monster_type": ev.get("monster_type"),
                            "killerId": ev.get("killerId"),
                            "killer_id": ev.get("killer_id"),
                        }
                        for ev in events[:10]
                    ],
                    "building_kill_events": sum(
                        1 for ev in events if ev.get("type") == "BUILDING_KILL"
                    ),
                    "elite_monster_kill_events": sum(
                        1 for ev in events if ev.get("type") == "ELITE_MONSTER_KILL"
                    ),
                    "our_team_id": team_id,
                    "our_participant_ids": list(our_part_ids),
                },
            )
            for ev in events:
                if ev.get("type") == "BUILDING_KILL":
                    # teamId = team that OWNS the destroyed building (not the attacker!)
                    # So we count when teamId != our team (we destroyed enemy buildings)
                    if int(ev.get("teamId", 0)) != team_id:
                        _count_objective(ev, total_objectives)
                elif (
                    ev.get("type") == "ELITE_MONSTER_KILL"
                    and int(ev.get("killerId", 0)) in our_part_ids
                ):
                    _count_objective(ev, total_objectives)

            # Second pass: conversion rate calculation (objectives within 120s after kills)
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
                            # teamId = team that OWNS the destroyed building (not the attacker!)
                            # So we count when teamId != our team (we destroyed enemy buildings)
                            if int(e2.get("teamId", 0)) != team_id:
                                converted = True
                                _count_objective(e2, conversion_objectives)
                                break
                        elif (
                            et == "ELITE_MONSTER_KILL"
                            and int(e2.get("killerId", 0)) in our_part_ids
                        ):
                            converted = True
                            _count_objective(e2, conversion_objectives)
                            break
                        j += 1
                    if converted:
                        conv_count += 1

            # DIAGNOSTIC: Log total objectives
            _log_event(
                "sr_enrichment_objectives_counted",
                {
                    "total_objectives": total_objectives,
                    "conversion_objectives": conversion_objectives,
                    "team_id": team_id,
                },
            )
    except Exception:
        _log_event("sr_enrichment_objective_counting_failed", {}, exc_info=True)

    rate = (conv_count / team_kills) if team_kills > 0 else 0.0

    # Preferred conversion path suggestion (based on conversion objectives, not total)
    order = sorted(conversion_objectives.items(), key=lambda kv: kv[1], reverse=True)
    preferred_path = (
        ">".join([k[:2].capitalize() for k, v in order if v > 0])
        if any(v > 0 for _, v in order)
        else "None"
    )

    return {
        "cs_at_10": int(cs10) if cs10 is not None else None,
        "cs_at_15": int(cs15) if cs15 is not None else None,
        "ward_rate_per_min": float(round(ward_rate, 2)),
        "post_kill_objective_conversions": int(conv_count),
        "team_kills_considered": int(team_kills),
        "conversion_rate": float(round(rate, 3)),
        "objective_breakdown": total_objectives,  # Total objectives for display
        "conversion_breakdown": conversion_objectives,  # Conversion objectives for analysis
        "preferred_conversion_path": preferred_path,
        "gold_diff_10": int(gold_diff_10) if gold_diff_10 is not None else None,
        "xp_diff_10": int(xp_diff_10) if xp_diff_10 is not None else None,
        "gold_diff_15": int(gold_diff_15) if gold_diff_15 is not None else None,
        "xp_diff_15": int(xp_diff_15) if xp_diff_15 is not None else None,
        "duration_min": float(round(duration_min, 1)),
    }
