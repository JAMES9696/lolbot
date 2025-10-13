"""
Discord adapter for handling bot interactions and commands.
This is the main frontend interface (CLI 1) for user interactions.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any, cast

import aiohttp
import discord
from discord import FFmpegPCMAudio, app_commands
from discord.ext import commands

from src.config.settings import get_settings
from src.contracts.discord_interactions import (
    CommandName,
    EmbedColor,
)
from src.core.observability import clear_correlation_id, set_correlation_id
from src.core.services.celery_task_service import TaskQueueError
from src.core.services.voice_broadcast_service import VoiceBroadcastService
import contextlib

# Configure logging
logger = logging.getLogger(__name__)


def _select_personal_tts_summary(meta: dict[str, Any]) -> str | None:
    if not isinstance(meta, dict):
        return None
    candidate = meta.get("tts_summary")
    if not isinstance(candidate, str):
        return None
    candidate = candidate.strip()
    if not candidate:
        return None

    source_hint = str(meta.get("tts_summary_source") or "").lower()
    if not source_hint:
        source_hint = str(meta.get("source") or "").lower()

    disallowed = {"team_tldr", "team_tts", "team_summary"}
    if source_hint in disallowed:
        return None

    allowed = {"llm", "fallback", "individual", "personal", ""}
    if source_hint and source_hint not in allowed:
        return None

    return candidate


def _normalize_voice_channel_id(raw_channel_id: int | str | None) -> int | None:
    """Convert arbitrary voice channel identifiers to a valid Discord snowflake."""

    try:
        channel_id = int(raw_channel_id)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None

    if channel_id <= 0:
        return None

    return channel_id


class ChimeraBot(commands.Bot):
    """Main Discord bot class for 蔚-上城人."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the bot with custom settings."""
        # Set up intents
        intents = discord.Intents.default()
        intents.message_content = True  # For future message commands
        intents.guilds = True
        intents.members = True

        # Extract command_prefix to avoid duplicate keyword argument
        command_prefix = kwargs.pop("command_prefix", "!")

        super().__init__(command_prefix=command_prefix, intents=intents, **kwargs)

        self.settings = get_settings()
        self.startup_time: datetime | None = None

    async def setup_hook(self) -> None:
        """Hook called when bot is getting ready."""
        logger.info("Setting up bot hooks...")

        # Sync slash commands
        if self.settings.discord_guild_id:
            # Development mode: sync to specific guild for instant updates
            guild = discord.Object(id=int(self.settings.discord_guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Synced commands to guild {self.settings.discord_guild_id}")
        else:
            # Production mode: sync globally (may take up to 1 hour)
            await self.tree.sync()
            logger.info("Synced commands globally")

    async def on_ready(self) -> None:
        """Event triggered when bot is ready."""
        self.startup_time = datetime.now(UTC)
        logger.info(f"Bot {self.user} is ready!")
        logger.info(f"Connected to {len(self.guilds)} guilds")

        # Set bot presence/status
        await self.change_presence(
            activity=discord.Game(name="/bind to link your LoL account"),
            status=discord.Status.online,
        )


class DiscordAdapter:
    """Adapter for Discord interactions following hexagonal architecture."""

    def __init__(
        self,
        rso_adapter: Any,
        db_adapter: Any,
        task_service: Any | None = None,
        match_history_service: Any | None = None,
    ) -> None:
        """Initialize the Discord adapter.

        Args:
            rso_adapter: RSO OAuth adapter instance
            db_adapter: Database adapter instance
            task_service: IAsyncTaskService implementation (Celery)
            match_history_service: IMatchHistoryService implementation
        """
        self.rso = rso_adapter
        self.db = db_adapter
        self.task_service = task_service
        self.match_history_service = match_history_service
        self.settings = get_settings()
        app_id = (
            int(self.settings.discord_application_id)
            if self.settings.discord_application_id
            else None
        )
        self.bot = ChimeraBot(command_prefix=self.settings.bot_prefix, application_id=app_id)
        self._setup_commands()
        self._setup_event_handlers()
        # Optional: voice broadcast service (single-lane per guild)
        self.voice_broadcast: VoiceBroadcastService | None = None
        if self.settings.feature_voice_enabled:
            try:
                self.voice_broadcast = VoiceBroadcastService(self)
                logger.info("VoiceBroadcastService initialized")
            except Exception:
                logger.exception("Failed to initialize VoiceBroadcastService")

    def _setup_commands(self) -> None:
        """Set up slash commands."""

        @self.bot.tree.command(
            name=CommandName.BIND.value,
            description="Link your Discord account with your League of Legends account",
        )
        @app_commands.describe(
            region="Your League of Legends server region (default: NA)",
            force_rebind="Force new binding even if already linked",
        )
        @app_commands.choices(
            region=[
                app_commands.Choice(name="North America", value="na1"),
                app_commands.Choice(name="Europe West", value="euw1"),
                app_commands.Choice(name="Europe Nordic & East", value="eun1"),
                app_commands.Choice(name="Korea", value="kr"),
                app_commands.Choice(name="Brazil", value="br1"),
                app_commands.Choice(name="Latin America North", value="la1"),
                app_commands.Choice(name="Latin America South", value="la2"),
                app_commands.Choice(name="Oceania", value="oc1"),
                app_commands.Choice(name="Russia", value="ru"),
                app_commands.Choice(name="Turkey", value="tr1"),
                app_commands.Choice(name="Japan", value="jp1"),
                app_commands.Choice(name="Philippines", value="ph2"),
                app_commands.Choice(name="Singapore", value="sg2"),
                app_commands.Choice(name="Thailand", value="th2"),
                app_commands.Choice(name="Taiwan", value="tw2"),
                app_commands.Choice(name="Vietnam", value="vn2"),
            ]
        )
        async def bind_command(
            interaction: discord.Interaction, region: str = "na1", force_rebind: bool = False
        ) -> None:
            """Handle /bind command."""
            await self._handle_bind_command(interaction, region, force_rebind)

        @self.bot.tree.command(
            name=CommandName.UNBIND.value,
            description="Unlink your Discord account from your League of Legends account",
        )
        async def unbind_command(interaction: discord.Interaction) -> None:
            """Handle /unbind command."""
            await self._handle_unbind_command(interaction)

        @self.bot.tree.command(
            name=CommandName.PROFILE.value, description="View your linked League of Legends profile"
        )
        async def profile_command(interaction: discord.Interaction) -> None:
            """Handle /profile command."""
            await self._handle_profile_command(interaction)

        # Conditionally register /analyze when dependencies are available
        if (
            self.settings.feature_ai_analysis_enabled
            and self.task_service is not None
            and self.match_history_service is not None
        ):

            @self.bot.tree.command(
                name="analyze",
                description="AI深度分析您最近的一场比赛（讲道理）",
            )
            @app_commands.describe(
                match_index="要分析的比赛序号（1=最新，2=倒数第二场，以此类推）",
                riot_id="未绑定时可填：Riot ID，例如 FujiShanXia#NA1",
            )
            async def analyze_command(
                interaction: discord.Interaction, match_index: int = 1, riot_id: str | None = None
            ) -> None:
                """Handle /analyze command - AI match analysis (supports unbound Riot ID)."""
                await self._handle_analyze_command(interaction, match_index, riot_id)
        else:
            logger.info(
                "Skipping /analyze registration: feature flag or dependencies not satisfied"
            )

        # Conditionally register /team-analyze when V2 team analysis is enabled
        if (
            self.settings.feature_team_analysis_enabled
            and self.task_service is not None
            and self.match_history_service is not None
        ):

            @self.bot.tree.command(
                name=CommandName.TEAM_ANALYZE.value,
                description="团队分析：对比您与队友的表现（V2 - 需要绑定账户）",
            )
            @app_commands.describe(match_index="要分析的比赛序号（1=最新，2=倒数第二场，以此类推）")
            @app_commands.describe(
                match_index="要分析的比赛序号（1=最新，2=倒数第二场，以此类推）",
                riot_id="未绑定时可填：Riot ID，例如 FujiShanXia#NA1",
            )
            async def team_analyze_command(
                interaction: discord.Interaction, match_index: int = 1, riot_id: str | None = None
            ) -> None:
                """Handle /team-analyze command - V2 team-relative analysis (supports unbound Riot ID)."""
                await self._handle_team_analyze_command(interaction, match_index, riot_id)
        else:
            logger.info(
                "Skipping /team-analyze registration: feature flag or dependencies not satisfied"
            )

        # V2.2: Register /settings command for user preference configuration
        @self.bot.tree.command(
            name=CommandName.SETTINGS.value,
            description="配置个性化偏好（主要位置、分析语气等）",
        )
        async def settings_command(interaction: discord.Interaction) -> None:
            """Handle /settings command - V2.2 user preference configuration."""
            await self._handle_settings_command(interaction)

        # V2.3: Register /help command for feature guidance and mode support info
        @self.bot.tree.command(
            name="help",
            description="查看机器人功能说明和支持的游戏模式",
        )
        async def help_command(interaction: discord.Interaction) -> None:
            """Handle /help command - V2.3 feature documentation."""
            await self._handle_help_command(interaction)

    def _setup_event_handlers(self) -> None:
        """Set up event handlers for the bot."""

        @self.bot.event
        async def on_guild_join(guild: discord.Guild) -> None:
            """Handle bot joining a new guild."""
            logger.info(f"Joined guild: {guild.name} (ID: {guild.id})")

        @self.bot.event
        async def on_guild_remove(guild: discord.Guild) -> None:
            """Handle bot being removed from a guild."""
            logger.info(f"Removed from guild: {guild.name} (ID: {guild.id})")

        @self.bot.event
        async def on_app_command_error(
            interaction: discord.Interaction, error: app_commands.AppCommandError
        ) -> None:
            """Handle application command errors."""
            logger.error(f"Command error: {error}", exc_info=True)

            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self._create_error_embed("An error occurred processing your command."),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=self._create_error_embed("An error occurred processing your command."),
                    ephemeral=True,
                )

        @self.bot.event
        async def on_interaction(interaction: discord.Interaction) -> None:
            """Handle low-level interactions for message components (buttons).

            V2.1 Enhancement: Added support for advice feedback buttons.
            """
            try:
                if interaction.type is discord.InteractionType.component:
                    data = interaction.data or {}
                    custom_id = data.get("custom_id")
                    if isinstance(custom_id, str):
                        # V2.0: General feedback buttons
                        if custom_id.startswith("chimera:fb:"):
                            await self._handle_feedback_interaction(interaction, custom_id)
                            return
                        # V2.1: Advice-specific feedback buttons
                        if custom_id.startswith("chimera:advice:"):
                            await self._handle_feedback_interaction(interaction, custom_id)
                            return
                        # Voice playback button
                        if custom_id.startswith("chimera:voice:play:"):
                            await self._handle_voice_play_interaction(interaction, custom_id)
                            return
            except Exception:
                logger.exception("Unhandled error in on_interaction handler")

    async def _handle_bind_command(
        self, interaction: discord.Interaction, region: str, force_rebind: bool
    ) -> None:
        """Handle the /bind slash command."""
        user_id = str(interaction.user.id)

        # Create response embed
        embed = discord.Embed(
            title="🔗 Account Binding",
            description=(
                "To link your League of Legends account, you'll need to authorize through Riot's secure login.\n\n"
                "**Steps:**\n"
                "1. Click the button below to open Riot Sign-On\n"
                "2. Log in with your Riot account\n"
                "3. Authorize the application\n"
                "4. You'll be automatically linked!\n\n"
                f"**Selected Region:** {region.upper()}"
            ),
            color=EmbedColor.INFO,
        )
        embed.set_thumbnail(
            url="https://raw.githubusercontent.com/CommunityDragon/Docs/master/assets/riot-logo.png"
        )
        embed.set_footer(text="This process is secure and uses official Riot OAuth")

        # Generate real authorization URL
        # Generate OAuth URL; surface config issues to user gracefully
        try:
            auth_url, state = await self.rso.generate_auth_url(user_id, region)
        except Exception as e:
            logger.error(f"RSO config error: {e}", exc_info=True)
            await interaction.response.send_message(
                embed=self._create_error_embed(
                    "RSO 未正确配置，请联系管理员设置 OAuth Client 与回调地址。"
                ),
                ephemeral=True,
            )
            return

        # Create button for authorization
        view = discord.ui.View(timeout=300)  # 5 minute timeout

        auth_button = discord.ui.Button(
            label="Authorize with Riot",
            style=discord.ButtonStyle.link,
            url=auth_url,
            emoji="🎮",
        )
        view.add_item(auth_button)

        # Send response
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True,  # Only visible to the user
        )

        # Log the binding attempt
        logger.info(f"User {user_id} initiated binding for region {region}")

    async def _handle_unbind_command(self, interaction: discord.Interaction) -> None:
        """Handle the /unbind slash command."""
        user_id = str(interaction.user.id)

        # Check if user has an existing binding
        binding = await self.db.get_user_binding(user_id)

        if binding:
            # Remove the binding
            await self.db.delete_user_binding(user_id)

            embed = discord.Embed(
                title="🔓 Account Unbinding",
                description=(
                    "Your account binding has been removed.\n"
                    "You can re-link your account at any time using `/bind`."
                ),
                color=EmbedColor.SUCCESS,
            )
        else:
            embed = discord.Embed(
                title="⚠️ No Binding Found",
                description=(
                    "You don't have a League of Legends account linked.\n"
                    "Use `/bind` to link your account first."
                ),
                color=EmbedColor.WARNING,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"User {user_id} unbound their account")

    async def _handle_profile_command(self, interaction: discord.Interaction) -> None:
        """Handle the /profile slash command."""
        user_id = str(interaction.user.id)

        # Get user binding from database
        binding = await self.db.get_user_binding(user_id)

        if binding:
            # Show real profile data
            embed = discord.Embed(
                title="👤 Your Profile",
                description="Here's your linked League of Legends account information:",
                color=EmbedColor.SUCCESS,
            )
            embed.add_field(name="Discord ID", value=user_id, inline=True)
            embed.add_field(name="Summoner Name", value=binding["summoner_name"], inline=True)
            embed.add_field(name="Region", value=binding["region"].upper(), inline=True)
            embed.add_field(name="PUUID", value=binding["puuid"], inline=False)
            embed.set_footer(text="Use /unbind to remove this link")
        else:
            # Show "Not Linked" status
            embed = discord.Embed(
                title="👤 Your Profile",
                description="Profile information will be available once you link your account.",
                color=EmbedColor.INFO,
            )
            embed.add_field(name="Discord ID", value=user_id, inline=True)
            embed.add_field(name="Status", value="Not Linked", inline=True)
            embed.set_footer(text="Use /bind to link your League of Legends account")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _handle_analyze_command(
        self, interaction: discord.Interaction, match_index: int, riot_id: str | None = None
    ) -> None:
        """Handle the /analyze slash command - AI match analysis (讲道理).

        This is the core P3 implementation following the delayed response pattern.
        Must defer() within 3 seconds to prevent token expiration.
        """
        # [STEP 1: DELAYED RESPONSE - IRON LAW]
        # Must send deferred response within 3 seconds or interaction token expires
        await interaction.response.defer(ephemeral=False)  # Public loading state

        # Bind correlation id early so all bot-side logs are traceable
        _cid = f"discord:{interaction.id}:{int(time.time() * 1000) % 1000000}"
        try:
            set_correlation_id(_cid)
        except Exception:
            _cid = _cid  # no-op; keep local for payload

        user_id = str(interaction.user.id)

        # [STEP 2: GET PUUID/REGION]
        # Priority: riot_id parameter > bound account
        if riot_id:
            # Use provided riot_id (overrides binding)
            parsed = self._parse_riot_id(riot_id)
            if not parsed:
                await interaction.followup.send(
                    embed=self._create_error_embed("Riot ID 格式无效，请使用 例如 `GameName#NA1`"),
                    ephemeral=True,
                )
                return
            game_name, tag_line = parsed
            puuid = await self.match_history_service.get_puuid_by_riot_id(game_name, tag_line)
            if not puuid:
                await interaction.followup.send(
                    embed=self._create_error_embed("未找到该 Riot ID，请检查大小写与区服标签"),
                    ephemeral=True,
                )
                return
            region = self._tag_to_platform(tag_line)
        else:
            # Fallback to bound account
            binding = await self.db.get_user_binding(user_id)
            if binding:
                puuid = binding["puuid"]
                region = binding["region"]
            else:
                await interaction.followup.send(
                    embed=self._create_error_embed(
                        "您尚未绑定 Riot 账户。可通过 `/bind` 绑定，或直接提供 `riot_id` 参数（例如 `FujiShanXia#NA1`）进行一次性分析。"
                    ),
                    ephemeral=True,
                )
                return

        try:
            # [STEP 3: FETCH MATCH HISTORY]
            match_id_list = await self.match_history_service.get_match_id_list(
                puuid=puuid, region=region, count=20
            )
            with contextlib.suppress(Exception):
                logger.info(f"match_history[0:5]={match_id_list[:5]} requested_index={match_index}")

            if len(match_id_list) < match_index:
                error_embed = discord.Embed(
                    title="❌ 比赛不存在",
                    description=f"您的比赛历史中没有第 {match_index} 场比赛。\n当前共有 {len(match_id_list)} 场历史记录。",
                    color=EmbedColor.ERROR,
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            target_match_id = match_id_list[match_index - 1]

            # [STEP 4: CHECK EXISTING ANALYSIS STATUS]
            analysis_status = await self.match_history_service.get_analysis_status(target_match_id)

            if analysis_status:
                status = analysis_status.get("status")
                if status == "completed" and self.settings.analysis_cache_enabled:
                    # Return cached result with full analysis render
                    try:
                        import json as _json

                        from src.core.views import render_analysis_embed

                        # Fetch full analysis record and match data from DB
                        record = await self.db.get_analysis_result(target_match_id)
                        match_row = await self.db.get_match_data(target_match_id)

                        if not record:
                            raise RuntimeError("cached_record_missing")

                        # Extract narrative + metadata (emotion, tts)
                        narrative = record.get("llm_narrative") or "[缓存数据]"
                        meta = record.get("llm_metadata")
                        if isinstance(meta, str):
                            try:
                                meta = _json.loads(meta)
                            except Exception:
                                meta = None

                        # Normalize sentiment tag (map English to Chinese cluster)
                        sentiment_map = {
                            "excited": "激动",
                            "positive": "鼓励",
                            "proud": "鼓励",
                            "motivational": "鼓励",
                            "encouraging": "鼓励",
                            "mocking": "嘲讽",
                            "critical": "遗憾",
                            "concerned": "遗憾",
                            "disappointed": "遗憾",
                            "sympathetic": "遗憾",
                            "neutral": "平淡",
                            "analytical": "平淡",
                            "reflective": "平淡",
                            "calm": "平淡",
                            "cautious": "平淡",
                        }
                        sentiment = sentiment_map.get(
                            (meta or {}).get("emotion", "neutral"), "平淡"
                        )

                        # Resolve participant info for requester
                        requester_puuid = record.get("puuid") or ""
                        champion_name = "Unknown"
                        champion_id = 0
                        match_result = "defeat"
                        if match_row and isinstance(match_row.get("match_data"), dict):
                            participants = (
                                match_row["match_data"].get("info", {}).get("participants", [])
                            )
                            target_p = next(
                                (p for p in participants if p.get("puuid") == requester_puuid),
                                None,
                            )
                            if target_p:
                                champion_name = target_p.get("championName", "Unknown")
                                champion_id = int(target_p.get("championId", 0) or 0)
                                match_result = "victory" if target_p.get("win", False) else "defeat"

                        # Build champion asset URL via DDragon (prefer by ID)
                        champion_icon_url = ""
                        try:
                            if champion_id:
                                from src.adapters.ddragon_adapter import DDragonAdapter

                                async def _get_icon(cid: int) -> str:
                                    async with DDragonAdapter(language="zh_CN") as ddragon:
                                        data = await ddragon.get_champion_by_id(cid)
                                        return (data or {}).get("image_url", "")

                                # Discord's thread loop context: we are inside async, so await is fine
                                icon = await _get_icon(champion_id)
                                champion_icon_url = icon or ""
                        except Exception:
                            # Fallback to static URL if DDragon fails
                            if champion_name and champion_name != "Unknown":
                                safe_name = champion_name.replace(" ", "").replace("'", "")
                                champion_icon_url = f"https://ddragon.leagueoflegends.com/cdn/14.20.1/img/champion/{safe_name}.png"

                        # Derive V1 summary from stored score_data (MatchAnalysisOutput)
                        raw_score = record.get("score_data")
                        if isinstance(raw_score, str):
                            try:
                                raw_score = _json.loads(raw_score)
                            except Exception:
                                raw_score = None

                        v1_summary = {
                            "combat_score": 0.0,
                            "economy_score": 0.0,
                            "vision_score": 0.0,
                            "objective_score": 0.0,
                            "teamplay_score": 0.0,
                            "overall_score": 0.0,
                        }

                        if isinstance(raw_score, dict):
                            player_scores = raw_score.get("player_scores") or []
                            # Try to locate participant_id via match_data
                            target_participant_id = None
                            if match_row and isinstance(match_row.get("match_data"), dict):
                                participants = (
                                    match_row["match_data"].get("info", {}).get("participants", [])
                                )
                                tp = next(
                                    (p for p in participants if p.get("puuid") == requester_puuid),
                                    None,
                                )
                                if tp:
                                    target_participant_id = int(tp.get("participantId", 0) or 0)

                            selected = None
                            if target_participant_id:
                                selected = next(
                                    (
                                        s
                                        for s in player_scores
                                        if int(s.get("participant_id", 0) or 0)
                                        == target_participant_id
                                    ),
                                    None,
                                )
                            if not selected and player_scores:
                                selected = player_scores[0]

                            if isinstance(selected, dict):
                                v1_summary = {
                                    "combat_score": float(selected.get("combat_efficiency", 0.0)),
                                    "economy_score": float(
                                        selected.get("economic_management", 0.0)
                                    ),
                                    "vision_score": float(selected.get("vision_control", 0.0)),
                                    "objective_score": float(
                                        selected.get("objective_control", 0.0)
                                    ),
                                    "teamplay_score": float(selected.get("team_contribution", 0.0)),
                                    "overall_score": float(selected.get("total_score", 0.0)),
                                }

                        analysis_dict = {
                            "match_id": target_match_id,
                            "match_result": match_result,
                            "summoner_name": record.get("summoner_name") or "",  # ← 修复None处理
                            "champion_name": champion_name,
                            "champion_id": champion_id,
                            "ai_narrative_text": narrative,
                            "llm_sentiment_tag": sentiment,
                            "v1_score_summary": v1_summary,
                            "champion_assets_url": champion_icon_url,
                            "processing_duration_ms": float(
                                record.get("processing_duration_ms") or 0.0
                            ),
                            "algorithm_version": record.get("algorithm_version")
                            or "v1",  # ← 修复None处理
                            "tts_audio_url": (meta or {}).get("tts_audio_url"),
                        }

                        if isinstance(meta, dict):
                            meta_summary = meta.get("builds_summary_text")
                            meta_payload = meta.get("builds_metadata")
                            if isinstance(meta_summary, str) and meta_summary.strip():
                                analysis_dict["builds_summary_text"] = meta_summary.strip()
                            if isinstance(meta_payload, dict) and meta_payload:
                                analysis_dict["builds_metadata"] = meta_payload

                        with contextlib.suppress(Exception):
                            logger.info(
                                "Cached render trace: match=%s puuid=%s champion_id=%s champion=%s icon_set=%s",
                                target_match_id,
                                (requester_puuid or "")[-8:],
                                champion_id,
                                champion_name,
                                bool(champion_icon_url),
                            )

                        result_embed = render_analysis_embed(analysis_dict)
                        await interaction.followup.send(embed=result_embed, ephemeral=False)
                        logger.info(
                            f"Returned cached analysis for {target_match_id} (match_index={match_index})"
                        )
                        return
                    except Exception as e:
                        logger.error(f"Failed to render cached analysis: {e}", exc_info=True)
                        # Fallback to simple message
                        result_embed = discord.Embed(
                            title="✅ 分析结果（缓存）",
                            description=f"该比赛已完成分析。Match ID: `{target_match_id}`",
                            color=EmbedColor.SUCCESS,
                        )
                        await interaction.followup.send(embed=result_embed, ephemeral=False)
                        logger.info(f"Returned cached analysis for {target_match_id}")
                        return
                elif status == "completed":
                    logger.info(
                        "Analysis cache disabled; forcing re-run for %s (match_index=%s)",
                        target_match_id,
                        match_index,
                    )
                elif status in ("pending", "processing"):
                    # Analysis in progress
                    info_embed = discord.Embed(
                        title="⏳ 分析进行中",
                        description="该比赛正在分析中，请稍后查看结果。",
                        color=EmbedColor.INFO,
                    )
                    await interaction.followup.send(embed=info_embed, ephemeral=True)
                    return

            # [STEP 5: CONSTRUCT TASK PAYLOAD]
            from src.contracts.tasks import TASK_ANALYZE_MATCH, AnalysisTaskPayload

            payload = AnalysisTaskPayload(
                application_id=str(self.bot.application_id),
                interaction_token=interaction.token,
                channel_id=str(interaction.channel_id),
                guild_id=str(interaction.guild_id) if interaction.guild_id else None,
                discord_user_id=user_id,
                puuid=puuid,
                match_id=target_match_id,
                region=region,
                match_index=match_index,
                correlation_id=_cid,
            )

            # [STEP 6: PUSH TASK TO CELERY QUEUE]
            try:
                task_id = await self.task_service.push_analysis_task(
                    task_name=TASK_ANALYZE_MATCH, payload=payload.model_dump()
                )
            except TaskQueueError as tq_err:
                logger.error(
                    "Celery queue unavailable for analyze command",
                    exc_info=True,
                    extra={"match_id": target_match_id, "error": str(tq_err)},
                )
                queue_embed = discord.Embed(
                    title="⚠️ 后台队列不可用",
                    description=(
                        "目前未检测到分析工作进程，请稍后重试。\n"
                        "管理员：请确认 Redis 与 Celery worker 已启动。"
                    ),
                    color=EmbedColor.WARNING,
                )
                await interaction.followup.send(embed=queue_embed, ephemeral=True)
                return

            # [STEP 7: SEND LOADING MESSAGE]
            loading_embed = discord.Embed(
                title="🔄 AI 分析中...",
                description=(
                    f"正在对您的第 {match_index} 场比赛进行深度分析。\n\n_预计耗时：30-60秒_"
                ),
                color=EmbedColor.INFO,
            )
            loading_embed.set_footer(text=f"Task ID: {task_id}")

            await interaction.followup.send(embed=loading_embed, ephemeral=False)

            logger.info(
                f"Analysis task pushed: user={user_id}, match={target_match_id}, index={match_index}, task_id={task_id}"
            )

        except Exception as e:
            logger.error(f"Error in analyze command: {e}", exc_info=True)
            error_embed = self._create_error_embed(
                f"分析请求失败：{type(e).__name__}\n请稍后重试或联系管理员。"
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
        finally:
            with contextlib.suppress(Exception):
                clear_correlation_id()

    async def _handle_team_analyze_command(
        self, interaction: discord.Interaction, match_index: int, riot_id: str | None = None
    ) -> None:
        """Handle the /team-analyze slash command - V2 team-relative analysis.

        This implements the same deferred response pattern as /analyze,
        but dispatches a team analysis task for processing all 5 players.
        """
        # [STEP 1: DELAYED RESPONSE - IRON LAW]
        # Must send deferred response within 3 seconds or interaction token expires
        await interaction.response.defer(ephemeral=False)  # Public loading state

        # Bind correlation id early for team analysis as well
        _cid = f"discord:{interaction.id}:{int(time.time() * 1000) % 1000000}"
        try:
            set_correlation_id(_cid)
        except Exception:
            _cid = _cid

        user_id = str(interaction.user.id)

        # [STEP 2: GET PUUID/REGION]
        # Priority: riot_id parameter > bound account
        if riot_id:
            # Use provided riot_id (overrides binding)
            parsed = self._parse_riot_id(riot_id)
            if not parsed:
                await interaction.followup.send(
                    embed=self._create_error_embed("Riot ID 格式无效，请使用 例如 `GameName#NA1`"),
                    ephemeral=True,
                )
                return
            game_name, tag_line = parsed
            puuid = await self.match_history_service.get_puuid_by_riot_id(game_name, tag_line)
            if not puuid:
                await interaction.followup.send(
                    embed=self._create_error_embed("未找到该 Riot ID，请检查大小写与区服标签"),
                    ephemeral=True,
                )
                return
            region = self._tag_to_platform(tag_line)
        else:
            # Fallback to bound account
            binding = await self.db.get_user_binding(user_id)
            if binding:
                puuid = binding["puuid"]
                region = binding["region"]
            else:
                await interaction.followup.send(
                    embed=self._create_error_embed(
                        "您尚未绑定 Riot 账户。可通过 `/bind` 绑定，或直接提供 `riot_id` 参数（例如 `FujiShanXia#NA1`）进行一次性团队分析。"
                    ),
                    ephemeral=True,
                )
                return

        try:
            # [STEP 3: FETCH MATCH HISTORY]
            match_id_list = await self.match_history_service.get_match_id_list(
                puuid=puuid, region=region, count=20
            )
            with contextlib.suppress(Exception):
                logger.info(
                    f"match_history[0:5]={match_id_list[:5]} requested_index={match_index} (team)"
                )

            if len(match_id_list) < match_index:
                error_embed = discord.Embed(
                    title="❌ 比赛不存在",
                    description=f"您的比赛历史中没有第 {match_index} 场比赛。\n当前共有 {len(match_id_list)} 场历史记录。",
                    color=EmbedColor.ERROR,
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            target_match_id = match_id_list[match_index - 1]

            # [STEP 4: CHECK EXISTING ANALYSIS STATUS]
            # Important: Distinguish V1 personal vs V2 team results.
            # Only treat as cached for team when score_data contains V2 team fields.
            analysis_status = await self.match_history_service.get_analysis_status(target_match_id)

            if analysis_status:
                status = analysis_status.get("status")
                if status == "completed":
                    # Inspect stored score_data to confirm V2 team result exists
                    try:
                        record = await self.db.get_analysis_result(target_match_id)
                        score_data = record.get("score_data") if record else None
                        # asyncpg returns JSONB as dict; tolerate string fallback
                        if isinstance(score_data, str):
                            import json as _json

                            try:
                                score_data = _json.loads(score_data)
                            except Exception:
                                score_data = None

                        has_team_v2 = False
                        if isinstance(score_data, dict):
                            # Heuristic: V2 team analysis includes these fields
                            has_team_v2 = bool(
                                "team_summary" in score_data or "team_analysis" in score_data
                            )

                        if has_team_v2:
                            # Return cached team analysis with full render
                            try:
                                from src.contracts.team_analysis import TeamAnalysisReport
                                from src.core.views import render_team_overview_embed

                                # Build TeamAnalysisReport from cached data
                                team_summary = score_data.get("team_summary", {})
                                team_report = TeamAnalysisReport(
                                    match_id=target_match_id,
                                    team_result=record.get("match_result", "defeat"),
                                    team_region=region,
                                    aggregates=team_summary.get("aggregates", {}),
                                    players=team_summary.get("players", []),
                                )
                                result_embed = render_team_overview_embed(team_report)
                                await interaction.followup.send(embed=result_embed, ephemeral=False)
                                logger.info(
                                    f"Returned cached team analysis for {target_match_id} (match_index={match_index})"
                                )
                                return
                            except Exception as e:
                                logger.error(
                                    f"Failed to render cached team analysis: {e}", exc_info=True
                                )
                                # Fallback to simple message
                                result_embed = discord.Embed(
                                    title="✅ 团队分析结果（缓存）",
                                    description=f"该比赛已完成团队分析。Match ID: `{target_match_id}`",
                                    color=EmbedColor.SUCCESS,
                                )
                                await interaction.followup.send(embed=result_embed, ephemeral=False)
                                logger.info(
                                    f"Returned cached team analysis for {target_match_id} (match_index={match_index})"
                                )
                                return
                        # Else: V1-only result present → continue to push V2 team task
                    except Exception:
                        # On any error inspecting existing data, continue to push task
                        pass
                elif status in ("pending", "processing"):
                    # Analysis in progress
                    info_embed = discord.Embed(
                        title="⏳ 分析进行中",
                        description="该比赛正在分析中，请稍后查看结果。",
                        color=EmbedColor.INFO,
                    )
                    await interaction.followup.send(embed=info_embed, ephemeral=True)
                    return

            # [STEP 5: CONSTRUCT TASK PAYLOAD]
            from src.contracts.tasks import TASK_ANALYZE_TEAM, TeamAnalysisTaskPayload

            payload = TeamAnalysisTaskPayload(
                application_id=str(self.bot.application_id),
                interaction_token=interaction.token,
                channel_id=str(interaction.channel_id),
                guild_id=str(interaction.guild_id) if interaction.guild_id else None,
                discord_user_id=user_id,
                puuid=puuid,
                match_id=target_match_id,
                region=region,
                match_index=match_index,
                correlation_id=_cid,
            )

            # [STEP 6: PUSH TASK TO CELERY QUEUE]
            try:
                task_id = await self.task_service.push_analysis_task(
                    task_name=TASK_ANALYZE_TEAM, payload=payload.model_dump()
                )
            except TaskQueueError as tq_err:
                logger.error(
                    "Celery queue unavailable for team analyze command",
                    exc_info=True,
                    extra={"match_id": target_match_id, "error": str(tq_err)},
                )
                queue_embed = discord.Embed(
                    title="⚠️ 后台队列不可用",
                    description=(
                        "团队分析服务暂不可用，因为未检测到 Celery worker。\n"
                        "请稍后重试，或联系管理员启动任务队列。"
                    ),
                    color=EmbedColor.WARNING,
                )
                await interaction.followup.send(embed=queue_embed, ephemeral=True)
                return

            # [STEP 7: SEND LOADING MESSAGE]
            loading_embed = discord.Embed(
                title="🔄 团队分析中...",
                description=(
                    f"正在对您的第 {match_index} 场比赛进行团队深度分析。\n\n_预计耗时：60-90秒_"
                ),
                color=EmbedColor.INFO,
            )
            loading_embed.set_footer(text=f"Task ID: {task_id} | V2 Team Analysis")

            await interaction.followup.send(embed=loading_embed, ephemeral=False)

            logger.info(
                f"Team analysis task pushed: user={user_id}, match={target_match_id}, index={match_index}, task_id={task_id}"
            )

        except Exception as e:
            logger.error(f"Error in team-analyze command: {e}", exc_info=True)
            error_embed = self._create_error_embed(
                f"团队分析请求失败：{type(e).__name__}\n请稍后重试或联系管理员。"
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
        finally:
            with contextlib.suppress(Exception):
                clear_correlation_id()

    # --- helpers: Riot ID parsing & region mapping (minimal, no extra deps) ---
    def _parse_riot_id(self, riot_id: str) -> tuple[str, str] | None:
        try:
            if "#" not in riot_id:
                return None
            name, tag = riot_id.split("#", 1)
            name = name.strip()
            tag = tag.strip().upper()
            if not name or not tag:
                return None
            return name, tag
        except Exception:
            return None

    def _tag_to_platform(self, tag: str) -> str:
        mapping = {
            "NA1": "na1",
            "EUW1": "euw1",
            "EUW": "euw1",
            "EUN1": "eun1",
            "EUNE": "eun1",
            "KR": "kr",
            "BR1": "br1",
            "LA1": "la1",
            "LA2": "la2",
            "OC1": "oc1",
            "OCE": "oc1",
            "RU": "ru",
            "TR1": "tr1",
            "JP1": "jp1",
            "PH2": "ph2",
            "SG2": "sg2",
            "TH2": "th2",
            "TW2": "tw2",
            "VN2": "vn2",
        }
        return mapping.get(tag.upper(), "na1")

    async def _handle_settings_command(self, interaction: discord.Interaction) -> None:
        """Handle the /settings slash command - V2.2 user preference configuration.

        This command shows the user's current preferences and provides
        a Discord Modal for interactive configuration.

        V2.2 Implementation: User empowerment through clear preference UI.
        """
        from src.core.views.settings_modal import (
            UserSettingsModal,
        )

        user_id = str(interaction.user.id)

        try:
            # [STEP 1: FETCH CURRENT PREFERENCES]
            # TODO(V2.2-CLI2): Integrate with UserProfileService.get_user_preferences()
            # For now, we'll use None (default settings) until backend is ready
            # current_preferences = None

            # [STEP 2: CREATE SETTINGS MODAL WITH CALLBACK HANDLER]
            # Create a custom modal instance that handles persistence
            settings_modal = UserSettingsModal()

            # Set up the callback handler for modal submission
            original_on_submit = settings_modal.on_submit

            async def on_submit_with_persistence(modal_interaction: discord.Interaction) -> None:
                """Extended on_submit handler that persists preferences to backend."""
                # Call original validation logic
                await original_on_submit(modal_interaction)

                # Check if validation passed (modal should have update_request)
                if hasattr(settings_modal, "update_request"):
                    update_request = settings_modal.update_request

                    # [STEP 3: PERSIST PREFERENCES]
                    # TODO(V2.2-CLI2): Integrate with UserProfileService.update_user_preferences()
                    # For now, we'll just acknowledge the update
                    logger.info(
                        f"User {user_id} submitted preference update: {update_request.model_dump()}"
                    )

                    # [STEP 4: SEND SUCCESS RESPONSE]
                    success_embed = discord.Embed(
                        title="✅ 设置已保存",
                        description="您的个性化配置已成功更新！",
                        color=EmbedColor.SUCCESS,
                    )

                    # Show what was updated
                    updated_fields = []
                    if update_request.main_role is not None:
                        updated_fields.append(f"**主要位置:** {update_request.main_role}")
                    if update_request.analysis_tone is not None:
                        tone_display = {
                            "competitive": "竞争型",
                            "casual": "休闲型",
                            "balanced": "平衡型",
                        }.get(update_request.analysis_tone, update_request.analysis_tone)
                        updated_fields.append(f"**分析语气:** {tone_display}")
                    if update_request.advice_detail_level is not None:
                        detail_display = {
                            "concise": "简洁",
                            "detailed": "详细",
                        }.get(
                            update_request.advice_detail_level,
                            update_request.advice_detail_level,
                        )
                        updated_fields.append(f"**建议详细程度:** {detail_display}")
                    if update_request.show_timeline_references is not None:
                        timeline_text = (
                            "显示" if update_request.show_timeline_references else "隐藏"
                        )
                        updated_fields.append(f"**时间轴引用:** {timeline_text}")

                    if updated_fields:
                        success_embed.add_field(
                            name="已更新的设置",
                            value="\n".join(updated_fields),
                            inline=False,
                        )

                    success_embed.set_footer(
                        text="这些设置将在下次分析时生效 | 使用 /settings 可随时修改"
                    )

                    await modal_interaction.followup.send(embed=success_embed, ephemeral=True)

            # Monkey-patch the on_submit method to include persistence
            settings_modal.on_submit = on_submit_with_persistence  # type: ignore[method-assign]

            # [STEP 5: SHOW MODAL TO USER]
            # Send modal as interaction response
            # The modal will handle submission automatically via on_submit callback
            await interaction.response.send_modal(settings_modal)

            logger.info(f"Settings modal sent to user {user_id}")

        except Exception as e:
            logger.error(f"Error in settings command: {e}", exc_info=True)
            error_embed = self._create_error_embed(
                f"设置配置失败：{type(e).__name__}\n请稍后重试或联系管理员。"
            )

            # Try to send error (if interaction not yet responded)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=error_embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
            except discord.errors.HTTPException as http_err:
                # Interaction might have expired or other HTTP error
                logger.warning(f"Could not send error message to user {user_id}: {http_err}")

    async def _handle_help_command(self, interaction: discord.Interaction) -> None:
        """Handle the /help command - V2.3 feature documentation and mode support.

        This command provides:
        - List of available commands
        - Supported game modes
        - Feature availability
        - Bot branding and compliance information
        """
        embed = discord.Embed(
            title="🤖 蔚-上城人 - 帮助文档",
            description=(
                "**蔚-上城人** 是一个英雄联盟比赛分析机器人，"
                "为您提供 AI 驱动的个性化表现评估和改进建议。"
            ),
            color=0x5865F2,
        )

        # Available commands section
        commands_text = (
            "**`/bind`** - 绑定您的 Riot 账户\n"
            "**`/unbind`** - 解除账户绑定\n"
            "**`/profile`** - 查看已绑定的账户信息\n"
            "**`/analyze [match_index] [riot_id]`** - 个人分析（支持未绑定：填写 `riot_id` 例如 `Name#NA1`）\n"
            "**`/team-analyze [match_index] [riot_id]`** - 团队分析（支持未绑定：填写 `riot_id`）\n"
            "**`/settings`** - 配置个性化偏好\n"
            "**`/help`** - 显示本帮助信息"
        )
        embed.add_field(
            name="📋 可用命令",
            value=commands_text,
            inline=False,
        )

        # Supported game modes section (V2.3 feature)
        modes_text = (
            "✅ **召唤师峡谷** - 5v5 排位/匹配\n"
            "✅ **极地大乱斗 (ARAM)** - 单线混战\n"
            "✅ **斗魂竞技场 (Arena)** - 2v2v2v2 竞技\n\n"
            "更多游戏模式支持开发中..."
        )
        embed.add_field(
            name="🎮 支持的游戏模式",
            value=modes_text,
            inline=False,
        )

        # Feature status section
        feature_status = []
        if self.settings.feature_ai_analysis_enabled:
            feature_status.append("✅ AI 深度分析")
        if self.settings.feature_team_analysis_enabled:
            feature_status.append("✅ 团队相对分析")
        if self.settings.feature_v21_prescriptive_enabled:
            feature_status.append("✅ 时间轴证据分析")
        if self.settings.feature_v22_personalization_enabled:
            feature_status.append("✅ 个性化分析")
        if self.settings.feature_voice_enabled:
            feature_status.append("✅ 语音播报")

        feature_text = "\n".join(feature_status) if feature_status else "基础功能已启用"

        embed.add_field(
            name="🚀 已启用功能",
            value=feature_text,
            inline=False,
        )

        # Getting started section
        getting_started_text = (
            "1️⃣ 使用 `/bind` 绑定您的 Riot 账户\n"
            "2️⃣ 使用 `/team-analyze` 分析最近的比赛\n"
            "3️⃣ 使用 `/settings` 配置个性化偏好\n"
            "4️⃣ 通过反馈按钮（👍👎⭐）帮助我们改进"
        )
        embed.add_field(
            name="🎯 快速开始",
            value=getting_started_text,
            inline=False,
        )

        # Legal and compliance section
        compliance_text = (
            "**免责声明:** 蔚-上城人 还在申请 Riot Games 的皮城高级海克斯水晶服务喵。再等等 \n"
            "本机器人使用 Riot Games API，遵循 Riot 开发者条款。\n\n"
            "**隐私:** 我们仅存储必要的账户绑定信息和匿名分析数据。\n"
            "您可以随时使用 `/unbind` 解除绑定并删除数据。"
        )
        embed.add_field(
            name="⚖️ 合规与隐私",
            value=compliance_text,
            inline=False,
        )

        # Footer with version and support
        embed.set_footer(
            text=f"蔚-上城人 {self.settings.app_version} | 环境: {self.settings.app_env}"
        )

        # Send ephemeral response
        await interaction.response.send_message(embed=embed, ephemeral=True)

        logger.info(f"Help command executed by user {interaction.user.id}")

    def _create_error_embed(self, message: str) -> discord.Embed:
        """Create a standardized error embed."""
        return discord.Embed(title="❌ Error", description=message, color=EmbedColor.ERROR)

    async def start(self) -> None:
        """Start the Discord bot."""
        logger.info("Starting Discord bot...")
        await self.bot.start(self.settings.discord_bot_token)

    async def stop(self) -> None:
        """Stop the Discord bot."""
        logger.info("Stopping Discord bot...")
        await self.bot.close()

    async def start_async(self) -> None:
        """Start the bot using async/await (non-blocking in async context)."""
        try:
            await self.bot.start(self.settings.discord_bot_token)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Bot crashed: {e}", exc_info=True)
            raise

    def run(self) -> None:
        """Run the bot (blocking, for non-async entry points)."""
        try:
            self.bot.run(self.settings.discord_bot_token)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Bot crashed: {e}", exc_info=True)
            raise

    async def _handle_feedback_interaction(
        self, interaction: discord.Interaction, custom_id: str
    ) -> None:
        """Process feedback button clicks and forward to backend asynchronously.

        Supported custom_id schemas:
        - V2.0 general: "chimera:fb:{type}:{match_id}" (type: up/down/star)
        - V2.1 advice: "chimera:advice:{advice_id}:{match_id}:{useful|not_useful}"

        V2.1 Enhancement: Added support for fine-grained advice feedback.
        """
        try:
            parts = custom_id.split(":")

            # V2.1: Advice-specific feedback (5 parts)
            if len(parts) == 5 and parts[1] == "advice":
                await self._handle_advice_feedback(interaction, parts)
                return

            # V2.0: General feedback (4 parts)
            if len(parts) == 4 and parts[1] == "fb":
                await self._handle_general_feedback(interaction, parts)
                return

            # Invalid format
            await interaction.response.send_message(
                embed=self._create_error_embed("反馈格式无效，请重试。"), ephemeral=True
            )

        except Exception:
            logger.exception("Failed to process feedback interaction")

    async def _handle_voice_play_interaction(
        self, interaction: discord.Interaction, custom_id: str
    ) -> None:
        """Handle voice play button interaction.

        Workflow:
        1. Parse match_id from custom_id
        2. Fetch analysis record from DB
        3. Extract tts_audio_url from llm_metadata
        4. If no audio_url, synthesize from narrative and update DB
        5. Resolve user's voice channel
        6. Play audio to user's channel with default settings
        7. Respond with ephemeral feedback

        Args:
            interaction: Discord interaction object
            custom_id: Button custom_id (chimera:voice:play:{match_id}:{issued_at})
        """
        import time

        start_time = time.time()

        try:
            # Parse match_id + optional issued_at timestamp (accepting legacy/new formats)
            parts = custom_id.split(":")
            if len(parts) < 4:
                logger.warning(
                    "Invalid voice play custom_id (expected >=4 segments)",
                    extra={"custom_id": custom_id, "segments": len(parts)},
                )
                await interaction.response.send_message("❌ 无效的按钮操作", ephemeral=True)
                return

            prefix, scope, action = parts[:3]
            if prefix != "chimera" or scope != "voice" or action != "play":
                logger.warning(
                    "Voice play custom_id prefix mismatch",
                    extra={
                        "custom_id": custom_id,
                        "prefix": prefix,
                        "scope": scope,
                        "action": action,
                    },
                )
                await interaction.response.send_message("❌ 无效的按钮操作", ephemeral=True)
                return

            match_segments = parts[3:]
            issued_at_ts: int | None = None
            if len(match_segments) >= 2:
                potential_ts = match_segments[-1]
                try:
                    issued_at_ts = int(potential_ts)
                    match_segments = match_segments[:-1]
                except ValueError:
                    issued_at_ts = None
                    logger.warning(
                        "Voice play custom_id timestamp parse failed",
                        extra={"custom_id": custom_id, "segment": potential_ts},
                    )

            match_id = ":".join(match_segments) if match_segments else ""
            if not match_id:
                logger.warning(
                    "Voice play custom_id missing match_id segment",
                    extra={"custom_id": custom_id},
                )
                await interaction.response.send_message("❌ 无效的按钮操作", ephemeral=True)
                return

            if issued_at_ts is not None:
                ttl_seconds = getattr(self.settings, "voice_button_ttl_seconds", 15 * 60)
                if time.time() - issued_at_ts > ttl_seconds:
                    logger.info(
                        "Voice play interaction expired locally",
                        extra={"match_id": match_id, "issued_at": issued_at_ts},
                    )
                    await interaction.response.send_message(
                        "⚠️ 语音播报请求已过期，请刷新结果后重新点击。", ephemeral=True
                    )
                    return

            logger.info(
                f"Voice play button clicked: match_id={match_id}, user={interaction.user.id}"
            )

            # Acknowledge interaction immediately
            await interaction.response.defer(ephemeral=True)

            # 1. Fetch analysis record from DB
            record = await self.db.get_analysis_result(match_id)
            if not record:
                logger.warning(f"No analysis record found for match_id={match_id}")
                await interaction.followup.send("❌ 未找到该场比赛的分析记录", ephemeral=True)
                return

            # 2. Extract tts_audio_url from llm_metadata
            audio_url = None
            llm_metadata = record.get("llm_metadata")

            # Handle both string (JSON) and dict formats
            if isinstance(llm_metadata, str):
                import json

                try:
                    llm_metadata = json.loads(llm_metadata)
                except Exception:
                    llm_metadata = {}
            elif not isinstance(llm_metadata, dict):
                llm_metadata = {}

            audio_url = llm_metadata.get("tts_audio_url")
            personal_summary = _select_personal_tts_summary(llm_metadata)

            # 3. If no audio_url, synthesize from narrative
            if not audio_url:
                narrative = record.get("llm_narrative")
                speech_source = personal_summary or narrative
                if not speech_source:
                    logger.warning(f"No narrative available for match_id={match_id}")
                    await interaction.followup.send("❌ 暂无可播报的分析内容", ephemeral=True)
                    return

                logger.info(f"Synthesizing TTS for match_id={match_id}")
                try:
                    from src.adapters.tts_adapter import TTSAdapter

                    tts = TTSAdapter()
                    emotion = llm_metadata.get("emotion", "平淡")
                    tts_options: dict[str, Any] = {}
                    recommended = llm_metadata.get("tts_recommended_params")
                    if isinstance(recommended, dict):
                        tts_options = dict(recommended)
                    tts_options.setdefault("match_id", match_id)
                    audio_url = await tts.synthesize_speech_to_url(
                        speech_source, emotion, options=tts_options
                    )

                    if audio_url:
                        # Update DB with new audio_url
                        updated_metadata = {**llm_metadata, "tts_audio_url": audio_url}
                        await self.db.update_llm_narrative(
                            match_id=match_id,
                            llm_narrative=narrative or speech_source,
                            llm_metadata=updated_metadata,
                        )
                        logger.info(f"TTS synthesized and saved for match_id={match_id}")
                    else:
                        logger.warning(f"TTS synthesis returned None for match_id={match_id}")
                        await interaction.followup.send(
                            "❌ 语音合成失败，请稍后重试", ephemeral=True
                        )
                        return

                except Exception as e:
                    logger.error(
                        f"TTS synthesis failed for match_id={match_id}: {e}", exc_info=True
                    )
                    await interaction.followup.send("❌ 语音合成失败，请稍后重试", ephemeral=True)
                    return

            # 4. Resolve user's voice channel and play
            guild_id = interaction.guild.id if interaction.guild else None
            user_id = interaction.user.id

            if not guild_id:
                await interaction.followup.send("❌ 无法获取服务器信息", ephemeral=True)
                return

            # 5. Play audio with default settings
            settings = self.settings
            success = await self.play_tts_to_user_channel(
                guild_id=guild_id,
                user_id=user_id,
                audio_url=audio_url,
                volume=settings.voice_volume_default,
                normalize=settings.voice_normalize_default,
                max_seconds=settings.voice_max_seconds_default,
            )

            elapsed_ms = (time.time() - start_time) * 1000

            # 6. Respond with result
            if success:
                logger.info(
                    f"Voice play successful: match_id={match_id}, user={user_id}, "
                    f"elapsed_ms={elapsed_ms:.0f}"
                )
                try:
                    await interaction.followup.send(
                        "✅ 已开始语音播报，记得保持在当前语音频道哦。",
                        ephemeral=True,
                    )
                except Exception:
                    logger.debug("voice_success_followup_failed", exc_info=True)
            else:
                logger.warning(
                    f"Voice play failed (user not in voice?): match_id={match_id}, user={user_id}"
                )
                await interaction.followup.send("⚠️ 你当前不在任何语音频道", ephemeral=True)

        except discord.NotFound as e:
            logger.warning(
                "Voice play interaction token invalid or expired",
                exc_info=True,
                extra={"custom_id": custom_id, "error": str(e)},
            )
            channel = getattr(interaction, "channel", None)
            if channel:
                try:
                    if audio_url:
                        await channel.send(f"⚠️ 播报按钮已过期，这是上次生成的语音链接：{audio_url}")
                    else:
                        await channel.send("⚠️ 播报请求已过期，请重新运行 /analyze。")
                except Exception:
                    pass
            return
        except discord.Forbidden as e:
            logger.warning(
                "Voice play interaction forbidden by Discord",
                exc_info=True,
                extra={"custom_id": custom_id, "error": str(e)},
            )
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "⚠️ 无法在当前频道播报，请联系管理员。", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "⚠️ 无法在当前频道播报，请联系管理员。", ephemeral=True
                    )
            except Exception:
                pass
            return
        except Exception as e:
            logger.error(f"Voice play interaction error: {e}", exc_info=True)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send("❌ 播报失败，请稍后重试", ephemeral=True)
                else:
                    await interaction.response.send_message(
                        "❌ 播报失败，请稍后重试", ephemeral=True
                    )
            except Exception:
                pass

    async def _handle_general_feedback(
        self, interaction: discord.Interaction, parts: list[str]
    ) -> None:
        """Handle V2.0 general feedback (thumbs up/down/star).

        Args:
            interaction: Discord interaction object
            parts: Parsed custom_id parts [chimera, fb, type, match_id]
        """
        _, _, fb_type, match_id = parts

        # Ack quickly to satisfy Discord 3s rule
        try:
            await interaction.response.send_message(content="✅ 已收到反馈，感谢！", ephemeral=True)
        except discord.InteractionResponded:
            # If already responded, fall back to followup
            await interaction.followup.send(content="✅ 已收到反馈，感谢！", ephemeral=True)

        # Compose payload
        user_id = str(interaction.user.id)
        # Derive A/B variant deterministically on the frontend
        from src.core.services.ab_testing import CohortAssignmentService

        cohort = CohortAssignmentService().assign_variant(user_id)
        variant = "A" if cohort == "A" else "B"

        payload: dict[str, Any] = {
            "match_id": match_id,
            "user_id": user_id,
            "feedback_type": fb_type,
            "prompt_variant": variant,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Fire and forget POST to backend if configured
        if self.settings.feedback_api_url:

            async def _post_feedback(url: str, data: dict[str, Any]) -> None:
                try:
                    timeout = aiohttp.ClientTimeout(total=5)
                    async with aiohttp.ClientSession(timeout=timeout) as sess:
                        async with sess.post(url, json=data) as resp:
                            if resp.status == 429:
                                retry_after = resp.headers.get("Retry-After")
                                logger.warning(f"Feedback 429; Retry-After={retry_after}")
                            elif resp.status >= 400:
                                txt = await resp.text()
                                logger.warning(f"Feedback POST failed: {resp.status} - {txt}")
                            else:
                                logger.info("Feedback POST succeeded")
                except Exception as e:
                    logger.warning(f"Feedback POST error: {e}")

            asyncio.create_task(_post_feedback(self.settings.feedback_api_url, payload))
        else:
            logger.info("FEEDBACK_API_URL not set; skipping backend POST")

    async def _handle_advice_feedback(
        self, interaction: discord.Interaction, parts: list[str]
    ) -> None:
        """Handle V2.1 advice-specific feedback (useful/not useful).

        Args:
            interaction: Discord interaction object
            parts: Parsed custom_id parts [chimera, advice, advice_id, match_id, useful|not_useful]
        """
        _, _, advice_id, match_id, usefulness = parts

        # Ack quickly to satisfy Discord 3s rule
        try:
            await interaction.response.send_message(
                content="✅ 已收到建议反馈，感谢！", ephemeral=True
            )
        except discord.InteractionResponded:
            await interaction.followup.send(content="✅ 已收到建议反馈，感谢！", ephemeral=True)

        # Compose V2.1 advice feedback payload
        user_id = str(interaction.user.id)
        from src.core.services.ab_testing import CohortAssignmentService

        cohort = CohortAssignmentService().assign_variant(user_id)
        variant = "A" if cohort == "A" else "B"

        # Map usefulness to feedback_type and value
        if usefulness == "useful":
            feedback_type = "advice_useful"
            feedback_value = 1
        else:  # not_useful
            feedback_type = "advice_not_useful"
            feedback_value = -1

        payload: dict[str, Any] = {
            "match_id": match_id,
            "advice_id": advice_id,  # V2.1 fine-grained tracking
            "user_id": user_id,
            "feedback_type": feedback_type,
            "feedback_value": feedback_value,
            "prompt_variant": variant,
            "timestamp": datetime.now(UTC).isoformat(),
            # Optional: could add dimension/priority if parsed from advice_id
        }

        # Fire and forget POST to backend if configured
        if self.settings.feedback_api_url:

            async def _post_feedback(url: str, data: dict[str, Any]) -> None:
                try:
                    timeout = aiohttp.ClientTimeout(total=5)
                    async with aiohttp.ClientSession(timeout=timeout) as sess:
                        async with sess.post(url, json=data) as resp:
                            if resp.status == 429:
                                retry_after = resp.headers.get("Retry-After")
                                logger.warning(f"Advice feedback 429; Retry-After={retry_after}")
                            elif resp.status >= 400:
                                txt = await resp.text()
                                logger.warning(
                                    f"Advice feedback POST failed: {resp.status} - {txt}"
                                )
                            else:
                                logger.info("Advice feedback POST succeeded")
                except Exception as e:
                    logger.warning(f"Advice feedback POST error: {e}")

            asyncio.create_task(_post_feedback(self.settings.feedback_api_url, payload))
        else:
            logger.info("FEEDBACK_API_URL not set; skipping backend POST")

    async def play_tts_in_voice_channel(
        self,
        *,
        guild_id: int,
        voice_channel_id: int | str,
        audio_url: str,
        volume: float = 0.5,
        normalize: bool = False,
        max_seconds: int | None = None,
    ) -> bool:
        """Join a voice channel and play a remote MP3/HTTP audio.

        Preconditions:
        - FFmpeg must be installed and available in PATH.
        - Bot must have Connect/Speak permissions in the target channel.
        """
        normalized_channel_id = _normalize_voice_channel_id(voice_channel_id)
        if normalized_channel_id is None:
            logger.error(
                "Invalid voice channel id",
                extra={
                    "guild_id": guild_id,
                    "voice_channel_id": voice_channel_id,
                },
            )
            return False
        voice_channel_id = normalized_channel_id

        try:
            # [DEV MODE: Validate TTS audio URL]
            import os

            if os.getenv("CHIMERA_DEV_VALIDATE_DISCORD", "").lower() in ("1", "true", "yes"):
                from src.core.validation import validate_tts_audio_url

                tts_validation = validate_tts_audio_url(audio_url)
                if not tts_validation.is_valid:
                    logger.error(f"❌ TTS URL validation failed: {tts_validation.errors}")
                    if os.getenv("CHIMERA_DEV_STRICT", "").lower() in ("1", "true"):
                        raise ValueError(f"Invalid TTS audio URL: {tts_validation.errors}")
                if tts_validation.warnings:
                    logger.warning(f"⚠️  TTS URL warnings: {tts_validation.warnings}")
                logger.info(f"✅ TTS URL validation passed: {audio_url[:100]}...")

            playback_start = asyncio.get_running_loop().time()
            # Best-effort runtime dependency check for voice
            try:
                import discord.opus as _opus

                if not _opus.is_loaded():
                    logger.warning("Opus not loaded; ensure libopus is installed and discoverable")
            except Exception:
                logger.warning("Could not verify libopus; PyNaCl/libopus may be missing")
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                guild = await self.bot.fetch_guild(guild_id)

            channel = guild.get_channel(voice_channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(voice_channel_id)

            if not isinstance(channel, discord.VoiceChannel):
                logger.error("Target channel is not a voice channel")
                return False

            # Reuse or create voice client
            vc: discord.VoiceClient | None = cast(
                discord.VoiceClient | None,
                discord.utils.get(self.bot.voice_clients, guild=guild),
            )
            if vc and vc.is_connected():
                if vc.channel.id != channel.id:
                    await vc.move_to(channel)
            else:
                vc = await channel.connect()

            # Prepare FFmpeg source (reconnect flags support HTTP streaming resilience)
            ff_before = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
            ff_opts = "-vn"
            # Optional audio normalization
            if normalize:
                ff_opts = f"{ff_opts} -filter:a loudnorm"
            # Optional duration cap (seconds)
            if isinstance(max_seconds, int) and max_seconds > 0:
                ff_opts = f"{ff_opts} -t {max_seconds}"

            source = FFmpegPCMAudio(
                audio_url,
                before_options=ff_before,
                options=ff_opts,
            )
            player = discord.PCMVolumeTransformer(source, volume=volume)

            vc.play(player)
            while vc.is_playing():
                await asyncio.sleep(1)

            await vc.disconnect()
            try:
                elapsed = (asyncio.get_running_loop().time() - playback_start) * 1000
                logger.info(
                    "Voice playback finished guild=%s channel=%s ms=%.0f",
                    guild_id,
                    voice_channel_id,
                    elapsed,
                )
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"Voice playback error: {e}", exc_info=True)
            return False

    async def play_tts_bytes_in_voice_channel(
        self,
        *,
        guild_id: int,
        voice_channel_id: int | str,
        audio_bytes: bytes,
        volume: float = 0.5,
        normalize: bool = False,
        max_seconds: int | None = None,
    ) -> bool:
        """Join a voice channel and play in-memory MP3 bytes via FFmpeg pipe.

        Avoids disk I/O for lower latency.
        """
        normalized_channel_id = _normalize_voice_channel_id(voice_channel_id)
        if normalized_channel_id is None:
            logger.error(
                "Invalid voice channel id",
                extra={
                    "guild_id": guild_id,
                    "voice_channel_id": voice_channel_id,
                },
            )
            return False
        voice_channel_id = normalized_channel_id

        try:
            import io

            playback_start = asyncio.get_running_loop().time()

            # Opus/lib checks as above (best-effort)
            try:
                import discord.opus as _opus

                if not _opus.is_loaded():
                    logger.warning("Opus not loaded; ensure libopus is installed and discoverable")
            except Exception:
                logger.warning("Could not verify libopus; PyNaCl/libopus may be missing")

            guild = self.bot.get_guild(guild_id) or await self.bot.fetch_guild(guild_id)
            channel = guild.get_channel(voice_channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(voice_channel_id)
            if not isinstance(channel, discord.VoiceChannel):
                logger.error("Target channel is not a voice channel")
                return False

            vc: discord.VoiceClient | None = cast(
                discord.VoiceClient | None,
                discord.utils.get(self.bot.voice_clients, guild=guild),
            )
            if vc and vc.is_connected():
                if vc.channel.id != channel.id:
                    await vc.move_to(channel)
            else:
                vc = await channel.connect()

            # Prepare BytesIO stream and ffmpeg pipe
            audio_stream = io.BytesIO(audio_bytes)
            ff_opts = "-vn"
            if normalize:
                ff_opts = f"{ff_opts} -filter:a loudnorm"
            if isinstance(max_seconds, int) and max_seconds > 0:
                ff_opts = f"{ff_opts} -t {max_seconds}"

            source = FFmpegPCMAudio(audio_stream, pipe=True, options=ff_opts)
            player = discord.PCMVolumeTransformer(source, volume=volume)
            vc.play(player)

            while vc.is_playing():
                await asyncio.sleep(0.1)

            await vc.disconnect()
            try:
                elapsed = (asyncio.get_running_loop().time() - playback_start) * 1000
                logger.info(
                    "Voice (bytes) playback finished guild=%s channel=%s ms=%.0f",
                    guild_id,
                    voice_channel_id,
                    elapsed,
                )
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"Voice bytes playback error: {e}", exc_info=True)
            return False

    async def play_tts_to_user_channel(
        self,
        *,
        guild_id: int,
        user_id: int,
        audio_url: str,
        volume: float = 0.5,
        normalize: bool = False,
        max_seconds: int | None = None,
    ) -> bool:
        """Resolve user's current voice channel in guild and play audio there."""
        try:
            guild = self.bot.get_guild(guild_id) or await self.bot.fetch_guild(guild_id)
            member = guild.get_member(user_id) or await guild.fetch_member(user_id)
            if not member or not member.voice or not member.voice.channel:
                logger.warning("User %s not in a voice channel", user_id)
                return False
            channel_id = member.voice.channel.id
            return await self.play_tts_in_voice_channel(
                guild_id=guild_id,
                voice_channel_id=channel_id,
                audio_url=audio_url,
                volume=volume,
                normalize=normalize,
                max_seconds=max_seconds,
            )
        except Exception:
            logger.exception("Failed to resolve user voice channel for playback")
            return False

    async def enqueue_tts_playback(
        self,
        *,
        guild_id: int,
        voice_channel_id: int | str,
        audio_url: str,
        volume: float = 0.5,
        normalize: bool = False,
        max_seconds: int | None = None,
    ) -> bool:
        """Enqueue a playback job to the per-guild queue if service available.

        Args:
            guild_id: Discord guild (server) ID
            voice_channel_id: Voice channel ID
            audio_url: URL to audio file
            volume: Playback volume (0.0-1.0)
            normalize: Whether to normalize audio
            max_seconds: Maximum playback duration

        Returns:
            True if job was successfully enqueued/played, False otherwise
        """
        normalized_channel_id = _normalize_voice_channel_id(voice_channel_id)
        if normalized_channel_id is None:
            logger.error(
                "Invalid voice channel id",
                extra={
                    "guild_id": guild_id,
                    "voice_channel_id": voice_channel_id,
                },
            )
            return False
        voice_channel_id = normalized_channel_id

        if not self.voice_broadcast:
            # Fallback to direct playback
            logger.info(
                "voice_broadcast_unavailable_fallback",
                extra={
                    "guild_id": guild_id,
                    "channel_id": voice_channel_id,
                    "fallback_direct": True,
                },
            )
            return await self.play_tts_in_voice_channel(
                guild_id=guild_id,
                voice_channel_id=voice_channel_id,
                audio_url=audio_url,
                volume=volume,
                normalize=normalize,
                max_seconds=max_seconds,
            )

        return await self.voice_broadcast.enqueue(
            guild_id=guild_id,
            channel_id=voice_channel_id,
            audio_url=audio_url,
            volume=volume,
            normalize=normalize,
            max_seconds=max_seconds,
        )

    async def enqueue_tts_playback_bytes(
        self,
        *,
        guild_id: int,
        voice_channel_id: int | str,
        audio_bytes: bytes,
        volume: float = 0.5,
        normalize: bool = False,
        max_seconds: int | None = None,
    ) -> bool:
        """Enqueue in-memory audio for playback when broadcast service available, fallback to direct.

        Args:
            guild_id: Discord guild (server) ID
            voice_channel_id: Voice channel ID
            audio_bytes: In-memory audio data
            volume: Playback volume (0.0-1.0)
            normalize: Whether to normalize audio
            max_seconds: Maximum playback duration

        Returns:
            True if job was successfully enqueued/played, False otherwise
        """
        normalized_channel_id = _normalize_voice_channel_id(voice_channel_id)
        if normalized_channel_id is None:
            logger.error(
                "Invalid voice channel id",
                extra={
                    "guild_id": guild_id,
                    "voice_channel_id": voice_channel_id,
                },
            )
            return False
        voice_channel_id = normalized_channel_id

        if not self.voice_broadcast:
            logger.info(
                "voice_broadcast_bytes_unavailable_fallback",
                extra={
                    "guild_id": guild_id,
                    "channel_id": voice_channel_id,
                    "fallback_stream": True,
                },
            )
            return await self.play_tts_bytes_in_voice_channel(
                guild_id=guild_id,
                voice_channel_id=voice_channel_id,
                audio_bytes=audio_bytes,
                volume=volume,
                normalize=normalize,
                max_seconds=max_seconds,
            )

        return await self.voice_broadcast.enqueue_bytes(
            guild_id=guild_id,
            channel_id=voice_channel_id,
            audio_bytes=audio_bytes,
            volume=volume,
            normalize=normalize,
            max_seconds=max_seconds,
        )
