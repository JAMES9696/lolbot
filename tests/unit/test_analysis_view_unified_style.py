from __future__ import annotations

import discord

from src.core.views.analysis_view import render_analysis_embed


def _sample_analysis_data() -> dict:
    raw_stats = {
        "kills": 7,
        "deaths": 3,
        "assists": 9,
        "kda": 5.33,
        "cs": 210,
        "cs_per_min": 7.5,
        "gold": 13420,
        "gold_diff": 420,
        "damage_dealt": 24880,
        "damage_taken": 18210,
        "damage_self_mitigated": 9650,
        "vision_score": 24,
        "wards_placed": 7,
        "wards_killed": 4,
        "queue_id": 420,
        "game_mode": "SR",
        "is_arena": False,
        "cc_time": 424.0,
        "cc_score": 180.0,
        "level": 16,
        "sr_enrichment": {
            "gold_diff_10": 450,
            "xp_diff_10": 220,
            "conversion_rate": 0.15,
            "ward_rate_per_min": 1.4,
            "cs_at_10": 82,
            "duration_min": 29.8,
        },
        "observability": {
            "session_id": "session321",
            "execution_branch_id": "branchZ",
            "fetch_ms": 210.2,
            "scoring_ms": 145.8,
            "llm_ms": 512.6,
            "overall_ms": 1189.9,
        },
    }

    v1_summary = {
        "combat_score": 92.0,
        "economy_score": 68.0,
        "vision_score": 32.0,
        "objective_score": 58.0,
        "teamplay_score": 44.0,
        "growth_score": 75.0,
        "tankiness_score": 49.0,
        "damage_composition_score": 83.0,
        "survivability_score": 52.0,
        "cc_contribution_score": 60.0,
        "overall_score": 66.0,
        "raw_stats": raw_stats,
    }

    return {
        "match_result": "victory",
        "summoner_name": "Tester#NA1",
        "champion_name": "Sylas",
        "ai_narrative_text": "测试叙事，强调强势对线与目标掌控。",
        "llm_sentiment_tag": "激动",
        "v1_score_summary": v1_summary,
        "champion_assets_url": "https://example.com/sylas.png",
        "processing_duration_ms": 1380.0,
        "algorithm_version": "v1",
    }


def test_personal_view_uses_unified_fields():
    embed = render_analysis_embed(_sample_analysis_data())

    assert isinstance(embed, discord.Embed)
    field_names = [field.name for field in embed.fields]
    assert field_names.count("⚡ 核心优势") == 1
    assert field_names.count("⚠️ 重点补强") == 1
    assert field_names.count("🕒 时间线增强") == 1
    assert field_names.count("🧠 个人快照") == 1

    strengths = next(field.value for field in embed.fields if field.name == "⚡ 核心优势")
    assert "[" in strengths
    assert "]" in strengths
    assert "█" in strengths or "▒" in strengths

    weaknesses = next(field.value for field in embed.fields if field.name == "⚠️ 重点补强")
    assert "Vision" in weaknesses or "视野" in weaknesses

    timeline = next(field.value for field in embed.fields if field.name == "🕒 时间线增强")
    assert "GoldΔ10 +450" in timeline
    assert "XPΔ10 +220" in timeline
    assert "转化率 15%" in timeline
    assert "插眼/分 1.40" in timeline

    snapshot = next(field.value for field in embed.fields if field.name == "🧠 个人快照")
    assert snapshot.startswith("```")
    assert "K/D/A" in snapshot
    assert "控制" in snapshot
    assert "7.1min" in snapshot
    assert "180 pts" in snapshot

    footer = embed.footer.text or ""
    assert "session321:branchZ" in footer
    assert "Φfetch=210ms" in footer
    assert "Φscore=146ms" in footer
    assert "Φllm=513ms" in footer
    assert "Φtotal=1190ms" in footer
