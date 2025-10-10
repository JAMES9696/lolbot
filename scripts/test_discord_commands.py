#!/usr/bin/env python3
"""Test Discord commands (/analyze, /team-analyze) execution flow.

This script simulates Discord command execution to verify:
1. Command handler logic
2. Data flow and transformations
3. Embed rendering
4. Error handling

Usage:
    # Test /analyze command with mock data
    python scripts/test_discord_commands.py --command analyze --mock

    # Test /team-analyze command with real match
    python scripts/test_discord_commands.py --command team-analyze --match-id NA1_4830294840

    # Test with summoner lookup
    python scripts/test_discord_commands.py --command analyze --summoner "PlayerName#NA1"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_section(title: str, char: str = "=") -> None:
    """Print formatted section header."""
    print(f"\n{char * 70}")
    print(f"{title}")
    print(f"{char * 70}\n")


async def test_analyze_command(match_id: str | None = None, summoner: str | None = None) -> None:
    """Test /analyze command flow."""
    from src.adapters.database import DatabaseAdapter
    from src.adapters.riot_api import RiotAPIAdapter
    from src.core.views.analysis_view import render_analysis_embed
    from src.core.validation import validate_embed_strict, validate_analysis_data

    print_section("🔍 TESTING /analyze COMMAND")

    # Initialize adapters
    db = DatabaseAdapter()
    await db.connect()
    riot_api = RiotAPIAdapter()

    # Get match ID
    if summoner:
        print(f"📊 Fetching recent matches for: {summoner}")
        if "#" in summoner:
            game_name, tag_line = summoner.split("#", 1)
        else:
            game_name, tag_line = summoner, "NA1"

        account = await riot_api.get_account_by_riot_id(game_name, tag_line)
        if not account:
            print(f"❌ Summoner not found: {summoner}")
            return

        puuid = account["puuid"]
        match_ids = await riot_api.get_match_history(puuid, count=5)
        if not match_ids:
            print("❌ No matches found")
            return

        match_id = match_ids[0]
        print(f"✅ Using most recent match: {match_id}")

    if not match_id:
        print("❌ No match ID provided")
        return

    print(f"\n📋 Match ID: {match_id}")

    # Simulate command execution
    try:
        print("\n🔄 Step 1: Fetching match data...")
        match_data = await riot_api.get_match_details(match_id, "americas")
        if not match_data:
            print("❌ Match data not found")
            return

        participants = match_data.get("info", {}).get("participants", [])
        print(f"✅ Match found: {len(participants)} participants")

        print("\n🔄 Step 2: Running analysis task...")
        # Note: This would normally be pushed to Celery queue
        # For testing, we can check if analysis already exists
        existing = await db.get_analysis_result(match_id)

        if existing:
            print("✅ Analysis found in database (cached)")

            # Validate cached data
            print("\n🔄 Step 3: Validating cached analysis data...")
            data_validation = validate_analysis_data(existing)

            if data_validation.is_valid:
                print("✅ Data validation: PASS")
            else:
                print("❌ Data validation: FAIL")
                for error in data_validation.errors:
                    print(f"   ERROR: {error}")

            # Render embed
            print("\n🔄 Step 4: Rendering Discord embed...")
            try:
                embed = render_analysis_embed(existing)
                embed_dict = embed.to_dict()

                print("✅ Embed rendered successfully")
                print(f"   Title: {embed_dict.get('title', 'N/A')[:60]}...")
                print(f"   Description length: {len(embed_dict.get('description', ''))} chars")
                print(f"   Fields: {len(embed_dict.get('fields', []))}")

                # Validate embed
                print("\n🔄 Step 5: Validating Discord embed...")
                embed_validation = validate_embed_strict(embed)

                if embed_validation.is_valid:
                    print("✅ Embed validation: PASS")
                    print(
                        f"   Total size: {embed_validation.total_chars}/6000 chars ({embed_validation.total_chars/60:.1f}%)"
                    )
                else:
                    print("❌ Embed validation: FAIL")
                    for error in embed_validation.errors:
                        print(f"   ERROR: {error}")

                if embed_validation.warnings:
                    print("⚠️  Warnings:")
                    for warning in embed_validation.warnings:
                        print(f"   {warning}")

                # Show preview
                print("\n📊 Preview:")
                print(f"   Summoner: {existing.get('summoner_name', 'N/A')}")
                print(f"   Champion: {existing.get('champion_name', 'N/A')}")
                print(f"   Result: {existing.get('match_result', 'N/A').upper()}")
                print(
                    f"   Overall Score: {existing.get('v1_score_summary', {}).get('overall_score', 'N/A')}"
                )

                # TTS info
                meta = existing.get("llm_metadata", {})
                if isinstance(meta, str):
                    import json as _json

                    try:
                        meta = _json.loads(meta)
                    except:
                        meta = {}

                if meta.get("tts_audio_url"):
                    print("   TTS: ✅ Available")
                else:
                    print("   TTS: ❌ Not generated yet")

            except Exception as e:
                print(f"❌ Embed rendering failed: {e}")
                import traceback

                traceback.print_exc()
        else:
            print("⚠️  No cached analysis found")
            print("   In production, this would trigger Celery task")
            print(f"   Task would be: analyze_match_task(match_id={match_id})")

    except Exception as e:
        print(f"❌ Command execution failed: {e}")
        import traceback

        traceback.print_exc()

    print_section("✅ /analyze COMMAND TEST COMPLETE")


async def test_team_analyze_command(
    match_id: str | None = None, summoner: str | None = None
) -> None:
    """Test /team-analyze command flow."""
    from src.adapters.database import DatabaseAdapter
    from src.adapters.riot_api import RiotAPIAdapter
    from src.core.views.team_analysis_view import render_team_overview_embed
    from src.core.validation import validate_embed_strict

    print_section("👥 TESTING /team-analyze COMMAND")

    # Initialize adapters
    db = DatabaseAdapter()
    await db.connect()
    riot_api = RiotAPIAdapter()

    # Get match ID (same logic as analyze)
    if summoner:
        print(f"📊 Fetching recent matches for: {summoner}")
        if "#" in summoner:
            game_name, tag_line = summoner.split("#", 1)
        else:
            game_name, tag_line = summoner, "NA1"

        account = await riot_api.get_account_by_riot_id(game_name, tag_line)
        if not account:
            print(f"❌ Summoner not found: {summoner}")
            return

        puuid = account["puuid"]
        match_ids = await riot_api.get_match_history(puuid, count=5)
        if not match_ids:
            print("❌ No matches found")
            return

        match_id = match_ids[0]
        print(f"✅ Using most recent match: {match_id}")

    if not match_id:
        print("❌ No match ID provided")
        return

    print(f"\n📋 Match ID: {match_id}")

    # Simulate command execution
    try:
        print("\n🔄 Step 1: Fetching match data...")
        match_data = await riot_api.get_match_details(match_id, "americas")
        if not match_data:
            print("❌ Match data not found")
            return

        participants = match_data.get("info", {}).get("participants", [])
        print(f"✅ Match found: {len(participants)} participants")

        print("\n🔄 Step 2: Checking for existing team analysis...")
        existing = await db.get_analysis_result(match_id)

        if existing:
            score_data = existing.get("score_data")
            if isinstance(score_data, str):
                import json as _json

                try:
                    score_data = _json.loads(score_data)
                except:
                    score_data = None

            has_team_data = bool(
                score_data
                and isinstance(score_data, dict)
                and ("team_summary" in score_data or "team_analysis" in score_data)
            )

            if has_team_data:
                print("✅ Team analysis found in database (cached)")

                print("\n🔄 Step 3: Rendering team overview embed...")
                try:
                    from src.contracts.team_analysis import TeamAnalysisReport

                    # Build TeamAnalysisReport from cached data
                    team_summary = score_data.get("team_summary", {})

                    # Extract necessary fields
                    team_report_data = {
                        "match_id": match_id,
                        "team_result": existing.get("match_result", "defeat"),
                        "team_region": "na1",  # Default
                        "game_mode": "summoners_rift",
                        "players": team_summary.get("players", []),
                        "aggregates": team_summary.get("aggregates", {}),
                        "summary_text": team_summary.get("team_tldr"),
                        "trace_task_id": existing.get("task_id"),
                    }

                    team_report = TeamAnalysisReport(**team_report_data)
                    embed = render_team_overview_embed(team_report)
                    embed_dict = embed.to_dict()

                    print("✅ Embed rendered successfully")
                    print(f"   Title: {embed_dict.get('title', 'N/A')[:60]}...")
                    print(f"   Description length: {len(embed_dict.get('description', ''))} chars")
                    print(f"   Fields: {len(embed_dict.get('fields', []))}")

                    # Validate embed
                    print("\n🔄 Step 4: Validating Discord embed...")
                    embed_validation = validate_embed_strict(embed)

                    if embed_validation.is_valid:
                        print("✅ Embed validation: PASS")
                        print(
                            f"   Total size: {embed_validation.total_chars}/6000 chars ({embed_validation.total_chars/60:.1f}%)"
                        )
                    else:
                        print("❌ Embed validation: FAIL")
                        for error in embed_validation.errors:
                            print(f"   ERROR: {error}")

                    if embed_validation.warnings:
                        print("⚠️  Warnings:")
                        for warning in embed_validation.warnings:
                            print(f"   {warning}")

                    # Show team summary
                    print("\n📊 Team Summary:")
                    print(f"   Result: {team_report.team_result.upper()}")
                    print(f"   Region: {team_report.team_region.upper()}")
                    print(f"   Players: {len(team_report.players)}")

                    if team_report.aggregates:
                        print("\n   Team Averages:")
                        print(f"      Combat: {team_report.aggregates.combat_avg:.1f}")
                        print(f"      Economy: {team_report.aggregates.economy_avg:.1f}")
                        print(f"      Vision: {team_report.aggregates.vision_avg:.1f}")
                        print(f"      Objective: {team_report.aggregates.objective_avg:.1f}")
                        print(f"      Teamplay: {team_report.aggregates.teamplay_avg:.1f}")
                        print(f"      Overall: {team_report.aggregates.overall_avg:.1f}")

                    if team_report.summary_text:
                        print(f"\n   TL;DR: {team_report.summary_text}")

                except Exception as e:
                    print(f"❌ Embed rendering failed: {e}")
                    import traceback

                    traceback.print_exc()
            else:
                print("⚠️  No team analysis data found (only V1 single-player data exists)")
                print("   In production, this would trigger Celery task")
                print(f"   Task would be: analyze_team_task(match_id={match_id})")
        else:
            print("⚠️  No analysis found")
            print("   In production, this would trigger Celery task")
            print(f"   Task would be: analyze_team_task(match_id={match_id})")

    except Exception as e:
        print(f"❌ Command execution failed: {e}")
        import traceback

        traceback.print_exc()

    print_section("✅ /team-analyze COMMAND TEST COMPLETE")


async def test_help_command() -> None:
    """Test /help command rendering."""
    print_section("📚 TESTING /help COMMAND")

    from src.config.settings import get_settings

    settings = get_settings()

    print("Available Commands:")
    print("  /bind - 绑定您的 Riot 账户")
    print("  /unbind - 解除账户绑定")
    print("  /profile - 查看已绑定的账户信息")
    print("  /analyze [match_index] [riot_id] - 个人分析")
    print("  /team-analyze [match_index] [riot_id] - 团队分析")
    print("  /settings - 配置个性化偏好")
    print("  /help - 显示帮助信息")

    print("\nEnabled Features:")
    if settings.feature_voice_enabled:
        print("  ✅ Voice/TTS播报")
    if settings.feature_team_analysis_enabled:
        print("  ✅ 团队分析")
    if settings.feature_ai_analysis_enabled:
        print("  ✅ AI深度分析")
    if settings.feature_v21_prescriptive_enabled:
        print("  ✅ 时间轴证据分析")
    if settings.feature_v22_personalization_enabled:
        print("  ✅ 个性化分析")

    print(f"\nEnvironment: {settings.app_env}")
    print(f"Version: {settings.app_version}")

    print_section("✅ /help COMMAND TEST COMPLETE")


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Test Discord command execution flow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--command",
        choices=["analyze", "team-analyze", "help", "all"],
        default="all",
        help="Command to test",
    )
    parser.add_argument(
        "--match-id",
        help="Match ID to test with",
    )
    parser.add_argument(
        "--summoner",
        help="Summoner name (format: Name#TAG) to fetch recent match",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock data (not implemented yet)",
    )

    args = parser.parse_args()

    if args.command == "analyze" or args.command == "all":
        asyncio.run(test_analyze_command(args.match_id, args.summoner))

    if args.command == "team-analyze" or args.command == "all":
        asyncio.run(test_team_analyze_command(args.match_id, args.summoner))

    if args.command == "help" or args.command == "all":
        asyncio.run(test_help_command())

    return 0


if __name__ == "__main__":
    sys.exit(main())
