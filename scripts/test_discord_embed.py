#!/usr/bin/env python3
"""Test Discord embed validation before sending.

This script helps you validate analysis data and Discord embeds locally,
catching formatting errors before they reach Discord API.

Usage:
    # Test with a match ID from database
    python scripts/test_discord_embed.py --match-id NA1_4830294840

    # Test with a JSON file
    python scripts/test_discord_embed.py --json-file test_data.json

    # Quick test with mock data
    python scripts/test_discord_embed.py --mock

Example output:
    ✅ Validation passed!
    ✓ Valid: True
    📊 Total chars: 2847/6000

    ⚠️  Warnings:
      - Description near limit: 3900/4096 chars
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_match_id(match_id: str) -> bool:
    """Fetch analysis result from database and validate."""
    from src.adapters.database import DatabaseAdapter
    from src.core.validation import test_embed_rendering

    db = DatabaseAdapter()
    await db.init()

    # Fetch analysis result
    analysis_data = await db.get_analysis_result(match_id)
    if not analysis_data:
        print(f"❌ Match {match_id} not found in database")
        return False

    print(f"📊 Testing analysis for match: {match_id}\n")

    # Validate
    success, report = test_embed_rendering(analysis_data)
    print(report)

    return success


def test_json_file(json_path: str) -> bool:
    """Load JSON file and validate."""
    from src.core.validation import test_embed_rendering

    try:
        with open(json_path) as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load JSON: {e}")
        return False

    print(f"📊 Testing data from: {json_path}\n")

    success, report = test_embed_rendering(data)
    print(report)

    return success


def test_mock_data() -> bool:
    """Test with mock FinalAnalysisReport data."""
    from src.contracts.analysis_results import FinalAnalysisReport, V1ScoreSummary
    from src.core.validation import test_embed_rendering

    print("📊 Testing with mock data\n")

    # Create mock report
    mock_report = FinalAnalysisReport(
        match_id="NA1_MOCK_12345",
        match_result="victory",
        summoner_name="TestPlayer#NA1",
        champion_name="Yasuo",
        champion_id=157,
        ai_narrative_text=(
            "在这场比赛中表现出色！你的对线压制力很强，"
            "成功建立了经济优势。团战中的切入时机把握得当，"
            "有效地击杀了敌方后排。建议继续保持这种积极的打法。"
        ),
        llm_sentiment_tag="鼓励",
        v1_score_summary=V1ScoreSummary(
            combat_score=85.5,
            economy_score=78.2,
            vision_score=65.0,
            objective_score=72.3,
            teamplay_score=88.0,
            growth_score=70.0,
            tankiness_score=55.0,
            damage_composition_score=82.0,
            survivability_score=68.0,
            cc_contribution_score=75.0,
            overall_score=77.8,
            raw_stats={
                "kills": 12,
                "deaths": 3,
                "assists": 8,
                "kda": 6.67,
                "cs": 245,
                "cs_per_min": 8.2,
                "gold": 15420,
                "gold_diff": 2500,
                "damage_dealt": 32100,
                "damage_taken": 18500,
                "vision_score": 42,
                "wards_placed": 15,
                "wards_killed": 8,
                "cc_time": 12.5,
                "level": 18,
            },
        ),
        champion_assets_url="https://ddragon.leagueoflegends.com/cdn/14.1.1/img/champion/Yasuo.png",
        processing_duration_ms=1250.0,
        algorithm_version="v1",
    )

    success, report = test_embed_rendering(mock_report.model_dump())
    print(report)

    return success


def test_edge_cases() -> None:
    """Test known edge cases that might break Discord embeds."""
    from src.contracts.analysis_results import FinalAnalysisReport, V1ScoreSummary
    from src.core.validation import test_embed_rendering

    print("\n" + "=" * 60)
    print("🧪 Testing Edge Cases")
    print("=" * 60 + "\n")

    test_cases: list[tuple[str, dict[str, Any]]] = [
        (
            "Ultra-long narrative (should fail)",
            {
                "ai_narrative_text": "x" * 5000,  # Exceeds Pydantic max_length=1900
            },
        ),
        (
            "Invalid sentiment tag",
            {
                "llm_sentiment_tag": "invalid_tag",  # Not in allowed list
            },
        ),
        (
            "Negative scores",
            {
                "v1_score_summary": V1ScoreSummary(
                    combat_score=-10.0,  # Invalid
                    economy_score=50.0,
                    vision_score=50.0,
                    objective_score=50.0,
                    teamplay_score=50.0,
                    overall_score=50.0,
                ).model_dump(),
            },
        ),
    ]

    base_report = FinalAnalysisReport(
        match_id="NA1_EDGE_TEST",
        match_result="victory",
        summoner_name="EdgeTester#NA1",
        champion_name="TestChamp",
        champion_id=1,
        ai_narrative_text="Base narrative",
        llm_sentiment_tag="平淡",
        v1_score_summary=V1ScoreSummary(
            combat_score=50.0,
            economy_score=50.0,
            vision_score=50.0,
            objective_score=50.0,
            teamplay_score=50.0,
            overall_score=50.0,
        ),
        champion_assets_url="https://example.com/champ.png",
        processing_duration_ms=1000.0,
    )

    for test_name, overrides in test_cases:
        print(f"\n📝 Test: {test_name}")
        print("-" * 60)

        test_data = base_report.model_dump()
        test_data.update(overrides)

        try:
            success, report = test_embed_rendering(test_data)
            print(report)
        except Exception as e:
            print(f"❌ Exception raised: {e}")


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Test Discord embed validation locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--match-id",
        help="Test with match ID from database",
    )
    parser.add_argument(
        "--json-file",
        help="Test with JSON file containing FinalAnalysisReport data",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Test with mock data",
    )
    parser.add_argument(
        "--edge-cases",
        action="store_true",
        help="Run edge case tests",
    )

    args = parser.parse_args()

    if args.edge_cases:
        test_edge_cases()
        return 0

    success = False

    if args.match_id:
        success = asyncio.run(test_match_id(args.match_id))
    elif args.json_file:
        success = test_json_file(args.json_file)
    elif args.mock:
        success = test_mock_data()
    else:
        parser.print_help()
        return 1

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
