from typing import Any

import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "sr_enrichment", str(pathlib.Path("src/core/services/sr_enrichment.py").resolve())
)
_sr_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
assert _spec and _spec.loader
_spec.loader.exec_module(_sr_mod)  # type: ignore[union-attr]
extract_sr_enrichment = _sr_mod.extract_sr_enrichment


def _timeline_with_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    # Minimal timeline payload: 10 min frame and 15 min frame to satisfy lookups
    frames = [
        {
            "timestamp": 600000,
            "participant_frames": {
                "1": {"totalGold": 4500, "xp": 6000},
                "7": {"totalGold": 4300, "xp": 5800},
            },
            "events": events,
        },
        {
            "timestamp": 900000,
            "participant_frames": {
                "1": {"totalGold": 7000, "xp": 9500},
                "7": {"totalGold": 6800, "xp": 9200},
            },
            "events": [],
        },
    ]
    return {"info": {"frames": frames}}


def _timeline_with_frames(frames: list[dict[str, Any]]) -> dict[str, Any]:
    return {"info": {"frames": frames}}


def _match_details_my_mid_vs_enemy_mid() -> dict[str, Any]:
    # participantId 1..5 = team 100 (blue); 6..10 = team 200 (red)
    parts: list[dict[str, Any]] = []
    # Ours
    parts.append(
        {
            "participantId": 1,
            "teamId": 100,
            "puuid": "me-puuid",
            "individualPosition": "MIDDLE",
            "teamPosition": "MIDDLE",
            "summonerName": "Me",
        }
    )
    for pid in range(2, 6):
        parts.append(
            {
                "participantId": pid,
                "teamId": 100,
                "individualPosition": "TOP",
                "summonerName": f"Ally{pid}",
            }
        )
    # Enemy mid is 7
    parts.append(
        {
            "participantId": 7,
            "teamId": 200,
            "individualPosition": "MIDDLE",
            "teamPosition": "MIDDLE",
            "summonerName": "EnemyMid",
        }
    )
    for pid in range(6, 11):
        if pid == 7:
            continue
        parts.append(
            {
                "participantId": pid,
                "teamId": 200,
                "individualPosition": "TOP",
                "summonerName": f"Enemy{pid}",
            }
        )

    return {"info": {"participants": parts}}


def test_objective_breakdown_counts_own_team() -> None:
    # IMPORTANT: Riot API teamId in BUILDING_KILL = team that OWNS the destroyed building
    # So teamId=200 means we (team 100) destroyed enemy's building
    events = [
        {
            "type": "BUILDING_KILL",
            "teamId": 200,  # Enemy tower destroyed (we destroyed it!)
            "buildingType": "TOWER_BUILDING",
        },
        {
            "type": "BUILDING_KILL",
            "teamId": 100,  # Our tower destroyed (enemy destroyed it - don't count!)
            "buildingType": "TOWER_BUILDING",
        },
        {
            "type": "ELITE_MONSTER_KILL",
            "monsterType": "DRAGON",
            "killerId": 9,  # enemy team (200) - don't count
        },
        {
            "type": "ELITE_MONSTER_KILL",
            "monsterType": "DRAGON",
            "killerId": 3,  # our team (100) - count this!
        },
    ]
    timeline = _timeline_with_events(events)
    details = _match_details_my_mid_vs_enemy_mid()

    data = extract_sr_enrichment(timeline, details, participant_id=1)

    # We should count 1 tower (enemy's, teamId=200) and 1 dragon (ours, killerId=3)
    ob = data.get("objective_breakdown") or {}
    assert ob.get("towers") == 1, f"Expected 1 tower, got {ob.get('towers')}"
    assert ob.get("drakes") == 1, f"Expected 1 dragon, got {ob.get('drakes')}"
    assert ob.get("barons", 0) == 0

    # conversion_rate present and in [0,1]
    assert 0.0 <= float(data.get("conversion_rate", 0.0)) <= 1.0


def test_conversion_breakdown_counts_per_kill_pairing() -> None:
    """同一条龙可由多个击杀窗口映射，conversion_breakdown 应累加配对次数。"""
    events = [
        {
            "type": "CHAMPION_KILL",
            "timestamp": 100_000,
            "killerId": 2,
            "victimId": 6,
        },
        {
            "type": "CHAMPION_KILL",
            "timestamp": 150_000,
            "killerId": 3,
            "victimId": 7,
        },
        {
            "type": "ELITE_MONSTER_KILL",
            "timestamp": 190_000,
            "killerId": 2,
            "monsterType": "DRAGON",
        },
    ]
    timeline = _timeline_with_events(events)
    details = _match_details_my_mid_vs_enemy_mid()

    data = extract_sr_enrichment(timeline, details, participant_id=1)

    breakdown = data.get("objective_breakdown") or {}
    conv_breakdown = data.get("conversion_breakdown") or {}

    assert breakdown.get("drakes") == 1, "唯一目标数量应为 1 条龙"
    assert data.get("team_kills_considered") == 2
    assert data.get("post_kill_objective_conversions") == 2
    assert conv_breakdown.get("drakes") == 2, "两次击杀都应匹配到该龙 → 计数为 2"


