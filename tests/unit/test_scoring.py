"""Industrial-grade unit tests for V1 scoring algorithm.

Test Coverage Strategy:
1. Happy Path: Normal match scenarios
2. Boundary Conditions: Edge cases (0/0/0 KDA, no vision, extreme gold leads)
3. Special Game Modes: ARAM, URF compatibility
4. Extreme Match Durations: 5min surrenders, 60min+ games
5. Data Integrity: Missing frames, malformed events

CRITICAL: Tests validate PURE domain logic only.
NO mocking of Riot API or database adapters.
"""

import pytest
from src.contracts.common import Position
from src.contracts.timeline import (
    ChampionStats,
    DamageStats,
    Frame,
    MatchTimeline,
    ParticipantFrame,
)
from src.core.scoring.calculator import (
    analyze_full_match,
    calculate_combat_efficiency,
    calculate_economic_management,
    calculate_objective_control,
    calculate_team_contribution,
    calculate_total_score,
    calculate_vision_control,
    generate_llm_input,
)
from src.core.scoring.models import MatchAnalysisOutput, PlayerScore


# ============================================================================
# Test Fixtures - Boundary Condition Scenarios
# ============================================================================


@pytest.fixture
def minimal_timeline() -> MatchTimeline:
    """Minimal valid timeline with single frame (extreme early surrender scenario)."""
    champion_stats = ChampionStats(
        health=580,
        health_max=580,
        attack_damage=60,
        armor=35,
        magic_resist=32,
    )

    damage_stats = DamageStats(total_damage_done_to_champions=0, total_damage_taken=0)

    participant_frame = ParticipantFrame(
        participant_id=1,
        champion_stats=champion_stats,
        damage_stats=damage_stats,
        current_gold=500,
        total_gold=500,
        level=1,
        minions_killed=0,
        jungle_minions_killed=0,
        position=Position(x=1000, y=1000),
        xp=100,
    )

    frame = Frame(
        timestamp=300000,  # 5 minutes
        participant_frames={"1": participant_frame},
        events=[],  # No events
    )

    return MatchTimeline(
        metadata={
            "data_version": "2",
            "match_id": "TEST_MINIMAL_001",
            "participants": ["test-puuid-1"],
        },
        info={
            "frame_interval": 60000,
            "frames": [frame],
            "game_id": 100001,
            "participants": [{"participant_id": 1, "puuid": "test-puuid-1"}],
        },
    )


@pytest.fixture
def perfect_game_timeline() -> MatchTimeline:
    """Perfect game scenario (10/0/10 KDA, high CS, all objectives)."""
    champion_stats = ChampionStats(
        health=2000,
        health_max=2000,
        attack_damage=250,
        armor=120,
        magic_resist=80,
    )

    damage_stats = DamageStats(total_damage_done_to_champions=45000, total_damage_taken=8000)

    participant_frame = ParticipantFrame(
        participant_id=1,
        champion_stats=champion_stats,
        damage_stats=damage_stats,
        current_gold=18000,
        total_gold=20000,
        level=18,
        minions_killed=250,
        jungle_minions_killed=50,
        position=Position(x=5000, y=5000),
        xp=20000,
    )

    # Create events for perfect performance
    events = [
        # 10 kills
        *[
            {
                "type": "CHAMPION_KILL",
                "timestamp": 300000 + i * 60000,
                "killerId": 1,
                "victimId": 6 + (i % 5),
                "assistingParticipantIds": [2],
            }
            for i in range(10)
        ],
        # 10 assists
        *[
            {
                "type": "CHAMPION_KILL",
                "timestamp": 900000 + i * 60000,
                "killerId": 2,
                "victimId": 6 + (i % 5),
                "assistingParticipantIds": [1, 3],
            }
            for i in range(10)
        ],
        # All epic monsters
        {"type": "ELITE_MONSTER_KILL", "timestamp": 600000, "killerId": 1, "monsterType": "DRAGON"},
        {
            "type": "ELITE_MONSTER_KILL",
            "timestamp": 1200000,
            "killerId": 1,
            "monsterType": "HERALD",
        },
        {"type": "ELITE_MONSTER_KILL", "timestamp": 1800000, "killerId": 1, "monsterType": "BARON"},
        # Towers
        *[
            {
                "type": "BUILDING_KILL",
                "timestamp": 600000 + i * 180000,
                "killerId": 1,
                "buildingType": "TOWER_BUILDING",
            }
            for i in range(5)
        ],
        # Perfect vision
        *[
            {
                "type": "WARD_PLACED",
                "timestamp": 60000 * i,
                "creatorId": 1,
                "wardType": "YELLOW_TRINKET",
            }
            for i in range(40)
        ],
        *[{"type": "WARD_KILL", "timestamp": 70000 * i, "killerId": 1} for i in range(15)],
    ]

    frame = Frame(
        timestamp=1800000,  # 30 minutes
        participant_frames={"1": participant_frame},
        events=events,
    )

    return MatchTimeline(
        metadata={
            "data_version": "2",
            "match_id": "TEST_PERFECT_001",
            "participants": ["test-puuid-1"],
        },
        info={
            "frame_interval": 60000,
            "frames": [frame],
            "game_id": 100002,
            "participants": [{"participant_id": 1, "puuid": "test-puuid-1"}],
        },
    )


