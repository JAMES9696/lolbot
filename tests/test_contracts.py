"""
Test file to validate our Pydantic V2 data contracts.
"""

from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from src.contracts import (
    ChampionKillEvent,
    EventType,
    LeagueEntry,
    MatchInfo,
    MatchTimeline,
    Participant,
    ParticipantFrame,
    Position,
    SummonerProfile,
    Tier,
)


def test_position_model() -> None:
    """Test Position model."""
    pos = Position(x=1000, y=2000)
    assert pos.x == 1000
    assert pos.y == 2000

    # Test immutability (frozen=True)
    with pytest.raises(ValidationError):
        pos.x = 3000  # type: ignore


def test_champion_kill_event() -> None:
    """Test ChampionKillEvent model."""
    event_data = {
        "timestamp": 120000,
        "type": EventType.CHAMPION_KILL.value,
        "killer_id": 1,
        "victim_id": 6,
        "position": {"x": 5000, "y": 5000},
        "assisting_participant_ids": [2, 3],
        "bounty": 300,
        "shutdown_bounty": 500,
        "kill_streak_length": 3,
    }

    event = ChampionKillEvent(**event_data)
    assert event.killer_id == 1
    assert event.victim_id == 6
    assert event.bounty == 300
    assert len(event.assisting_participant_ids) == 2
    assert event.position.x == 5000


def test_participant_frame() -> None:
    """Test ParticipantFrame model."""
    frame_data = {
        "participant_id": 1,
        "champion_stats": {
            "ability_haste": 10,
            "ability_power": 80,
            "armor": 50,
            "attack_damage": 100,
            "health": 1500,
            "health_max": 2000,
        },
        "damage_stats": {
            "total_damage_done": 5000,
            "total_damage_done_to_champions": 2000,
            "total_damage_taken": 3000,
        },
        "current_gold": 1500,
        "total_gold": 3000,
        "level": 6,
        "position": {"x": 3000, "y": 4000},
    }

    frame = ParticipantFrame(**frame_data)
    assert frame.participant_id == 1
    assert frame.level == 6
    assert frame.champion_stats.health == 1500
    assert frame.damage_stats.total_damage_done == 5000


def test_match_timeline() -> None:
    """Test MatchTimeline model."""
    timeline_data = {
        "metadata": {
            "data_version": "2",
            "match_id": "NA1_1234567890",
            "participants": ["puuid1", "puuid2"],
        },
        "info": {
            "frame_interval": 60000,
            "game_id": 1234567890,
            "participants": [
                {"participant_id": 1, "puuid": "puuid1"},
                {"participant_id": 2, "puuid": "puuid2"},
            ],
            "frames": [
                {
                    "timestamp": 0,
                    "participant_frames": {
                        "1": {
                            "participant_id": 1,
                            "champion_stats": {},
                            "damage_stats": {},
                            "current_gold": 500,
                            "total_gold": 500,
                            "level": 1,
                            "position": {"x": 1000, "y": 1000},
                        }
                    },
                    "events": [],
                }
            ],
        },
    }

    timeline = MatchTimeline(**timeline_data)
    assert timeline.metadata.match_id == "NA1_1234567890"
    assert len(timeline.info.participants) == 2
    assert timeline.get_participant_by_puuid("puuid1") == 1
    assert timeline.get_participant_by_puuid("unknown") is None


def test_match_timeline_metadata_fallback_for_participant_lookup() -> None:
    """即使 info.participants 缺失，也应通过 metadata 映射 participantId。"""
    timeline_data = {
        "metadata": {
            "data_version": "2",
            "match_id": "NA1_FALLBACK_321",
            "participants": ["pA", "pB", "pC"],
        },
        "info": {
            "frame_interval": 60000,
            "game_id": 987654321,
            "participants": [],
            "frames": [
                {
                    "timestamp": 0,
                    "participant_frames": {},
                    "events": [],
                }
            ],
        },
    }

    timeline = MatchTimeline(**timeline_data)
    assert timeline.get_participant_by_puuid("pB") == 2
    assert timeline.get_participant_by_puuid("missing") is None


