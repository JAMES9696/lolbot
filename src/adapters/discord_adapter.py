"""
Discord adapter for handling bot interactions and commands.
This is the main frontend interface (CLI 1) for user interactions.
"""

import logging
from datetime import UTC, datetime
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from src.config import get_settings
from src.contracts.discord_interactions import (
    CommandName,
    EmbedColor,
)

# Configure logging
logger = logging.getLogger(__name__)


class ChimeraBot(commands.Bot):
    """Main Discord bot class for Project Chimera."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the bot with custom settings."""
        # Set up intents
        intents = discord.Intents.default()
        intents.message_content = True  # For future message commands
        intents.guilds = True
        intents.members = True

        super().__init__(
            command_prefix=kwargs.get("command_prefix", "!"), intents=intents, **kwargs
        )

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
        task_service: Any,
        match_history_service: Any,
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

        @self.bot.tree.command(
            name="讲道理",
            description="AI深度分析您最近的一场比赛（需要绑定账户）",
        )
        @app_commands.describe(
            match_index="要分析的比赛序号（1=最新，2=倒数第二场，以此类推）"
        )
        async def analyze_command(
            interaction: discord.Interaction, match_index: int = 1
        ) -> None:
            """Handle /讲道理 command - AI match analysis."""
            await self._handle_analyze_command(interaction, match_index)

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
        auth_url, state = await self.rso.generate_auth_url(user_id, region)

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
            embed.add_field(name="Summoner Name", value=binding.summoner_name, inline=True)
            embed.add_field(name="Region", value=binding.region.upper(), inline=True)
            embed.add_field(name="PUUID", value=binding.puuid, inline=False)
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
        self, interaction: discord.Interaction, match_index: int
    ) -> None:
        """Handle the /讲道理 slash command - AI match analysis.

        This is the core P3 implementation following the delayed response pattern.
        Must defer() within 3 seconds to prevent token expiration.
        """
        # [STEP 1: DELAYED RESPONSE - IRON LAW]
        # Must send deferred response within 3 seconds or interaction token expires
        await interaction.response.defer(ephemeral=False)  # Public loading state

        user_id = str(interaction.user.id)

        # [STEP 2: VALIDATE USER BINDING]
        binding = await self.db.get_user_binding(user_id)
        if not binding:
            error_embed = discord.Embed(
                title="❌ 账户未绑定",
                description=(
                    "您尚未绑定 Riot 账户，无法进行比赛分析。\n\n"
                    "请先使用 `/bind` 命令绑定您的英雄联盟账户。"
                ),
                color=EmbedColor.ERROR,
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        puuid = binding["puuid"]
        region = binding["region"]

        try:
            # [STEP 3: FETCH MATCH HISTORY]
            match_id_list = await self.match_history_service.get_match_id_list(
                puuid=puuid, region=region, count=20
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
            analysis_status = await self.match_history_service.get_analysis_status(
                target_match_id
            )

            if analysis_status:
                status = analysis_status.get("status")
                if status == "completed":
                    # Analysis already exists, return cached result
                    result_embed = discord.Embed(
                        title="✅ 分析结果（缓存）",
                        description=f"该比赛已完成分析。Match ID: `{target_match_id}`",
                        color=EmbedColor.SUCCESS,
                    )
                    await interaction.followup.send(embed=result_embed, ephemeral=False)
                    logger.info(f"Returned cached analysis for {target_match_id}")
                    return
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
                discord_user_id=user_id,
                puuid=puuid,
                match_id=target_match_id,
                region=region,
                match_index=match_index,
            )

            # [STEP 6: PUSH TASK TO CELERY QUEUE]
            task_id = await self.task_service.push_analysis_task(
                task_name=TASK_ANALYZE_MATCH, payload=payload.model_dump()
            )

            # [STEP 7: SEND LOADING MESSAGE]
            loading_embed = discord.Embed(
                title="🔄 AI 分析中...",
                description=(
                    f"正在对您的第 {match_index} 场比赛进行深度分析。\n\n"
                    "**分析内容包括：**\n"
                    "• 个人表现评分\n"
                    "• 关键时刻复盘\n"
                    "• 改进建议\n\n"
                    "_预计耗时：30-60秒_"
                ),
                color=EmbedColor.INFO,
            )
            loading_embed.set_footer(text=f"Task ID: {task_id[:8]}...")

            await interaction.followup.send(embed=loading_embed, ephemeral=False)

            logger.info(
                f"Analysis task pushed: user={user_id}, match={target_match_id}, task_id={task_id}"
            )

        except Exception as e:
            logger.error(f"Error in analyze command: {e}", exc_info=True)
            error_embed = self._create_error_embed(
                f"分析请求失败：{type(e).__name__}\n请稍后重试或联系管理员。"
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)

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

    def run(self) -> None:
        """Run the bot (blocking)."""
        try:
            self.bot.run(self.settings.discord_bot_token)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Bot crashed: {e}", exc_info=True)
            raise
