import json
import pytest

from pydantic import ValidationError

from src.core.validation.json_validation import validate_v2_team_json


def test_v2_json_validation_failure_missing_fields():
    bad_json = json.dumps(
        {
            "match_id": "NA1_123",
            # missing required fields like team_analysis, target_player_name, etc.
        }
    )
    with pytest.raises(ValidationError):
        validate_v2_team_json(bad_json)


def test_v2_json_validation_failure_wrong_types():
    # team_analysis present but with wrong types
    bad_json = json.dumps(
        {
            "match_id": "NA1_123",
            "match_result": "victory",
            "target_player_puuid": "x",
            "target_player_name": "y",
            "team_analysis": [
                {
                    "puuid": "p",
                    "summoner_name": "s",
                    "champion_name": "c",
                    "champion_icon_url": "http://...",
                    "overall_score": "ninety",  # should be number
                    "team_rank": 1,
                    "top_strength_dimension": "Combat",
                    "top_strength_score": 90.0,
                    "top_strength_team_rank": 1,
                    "top_weakness_dimension": "Vision",
                    "top_weakness_score": 50.0,
                    "top_weakness_team_rank": 4,
                    "narrative_summary": "ok",
                }
            ],
        }
    )
    with pytest.raises(ValidationError):
        validate_v2_team_json(bad_json)