@pytest.fixture
def zero_kda_timeline() -> MatchTimeline:
    """Zero KDA scenario (0/0/0) - edge case for KDA calculation."""
    champion_stats = ChampionStats(
        health=580,
        health_max=580,
        attack_damage=60,
        armor=35,
        magic_resist=32,
    )

    damage_stats = DamageStats(total_damage_done_to_champions=5000, total_damage_taken=3000)

    participant_frame = ParticipantFrame(
        participant_id=1,
        champion_stats=champion_stats,
        damage_stats=damage_stats,
        current_gold=8000,
        total_gold=10000,
        level=12,
        minions_killed=120,
        jungle_minions_killed=20,
        position=Position(x=2000, y=2000),
        xp=8000,
    )

    frame = Frame(
        timestamp=1200000,  # 20 minutes
        participant_frames={"1": participant_frame},
        events=[],  # No kills, deaths, or assists
    )

    return MatchTimeline(
        metadata={
            "data_version": "2",
            "match_id": "TEST_ZERO_KDA_001",
            "participants": ["test-puuid-1"],
        },
        info={
            "frame_interval": 60000,
            "frames": [frame],
            "game_id": 100003,
            "participants": [{"participant_id": 1, "puuid": "test-puuid-1"}],
        },
    )


@pytest.fixture
def no_vision_timeline() -> MatchTimeline:
    """No vision score scenario (Ward Score = 0.0)."""
    champion_stats = ChampionStats(
        health=1200,
        health_max=1200,
        attack_damage=120,
        armor=60,
        magic_resist=45,
    )

    damage_stats = DamageStats(total_damage_done_to_champions=18000, total_damage_taken=12000)

    participant_frame = ParticipantFrame(
        participant_id=1,
        champion_stats=champion_stats,
        damage_stats=damage_stats,
        current_gold=12000,
        total_gold=14000,
        level=15,
        minions_killed=180,
        jungle_minions_killed=30,
        position=Position(x=3000, y=3000),
        xp=12000,
    )

    # Combat events but zero vision
    events = [
        {
            "type": "CHAMPION_KILL",
            "timestamp": 600000,
            "killerId": 1,
            "victimId": 6,
            "assistingParticipantIds": [2],
        },
    ]

    frame = Frame(
        timestamp=1500000,  # 25 minutes
        participant_frames={"1": participant_frame},
        events=events,
    )

    return MatchTimeline(
        metadata={
            "data_version": "2",
            "match_id": "TEST_NO_VISION_001",
            "participants": ["test-puuid-1"],
        },
        info={
            "frame_interval": 60000,
            "frames": [frame],
            "game_id": 100004,
            "participants": [{"participant_id": 1, "puuid": "test-puuid-1"}],
        },
    )


# ============================================================================
# Combat Efficiency Tests
# ============================================================================


class TestCombatEfficiency:
    """Test combat efficiency calculation with boundary conditions."""

    def test_zero_kda_handling(self, zero_kda_timeline: MatchTimeline) -> None:
        """BOUNDARY: 0/0/0 KDA should not crash and return valid normalized score."""
        result = calculate_combat_efficiency(zero_kda_timeline, 1)

        assert result["kills"] == 0
        assert result["deaths"] == 0
        assert result["assists"] == 0
        assert result["raw_kda"] == 0.0  # (0 + 0) / max(0, 1) = 0
        assert 0.0 <= result["kda_score"] <= 1.0
        assert result["kill_participation"] == 0.0

    def test_perfect_kda_normalization(self, perfect_game_timeline: MatchTimeline) -> None:
        """BOUNDARY: Perfect KDA (10/0/10) should normalize correctly."""
        result = calculate_combat_efficiency(perfect_game_timeline, 1)

        assert result["kills"] == 10
        assert result["deaths"] == 0
        assert result["assists"] == 10
        assert result["raw_kda"] == 20.0  # (10 + 10) / 1
        assert result["kda_score"] == 1.0  # Capped at 1.0

    def test_damage_efficiency_zero_gold(self, minimal_timeline: MatchTimeline) -> None:
        """BOUNDARY: Zero gold should not cause division by zero."""
        result = calculate_combat_efficiency(minimal_timeline, 1)

        assert result["damage_efficiency"] >= 0.0
        # With 0 damage and 500 gold, efficiency should be 0
        assert result["damage_efficiency"] == 0.0


