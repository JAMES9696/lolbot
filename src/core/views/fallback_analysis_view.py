"""
Fallback Analysis View for Unsupported Game Modes.

V2.3 Enhancement: Provides positive degraded experience for game modes
that are not yet supported with deep analysis (e.g., new modes or queue types).

This view displays basic match data without complex mode-specific analysis,
ensuring users always get some value even when encountering unknown modes.

Design Principles:
- Positive User Experience: Friendly messaging about future support
- Basic Data Delivery: KDA, match result, champion played
- No Failure State: Avoid error messages or negative framing
- Consistent Branding: Matches main analysis view styling
"""

from typing import Any

import discord
from pydantic import BaseModel, Field


class FallbackMatchData(BaseModel):
    """Basic match data contract for fallback analysis.

    This minimal contract provides essential match information that
    doesn't require mode-specific analysis algorithms.
    """

    # Match metadata
    match_id: str = Field(description="Match ID")
    summoner_name: str = Field(description="Player's summoner name")
    champion_name: str = Field(description="Played champion")
    match_result: str = Field(description="Match outcome (victory/defeat)")

    # Game mode info
    queue_id: int = Field(description="Queue ID from Match-V5", default=0)
    queue_name: str = Field(description="Human-readable queue name", default="Unknown")
    mode_label: str = Field(
        description="Mode label (e.g., 'URF', 'One For All')", default="Unknown"
    )

    # Basic stats
    kills: int = Field(description="Kills", ge=0, default=0)
    deaths: int = Field(description="Deaths", ge=0, default=0)
    assists: int = Field(description="Assists", ge=0, default=0)
    total_damage_dealt: int = Field(description="Total damage dealt to champions", ge=0, default=0)
    gold_earned: int = Field(description="Gold earned", ge=0, default=0)

    # Optional message
    fallback_message: str | None = Field(
        default=None, description="Optional custom fallback message"
    )


def render_fallback_analysis_embed(data: dict[str, Any]) -> discord.Embed:
    """Render fallback analysis embed for unsupported game modes.

    This function creates a friendly, informative embed that:
    - Shows basic match stats (KDA, damage, gold)
    - Explains why deep analysis isn't available
    - Provides positive messaging about future support

    Args:
        data: Dict containing V23FallbackAnalysisReport data

    Returns:
        Discord Embed with fallback analysis UI
    """
    # Extract basic info
    match_result = data.get("match_result", "defeat")
    summoner_name = data.get("summoner_name", "Unknown")
    champion_name = data.get("champion_name", "Unknown")
    kills = data.get("kills", 0)
    deaths = data.get("deaths", 0)
    assists = data.get("assists", 0)
    total_damage = data.get("total_damage_dealt", 0)
    gold = data.get("gold_earned", 0)

    # Game mode info
    detected_mode = data.get("detected_mode", {})
    queue_name = detected_mode.get("queue_name", "未知模式")
    detected_mode.get("mode", "unknown")

    # Fallback message
    fallback_msg = data.get(
        "fallback_message",
        "该游戏模式的专业分析功能正在开发中。当前仅提供基础数据展示。我们将在未来版本中支持更多模式的深度分析。",
    )

    # Optional generic summary
    generic_summary = data.get("generic_summary")

    # Title & color
    if match_result == "victory":
        embed_color = 0x00FF00
        title_emoji = "🏆"
    else:
        embed_color = 0xFF0000
        title_emoji = "💔"

    title_text = f"{title_emoji} 基础战绩 | {champion_name}"

    # Description: KDA + basic stats
    kda_ratio = ((kills + assists) / deaths) if deaths > 0 else float(kills + assists)

    description = (
        f"**召唤师**: {summoner_name}\n"
        f"**模式**: {queue_name}\n\n"
        f"**战绩**: {kills}/{deaths}/{assists} (KDA: {kda_ratio:.2f})\n"
        f"**伤害**: {total_damage:,}\n"
        f"**金币**: {gold:,}\n"
    )

    embed = discord.Embed(
        title=title_text,
        description=description[:4000],
        color=embed_color,
    )

    # Add fallback message
    embed.add_field(
        name="💡 关于此模式",
        value=fallback_msg[:1024],
        inline=False,
    )

    # Add optional generic summary if available
    if generic_summary:
        embed.add_field(
            name="📊 本场概况",
            value=generic_summary[:1024],
            inline=False,
        )

    # Footer
    match_id = data.get("match_id", "unknown")
    algorithm_version = data.get("algorithm_version", "v2.3-fallback")
    embed.set_footer(text=f"Match ID: {match_id} | {algorithm_version}")

    return embed
