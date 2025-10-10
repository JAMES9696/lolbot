import discord
import pytest

from src.core.views.paginated_team_view import PaginatedTeamAnalysisView
from src.contracts.v2_team_analysis import (
    V2TeamAnalysisReport,
    V2PlayerAnalysisResult,
)


def _make_report() -> V2TeamAnalysisReport:
    players = []
    for i in range(5):
        players.append(
            V2PlayerAnalysisResult(
                puuid=f"p{i}",
                summoner_name=f"Player{i}",
                champion_name=f"Champ{i}",
                champion_icon_url="http://example.com/i.png",
                overall_score=70 + i,
                team_rank=i + 1,
                top_strength_dimension="Combat",
                top_strength_score=80 + i,
                top_strength_team_rank=1,
                top_weakness_dimension="Vision",
                top_weakness_score=50 - i,
                top_weakness_team_rank=4,
                narrative_summary="solid performance",
            )
        )
    return V2TeamAnalysisReport(
        match_id="NA1_123",
        match_result="victory",
        target_player_puuid="p0",
        target_player_name="Player0",
        team_analysis=players,
        team_summary_insight="团队经济领先但视野薄弱",
        ab_cohort="B",
        variant_id="v2_team_summary_20251006",
        processing_duration_ms=2300.0,
        algorithm_version="v2",
    )


@pytest.mark.asyncio
async def test_pagination_embeds_render():
    report = _make_report()
    view = PaginatedTeamAnalysisView(report, match_id=report.match_id, timeout=1)

    # Page 0 summary
    embed0 = view._create_page_embed()
    assert isinstance(embed0, discord.Embed)
    assert "团队分析总览" in embed0.title

    # Move to next page and render
    view.current_page = 1
    embed1 = view._create_page_embed()
    assert "团队成员详细分析" in embed1.title


@pytest.mark.asyncio
async def test_arena_view_adds_select_and_sections():
    report = _make_report()
    report.game_mode = "arena"
    report.arena_rounds_block = (
        "名次: 第2名  |  战绩: 6胜-2负\n"
        "高光回合:\n"
        "• R3: 5杀/0死, 伤害24000 承伤8000\n"
        "艰难回合: R7: 阵亡3次, 承伤18000\n"
        "连胜/连败: 最长连胜 3 局 (R1–R3)，最长连败 1 局 (R7–R7)\n"
        "轨迹: W2 L1 W1 L2\n"
    )

    view = PaginatedTeamAnalysisView(report, match_id=report.match_id, timeout=1)

    selects = [child for child in view.children if isinstance(child, discord.ui.Select)]
    assert selects, "Arena 视图应添加 Select 组件"

    default_option = next((opt for opt in selects[0].options if opt.default), None)
    assert default_option is not None
    assert default_option.value == "overview"

    view.current_page = 2
    arena_embed = view._create_page_embed()
    section_field = next(
        (f for f in arena_embed.fields if "战绩总结" in f.name or "Arena 摘要" in f.name),
        None,
    )
    assert section_field is not None, "Arena 页面应包含分段摘要字段"
    assert "名次" in section_field.value
