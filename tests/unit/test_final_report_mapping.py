import sys
from types import ModuleType


class _LazyModule(ModuleType):
    def __getattr__(self, item: str):
        def _missing(*_args, **_kwargs):
            raise RuntimeError(f"Accessed stubbed module attr '{item}' on {_args}")

        return _missing


np_stub = _LazyModule("numpy")
sys.modules.setdefault("numpy", np_stub)

google_stub = ModuleType("google")
genai_stub = ModuleType("google.generativeai")
google_stub.generativeai = genai_stub
sys.modules.setdefault("google", google_stub)
sys.modules.setdefault("google.generativeai", genai_stub)
sys.modules.setdefault("aioboto3", ModuleType("aioboto3"))
sys.modules.setdefault("aiobotocore", ModuleType("aiobotocore"))
sys.modules.setdefault("botocore", ModuleType("botocore"))

from src.tasks.team_tasks import _build_final_analysis_report


def _mk_match(summoner_name: str = "Tester", champion_name: str = "Lux", win: bool = True):
    return {
        "metadata": {"matchId": "NA1_999"},
        "info": {
            "participants": [
                {
                    "puuid": "P1",
                    "summonerName": summoner_name,
                    "championName": champion_name,
                    "championId": 99,
                    "win": win,
                    "kills": 5,
                    "deaths": 3,
                    "assists": 7,
                    "totalDamageDealtToChampions": 15000,
                    "totalDamageTaken": 14000,
                    "playerAugment1": "1",
                    "placement": 4,
                }
            ]
        },
    }


def _mk_arena_match(
    *,
    summoner_name: str,
    champion_name: str,
    kills: int,
    deaths: int,
    assists: int,
    damage_dealt: int,
    damage_taken: int,
    placement: int,
) -> dict:
    return {
        "metadata": {"matchId": "NA1_ARENA"},
        "info": {
            "participants": [
                {
                    "puuid": "ARENA_P1",
                    "summonerName": summoner_name,
                    "championName": champion_name,
                    "championId": 39,
                    "win": placement <= 2,
                    "kills": kills,
                    "deaths": deaths,
                    "assists": assists,
                    "totalDamageDealtToChampions": damage_dealt,
                    "totalDamageTaken": damage_taken,
                    "damageSelfMitigated": damage_taken // 2,
                    "timeCCingOthers": 33,
                    "subteamId": 11,
                    "playerAugment1": "1",
                    "playerAugment2": "2",
                    "placement": placement,
                },
                {
                    "puuid": "ARENA_P2",
                    "summonerName": "Partner",
                    "championName": "Braum",
                    "subteamId": 11,
                },
            ]
        },
    }


def _arena_round(
    round_number: int,
    *,
    result: str,
    kills: int,
    deaths: int,
    damage_dealt: int,
    damage_taken: int,
    positioning: float = 65.0,
) -> dict:
    return {
        "round_number": round_number,
        "round_result": result,
        "damage_dealt": damage_dealt,
        "damage_taken": damage_taken,
        "kills": kills,
        "deaths": deaths,
        "positioning_score": positioning,
    }


def _mk_arena_strategy_result(
    *,
    overall_score: float,
    placement: int,
    rounds_played: int,
    rounds_won: int,
    round_performances: list[dict],
) -> dict:
    return {
        "mode": "arena",
        "score_data": {
            "match_id": "NA1_ARENA",
            "summoner_name": "Fuji shan xia",
            "champion_name": "Irelia",
            "partner_summoner_name": "Partner",
            "partner_champion_name": "Braum",
            "final_placement": placement,
            "overall_score": overall_score,
            "rounds_played": rounds_played,
            "rounds_won": rounds_won,
            "round_performances": round_performances,
            "augment_analysis": {
                "augments_selected": ["猛攻", "疾行"],
                "augment_synergy_with_champion": "攻击节奏契合 Irelia 被动。",
                "augment_synergy_with_partner": "为布隆提供快速开团后的追击节奏。",
                "alternative_augment_suggestion": None,
            },
            "combat_score": 62.0,
            "duo_synergy_score": 74.0,
            "growth_score": 42.0,
            "tankiness_score": 68.0,
            "damage_composition_score": 55.0,
            "survivability_score": 49.0,
            "cc_contribution_score": 35.0,
            "analysis_summary": "测试总结",
            "improvement_suggestions": ["测试建议"],
            "algorithm_version": "v2.3-arena-lite",
        },
        "metrics": {},
    }


def test_final_report_mapping_for_aram_v1_lite():
    strategy_result = {
        "mode": "aram",
        "score_data": {
            "match_id": "NA1_999",
            "summoner_name": "Tester",
            "champion_name": "Lux",
            "match_result": "victory",
            "overall_score": 82.5,
            "teamfight_metrics": {
                "total_teamfights": 3,
                "damage_share_in_teamfights": 0.28,
                "damage_taken_share": 0.15,
                "avg_survival_time_in_teamfights": 12.3,
                "kills_participation_rate": 0.7,
                "deaths_before_teamfight_end": 1,
            },
            "build_adaptation": {
                "enemy_ap_threat_level": 0.7,
                "enemy_ad_threat_level": 0.3,
                "player_mr_items": 1,
                "player_armor_items": 0,
                "build_adaptation_score": 78.5,
            },
            "combat_score": 85.0,
            "teamplay_score": 76.0,
            "growth_score": 0.0,
            "tankiness_score": 0.0,
            "damage_composition_score": 0.0,
            "survivability_score": 0.0,
            "cc_contribution_score": 0.0,
            "analysis_summary": "良好的ARAM表现",
            "improvement_suggestions": ["保持后排站位"],
            "algorithm_version": "v2.3-aram-lite",
        },
        "metrics": {},
    }

    report = _build_final_analysis_report(
        strategy_result, _mk_match(), "P1", processing_duration_ms=123.0
    )

    assert report.ai_narrative_text.startswith("良好的")
    assert report.v1_score_summary.combat_score == 85.0
    assert report.v1_score_summary.teamplay_score == 76.0
    assert report.v1_score_summary.vision_score == 0.0
    assert report.algorithm_version == "v2.3-aram-lite"


