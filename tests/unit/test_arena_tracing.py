import sys
from types import ModuleType

if "numpy" not in sys.modules:

    class _LazyModule(ModuleType):
        def __getattr__(self, item: str):
            def _missing(*_args, **_kwargs):
                raise RuntimeError(f"Accessed stubbed module attr '{item}'")

            return _missing

    sys.modules["numpy"] = _LazyModule("numpy")

if "google" not in sys.modules:
    google_stub = ModuleType("google")
    genai_stub = ModuleType("google.generativeai")
    google_stub.generativeai = genai_stub
    sys.modules["google"] = google_stub
    sys.modules["google.generativeai"] = genai_stub
sys.modules.setdefault("aioboto3", ModuleType("aioboto3"))
sys.modules.setdefault("aiobotocore", ModuleType("aiobotocore"))
sys.modules.setdefault("botocore", ModuleType("botocore"))

from structlog.testing import capture_logs

from src.core.scoring.arena_v1_lite import generate_arena_analysis_report


def _basic_match_payload() -> tuple[dict, dict]:
    match_data = {
        "metadata": {"matchId": "NA1_TRACE"},
        "info": {
            "participants": [
                {
                    "puuid": "TRACE_P1",
                    "summonerName": "TraceTester",
                    "championName": "Yone",
                    "championId": 777,
                    "win": False,
                    "kills": 4,
                    "deaths": 6,
                    "assists": 3,
                    "totalDamageDealtToChampions": 16800,
                    "totalDamageTaken": 22000,
                    "damageSelfMitigated": 18000,
                    "timeCCingOthers": 24,
                    "subteamId": 21,
                    "playerAugment1": "1",
                    "placement": 4,
                },
                {
                    "puuid": "TRACE_P2",
                    "summonerName": "TraceMate",
                    "championName": "Janna",
                    "subteamId": 21,
                },
            ]
        },
    }
    timeline_data = {
        "info": {
            "participants": [{"puuid": "TRACE_P1", "participant_id": 3}],
            "frames": [
                {
                    "participant_frames": {
                        "3": {
                            "damage_stats": {
                                "total_damage_done_to_champions": 500,
                                "total_damage_taken": 320,
                            }
                        }
                    },
                    "events": [
                        {"type": "CHAMPION_KILL", "killerId": 3, "victimId": 7},
                        {"type": "CHAMPION_KILL", "killerId": 5, "victimId": 3},
                    ],
                }
            ],
        }
    }
    return match_data, timeline_data


def test_generate_arena_analysis_report_emits_execution_trace():
    match_data, timeline_data = _basic_match_payload()

    with capture_logs() as captured:
        report = generate_arena_analysis_report(
            match_data=match_data,
            timeline_data=timeline_data,
            player_puuid="TRACE_P1",
            summoner_name="TraceTester",
        )

    assert report.match_id == "NA1_TRACE"
    execution_events = [event for event in captured if "execution_id" in event]
    assert execution_events, "Expected llm_debug_wrapper to emit structured logs with execution_id"
    assert any(
        "generate_arena_analysis_report" in (event.get("function_name") or event.get("event", ""))
        for event in execution_events
    )
