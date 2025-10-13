from src.contracts.team_analysis import (
    TeamAggregates,
    TeamAnalysisReport,
    TeamPlayerEntry,
)
from src.core.views.team_analysis_view import render_team_overview_embed


def _make_player(
    *,
    name: str,
    champion: str,
    role: str,
    overall: float,
    combat: float,
    economy: float,
    vision: float,
    objective: float,
    teamplay: float,
    rank: int,
    icon: str,
) -> TeamPlayerEntry:
    normalized = name.replace("#", "").replace(" ", "").lower()
    puuid = (normalized + "_puuid" + "0" * 40)[:40]
    return TeamPlayerEntry(
        puuid=puuid,
        summoner_name=name,
        champion_name=champion,
        role=role,
        combat_score=combat,
        economy_score=economy,
        vision_score=vision,
        objective_score=objective,
        teamplay_score=teamplay,
        overall_score=overall,
        team_rank=rank,
        champion_icon_url=icon,
    )


def _base_report(target_name: str = "BitAnnoying#NA1") -> TeamAnalysisReport:
    players = [
        _make_player(
            name="久未晴#sky",
            champion="Malphite",
            role="TOP",
            overall=52.9,
            combat=71.7,
            economy=65.4,
            vision=14.2,
            objective=12.5,
            teamplay=64.4,
            rank=2,
            icon="https://ddragon.leagueoflegends.com/cdn/13.24.1/img/champion/Malphite.png",
        ),
        _make_player(
            name=target_name,
            champion="Qiyana",
            role="JUNGLE",
            overall=64.7,
            combat=94.4,
            economy=87.9,
            vision=19.2,
            objective=62.5,
            teamplay=35.6,
            rank=1,
            icon="https://ddragon.leagueoflegends.com/cdn/13.24.1/img/champion/Qiyana.png",
        ),
        _make_player(
            name="Aurora#mid",
            champion="Aurora",
            role="MIDDLE",
            overall=50.7,
            combat=57.8,
            economy=83.4,
            vision=11.9,
            objective=12.5,
            teamplay=34.4,
            rank=3,
            icon="https://ddragon.leagueoflegends.com/cdn/13.24.1/img/champion/Aurora.png",
        ),
        _make_player(
            name="Samira#bot",
            champion="Samira",
            role="BOTTOM",
            overall=50.6,
            combat=63.6,
            economy=85.2,
            vision=14.6,
            objective=37.5,
            teamplay=45.3,
            rank=4,
            icon="https://ddragon.leagueoflegends.com/cdn/13.24.1/img/champion/Samira.png",
        ),
        _make_player(
            name="Rell#sup",
            champion="Rell",
            role="UTILITY",
            overall=50.9,
            combat=66.8,
            economy=49.8,
            vision=47.7,
            objective=12.5,
            teamplay=90.2,
            rank=5,
            icon="https://ddragon.leagueoflegends.com/cdn/13.24.1/img/champion/Rell.png",
        ),
    ]

    aggregates = TeamAggregates(
        combat_avg=70.9,
        economy_avg=74.4,
        vision_avg=21.6,
        objective_avg=27.5,
        teamplay_avg=54.0,
        overall_avg=54.0,
    )

    return TeamAnalysisReport(
        match_id="NA1_5389795464",
        team_result="defeat",
        team_region="na1",
        game_mode="summoners_rift",
        players=players,
        aggregates=aggregates,
        summary_text=(
            "AI数据裁判：你在打野节奏上领先全队，三次成功反蹲带动了上路优势；"
            "然而中后期视野布控不足，导致大龙区连续被断节奏。"
            "建议继续保持入侵节奏，同时请队友配合布控关键点位。"
        ),
        strengths=[
            TeamAnalysisReport.DimensionHighlight(
                dimension="combat_efficiency",
                label="战斗效率",
                score=94.4,
                delta_vs_team=+23.5,
            ),
            TeamAnalysisReport.DimensionHighlight(
                dimension="economic_management",
                label="经济管理",
                score=87.9,
                delta_vs_team=+13.5,
            ),
            TeamAnalysisReport.DimensionHighlight(
                dimension="objective_control",
                label="目标控制",
                score=62.5,
                delta_vs_team=+35.0,
            ),
        ],
        weaknesses=[
            TeamAnalysisReport.DimensionHighlight(
                dimension="vision_control",
                label="视野控制",
                score=19.2,
                delta_vs_team=-2.4,
            ),
            TeamAnalysisReport.DimensionHighlight(
                dimension="team_contribution",
                label="团队协同",
                score=35.6,
                delta_vs_team=-18.4,
            ),
            TeamAnalysisReport.DimensionHighlight(
                dimension="survivability",
                label="生存能力",
                score=41.0,
                delta_vs_team=-6.0,
            ),
        ],
        enhancements=TeamAnalysisReport.EnhancementMetrics(
            gold_diff_10=540,
            xp_diff_10=220,
            conversion_rate=0.24,
            ward_rate_per_min=0.9,
        ),
        observability=TeamAnalysisReport.ObservabilitySnapshot(
            session_id="session123",
            execution_branch_id="branchA",
            fetch_ms=320.0,
            scoring_ms=180.0,
            llm_ms=920.5,
            webhook_ms=145.0,
            overall_ms=1820.4,
        ),
        target_player_name=target_name,
        target_player_puuid=f"{target_name}-puuid",
    )


