"""
Main entry point for Project Chimera Discord Bot.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.adapters.discord_adapter import DiscordAdapter
from src.config import get_settings


def setup_logging() -> None:
    """Set up logging configuration."""
    settings = get_settings()

    # Configure logging format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("chimera_bot.log", encoding="utf-8")
        ]
    )

    # Reduce discord.py logging verbosity unless in debug mode
    if not settings.debug_mode:
        logging.getLogger("discord").setLevel(logging.INFO)
        logging.getLogger("discord.http").setLevel(logging.WARNING)


async def health_check() -> None:
    """Perform basic health checks before starting the bot."""
    logger = logging.getLogger(__name__)
    settings = get_settings()

    logger.info("Performing health checks...")

    # Check Discord token is present
    if not settings.discord_bot_token:
        logger.error("Discord bot token not found in environment variables!")
        sys.exit(1)

    # Validate token format (basic check)
    if not settings.discord_bot_token.strip():
        logger.error("Discord bot token is empty!")
        sys.exit(1)

    logger.info("Health checks passed ✓")


def print_startup_banner() -> None:
    """Print a nice startup banner."""
    banner = """
    ╔══════════════════════════════════════════╗
    ║       Project Chimera - LoL Bot         ║
    ║         AI-Powered Match Analysis       ║
    ╚══════════════════════════════════════════╝
    """
    print(banner)


async def main() -> None:
    """Main async entry point."""
    logger = logging.getLogger(__name__)

    try:
        # Print banner
        print_startup_banner()

        # Setup logging
        setup_logging()

        logger.info("Starting Project Chimera Discord Bot...")

        # Perform health checks
        await health_check()

        # Create and start the Discord adapter
        adapter = DiscordAdapter()

        logger.info("Bot initialization complete. Connecting to Discord...")

        # Run the bot (this blocks)
        adapter.run()

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Run the main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    except Exception as e:
        print(f"Failed to start bot: {e}")
        sys.exit(1)