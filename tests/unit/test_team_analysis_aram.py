from types import SimpleNamespace

from src.core.views.team_analysis_view import (
    _derive_highlights,
    _format_enhancements,
    _format_team_snapshot,
)
from src.core.views.team_ascii_receipt import build_team_receipt


def test_aram_enhancement_text_suppressed() -> None:
    assert _format_enhancements(None, mode="aram") == "ARAM 模式暂无时间线增强指标"
    assert _format_enhancements(None, mode="summoners_rift") == "暂无时间线增强数据"


def test_aram_highlights_exclude_sr_dimensions() -> None:
    report = SimpleNamespace(
        game_mode="aram",
        aggregates=SimpleNamespace(
            combat_avg=50.0,
            economy_avg=50.0,
            objective_avg=50.0,
            vision_avg=50.0,
            teamplay_avg=50.0,
        ),
        players=[],
    )
    target = SimpleNamespace(
        combat_score=60.0,
        economy_score=55.0,
        objective_score=40.0,
        vision_score=30.0,
        teamplay_score=58.0,
        survivability_score=None,
    )

    highlights = _derive_highlights(report, target, top=True)
    dimensions = {h.dimension for h in highlights}
    assert "vision_control" not in dimensions
    assert "objective_control" not in dimensions


def test_team_receipt_aram_omits_sr_bars() -> None:
    players = [
        SimpleNamespace(
            combat_score=60.0,
            economy_score=55.0,
            vision_score=10.0,
            objective_score=15.0,
            teamplay_score=58.0,
            survivability_score=30.0,
            summoner_name="Player",
        )
    ]
    report = SimpleNamespace(
        team_analysis=players,
        target_player_name="Player",
        game_mode="aram",
    )

    receipt = build_team_receipt(report)
    assert "Vision" not in receipt
    assert "Obj" not in receipt


def test_team_snapshot_includes_both_sides() -> None:
    friendly = [
        SimpleNamespace(
            summoner_name=f"Ally{i}",
            champion_name="Ahri",
            overall_score=50 + i,
            combat_score=55 + i,
            teamplay_score=52 + i,
            kills=5 + i,
            deaths=3 + i,
            assists=7 + i,
            damage_dealt=15000 + i * 1000,
            team_rank=i + 1,
            vision_score=10.0,
        )
        for i in range(5)
    ]
    enemies = [
        SimpleNamespace(
            summoner_name=f"Enemy{i}",
            champion_name="Zed",
            overall_score=48 + i,
            combat_score=50 + i,
            teamplay_score=47 + i,
            kills=6 + i,
            deaths=4 + i,
            assists=5 + i,
            damage_dealt=13000 + i * 900,
            team_rank=i + 1,
            vision_score=12.0,
        )
        for i in range(5)
    ]

    snapshot = _format_team_snapshot(friendly, enemies, ascii_safe=True)
    assert "Ally0" in snapshot and "Enemy0" in snapshot
    # Ensure both columns rendered per row
    assert "|" in snapshot
    assert "KDA" in snapshot and "Dmg" in snapshot