def test_summoner_profile() -> None:
    """Test SummonerProfile model."""
    summoner_data = {
        "account_id": "encrypted_account_id",
        "profile_icon_id": 4567,
        "revision_date": 1704067200000,  # 2024-01-01 00:00:00 UTC
        "id": "encrypted_summoner_id",
        "puuid": "player_puuid",
        "summoner_level": 250,
        "name": "TestPlayer",
        "tag_line": "NA1",
    }

    summoner = SummonerProfile(**summoner_data)
    assert summoner.name == "TestPlayer"
    assert summoner.game_name == "TestPlayer#NA1"
    assert summoner.summoner_level == 250
    assert isinstance(summoner.last_modified, datetime)


def test_league_entry() -> None:
    """Test LeagueEntry model with win rate calculation."""
    entry_data = {
        "summoner_id": "encrypted_id",
        "summoner_name": "TestPlayer",
        "queue_type": "RANKED_SOLO_5x5",
        "tier": Tier.GOLD,
        "rank": "II",
        "league_points": 75,
        "wins": 120,
        "losses": 80,
        "hot_streak": True,
    }

    entry = LeagueEntry(**entry_data)
    assert entry.full_rank == "GOLD II"
    assert entry.win_rate == 60.0  # 120/(120+80) * 100
    assert entry.hot_streak is True


def test_participant_kda() -> None:
    """Test Participant KDA calculation."""
    participant_data = {
        "puuid": "test_puuid",
        "summoner_id": "test_id",
        "summoner_name": "TestPlayer",
        "participant_id": 1,
        "team_id": 100,
        "champion_id": 1,
        "champion_name": "Annie",
        "champion_level": 18,
        "summoner1_id": 4,
        "summoner2_id": 14,
        "kills": 10,
        "deaths": 2,
        "assists": 15,
        "gold_earned": 15000,
        "vision_score": 45,
    }

    participant = Participant(**participant_data)
    assert participant.kda == 12.5  # (10+15)/2
    assert participant.items == []  # No items set

    # Test with 0 deaths
    participant_data["deaths"] = 0
    participant_zero_deaths = Participant(**participant_data)
    assert participant_zero_deaths.kda == 25.0  # (10+15) with 0 deaths


def test_match_info_teams() -> None:
    """Test MatchInfo with teams."""
    match_data: dict[str, Any] = {
        "game_creation": 1704067200000,
        "game_duration": 1800,
        "game_id": 123456,
        "game_mode": "CLASSIC",
        "game_name": "Test Game",
        "game_start_timestamp": 1704067260000,
        "game_type": "MATCHED_GAME",
        "game_version": "14.1.1",
        "map_id": 11,
        "platform_id": "NA1",
        "queue_id": 420,
        "teams": [
            {
                "team_id": 100,
                "win": True,
                "baron_kills": 2,
                "champion_kills": 35,
                "dragon_kills": 3,
                "tower_kills": 8,
                "first_blood": True,
            },
            {
                "team_id": 200,
                "win": False,
                "baron_kills": 0,
                "champion_kills": 20,
                "dragon_kills": 1,
                "tower_kills": 3,
                "first_blood": False,
            },
        ],
        "participants": [
            {
                "puuid": f"puuid_{i}",
                "summoner_id": f"id_{i}",
                "summoner_name": f"Player{i}",
                "participant_id": i,
                "team_id": 100 if i <= 5 else 200,
                "champion_id": i,
                "champion_name": f"Champion{i}",
                "champion_level": 18,
                "summoner1_id": 4,
                "summoner2_id": 14,
            }
            for i in range(1, 11)
        ],
    }

    match_info = MatchInfo(**match_data)
    assert match_info.winning_team_id == 100
    assert len(match_info.get_team_participants(100)) == 5
    assert len(match_info.get_team_participants(200)) == 5
    assert match_info.teams[0].first_blood is True


def test_extra_fields_forbidden() -> None:
    """Test that extra fields are forbidden."""
    with pytest.raises(ValidationError) as exc_info:
        Position(x=100, y=200, z=300)  # type: ignore

    # Verify the error contains expected information
    assert "Extra inputs are not permitted" in str(exc_info.value)


def test_type_validation() -> None:
    """Test strict type validation."""
    # String instead of int
    with pytest.raises(ValidationError):
        Position(x="100", y=200)  # type: ignore

    # Out of range participant_id
    with pytest.raises(ValidationError):
        ParticipantFrame(
            participant_id=17,  # Max is 16 (supports Arena teams)
            champion_stats={},
            damage_stats={},
            position={"x": 0, "y": 0},
            level=1,
        )
