from src.contracts.v23_multi_mode_analysis import (
    V23ArenaAnalysisReport,
    V23ArenaRoundPerformance,
    V23ArenaAugmentAnalysis,
)


def test_arena_contract_allows_empty_summary_and_suggestions():
    round_perf = V23ArenaRoundPerformance(
        round_number=1,
        round_result="win",
        damage_dealt=1234,
        damage_taken=500,
        kills=2,
        deaths=0,
        positioning_score=75.0,
    )

    aug = V23ArenaAugmentAnalysis(
        augments_selected=[],
        augment_synergy_with_champion="",
        augment_synergy_with_partner="",
    )

    # Empty text fields should validate
    model = V23ArenaAnalysisReport(
        match_id="NA1_123",
        summoner_name="Tester",
        champion_name="Garen",
        partner_summoner_name=None,
        partner_champion_name=None,
        final_placement=4,
        overall_score=72.5,
        rounds_played=10,
        rounds_won=6,
        round_performances=[round_perf],
        augment_analysis=aug,
        combat_score=70.0,
        duo_synergy_score=80.0,
        analysis_summary="",  # relaxed
        improvement_suggestions=[],  # relaxed
    )

    assert model.analysis_summary == ""
    assert model.improvement_suggestions == []
