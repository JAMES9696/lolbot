"""
Main entry point for Project Chimera Discord Bot.
"""

import asyncio
import logging
import sys

from src.adapters.discord_adapter import DiscordAdapter
from src.config import get_settings


def setup_logging() -> None:
    """Set up logging configuration."""
    settings = get_settings()

    # Configure logging format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=getattr(logging, settings.app_log_level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("chimera_bot.log", encoding="utf-8"),
        ],
    )

    # Reduce discord.py logging verbosity unless in debug mode
    if not settings.app_debug:
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

        # Initialize adapters
        logger.info("Initializing adapters...")

        # Database adapter
        from src.adapters.database import DatabaseAdapter

        db_adapter = DatabaseAdapter()
        await db_adapter.connect()

        # Redis adapter
        from src.adapters.redis_adapter import RedisAdapter

        redis_adapter = RedisAdapter()
        await redis_adapter.connect()

        # RSO adapter
        from src.adapters.rso_adapter import RSOAdapter

        rso_adapter = RSOAdapter(redis_client=redis_adapter)

        # Discord adapter
        discord_adapter = DiscordAdapter(
            rso_adapter=rso_adapter,
            db_adapter=db_adapter,
        )

        # RSO callback server
        from src.api.rso_callback import RSOCallbackServer

        callback_server = RSOCallbackServer(
            rso_adapter=rso_adapter,
            db_adapter=db_adapter,
            redis_adapter=redis_adapter,
        )

        # Start RSO callback server
        settings = get_settings()
        callback_port = 3000  # Default port for RSO callbacks
        await callback_server.start(host="0.0.0.0", port=callback_port)
        logger.info(f"RSO callback server listening on port {callback_port}")

        logger.info("All services initialized successfully")
        logger.info("Bot initialization complete. Connecting to Discord...")

        # Run the Discord bot (this blocks until shutdown)
        discord_adapter.run()

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        logger.info("Shutting down services...")
        if "db_adapter" in locals():
            await db_adapter.disconnect()
        if "redis_adapter" in locals():
            await redis_adapter.disconnect()
        if "callback_server" in locals():
            await callback_server.stop()
        logger.info("All services stopped")


if __name__ == "__main__":
    # Run the main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    except Exception as e:
        print(f"Failed to start bot: {e}")
        sys.exit(1)
