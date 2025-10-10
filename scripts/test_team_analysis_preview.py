#!/usr/bin/env python3
"""Test team analysis and preview all outputs BEFORE sending to Discord.

This script runs a complete team analysis workflow and shows you:
1. Raw analysis data (JSON)
2. Rendered Discord embed (dict)
3. TTS audio URL (if enabled)
4. Validation results
5. Final webhook payload

Usage:
    # Test with a recent match ID
    python scripts/test_team_analysis_preview.py --match-id NA1_4830294840

    # Test with mock data
    python scripts/test_team_analysis_preview.py --mock

    # Test with specific summoner
    python scripts/test_team_analysis_preview.py --summoner "PlayerName#NA1"

    # Save output to file
    python scripts/test_team_analysis_preview.py --match-id NA1_123 --output result.json
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


async def test_team_analysis_with_match_id(
    match_id: str, output_file: str | None = None
) -> dict[str, Any]:
    """Test team analysis with a specific match ID."""
    from src.adapters.database import DatabaseAdapter
    from src.adapters.riot_api import RiotAPIAdapter
    from src.tasks.team_tasks import analyze_team_task
    from src.core.views.team_analysis_view import render_team_overview_embed
    from src.core.validation import validate_embed_strict

    print(f"🔍 Fetching match data: {match_id}")

    # Initialize adapters
    db = DatabaseAdapter()
    await db.init()
    riot_api = RiotAPIAdapter()

    # Fetch match details
    match_details = await riot_api.get_match_by_id(match_id)
    if not match_details:
        print(f"❌ Match not found: {match_id}")
        return {}

    print(f"✅ Match found: {match_id}")
    print(f"   Game mode: {match_details.get('info', {}).get('gameMode')}")
    print(f"   Duration: {match_details.get('info', {}).get('gameDuration')}s")

    # Run team analysis task
    print("\n📊 Running team analysis task...")
    try:
        result = await analyze_team_task(match_id=match_id)

        print("\n✅ Team analysis completed!")
        print(f"   Task ID: {result.get('task_id')}")
        print(
            f"   Blue team score: {result.get('team_analysis', {}).get('team_100', {}).get('overall_score', 'N/A')}"
        )
        print(
            f"   Red team score: {result.get('team_analysis', {}).get('team_200', {}).get('overall_score', 'N/A')}"
        )

        # Render embed
        print("\n🎨 Rendering Discord embed...")
        embed = render_team_overview_embed(result)
        embed_dict = embed.to_dict()

        print("✅ Embed rendered!")
        print(f"   Title: {embed_dict.get('title', 'N/A')[:50]}...")
        print(f"   Description length: {len(embed_dict.get('description', ''))} chars")
        print(f"   Fields count: {len(embed_dict.get('fields', []))}")

        # Validate embed
        print("\n🔍 Validating embed...")
        validation = validate_embed_strict(embed)

        if validation.is_valid:
            print("✅ Validation passed!")
        else:
            print("❌ Validation failed!")
            for error in validation.errors:
                print(f"   ERROR: {error}")

        if validation.warnings:
            print("⚠️  Warnings:")
            for warning in validation.warnings:
                print(f"   {warning}")

        print(f"\n📊 Total embed size: {validation.total_chars}/6000 chars")

        # TTS preview (if enabled)
        tts_info = None
        try:
            from src.config.settings import get_settings

            settings = get_settings()

            if settings.feature_voice_enabled:
                print("\n🔊 TTS feature enabled - checking audio...")
                tldr = result.get("team_analysis", {}).get("team_tldr")
                if tldr:
                    print(f"   TL;DR text ({len(tldr)} chars): {tldr[:100]}...")
                    tts_info = {
                        "enabled": True,
                        "text": tldr,
                        "text_length": len(tldr),
                        "auto_playback": settings.feature_team_auto_tts_enabled,
                    }
                else:
                    print("   ⚠️  No TL;DR text found")
                    tts_info = {"enabled": True, "text": None}
            else:
                print("\n🔇 TTS feature disabled")
                tts_info = {"enabled": False}
        except Exception as e:
            print(f"⚠️  TTS check error: {e}")
            tts_info = {"enabled": False, "error": str(e)}

        # Build preview output
        preview = {
            "match_id": match_id,
            "task_id": result.get("task_id"),
            "team_analysis": result.get("team_analysis"),
            "embed": embed_dict,
            "validation": {
                "is_valid": validation.is_valid,
                "errors": validation.errors,
                "warnings": validation.warnings,
                "total_chars": validation.total_chars,
            },
            "tts": tts_info,
            "metadata": {
                "game_mode": match_details.get("info", {}).get("gameMode"),
                "game_duration": match_details.get("info", {}).get("gameDuration"),
                "participants_count": len(match_details.get("info", {}).get("participants", [])),
            },
        }

        # Save to file if requested
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(preview, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Output saved to: {output_file}")

        # Print summary
        print("\n" + "=" * 60)
        print("📋 PREVIEW SUMMARY")
        print("=" * 60)
        print(f"Match ID: {match_id}")
        print(f"Task ID: {result.get('task_id')}")
        print(f"Validation: {'✅ PASS' if validation.is_valid else '❌ FAIL'}")
        print(
            f"Embed size: {validation.total_chars}/6000 chars ({validation.total_chars/6000*100:.1f}%)"
        )
        print(f"TTS enabled: {'✅ Yes' if tts_info and tts_info.get('enabled') else '❌ No'}")

        if validation.errors:
            print(f"\n❌ ERRORS ({len(validation.errors)}):")
            for i, error in enumerate(validation.errors, 1):
                print(f"  {i}. {error}")

        if validation.warnings:
            print(f"\n⚠️  WARNINGS ({len(validation.warnings)}):")
            for i, warning in enumerate(validation.warnings, 1):
                print(f"  {i}. {warning}")

        print("=" * 60)

        return preview

    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback

        traceback.print_exc()
        return {"error": str(e)}


async def test_with_mock_data(output_file: str | None = None) -> dict[str, Any]:
    """Test with mock team analysis data."""
    print("🎭 Testing with mock data...")

    from src.core.views.team_analysis_view import render_team_overview_embed
    from src.core.validation import validate_embed_strict

    # Create mock team analysis result
    mock_result = {
        "task_id": "mock_task_12345678",
        "match_id": "NA1_MOCK_TEST",
        "team_analysis": {
            "match_result": "victory",
            "game_mode": "CLASSIC",
            "game_duration_minutes": 28.5,
            "team_100": {
                "team_id": 100,
                "win": True,
                "overall_score": 75.8,
                "combat_efficiency": 78.2,
                "economic_management": 72.5,
                "vision_control": 68.9,
                "objective_control": 81.3,
                "team_contribution": 76.4,
            },
            "team_200": {
                "team_id": 200,
                "win": False,
                "overall_score": 58.3,
                "combat_efficiency": 62.1,
                "economic_management": 55.7,
                "vision_control": 52.4,
                "objective_control": 48.9,
                "team_contribution": 61.2,
            },
            "team_tldr": "蓝色方在对线期建立了经济优势，通过有效的视野控制和团战配合，在28分钟取得胜利。红色方中期团战决策失误，导致大龙控制权丢失。",
            "processing_duration_ms": 2345.6,
        },
    }

    # Render embed
    print("\n🎨 Rendering embed from mock data...")
    embed = render_team_overview_embed(mock_result)
    embed_dict = embed.to_dict()

    # Validate
    print("\n🔍 Validating embed...")
    validation = validate_embed_strict(embed)

    preview = {
        "mock": True,
        "team_analysis": mock_result["team_analysis"],
        "embed": embed_dict,
        "validation": {
            "is_valid": validation.is_valid,
            "errors": validation.errors,
            "warnings": validation.warnings,
            "total_chars": validation.total_chars,
        },
    }

    # Save if requested
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(preview, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Mock output saved to: {output_file}")

    # Print summary
    print("\n" + "=" * 60)
    print("📋 MOCK DATA PREVIEW")
    print("=" * 60)
    print(f"Validation: {'✅ PASS' if validation.is_valid else '❌ FAIL'}")
    print(f"Embed size: {validation.total_chars}/6000 chars")
    print(f"Blue team score: {mock_result['team_analysis']['team_100']['overall_score']}")
    print(f"Red team score: {mock_result['team_analysis']['team_200']['overall_score']}")
    print("=" * 60)

    return preview


async def test_with_summoner(summoner_name: str, output_file: str | None = None) -> dict[str, Any]:
    """Test by fetching recent match for a summoner."""
    print(f"🔍 Fetching recent matches for: {summoner_name}")

    from src.adapters.riot_api import RiotAPIAdapter

    riot_api = RiotAPIAdapter()

    # Parse summoner name and tag
    if "#" in summoner_name:
        game_name, tag_line = summoner_name.split("#", 1)
    else:
        game_name = summoner_name
        tag_line = "NA1"

    # Get account by Riot ID
    account = await riot_api.get_account_by_riot_id(game_name, tag_line)
    if not account:
        print(f"❌ Account not found: {summoner_name}")
        return {}

    puuid = account.get("puuid")
    print(f"✅ Account found: {game_name}#{tag_line}")
    print(f"   PUUID: {puuid}")

    # Get recent matches
    match_ids = await riot_api.get_match_history(puuid, count=5)
    if not match_ids:
        print("❌ No recent matches found")
        return {}

    print(f"✅ Found {len(match_ids)} recent matches")
    print(f"   Most recent: {match_ids[0]}")

    # Test with most recent match
    return await test_team_analysis_with_match_id(match_ids[0], output_file)


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Preview team analysis output before sending to Discord",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--match-id",
        help="Test with specific match ID",
    )
    parser.add_argument(
        "--summoner",
        help="Test with recent match from summoner (format: Name#TAG)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Test with mock data",
    )
    parser.add_argument(
        "--output",
        help="Save output to JSON file",
    )

    args = parser.parse_args()

    if args.mock:
        result = asyncio.run(test_with_mock_data(args.output))
    elif args.match_id:
        result = asyncio.run(test_team_analysis_with_match_id(args.match_id, args.output))
    elif args.summoner:
        result = asyncio.run(test_with_summoner(args.summoner, args.output))
    else:
        parser.print_help()
        return 1

    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
