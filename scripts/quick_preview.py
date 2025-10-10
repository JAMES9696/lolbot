#!/usr/bin/env python3
"""Quick preview of Discord output (team analysis or single analysis).

Ultra-simple script to preview what will be sent to Discord.

Usage:
    # Preview with mock team data
    python scripts/quick_preview.py

    # Preview specific match
    python scripts/quick_preview.py NA1_4830294840

    # Preview and show raw JSON
    python scripts/quick_preview.py --json

    # Preview single-player analysis
    python scripts/quick_preview.py --single
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def print_section(title: str, symbol: str = "=") -> None:
    """Print a formatted section header."""
    print(f"\n{symbol * 60}")
    print(f"{title}")
    print(f"{symbol * 60}")


async def preview_team_analysis(match_id: str | None = None, show_json: bool = False) -> None:
    """Preview team analysis output."""
    from src.core.views.team_analysis_view import render_team_overview_embed
    from src.core.validation import validate_embed_strict
    from src.contracts.team_analysis import TeamAnalysisReport, TeamPlayerEntry, TeamAggregates

    # Mock data for quick testing
    if not match_id:
        print_section("🎭 MOCK TEAM ANALYSIS PREVIEW", "=")

        # Create mock TeamAnalysisReport using Pydantic models
        result = TeamAnalysisReport(
            match_id="NA1_MOCK_12345",
            team_result="victory",
            team_region="na1",
            game_mode="summoners_rift",
            players=[
                TeamPlayerEntry(
                    puuid="mock_puuid_" + "a" * 60,
                    summoner_name="TopLaner#NA1",
                    champion_name="Garen",
                    role="TOP",
                    combat_score=78.2,
                    economy_score=72.5,
                    vision_score=65.0,
                    objective_score=81.3,
                    teamplay_score=76.4,
                    overall_score=74.7,
                ),
                TeamPlayerEntry(
                    puuid="mock_puuid_" + "b" * 60,
                    summoner_name="Jungler#NA1",
                    champion_name="Lee Sin",
                    role="JUNGLE",
                    combat_score=82.1,
                    economy_score=68.9,
                    vision_score=71.2,
                    objective_score=85.5,
                    teamplay_score=79.3,
                    overall_score=77.4,
                ),
                TeamPlayerEntry(
                    puuid="mock_puuid_" + "c" * 60,
                    summoner_name="MidLaner#NA1",
                    champion_name="Yasuo",
                    role="MIDDLE",
                    combat_score=88.5,
                    economy_score=81.2,
                    vision_score=62.3,
                    objective_score=73.8,
                    teamplay_score=82.1,
                    overall_score=77.6,
                ),
                TeamPlayerEntry(
                    puuid="mock_puuid_" + "d" * 60,
                    summoner_name="ADC#NA1",
                    champion_name="Jinx",
                    role="BOTTOM",
                    combat_score=85.3,
                    economy_score=84.7,
                    vision_score=58.9,
                    objective_score=69.2,
                    teamplay_score=75.8,
                    overall_score=74.8,
                ),
                TeamPlayerEntry(
                    puuid="mock_puuid_" + "e" * 60,
                    summoner_name="Support#NA1",
                    champion_name="Thresh",
                    role="UTILITY",
                    combat_score=68.4,
                    economy_score=55.2,
                    vision_score=88.5,
                    objective_score=78.9,
                    teamplay_score=91.2,
                    overall_score=76.4,
                ),
            ],
            aggregates=TeamAggregates(
                combat_avg=80.5,
                economy_avg=72.5,
                vision_avg=69.2,
                objective_avg=77.7,
                teamplay_avg=80.96,
                overall_avg=76.18,
            ),
            summary_text="蓝色方通过优秀的团队配合和经济管理取得胜利。强项：团队协作 +10.96% | 弱项：视野控制需提升。",
            trace_task_id="mock_task_12345678",
        )
    else:
        print_section(f"🔍 REAL MATCH PREVIEW: {match_id}", "=")
        from src.tasks.team_tasks import analyze_team_task

        try:
            result = await analyze_team_task(match_id=match_id)
        except Exception as e:
            print(f"❌ Error fetching match: {e}")
            return

    # Render embed
    embed = render_team_overview_embed(result)
    embed_dict = embed.to_dict()

    # Validate
    validation = validate_embed_strict(embed)

    # Print results
    print_section("📊 ANALYSIS DATA", "-")

    print(f"Match: {result.match_id}")
    print(f"Result: {'✅ VICTORY' if result.team_result == 'victory' else '❌ DEFEAT'}")
    print(f"Region: {result.team_region.upper()}")
    print(f"Mode: {result.game_mode}")

    print("\n👥 Team Aggregates:")
    print(f"   Combat: {result.aggregates.combat_avg:.1f}")
    print(f"   Economy: {result.aggregates.economy_avg:.1f}")
    print(f"   Vision: {result.aggregates.vision_avg:.1f}")
    print(f"   Objective: {result.aggregates.objective_avg:.1f}")
    print(f"   Teamplay: {result.aggregates.teamplay_avg:.1f}")
    print(f"   Overall: {result.aggregates.overall_avg:.1f}")

    print(f"\n🎮 Players ({len(result.players)}):")
    for i, p in enumerate(result.players, 1):
        print(f"   {i}. {p.summoner_name} ({p.champion_name} - {p.role.upper()})")
        print(
            f"      Overall: {p.overall_score:.1f} | Combat: {p.combat_score:.1f} | Vision: {p.vision_score:.1f}"
        )

    print_section("🎨 DISCORD EMBED PREVIEW", "-")
    print(f"Title: {embed_dict.get('title', 'N/A')}")
    print(f"Description length: {len(embed_dict.get('description', ''))} chars")
    print(f"Fields: {len(embed_dict.get('fields', []))}")
    print(f"Footer: {embed_dict.get('footer', {}).get('text', 'N/A')[:50]}...")

    # Show description preview
    desc = embed_dict.get("description", "")
    if desc:
        print("\nDescription preview:")
        print(f"{'─' * 60}")
        print(desc[:300] + ("..." if len(desc) > 300 else ""))
        print(f"{'─' * 60}")

    print_section("✅ VALIDATION RESULTS", "-")
    if validation.is_valid:
        print("Status: ✅ VALID")
    else:
        print("Status: ❌ INVALID")
        for error in validation.errors:
            print(f"  ❌ {error}")

    print("\n📊 Size Analysis:")
    print(f"   Total: {validation.total_chars}/6000 chars ({validation.total_chars/60:.1f}%)")

    if validation.warnings:
        print("\n⚠️  Warnings:")
        for warning in validation.warnings:
            print(f"  ⚠️  {warning}")

    # TTS preview
    if result.summary_text:
        print_section("🔊 TTS TEXT (Summary)", "-")
        print(f"Length: {len(result.summary_text)} chars")
        print(f"Text: {result.summary_text}")

    # Show JSON if requested
    if show_json:
        print_section("📋 RAW JSON OUTPUT", "-")
        print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))

    print_section("✅ PREVIEW COMPLETE", "=")


async def preview_single_analysis() -> None:
    """Preview single-player analysis output."""
    from src.contracts.analysis_results import FinalAnalysisReport, V1ScoreSummary
    from src.core.views.analysis_view import render_analysis_embed
    from src.core.validation import validate_embed_strict, validate_analysis_data

    print_section("🎭 MOCK SINGLE-PLAYER ANALYSIS PREVIEW", "=")

    # Create mock report
    mock_report = FinalAnalysisReport(
        match_id="NA1_MOCK_SINGLE",
        match_result="victory",
        summoner_name="TestPlayer#NA1",
        champion_name="Yasuo",
        champion_id=157,
        ai_narrative_text="在这场比赛中表现出色！你的对线压制力很强，成功建立了经济优势。团战中的切入时机把握得当，有效地击杀了敌方后排。",
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
                "gold": 15420,
            },
        ),
        champion_assets_url="https://ddragon.leagueoflegends.com/cdn/14.1.1/img/champion/Yasuo.png",
        processing_duration_ms=1250.0,
        algorithm_version="v1",
    )

    # Validate data
    print_section("📊 DATA VALIDATION", "-")
    data_validation = validate_analysis_data(mock_report.model_dump())
    if data_validation.is_valid:
        print("✅ Data validation passed")
    else:
        print("❌ Data validation failed:")
        for error in data_validation.errors:
            print(f"  ❌ {error}")

    # Render embed
    print_section("🎨 DISCORD EMBED PREVIEW", "-")
    embed = render_analysis_embed(mock_report.model_dump())
    embed_dict = embed.to_dict()

    print(f"Title: {embed_dict.get('title', 'N/A')}")
    print(f"Description length: {len(embed_dict.get('description', ''))} chars")
    print(f"Fields: {len(embed_dict.get('fields', []))}")

    # Validate embed
    print_section("✅ EMBED VALIDATION", "-")
    validation = validate_embed_strict(embed)

    if validation.is_valid:
        print("✅ Embed validation passed")
    else:
        print("❌ Embed validation failed:")
        for error in validation.errors:
            print(f"  ❌ {error}")

    print(f"\n📊 Size: {validation.total_chars}/6000 chars ({validation.total_chars/60:.1f}%)")

    if validation.warnings:
        print("\n⚠️  Warnings:")
        for warning in validation.warnings:
            print(f"  ⚠️  {warning}")

    print_section("✅ PREVIEW COMPLETE", "=")


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Quick preview of Discord output")
    parser.add_argument("match_id", nargs="?", help="Match ID to preview (optional)")
    parser.add_argument("--json", action="store_true", help="Show raw JSON output")
    parser.add_argument("--single", action="store_true", help="Preview single-player analysis")

    args = parser.parse_args()

    if args.single:
        asyncio.run(preview_single_analysis())
    else:
        asyncio.run(preview_team_analysis(args.match_id, args.json))

    return 0


if __name__ == "__main__":
    sys.exit(main())