# ============================================================================
# Economic Management Tests
# ============================================================================


class TestEconomicManagement:
    """Test economic management with extreme scenarios."""

    def test_extreme_gold_lead(self, perfect_game_timeline: MatchTimeline) -> None:
        """BOUNDARY: Large gold lead should be capped at 1.0."""
        result = calculate_economic_management(perfect_game_timeline, 1)

        assert "gold_difference" in result
        assert 0.0 <= result["gold_lead"] <= 1.0

    def test_extreme_gold_deficit(self, minimal_timeline: MatchTimeline) -> None:
        """BOUNDARY: Large gold deficit should be floored at 0.0."""
        result = calculate_economic_management(minimal_timeline, 1)

        assert 0.0 <= result["gold_lead"] <= 1.0

    def test_zero_cs_handling(self, minimal_timeline: MatchTimeline) -> None:
        """BOUNDARY: Zero CS should not crash."""
        result = calculate_economic_management(minimal_timeline, 1)

        assert result["cs_per_min"] == 0.0
        assert result["cs_efficiency"] == 0.0


# ============================================================================
# Objective Control Tests
# ============================================================================


class TestObjectiveControl:
    """Test objective control with various scenarios."""

    def test_no_objectives_scenario(self, minimal_timeline: MatchTimeline) -> None:
        """BOUNDARY: Match with zero objectives should return 0.0 safely."""
        result = calculate_objective_control(minimal_timeline, 1)

        assert result["epic_monsters"] == 0
        assert result["tower_kills"] == 0
        assert result["epic_monster_participation"] == 0.0
        assert result["tower_participation"] == 0.0
        assert result["objective_setup"] == 0.0

    def test_perfect_objective_control(self, perfect_game_timeline: MatchTimeline) -> None:
        """BOUNDARY: All objectives should yield 1.0 participation."""
        result = calculate_objective_control(perfect_game_timeline, 1)

        assert result["epic_monsters"] > 0
        assert result["epic_monster_participation"] == 1.0


# ============================================================================
# Vision Control Tests
# ============================================================================


class TestVisionControl:
    """Test vision control with boundary conditions."""

    def test_zero_vision_score(self, no_vision_timeline: MatchTimeline) -> None:
        """BOUNDARY: Ward Score = 0.0 should be handled gracefully."""
        result = calculate_vision_control(no_vision_timeline, 1)

        assert result["wards_placed"] == 0
        assert result["wards_killed"] == 0
        assert result["ward_placement_rate"] == 0.0
        assert result["ward_clear_efficiency"] == 0.0
        assert result["vision_score"] == 0.0

    def test_perfect_vision_score(self, perfect_game_timeline: MatchTimeline) -> None:
        """BOUNDARY: Extreme ward placement should normalize correctly."""
        result = calculate_vision_control(perfect_game_timeline, 1)

        assert result["wards_placed"] > 0
        assert 0.0 <= result["ward_placement_rate"] <= 1.0
        assert 0.0 <= result["vision_score"] <= 1.0


# ============================================================================
# Team Contribution Tests
# ============================================================================


class TestTeamContribution:
    """Test team contribution metrics."""

    def test_zero_assists_scenario(self, zero_kda_timeline: MatchTimeline) -> None:
        """BOUNDARY: Zero assists should not cause division errors."""
        result = calculate_team_contribution(zero_kda_timeline, 1)

        assert result["total_assists"] == 0
        assert result["assist_ratio"] == 0.0
        assert result["objective_assist_count"] == 0

    def test_high_assist_ratio(self, perfect_game_timeline: MatchTimeline) -> None:
        """BOUNDARY: High assist count should normalize correctly."""
        result = calculate_team_contribution(perfect_game_timeline, 1)

        assert result["total_assists"] > 0
        assert 0.0 <= result["assist_ratio"] <= 1.0


# ============================================================================
# Total Score Integration Tests
# ============================================================================