def test_conversion_pairing() -> None:
    """别名：方便按名称运行新增用例。"""
    test_conversion_breakdown_counts_per_kill_pairing()


def test_gold_xp_diff_vs_lane_opponent_at_10() -> None:
    timeline = _timeline_with_events(events=[])
    details = _match_details_my_mid_vs_enemy_mid()

    data = extract_sr_enrichment(timeline, details, participant_id=1)

    # Our gold/xp are higher than opponent at 10 by +200 each
    assert data.get("gold_diff_10") == 200
    assert data.get("xp_diff_10") == 200


def test_frame_fallback_within_window_uses_nearest_frame() -> None:
    frames = [
        {
            "timestamp": 588000,  # 12s before 10 min, within tolerance
            "participant_frames": {
                "1": {
                    "totalGold": 4900,
                    "xp": 6500,
                    "minionsKilled": 80,
                    "jungleMinionsKilled": 20,
                },
                "7": {
                    "totalGold": 4700,
                    "xp": 6200,
                    "minionsKilled": 70,
                    "jungleMinionsKilled": 15,
                },
            },
            "events": [],
        },
        {
            "timestamp": 905000,  # 5s after 15 min, within tolerance
            "participant_frames": {
                "1": {
                    "totalGold": 7600,
                    "xp": 11200,
                    "minionsKilled": 130,
                    "jungleMinionsKilled": 30,
                },
                "7": {
                    "totalGold": 7200,
                    "xp": 10800,
                    "minionsKilled": 118,
                    "jungleMinionsKilled": 26,
                },
            },
            "events": [],
        },
    ]
    timeline = _timeline_with_frames(frames)
    details = _match_details_my_mid_vs_enemy_mid()

    data = extract_sr_enrichment(timeline, details, participant_id=1)

    assert data.get("cs_at_10") == 100  # 80 + 20 from fallback frame
    assert data.get("gold_diff_10") == 200
    assert data.get("xp_diff_10") == 300
    assert data.get("cs_at_15") == 160
    assert data.get("gold_diff_15") == 400
    assert data.get("xp_diff_15") == 400


def test_frame_outside_tolerance_uses_fallback() -> None:
    """When frames are outside the initial tolerance, expanded search finds the closest available frame."""
    frames = [
        {
            "timestamp": 540000,  # 60s before 10min target
            "participant_frames": {
                "1": {
                    "totalGold": 4200,
                    "xp": 5800,
                    "minionsKilled": 70,
                    "jungleMinionsKilled": 18,
                },
                "7": {
                    "totalGold": 4300,
                    "xp": 5900,
                    "minionsKilled": 68,
                    "jungleMinionsKilled": 17,
                },
            },
            "events": [],
        },
        {
            "timestamp": 840000,  # 60s before 15min target
            "participant_frames": {
                "1": {
                    "totalGold": 6200,
                    "xp": 8700,
                    "minionsKilled": 110,
                    "jungleMinionsKilled": 25,
                },
                "7": {
                    "totalGold": 6400,
                    "xp": 8900,
                    "minionsKilled": 112,
                    "jungleMinionsKilled": 24,
                },
            },
            "events": [],
        },
    ]
    timeline = _timeline_with_frames(frames)
    details = _match_details_my_mid_vs_enemy_mid()

    data = extract_sr_enrichment(timeline, details, participant_id=1)

    # SR enrichment now uses expanded frame search with fallback
    # So it should find the closest available frames and return data
    assert data.get("cs_at_10") == 88  # 70 + 18 from 540s frame (closest to 600s)
    assert data.get("gold_diff_10") == -100  # 4200 - 4300
    assert data.get("xp_diff_10") == -100  # 5800 - 5900
    assert data.get("cs_at_15") == 135  # 110 + 25 from 840s frame (closest to 900s)
    assert data.get("gold_diff_15") == -200  # 6200 - 6400
    assert data.get("xp_diff_15") == -200  # 8700 - 8900
