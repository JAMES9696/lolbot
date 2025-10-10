from __future__ import annotations

import math
from typing import Any


def _merge_windows(windows: list[tuple[int, int]], pad: int = 2000) -> list[tuple[int, int]]:
    if not windows:
        return []
    ws = sorted([(a - pad, b + pad) for a, b in windows])
    out: list[tuple[int, int]] = []
    cur_s, cur_e = ws[0]
    for s, e in ws[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            out.append((cur_s, cur_e))
            cur_s, cur_e = s, e
    out.append((cur_s, cur_e))
    return out


def _rdp(points: list[tuple[float, float]], eps: float) -> list[tuple[float, float]]:
    if len(points) <= 2:
        return points

    def _dist(p, a, b) -> float:
        (x, y), (x1, y1), (x2, y2) = p, a, b
        if (x1, y1) == (x2, y2):
            return math.hypot(x - x1, y - y1)
        num = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
        den = math.hypot(x2 - x1, y2 - y1)
        return num / den

    def _rdp_rec(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(pts) <= 2:
            return pts
        a, b = pts[0], pts[-1]
        idx, dmax = 0, 0.0
        for i in range(1, len(pts) - 1):
            d = _dist(pts[i], a, b)
            if d > dmax:
                idx, dmax = i, d
        if dmax > eps:
            left = _rdp_rec(pts[: idx + 1])
            right = _rdp_rec(pts[idx:])
            return left[:-1] + right
        return [a, b]

    return _rdp_rec(points)


def _region_label(x: float, y: float) -> str:
    # Heuristic regions for SR (x,y in ~[0, 15000])
    # Baron's pit around top river (x~5000-8000, y~12000-14000)
    if 5000 <= x <= 9000 and 11500 <= y <= 15000:
        return "Baron Pit"
    # Dragon's pit around bottom river (x~9000-12000, y~3000-6000)
    if 8500 <= x <= 12500 and 2500 <= y <= 6500:
        return "Dragon Pit"
    # River band (diagonal); rough y against (15000 - x)
    diag = 15000 - x
    if abs(y - diag) <= 1500:
        return "River"
    # Lanes (very rough)
    if y >= 10000 and x <= 6000:
        return "Top Lane"
    if 6000 < y < 10000 and 6000 < x < 11000:
        return "Mid Lane"
    if y <= 5000 and x >= 9000:
        return "Bot Lane"
    return "Jungle"


def _nearest_enemy_distance(
    pos: dict[int, tuple[float, float]], pid: int, team_pid_set: set[int], enemy_pid_set: set[int]
) -> float:
    if pid not in pos:
        return 1e9
    x, y = pos[pid]
    dmin = 1e9
    for eid in enemy_pid_set:
        if eid not in pos:
            continue
        ex, ey = pos[eid]
        d = math.hypot(x - ex, y - ey)
        if d < dmin:
            dmin = d
    return dmin


def extract_teamfight_summaries(
    timeline_data: dict[str, Any], match_details: dict[str, Any] | None, top_k: int = 2
) -> list[str]:
    """Return compact CN summaries of top teamfights using timeline position + events.

    Designed for lightweight enrichment and ASCII-SAFE embedding; no heavy deps.
    """
    if not isinstance(timeline_data, dict) or not timeline_data.get("info"):
        return []

    info = timeline_data.get("info", {})
    frames: list[dict[str, Any]] = info.get("frames", []) or []
    if not frames:
        return []

    # Build pid -> team mapping from match_details (preferred)
    team_map: dict[int, int] = {}
    if match_details and isinstance(match_details.get("info"), dict):
        for p in match_details["info"].get("participants", []) or []:
            try:
                pid = int(p.get("participantId", 0) or 0)
                tid = int(p.get("teamId", 0) or 0)
            except Exception:
                continue
            if 1 <= pid <= 10 and tid in (100, 200):
                team_map[pid] = tid

    # Seed windows from combat/objective events
    seeds: list[tuple[int, int]] = []
    for fr in frames:
        for ev in fr.get("events", []) or []:
            et = ev.get("type")
            if et in ("CHAMPION_KILL", "ELITE_MONSTER_KILL"):
                ts = int(ev.get("timestamp", fr.get("timestamp", 0)) or 0)
                seeds.append((ts - 8000, ts + 8000))

    windows = _merge_windows(seeds, pad=2000)
    if not windows:
        return []

    summaries: list[tuple[float, str]] = []
    for ws, we in windows:
        # Slice frames within window
        wf = [fr for fr in frames if ws <= int(fr.get("timestamp", 0)) <= we]
        if not wf:
            continue
        # Build pos map per frame
        contact_flags: list[tuple[int, bool]] = []
        kills = 0
        obj = ""
        for fr in wf:
            ts = int(fr.get("timestamp", 0))
            pf = fr.get("participantFrames", {}) or fr.get("participant_frames", {}) or {}
            pos: dict[int, tuple[float, float]] = {}
            for key, val in pf.items():
                try:
                    pid = int(val.get("participant_id", key))
                    pos[pid] = (
                        float((val.get("position") or {}).get("x", 0.0)),
                        float((val.get("position") or {}).get("y", 0.0)),
                    )
                except Exception:
                    continue

            blues = {pid for pid, t in team_map.items() if t == 100}
            reds = {pid for pid, t in team_map.items() if t == 200}
            engaged_b = sum(
                1 for pid in blues if _nearest_enemy_distance(pos, pid, blues, reds) <= 950
            )
            engaged_r = sum(
                1 for pid in reds if _nearest_enemy_distance(pos, pid, reds, blues) <= 950
            )
            contact = engaged_b >= 2 and engaged_r >= 2
            contact_flags.append((ts, contact))

            for ev in fr.get("events", []) or []:
                if ev.get("type") == "CHAMPION_KILL":
                    kills += 1
                elif ev.get("type") == "ELITE_MONSTER_KILL":
                    m = (ev.get("monsterType") or "").upper()
                    if m in ("BARON_NASHOR", "RIFTHERALD", "DRAGON"):
                        obj = (
                            "男爵"
                            if m == "BARON_NASHOR"
                            else ("先锋" if m == "RIFTHERALD" else "小龙")
                        )

        # refine window to first/last contact
        ts_contact = [ts for ts, c in contact_flags if c]
        if not ts_contact:
            continue
        s, e = min(ts_contact), max(ts_contact)
        # Build coarse centroid labels
        mid_idx = len(wf) // 2
        mid_fr = wf[mid_idx]
        pf = mid_fr.get("participantFrames", {}) or mid_fr.get("participant_frames", {}) or {}
        bx, by, rc, ry = 0.0, 0.0, 0, 0
        for key, val in pf.items():
            try:
                pid = int(val.get("participant_id", key))
                if pid not in team_map:
                    continue
                x = float((val.get("position") or {}).get("x", 0.0))
                y = float((val.get("position") or {}).get("y", 0.0))
                if team_map[pid] == 100:
                    bx += x
                    by += y
                    rc += 1
                else:
                    rc += 0
                    ry += 0  # keep placeholders for symmetry
            except Exception:
                continue
        start_min = max(0, s // 60000)
        start_sec = (s // 1000) % 60
        region = _region_label(bx / max(1, rc), by / max(1, rc)) if rc > 0 else "河道附近"
        label = f"{start_min:02d}:{start_sec:02d} {region} | 击杀{kills}"
        if obj:
            label += f" | 目标:{obj}"
        # importance score: kills + objective bonus + duration
        score = kills + (1.5 if obj else 0.0) + (e - s) / 20000.0
        summaries.append((score, label))

    summaries.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in summaries[:top_k]]