def test_raw_stats_includes_crowd_control_score():
    match_data = _mk_match()
    participant = match_data["info"]["participants"][0]
    participant.update(
        {
            "puuid": "P1",
            "participantId": 1,
            "totalMinionsKilled": 150,
            "neutralMinionsKilled": 18,
            "goldEarned": 12400,
            "totalDamageDealtToChampions": 20500,
            "totalDamageTaken": 15900,
            "damageSelfMitigated": 7800,
            "visionScore": 21,
            "wardsPlaced": 6,
            "wardsKilled": 3,
            "timeCCingOthers": 424.0,
            "totalTimeCCDealt": 430.0,
            "crowdControlScore": 275.0,
            "challenges": {"crowdControlScore": 312.5},
        }
    )
    match_data["info"]["queueId"] = 450

    strategy_result = {
        "mode": "aram",
        "score_data": {
            "analysis_summary": "测试 ARAM 叙事。",
            "combat_score": 70.0,
            "teamplay_score": 62.0,
            "growth_score": 58.0,
            "tankiness_score": 55.0,
            "damage_composition_score": 60.0,
            "survivability_score": 48.0,
            "cc_contribution_score": 52.0,
            "overall_score": 64.0,
            "algorithm_version": "v2.3-aram-lite",
        },
        "metrics": {},
    }

    report = _build_final_analysis_report(
        strategy_result, match_data, "P1", processing_duration_ms=321.0
    )

    raw_stats = report.v1_score_summary.raw_stats
    assert raw_stats.get("cc_time") == 424.0
    assert raw_stats.get("cc_score") == 312.5


def test_arena_sentiment_watch_level_triggers_attention_tag():
    rounds = [
        _arena_round(
            1,
            result="win",
            kills=1,
            deaths=0,
            damage_dealt=1800,
            damage_taken=700,
            positioning=88.0,
        ),
        _arena_round(2, result="loss", kills=0, deaths=1, damage_dealt=900, damage_taken=1600),
        _arena_round(
            3,
            result="win",
            kills=1,
            deaths=0,
            damage_dealt=2100,
            damage_taken=800,
            positioning=90.0,
        ),
        _arena_round(4, result="loss", kills=0, deaths=1, damage_dealt=600, damage_taken=1400),
    ]
    strategy_result = _mk_arena_strategy_result(
        overall_score=38.5,
        placement=5,
        rounds_played=len(rounds),
        rounds_won=2,
        round_performances=rounds,
    )
    match_data = _mk_arena_match(
        summoner_name="Fuji shan xia",
        champion_name="Irelia",
        kills=6,
        deaths=2,
        assists=7,
        damage_dealt=19500,
        damage_taken=17800,
        placement=5,
    )

    report = _build_final_analysis_report(
        strategy_result, match_data, "ARENA_P1", processing_duration_ms=512.0
    )

    assert report.llm_sentiment_tag == "鼓励"
    sentiment_factors = report.v1_score_summary.raw_stats.get("arena_sentiment_factors")
    assert sentiment_factors is not None
    assert sentiment_factors["ui_sentiment"] == "关注"
    assert sentiment_factors["severity"] == "watch"
    assert sentiment_factors["trigger_flags"] == ["overall_low"]
    assert sentiment_factors["severity"] == "watch"
    assert sentiment_factors["trigger_flags"] == ["overall_low"]


def test_arena_sentiment_critical_flags_surface_factors():
    rounds = []
    for idx in range(1, 13):
        rounds.append(
            _arena_round(
                idx,
                result="loss",
                kills=0 if idx != 3 else 1,
                deaths=1 if idx >= 7 else (1 if idx in {2, 4, 5} else 0),
                damage_dealt=450 if idx >= 7 else 900,
                damage_taken=2100 if idx >= 7 else 1500,
                positioning=55.0 if idx >= 7 else 65.0,
            )
        )
    strategy_result = _mk_arena_strategy_result(
        overall_score=32.0,
        placement=7,
        rounds_played=len(rounds),
        rounds_won=3,
        round_performances=rounds,
    )
    match_data = _mk_arena_match(
        summoner_name="Fuji shan xia",
        champion_name="Irelia",
        kills=1,
        deaths=9,
        assists=5,
        damage_dealt=13387,
        damage_taken=28926,
        placement=7,
    )

    report = _build_final_analysis_report(
        strategy_result, match_data, "ARENA_P1", processing_duration_ms=640.0
    )

    assert report.llm_sentiment_tag == "遗憾"
    sentiment_factors = report.v1_score_summary.raw_stats.get("arena_sentiment_factors")
    assert sentiment_factors is not None
    assert sentiment_factors["severity"] == "critical"
    assert "death_streak" in sentiment_factors["trigger_flags"]
    assert "placement_low" in sentiment_factors["trigger_flags"]
    assert sentiment_factors["longest_death_streak"] >= 4
    assert sentiment_factors["death_rate"] > 0.6
