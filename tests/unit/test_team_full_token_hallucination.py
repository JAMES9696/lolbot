"""Team full-token analysis hallucination guards."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from src.contracts.common import Position
from src.contracts.timeline import (
    ChampionStats,
    DamageStats,
    Frame,
    MatchTimeline,
    ParticipantFrame,
    TimelineInfo,
    TimelineMetadata,
    TimelineParticipant,
)


class _StubGenerativeModel:
    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        pass

    def generate_content(self, prompt: Any) -> Any:  # noqa: D401
        return types.SimpleNamespace(text="stub-response", usage_metadata=None)


class _ImportSafeGemini:
    async def analyze_match(self, *_args: Any, **_kwargs: Any) -> str:  # noqa: D401
        return "stub"

    async def analyze_match_json(self, *_args: Any, **_kwargs: Any) -> str:  # noqa: D401
        return "{}"


sys.modules.setdefault(
    "google.generativeai",
    types.SimpleNamespace(GenerativeModel=_StubGenerativeModel, configure=lambda **_: None),
)
sys.modules.setdefault("aioboto3", types.SimpleNamespace(Session=lambda *args, **kwargs: None))
sys.modules.setdefault(
    "src.adapters.gemini_llm",
    types.SimpleNamespace(GeminiLLMAdapter=_ImportSafeGemini, GeminiAPIError=Exception),
)


class _PlayerScoreStub:
    def __init__(
        self,
        participant_id: int,
        total_score: float,
        combat: float,
        econ: float,
        vision: float,
        objective: float,
        teamplay: float,
    ) -> None:
        self.participant_id = participant_id
        self.total_score = total_score
        self.combat_efficiency = combat
        self.economic_management = econ
        self.vision_control = vision
        self.objective_control = objective
        self.team_contribution = teamplay
        self.growth_score = 60.0
        self.tankiness_score = 55.0
        self.damage_composition_score = 58.0
        self.survivability_score = 52.0
        self.cc_contribution_score = 47.0


class _AnalysisOutputStub:
    def __init__(self, player_scores: list[_PlayerScoreStub]) -> None:
        self.player_scores = player_scores

    def model_dump(self, *, mode: str) -> dict[str, Any]:  # noqa: D401
        assert mode == "json"

        def _convert(ps: _PlayerScoreStub) -> dict[str, Any]:
            return {
                "participant_id": ps.participant_id,
                "total_score": ps.total_score,
                "combat_efficiency": ps.combat_efficiency,
                "economic_management": ps.economic_management,
                "vision_control": ps.vision_control,
                "objective_control": ps.objective_control,
                "team_contribution": ps.team_contribution,
                "kda": 3.2,
                "cs_per_min": 6.2,
                "kill_participation": 72.0,
                "strengths": ["团战接管"],
                "improvements": ["边路换血控制"],
            }

        return {
            "match_id": "NA1_FALLBACK_001",
            "game_duration_minutes": 30.0,
            "player_scores": [_convert(ps) for ps in self.player_scores],
            "mvp_id": self.player_scores[0].participant_id if self.player_scores else 1,
            "team_blue_avg_score": 65.0,
            "team_red_avg_score": 54.0,
        }


class _StubTeamSummary:
    def model_dump_json(self, **_: Any) -> str:
        return "{}"


class _StubPromptSelectorService:
    @staticmethod
    def calculate_team_summary(**_: Any) -> _StubTeamSummary:  # type: ignore[override]
        return _StubTeamSummary()


sys.modules.setdefault(
    "src.core.services.ab_testing",
    types.SimpleNamespace(PromptSelectorService=_StubPromptSelectorService),
)
sys.modules.setdefault(
    "src.core.services.timeline_evidence_extractor",
    types.SimpleNamespace(extract_timeline_evidence=lambda *_, **__: None),
)
sys.modules.setdefault(
    "src.core.services.user_profile_service",
    types.SimpleNamespace(
        UserProfileService=lambda: types.SimpleNamespace(
            get_user_profile_context=lambda *_, **__: None
        )
    ),
)
sys.modules.setdefault(
    "src.prompts.v2_team_relative_prompt",
    types.SimpleNamespace(V2_TEAM_RELATIVE_SYSTEM_PROMPT="stub-prompt"),
)


def _noop_task(*_args: Any, **_kwargs: Any):
    def decorator(func: Any) -> Any:
        return func

    return decorator


_celery_app_stub = types.SimpleNamespace(task=_noop_task)
_tasks_module_stub = types.ModuleType("src.tasks")
_tasks_module_stub.celery_app = types.SimpleNamespace(celery_app=_celery_app_stub)
sys.modules.setdefault("src.tasks", _tasks_module_stub)
sys.modules.setdefault("src.tasks.celery_app", types.SimpleNamespace(celery_app=_celery_app_stub))

_MODULE_NAME = "team_tasks_under_test"
_MODULE_PATH = Path(__file__).resolve().parents[2] / "src" / "tasks" / "team_tasks.py"
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
assert _spec and _spec.loader
team_tasks = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = team_tasks
_spec.loader.exec_module(team_tasks)
sys.modules["src.tasks"].team_tasks = team_tasks


class _StubGemini:
    """Stub Gemini adapter that returns controllable outputs."""

    async def analyze_match(self, payload: dict[str, Any], prompt: str) -> str:  # noqa: D401
        if payload.get("evidence"):
            return "关键回合：R5 小龙团失利，建议提前布控。"

        if "phase_minutes" in payload:
            return (
                "# 比赛分析报告 - 数据缺失\n\n"
                "## ⚠️ 无法生成分析\n"
                "TL;DR: 比赛数据完全缺失，无法进行任何有效分析。"
            )

        return "强项TOP1 | 短板TOP1 | 建议：沟通交闪进场。"


def _make_frame(timestamp: int) -> Frame:
    participant_frames: dict[str, ParticipantFrame] = {}
    for pid in range(1, 11):
        participant_frames[str(pid)] = ParticipantFrame(
            participant_id=pid,
            champion_stats=ChampionStats(health=1000 + pid, health_max=1200 + pid),
            damage_stats=DamageStats(
                total_damage_done_to_champions=1500 + pid * 10,
                total_damage_taken=900 + pid * 5,
            ),
            current_gold=3500 + pid * 50,
            total_gold=4000 + pid * 60,
            jungle_minions_killed=12,
            minions_killed=140,
            level=12 + pid % 3,
            position=Position(x=500 + pid * 10, y=500 + pid * 15),
            xp=9000 + pid * 120,
        )
    return Frame(timestamp=timestamp, participant_frames=participant_frames, events=[])


def _build_timeline() -> dict[str, Any]:
    timeline = MatchTimeline(
        metadata=TimelineMetadata(
            data_version="2",
            match_id="NA1_FALLBACK_001",
            participants=[f"P{i}" for i in range(1, 11)],
        ),
        info=TimelineInfo(
            frame_interval=60000,
            game_id=987654321,
            participants=[
                TimelineParticipant(participant_id=i, puuid=f"P{i}") for i in range(1, 11)
            ],
            frames=[_make_frame(0), _make_frame(1_800_000)],
        ),
    )
    return timeline.model_dump(mode="json")


def _build_match_details() -> dict[str, Any]:
    roles = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
    participants: list[dict[str, Any]] = []
    for pid in range(1, 11):
        side = 100 if pid <= 5 else 200
        role = roles[(pid - 1) % len(roles)]
        participants.append(
            {
                "participantId": pid,
                "teamId": side,
                "puuid": f"P{pid}",
                "summonerName": f"Player{pid}",
                "riotIdGameName": f"Player{pid}",
                "riotIdTagline": "NA1",
                "championName": "Ahri" if pid <= 5 else "Yone",
                "teamPosition": role,
                "individualPosition": role,
                "lane": role,
                "role": role,
                "win": side == 100,
                "kills": pid,
                "deaths": max(1, pid // 2),
                "assists": pid * 2,
                "totalDamageDealtToChampions": 15000 + pid * 100,
                "totalDamageTaken": 12000 + pid * 80,
                "damageSelfMitigated": 6000 + pid * 50,
                "visionScore": 25 + pid,
                "detectorWardsPlaced": 2,
                "wardsPlaced": 7,
                "wardsKilled": 3,
                "goldEarned": 11500 + pid * 120,
                "totalMinionsKilled": 200,
                "neutralMinionsKilled": 35,
                "timeCCingOthers": 60,
                "champLevel": 16,
                "turretTakedowns": 2,
                "dragonTakedowns": 1 if side == 100 else 0,
                "doubleKills": 0,
                "tripleKills": 0,
                "quadraKills": 0,
                "pentaKills": 0,
                "killingSprees": 1,
                "largestKillingSpree": 2,
                "largestMultiKill": 2,
            }
        )

    return {
        "metadata": {"matchId": "NA1_FALLBACK_001"},
        "info": {
            "gameDuration": 1800,
            "gameStartTimestamp": 0,
            "gameEndTimestamp": 1_800_000,
            "participants": participants,
            "teams": [
                {
                    "teamId": 100,
                    "win": True,
                    "objectives": {
                        "baron": {"kills": 1},
                        "dragon": {"kills": 2},
                        "riftHerald": {"kills": 1},
                        "tower": {"kills": 9},
                    },
                },
                {
                    "teamId": 200,
                    "win": False,
                    "objectives": {
                        "baron": {"kills": 0},
                        "dragon": {"kills": 1},
                        "riftHerald": {"kills": 0},
                        "tower": {"kills": 3},
                    },
                },
            ],
        },
    }


def test_full_token_hallucination_triggers_structured_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the full-token narrative hallucinate, use deterministic fallback narrative."""

    monkeypatch.setattr(sys.modules["src.adapters.gemini_llm"], "GeminiLLMAdapter", _StubGemini)

    def _stub_generate_llm_input(*_args: Any, **_kwargs: Any) -> _AnalysisOutputStub:
        players = [
            _PlayerScoreStub(
                participant_id=i,
                total_score=70.0 + (10 - i),
                combat=65.0 + (5 - i / 2),
                econ=60.0 + (5 - i / 3),
                vision=50.0 + (i / 2),
                objective=55.0 + (5 - i / 4),
                teamplay=58.0 + (5 - i / 5),
            )
            for i in range(1, 11)
        ]
        return _AnalysisOutputStub(players)

    scoring_stub = types.SimpleNamespace(generate_llm_input=_stub_generate_llm_input)
    monkeypatch.setitem(sys.modules, "src.core.scoring", scoring_stub)
    monkeypatch.setattr(team_tasks, "generate_llm_input", _stub_generate_llm_input)

    match_details = _build_match_details()
    timeline_data = _build_timeline()

    score_data = team_tasks._run_full_token_team_analysis(  # type: ignore[attr-defined]
        match_details=match_details,
        timeline_data=timeline_data,
        requester_puuid="P1",
    )

    narrative = score_data["ai_narrative_text"]
    assert "[降级模式]" in narrative
    assert "数据缺失" not in narrative

    tldr = score_data.get("tldr", "")
    assert isinstance(tldr, str)
    assert "数据缺失" not in tldr
    assert len(tldr) <= 400
