import discord


from src.core.views.analysis_view import render_analysis_embed


def _make_analysis_data(
    cc_time: float,
    *,
    cc_score: float = 0.0,
    observability: dict | None = None,
    algorithm_version: str = "v1",
) -> dict:
    v1_summary = {
        "combat_score": 50.0,
        "economy_score": 50.0,
        "vision_score": 25.0,
        "objective_score": 40.0,
        "teamplay_score": 35.0,
        "growth_score": 20.0,
        "tankiness_score": 30.0,
        "damage_composition_score": 45.0,
        "survivability_score": 38.0,
        "cc_contribution_score": 55.0,
        "overall_score": 48.0,
        "raw_stats": {
            "kills": 3,
            "deaths": 2,
            "assists": 4,
            "kda": 3.5,
            "gold": 10100,
            "gold_diff": 0,
            "damage_dealt": 12345,
            "damage_taken": 9876,
            "vision_score": 18,
            "wards_placed": 4,
            "wards_killed": 2,
            "queue_id": 420,
            "game_mode": "SR",
            "is_arena": False,
            "cc_time": cc_time,
            "cc_per_min": cc_time / max(1.0, 30.0),
            "cc_score": cc_score,
            "level": 14,
            "sr_enrichment": {"duration_min": 30.0},
        },
    }
    if observability:
        v1_summary["raw_stats"]["observability"] = observability
    return {
        "match_result": "defeat",
        "summoner_name": "Tester#NA1",
        "champion_name": "Sylas",
        "ai_narrative_text": "test narrative",
        "llm_sentiment_tag": "平淡",
        "v1_score_summary": v1_summary,
        "champion_assets_url": "https://example.com/sylas.png",
        "processing_duration_ms": 1500.0,
        "algorithm_version": algorithm_version,
    }


def _extract_snapshot_field(embed: discord.Embed) -> str:
    for field in embed.fields:
        if "个人快照" in field.name:
            return field.value
    raise AssertionError("个人快照字段缺失")


def test_cc_duration_under_minute_shows_seconds():
    embed = render_analysis_embed(_make_analysis_data(42.4, cc_score=12.0))
    snapshot = _extract_snapshot_field(embed)
    assert "控制" in snapshot
    assert "42.4s / 12 pts" in snapshot


def test_cc_duration_over_minute_shows_minutes_with_single_decimal():
    embed = render_analysis_embed(_make_analysis_data(424.109, cc_score=180.0))
    snapshot = _extract_snapshot_field(embed)
    assert "控制" in snapshot
    assert "7.1min / 180 pts" in snapshot


def test_footer_contains_observability_metrics() -> None:
    """验证Footer包含统一的Φ指标格式（与Team一致）"""
    observability = {
        "session_id": "session123",
        "execution_branch_id": "branchA",
        "fetch_ms": 320.4,
        "scoring_ms": 189.6,
        "llm_ms": 920.5,
        "overall_ms": 1820.4,
    }
    data = _make_analysis_data(42.4, observability=observability)
    data["processing_duration_ms"] = 1820.4
    embed = render_analysis_embed(data)
    footer = embed.footer.text or ""
    assert "session123:branchA" in footer
    assert "Φfetch=320ms" in footer
    assert "Φscore=190ms" in footer
    assert "Φllm=920ms" in footer or "Φllm=921ms" in footer  # 四舍五入可能是920或921
    assert "Φtotal=1820ms" in footer
    assert "算法 V1" in footer
    assert "⏱️" in footer


def test_footer_phi_metrics_present() -> None:
    """额外验证：确保至少一个Φ指标存在于Footer"""
    observability = {
        "session_id": "s1",
        "execution_branch_id": "b1",
        "fetch_ms": 100.0,
    }
    data = _make_analysis_data(10.0, observability=observability)
    embed = render_analysis_embed(data)
    footer = embed.footer.text or ""
    assert "Φ" in footer, "Footer应包含至少一个Φ指标"
