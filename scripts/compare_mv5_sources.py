#!/usr/bin/env python3
"""
Compare two data sources for the same Match-V5 ID:
1) REST adapter (src/adapters/riot_api.py)
2) Cassiopeia adapter (src/adapters/riot_api_enhanced.py)

Outputs a normalized summary to spot mismatches quickly:
- queueId, gameMode
- participants count
- participantId → (puuid, summonerName, champion)
- timeline frames/last timestamp
- detect_game_mode(queueId) and any heuristic corrections

Usage:
  python scripts/compare_mv5_sources.py --match NA1_5388494924 --region na1 [--puuid <your puuid>]
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import pathlib

# Make repo importable when executed as a script
_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config.settings import settings
from src.adapters.riot_api import RiotAPIAdapter
from src.contracts.v23_multi_mode_analysis import detect_game_mode


def _norm_participants(info: dict) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for p in info.get("participants") or []:
        try:
            pid = int(p.get("participantId", 0) or 0)
        except Exception:
            pid = 0
        out[pid] = {
            "puuid": p.get("puuid"),
            "name": p.get("riotIdGameName") or p.get("summonerName") or p.get("gameName"),
            "champion": p.get("championName") or p.get("champion_name") or p.get("champion"),
        }
    return out


def _timeline_summary(timeline: dict | None) -> tuple[int, int]:
    if not timeline:
        return 0, 0
    info = timeline.get("info", {}) or {}
    frames = info.get("frames", []) or []
    if not frames:
        return 0, 0
    last_ts = int(frames[-1].get("timestamp", 0) or 0)
    return len(frames), last_ts


def _route_for_region(platform_region: str) -> str:
    pr = platform_region.upper()
    americas = {"NA1", "BR1", "LA1", "LA2", "OC1"}
    europe = {"EUW1", "EUN1", "RU", "TR1"}
    asia = {"KR", "JP1"}
    sea = {"PH2", "SG2", "TH2", "TW2", "VN2"}
    if pr in americas:
        return "americas"
    if pr in europe:
        return "europe"
    if pr in asia:
        return "asia"
    if pr in sea:
        return "sea"
    return "americas"


async def _raw_fetch(match_id: str, region: str) -> tuple[dict | None, dict | None]:
    import aiohttp

    route = _route_for_region(region)
    base = f"https://{route}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    headers = {"X-Riot-Token": settings.riot_api_key}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        async with s.get(base, headers=headers) as r1:
            md = await r1.json() if r1.status == 200 else None
        async with s.get(base + "/timeline", headers=headers) as r2:
            tl = await r2.json() if r2.status == 200 else None
    return md, tl


async def fetch(rest: RiotAPIAdapter, match_id: str, region: str) -> dict:
    rest_md = await rest.get_match_details(match_id, region)
    rest_tl = await rest.get_match_timeline(match_id, region)
    raw_md, raw_tl = await _raw_fetch(match_id, region)

    def pack(label: str, md: dict | None, tl: dict | None) -> dict[str, Any]:
        info = (md or {}).get("info", {}) if md else {}
        qid = int(info.get("queueId", 0) or 0)
        gmode = (info.get("gameMode") or info.get("game_mode") or "").upper()
        parts = _norm_participants(info) if info else {}
        n_frames, last_ts = _timeline_summary(tl)
        det = None
        if qid:
            try:
                det = detect_game_mode(qid).mode
            except Exception:
                det = None
        return {
            "source": label,
            "queueId": qid,
            "gameMode": gmode,
            "participants": len(parts),
            "participants_map": parts,
            "timeline_frames": n_frames,
            "timeline_last_ts": last_ts,
            "detect_game_mode(queueId)": det,
        }

    return {
        "rest": pack("rest", rest_md, rest_tl),
        "raw": pack("raw", raw_md, raw_tl),
    }


def _print_diff(result: dict, puuid: str | None) -> None:
    rest = result["rest"]
    cass = result["raw"]
    print("== REST ==")
    print(json.dumps(rest, ensure_ascii=False, indent=2))
    print("\n== CASS ==")
    print(json.dumps(cass, ensure_ascii=False, indent=2))

    # Quick checks
    issues: list[str] = []
    if rest["queueId"] != cass["queueId"]:
        issues.append(f"queueId mismatch: REST={rest['queueId']} CASS={cass['queueId']}")
    if (rest["participants"] or 0) != (cass["participants"] or 0):
        issues.append(
            f"participants count mismatch: REST={rest['participants']} CASS={cass['participants']}"
        )
    if (rest["gameMode"] or "") != (cass["gameMode"] or ""):
        issues.append(f"gameMode mismatch: REST={rest['gameMode']} CASS={cass['gameMode']}")

    if puuid:

        def find_by_puuid(m: dict) -> tuple[int | None, str | None, str | None]:
            for pid, data in (m.get("participants_map") or {}).items():
                if str(data.get("puuid")) == puuid:
                    return int(pid), data.get("name"), data.get("champion")
            return None, None, None

        r_pid, r_name, r_champ = find_by_puuid(rest)
        c_pid, c_name, c_champ = find_by_puuid(cass)
        print("\nTarget participant (by puuid):")
        print(f" REST: pid={r_pid} name={r_name} champ={r_champ}")
        print(f" CASS: pid={c_pid} name={c_name} champ={c_champ}")
        if r_pid != c_pid:
            issues.append(f"participantId mismatch for puuid: REST={r_pid} CASS={c_pid}")
        if (r_champ or "") != (c_champ or ""):
            issues.append(f"champion mismatch for puuid: REST={r_champ} CASS={c_champ}")

    # Cross-check: queueId mapping vs gameMode string within each source
    def _label_from_qid(qid: int) -> str:
        try:
            from src.contracts.v23_multi_mode_analysis import detect_game_mode

            return detect_game_mode(int(qid or 0)).mode
        except Exception:
            return "Unknown"

    def _label_from_str(gm: str | None) -> str:
        m = (gm or "").upper()
        return {"CLASSIC": "SR", "ARAM": "ARAM", "CHERRY": "Arena"}.get(m, "Unknown")

    for src in ("rest", "raw"):
        m = result[src]
        q_label = _label_from_qid(m.get("queueId", 0))
        s_label = _label_from_str(m.get("gameMode"))
        if q_label != "Unknown" and s_label != "Unknown" and q_label != s_label:
            issues.append(f"{src.upper()} queueId vs gameMode mismatch: {q_label} vs {s_label}")

    print("\n== QUICK DIAGNOSTICS ==")
    if not issues:
        print("No mismatches detected ✓")
    else:
        for it in issues:
            print(f"- {it}")

    # Heuristic inconsistency: Arena vs SR
    def label(m: dict) -> str:
        det = (m.get("detect_game_mode(queueId)") or "").lower()
        if det == "arena" and m.get("participants") == 10:
            return "[!] queueId says Arena but participants==10 (SR-like)"
        return ""

    for src in ("rest", "raw"):
        msg = label(result[src])
        if msg:
            print(f"{src.upper()} {msg}")


async def _amain(match_id: str, region: str, puuid: str | None) -> int:
    # Pre-flight env
    if not settings.riot_api_key:
        print("RIOT_API_KEY is not configured (.env)", file=sys.stderr)
        return 2
    rest = RiotAPIAdapter()
    try:
        result = await fetch(rest, match_id, region)
        _print_diff(result, puuid)
        return 0
    finally:
        await rest.close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Compare Match-V5 data across adapters")
    parser.add_argument("--match", dest="match_id", required=True)
    parser.add_argument("--region", dest="region", default="na1")
    parser.add_argument("--puuid", dest="puuid", default=None)
    args = parser.parse_args()

    code = asyncio.run(_amain(args.match_id, args.region, args.puuid))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
