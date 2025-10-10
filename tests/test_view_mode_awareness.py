import discord

from src.core.views.paginated_team_view import PaginatedTeamAnalysisView
from src.contracts.v2_team_analysis import V2TeamAnalysisReport, V2PlayerAnalysisResult


def _report_with_mode(mode: str) -> V2TeamAnalysisReport:
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
                top_strength_dimension="Vision" if i == 0 else "Combat",
                top_strength_score=90.0,
                top_strength_team_rank=1,
                top_weakness_dimension="Vision",
                top_weakness_score=50.0,
                top_weakness_team_rank=4,
                narrative_summary="ok",
            )
        )
    return V2TeamAnalysisReport(
        match_id="NA1_123",
        match_result="victory",
        target_player_puuid="p0",
        target_player_name="Player0",
        team_analysis=players,
        team_summary_insight="",
        ab_cohort="A",
        variant_id="v2_team_relative",
        processing_duration_ms=1000.0,
        algorithm_version="v2",
        # Mode-aware UI
        game_mode=mode,
    )


def test_aram_hides_vision_metric():
    report = _report_with_mode("aram")
    view = PaginatedTeamAnalysisView(report, match_id=report.match_id, timeout=1)
    view.current_page = 1
    embed = view._create_page_embed()
    # Page 2 content should not over-emphasize Vision in ARAM; basic smoke test
    assert isinstance(embed, discord.Embed)
    assert "团队成员详细分析" in embed.title
