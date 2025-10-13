import json

import pytest

from src.core.services.strategies.aram_strategy import ARAMStrategy
from src.core.services.strategies.arena_strategy import ArenaStrategy


@pytest.mark.asyncio
async def test_aram_strategy_v1_lite_happy_path(monkeypatch):
    # Mock GeminiLLMAdapter to avoid network
    class _FakeLLM:
        async def analyze_match_json(self, match_data, system_prompt, game_mode=None):  # noqa: D401
            return json.dumps(
                {
                    "analysis_summary": (
                        "本场ARAM你的团战输出与生存表现稳定，建议在前排交控制后再进场收割。"
                        "整体击杀参与率优秀，说明团战意识到位。防御装备选择合理，"
                        "针对敌方AP威胁做出了正确应对。继续保持当前打法风格，"
                        "注意在团战中合理利用技能CD，优先集火敌方脆皮输出位。"
                    ),
                    "improvement_suggestions": [
                        "团战起手站位更靠后，等待关键控制技能交出后再前压",
                        "针对AP威胁增加一件魔抗装，如女妖面纱",
                    ],
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr("src.core.services.strategies.aram_strategy.GeminiLLMAdapter", _FakeLLM)

    strategy = ARAMStrategy()

    # Minimal ARAM match/timeline
    match = {
        "metadata": {"matchId": "NA1_123"},
        "info": {
            "queueId": 450,
            "participants": [
                {
                    "puuid": "P1",
                    "summonerName": "Tester",
                    "championName": "Lux",
                    "teamId": 100,
                    "kills": 8,
                    "deaths": 3,
                    "assists": 7,
                    "totalDamageDealtToChampions": 18000,
                    "magicDamageDealtToChampions": 16000,
                    "physicalDamageDealtToChampions": 2000,
                    "totalDamageTaken": 9000,
                    "longestTimeSpentLiving": 300,
                    "item0": 3089,
                    "item1": 3020,
                    "item2": 3916,
                    "item3": 3135,
                    "item4": 3102,
                    "item5": 3157,
                    "item6": 3364,
                    "win": True,
                },
                {
                    "puuid": "P2",
                    "teamId": 100,
                    "kills": 7,
                    "deaths": 4,
                    "assists": 15,
                    "totalDamageDealtToChampions": 14000,
                    "magicDamageDealtToChampions": 12000,
                    "physicalDamageDealtToChampions": 2000,
                    "totalDamageTaken": 11000,
                    "longestTimeSpentLiving": 250,
                    "item0": 3089,
                    "item1": 3020,
                    "item2": 3916,
                    "item3": 3135,
                    "item4": 3157,
                    "item5": 0,
                    "item6": 3364,
                },
                {
                    "puuid": "E1",
                    "teamId": 200,
                    "kills": 4,
                    "deaths": 10,
                    "assists": 8,
                    "totalDamageDealtToChampions": 15000,
                    "magicDamageDealtToChampions": 13000,
                    "physicalDamageDealtToChampions": 2000,
                    "totalDamageTaken": 10000,
                    "longestTimeSpentLiving": 280,
                    "item0": 3089,
                    "item1": 3020,
                    "item2": 3916,
                    "item3": 3135,
                    "item4": 3157,
                    "item5": 0,
                    "item6": 3364,
                },
                {
                    "puuid": "E2",
                    "teamId": 200,
                    "kills": 3,
                    "deaths": 5,
                    "assists": 5,
                    "totalDamageDealtToChampions": 12000,
                    "magicDamageDealtToChampions": 10000,
                    "physicalDamageDealtToChampions": 2000,
                    "totalDamageTaken": 8000,
                    "longestTimeSpentLiving": 200,
                    "item0": 3089,
                    "item1": 3020,
                    "item2": 3916,
                    "item3": 3135,
                    "item4": 3102,
                    "item5": 0,
                    "item6": 3364,
                },
            ],
        },
    }
    timeline = {
        "info": {
            "frames": [
                {"events": [{"type": "CHAMPION_KILL", "timestamp": 10000}]},
                {"events": [{"type": "CHAMPION_KILL", "timestamp": 20000}]},
                {"events": [{"type": "CHAMPION_KILL", "timestamp": 30000}]},
            ]
        }
    }

    out = await strategy.execute_analysis(
        match_data=match,
        timeline_data=timeline,
        requester_puuid="P1",
        discord_user_id="U1",
    )

    assert out["mode"] == "aram"
    assert out["score_data"]["algorithm_version"] == "v2.3-aram-lite"
    assert out["score_data"]["analysis_summary"]


@pytest.mark.asyncio
async def test_arena_strategy_compliance_degrades(monkeypatch):
    # LLM returns non-compliant text (contains percentage)
    class _FakeLLM:
        async def analyze_match_json(self, match_data, system_prompt, game_mode=None):
            return json.dumps(
                {
                    "analysis_summary": "你的增强符文胜率 68% ，下场继续这样选。",
                    "improvement_suggestions": ["保持当前高胜率选择"],
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr("src.core.services.strategies.arena_strategy.GeminiLLMAdapter", _FakeLLM)

    strategy = ArenaStrategy()

    match = {
        "metadata": {"matchId": "NA1_456"},
        "info": {
            "queueId": 1700,
            "participants": [
                {
                    "puuid": "P1",
                    "summonerName": "Tester",
                    "championName": "Yasuo",
                    "kills": 10,
                    "deaths": 5,
                    "assists": 8,
                    "totalDamageDealtToChampions": 22000,
                    "win": False,
                    "placement": 3,
                    "subteamId": 1,
                },
                {"puuid": "P2", "summonerName": "Mate", "championName": "Malphite", "subteamId": 1},
            ],
        },
    }
    timeline = {"info": {"frames": [{"events": []}]}}

    out = await strategy.execute_analysis(
        match_data=match,
        timeline_data=timeline,
        requester_puuid="P1",
        discord_user_id="U1",
    )

    # Degraded to fallback but mode stays 'arena'
    assert out["mode"] == "arena"
    assert "fallback_message" in out["score_data"]
