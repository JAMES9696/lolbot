"""
Discord adapter for handling bot interactions and commands.
This is the main frontend interface (CLI 1) for user interactions.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import discord
from discord import app_commands
from discord.ext import commands

from src.config import get_settings
from src.contracts.discord_interactions import (
    BindCommandOptions,
    CommandName,
    DeferredTask,
    EmbedColor,
    InteractionResponse,
)
from src.contracts.user_binding import (
    BindingRequest,
    BindingResponse,
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
            command_prefix=kwargs.get("command_prefix", "!"),
            intents=intents,
            **kwargs
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
        self.startup_time = datetime.utcnow()
        logger.info(f"Bot {self.user} is ready!")
        logger.info(f"Connected to {len(self.guilds)} guilds")

        # Set bot presence/status
        await self.change_presence(
            activity=discord.Game(name="/bind to link your LoL account"),
            status=discord.Status.online
        )


class DiscordAdapter:
    """Adapter for Discord interactions following hexagonal architecture."""

    def __init__(self) -> None:
        """Initialize the Discord adapter."""
        self.settings = get_settings()
        app_id = int(self.settings.discord_application_id) if self.settings.discord_application_id else None
        self.bot = ChimeraBot(command_prefix=self.settings.bot_prefix, application_id=app_id)
        self._setup_commands()
        self._setup_event_handlers()

    def _setup_commands(self) -> None:
        """Set up slash commands."""

        @self.bot.tree.command(
            name=CommandName.BIND.value,
            description="Link your Discord account with your League of Legends account"
        )
        @app_commands.describe(
            region="Your League of Legends server region (default: NA)",
            force_rebind="Force new binding even if already linked"
        )
        @app_commands.choices(region=[
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
        ])
        async def bind_command(
            interaction: discord.Interaction,
            region: str = "na1",
            force_rebind: bool = False
        ) -> None:
            """Handle /bind command."""
            await self._handle_bind_command(interaction, region, force_rebind)

        @self.bot.tree.command(
            name=CommandName.UNBIND.value,
            description="Unlink your Discord account from your League of Legends account"
        )
        async def unbind_command(interaction: discord.Interaction) -> None:
            """Handle /unbind command."""
            await self._handle_unbind_command(interaction)

        @self.bot.tree.command(
            name=CommandName.PROFILE.value,
            description="View your linked League of Legends profile"
        )
        async def profile_command(interaction: discord.Interaction) -> None:
            """Handle /profile command."""
            await self._handle_profile_command(interaction)

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
            interaction: discord.Interaction,
            error: app_commands.AppCommandError
        ) -> None:
            """Handle application command errors."""
            logger.error(f"Command error: {error}", exc_info=True)

            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=self._create_error_embed("An error occurred processing your command."),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=self._create_error_embed("An error occurred processing your command."),
                    ephemeral=True
                )

    async def _handle_bind_command(
        self,
        interaction: discord.Interaction,
        region: str,
        force_rebind: bool
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
            color=EmbedColor.INFO
        )
        embed.set_thumbnail(url="https://raw.githubusercontent.com/CommunityDragon/Docs/master/assets/riot-logo.png")
        embed.set_footer(text="This process is secure and uses official Riot OAuth")

        # For P1, we'll create a mock authorization URL
        # In production, this would call the backend to generate a real RSO URL
        mock_auth_url = self._generate_mock_auth_url(user_id, region)

        # Create button for authorization
        view = discord.ui.View(timeout=300)  # 5 minute timeout

        auth_button = discord.ui.Button(
            label="Authorize with Riot",
            style=discord.ButtonStyle.link,
            url=mock_auth_url,
            emoji="🎮"
        )
        view.add_item(auth_button)

        # Send response
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True  # Only visible to the user
        )

        # Log the binding attempt
        logger.info(f"User {user_id} initiated binding for region {region}")

        # TODO: In P1 completion, this would:
        # 1. Call the database adapter (CLI 2) to check existing binding
        # 2. Generate a real RSO authorization URL
        # 3. Store the state token for verification
        # 4. Handle the OAuth callback

    async def _handle_unbind_command(self, interaction: discord.Interaction) -> None:
        """Handle the /unbind slash command."""
        user_id = str(interaction.user.id)

        embed = discord.Embed(
            title="🔓 Account Unbinding",
            description=(
                "Your account binding has been removed.\n"
                "You can re-link your account at any time using `/bind`."
            ),
            color=EmbedColor.WARNING
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"User {user_id} unbound their account")

        # TODO: Call database adapter to remove binding

    async def _handle_profile_command(self, interaction: discord.Interaction) -> None:
        """Handle the /profile slash command."""
        user_id = str(interaction.user.id)

        # For P1, show a placeholder profile
        embed = discord.Embed(
            title="👤 Your Profile",
            description="Profile information will be available once you link your account.",
            color=EmbedColor.INFO
        )
        embed.add_field(name="Discord ID", value=user_id, inline=True)
        embed.add_field(name="Status", value="Not Linked", inline=True)
        embed.set_footer(text="Use /bind to link your League of Legends account")

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # TODO: Query database for actual binding status and show real profile

    def _generate_mock_auth_url(self, user_id: str, region: str) -> str:
        """Generate a mock authorization URL for P1 testing."""
        # In production, this would be a real Riot OAuth URL
        state_token = uuid4().hex
        return (
            f"https://auth.riotgames.com/authorize"
            f"?client_id=PROJECT_CHIMERA"
            f"&redirect_uri=http://localhost:8000/callback"
            f"&response_type=code"
            f"&scope=openid"
            f"&state={state_token}"
            f"&region={region}"
            f"&discord_id={user_id}"
        )

    def _create_error_embed(self, message: str) -> discord.Embed:
        """Create a standardized error embed."""
        return discord.Embed(
            title="❌ Error",
            description=message,
            color=EmbedColor.ERROR
        )

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