def test_thumbnail_uses_target_icon():
    report = _base_report()
    embed = render_team_overview_embed(report)

    assert embed.thumbnail.url.endswith("/Qiyana.png")


def test_description_clamped_to_discord_limit():
    report = _base_report()
    report.summary_text = "很长的叙事。" * 500

    embed = render_team_overview_embed(report)

    assert len(embed.description) <= 4096


def test_progress_fields_include_ascii_bars():
    report = _base_report()
    embed = render_team_overview_embed(report)

    assert embed.fields, "expected embed to contain fields"
    core_field = embed.fields[0]
    watch_field = embed.fields[1]

    assert "[" in core_field.value and "]" in core_field.value
    assert "▒" in watch_field.value or "█" in watch_field.value


def test_highlights_include_opponent_delta():
    report = _base_report()
    report.strengths = [
        TeamAnalysisReport.DimensionHighlight(
            dimension="combat_efficiency",
            label="战斗效率",
            score=88.8,
            delta_vs_team=12.3,
            delta_vs_opponent=4.5,
        )
    ]

    embed = render_team_overview_embed(report)
    core_field = next((f for f in embed.fields if "核心优势" in f.name), None)

    assert core_field is not None, "核心优势字段缺失"
    assert "vs 队均" in core_field.value
    assert "vs 对位" in core_field.value


def test_builds_field_uses_summary_text():
    report = _base_report()
    report.builds_summary_text = "出装: 破败王者之刃 · 无尽之刃\n符文: 精密 - 强攻 | 次系 主宰"

    embed = render_team_overview_embed(report)

    builds_field = next((f for f in embed.fields if "出装" in f.name), None)
    assert builds_field is not None, "应渲染出装/符文字段"
    assert "破败王者之刃" in builds_field.value
    assert "强攻" in builds_field.value


def test_builds_field_falls_back_to_metadata():
    report = _base_report()
    report.builds_summary_text = None
    report.builds_metadata = {
        "items": ["破败王者之刃", "狂战士胫甲", "无尽之刃"],
        "primary_tree_name": "精密",
        "primary_keystone": "强攻",
        "secondary_tree_name": "主宰",
        "opgg_available": True,
    }

    embed = render_team_overview_embed(report)

    builds_field = next((f for f in embed.fields if "出装" in f.name), None)
    assert builds_field is not None
    assert "狂战士胫甲" in builds_field.value
    assert "精密" in builds_field.value