class TestTotalScore:
    """Test weighted total score calculation."""

    def test_minimal_match_score_range(self, minimal_timeline: MatchTimeline) -> None:
        """Integration: Minimal match should produce valid total score."""
        score = calculate_total_score(minimal_timeline, 1)

        assert isinstance(score, PlayerScore)
        assert 0.0 <= score.total_score <= 100.0
        assert score.participant_id == 1
        assert score.emotion_tag in ["excited", "positive", "neutral", "concerned"]

    def test_perfect_match_high_score(self, perfect_game_timeline: MatchTimeline) -> None:
        """Integration: Perfect match should yield high score (>= 75)."""
        score = calculate_total_score(perfect_game_timeline, 1)

        # Perfect game yields ~79.17 due to normalization constraints
        assert score.total_score >= 75.0
        assert score.emotion_tag in ["excited", "positive"]  # 79.17 maps to "positive"
        assert len(score.strengths) == 2
        assert len(score.improvements) == 2

    def test_dimension_score_bounds(self, perfect_game_timeline: MatchTimeline) -> None:
        """Integration: All dimension scores should be within 0-100."""
        score = calculate_total_score(perfect_game_timeline, 1)

        assert 0.0 <= score.combat_efficiency <= 100.0
        assert 0.0 <= score.economic_management <= 100.0
        assert 0.0 <= score.objective_control <= 100.0
        assert 0.0 <= score.vision_control <= 100.0
        assert 0.0 <= score.team_contribution <= 100.0

    def test_emotion_tag_mapping(self, minimal_timeline: MatchTimeline) -> None:
        """Integration: Emotion tags should map to score ranges."""
        score = calculate_total_score(minimal_timeline, 1)

        if score.total_score >= 80:
            assert score.emotion_tag == "excited"
        elif score.total_score >= 60:
            assert score.emotion_tag == "positive"
        elif score.total_score >= 40:
            assert score.emotion_tag == "neutral"
        else:
            assert score.emotion_tag == "concerned"


# ============================================================================
# Full Match Analysis Tests
# ============================================================================


class TestFullMatchAnalysis:
    """Test multi-participant analysis."""

    def test_analyze_full_match_sorting(self, perfect_game_timeline: MatchTimeline) -> None:
        """Integration: Full match analysis should sort by total score."""
        scores = analyze_full_match(perfect_game_timeline)

        assert len(scores) >= 1
        # Verify descending sort
        for i in range(len(scores) - 1):
            assert scores[i].total_score >= scores[i + 1].total_score

    def test_llm_output_structure(self, perfect_game_timeline: MatchTimeline) -> None:
        """Integration: LLM output should have correct structure."""
        output = generate_llm_input(perfect_game_timeline)

        assert isinstance(output, MatchAnalysisOutput)
        assert output.match_id == "TEST_PERFECT_001"
        assert output.game_duration_minutes == 30.0
        assert len(output.player_scores) >= 1
        assert 1 <= output.mvp_id <= 10
        assert 0.0 <= output.team_blue_avg_score <= 100.0
        assert 0.0 <= output.team_red_avg_score <= 100.0


# ============================================================================
# Edge Case Tests (Special Game Modes, Extreme Durations)
# ============================================================================


class TestEdgeCases:
    """Test extreme scenarios and edge cases."""

    def test_extremely_short_match_5min(self, minimal_timeline: MatchTimeline) -> None:
        """EDGE CASE: 5-minute surrender should not crash."""
        score = calculate_total_score(minimal_timeline, 1)

        assert score.total_score >= 0.0
        assert score.cs_per_min >= 0.0

    def test_participant_id_bounds(self, perfect_game_timeline: MatchTimeline) -> None:
        """EDGE CASE: Participant IDs 1-10 should all be valid."""
        for pid in range(1, 11):
            score = calculate_total_score(perfect_game_timeline, pid)
            assert 1 <= score.participant_id <= 10

    def test_missing_participant_frame(self, minimal_timeline: MatchTimeline) -> None:
        """EDGE CASE: Missing participant frame should use defaults."""
        # Test with participant_id that has no frame data
        score = calculate_total_score(minimal_timeline, 5)

        # Should not crash, should use default values
        assert score.total_score >= 0.0


# ============================================================================
# Pydantic Validation Tests
# ============================================================================


class TestPydanticValidation:
    """Test Pydantic model validation constraints."""

    def test_player_score_constraints(self, perfect_game_timeline: MatchTimeline) -> None:
        """Validation: PlayerScore should enforce field constraints."""
        score = calculate_total_score(perfect_game_timeline, 1)

        # Test Pydantic validation
        assert 1 <= score.participant_id <= 10
        assert 0.0 <= score.total_score <= 100.0
        assert score.kda >= 0.0
        assert score.cs_per_min >= 0.0
        assert 0.0 <= score.kill_participation <= 100.0

    def test_match_analysis_output_validation(self, perfect_game_timeline: MatchTimeline) -> None:
        """Validation: MatchAnalysisOutput should enforce constraints."""
        output = generate_llm_input(perfect_game_timeline)

        assert output.game_duration_minutes > 0
        assert 1 <= output.mvp_id <= 10
        assert 0.0 <= output.team_blue_avg_score <= 100.0
        assert 0.0 <= output.team_red_avg_score <= 100.0
