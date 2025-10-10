"""
Main entry point for 蔚-上城人 Discord Bot.
"""

import asyncio
import logging
import os
import shutil
import sys

from src.adapters.discord_adapter import DiscordAdapter
from src.core.observability import configure_stdlib_json_logging
from src.config.settings import get_settings


def setup_logging() -> None:
    """Set up structured JSON logging for both stdout and file.

    KISS: write logs to a stable path under `logs/` and stdout.
    """
    settings = get_settings()

    # Ensure logs directory exists to avoid silent handler failures
    try:
        os.makedirs("logs", exist_ok=True)
        file_target = os.path.join("logs", "chimera_bot.log")
    except Exception:
        # Fallback to CWD if logs/ is not writable
        file_target = "chimera_bot.log"

    # Configure structured JSON logging via structlog bridge
    configure_stdlib_json_logging(
        level=settings.app_log_level,
        file_target=file_target,
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
    # RSO production guardrails
    if settings.is_production:
        # Disallow mock RSO in production
        if settings.mock_rso_enabled:
            logger.error(
                "MOCK_RSO_ENABLED=true is forbidden in production. Disable mock RSO to continue."
            )
            sys.exit(1)
        # Require production RSO credentials for /bind availability
        if not settings.security_rso_client_id or not settings.security_rso_client_secret:
            logger.error(
                "Production requires SECURITY_RSO_CLIENT_ID/SECURITY_RSO_CLIENT_SECRET for /bind."
            )
            sys.exit(1)
        # Enforce HTTPS redirect_uri in production
        try:
            from urllib.parse import urlparse

            ru = urlparse(settings.security_rso_redirect_uri)
            if ru.scheme.lower() != "https":
                logger.error("SECURITY_RSO_REDIRECT_URI must use HTTPS in production.")
                sys.exit(1)
        except Exception:
            logger.error("Invalid SECURITY_RSO_REDIRECT_URI format.")
            sys.exit(1)


def voice_preflight() -> None:
    """Perform voice feature preflight checks when FEATURE_VOICE_ENABLED=true."""
    logger = logging.getLogger(__name__)
    from src.config.settings import get_settings

    settings = get_settings()
    if not settings.feature_voice_enabled:
        return
    # ffmpeg
    if shutil.which("ffmpeg") is None:
        logger.error("FFmpeg not found in PATH; required for voice playback.")
        sys.exit(1)
    # PyNaCl / libopus
    try:
        import nacl.secret  # noqa: F401
    except Exception:
        logger.warning("PyNaCl not importable; Discord voice may fail. Please pip install PyNaCl.")
    try:
        import discord.opus as _opus  # type: ignore

        if not _opus.is_loaded():
            # Try common macOS Homebrew paths
            opus_paths = [
                "/opt/homebrew/lib/libopus.dylib",  # Apple Silicon
                "/usr/local/lib/libopus.dylib",  # Intel Mac
                "libopus.0.dylib",  # System search
            ]
            for opus_path in opus_paths:
                try:
                    _opus.load_opus(opus_path)
                    if _opus.is_loaded():
                        logger.info(f"discord.opus loaded from {opus_path}")
                        break
                except Exception:
                    continue

            if not _opus.is_loaded():
                logger.warning(
                    "discord.opus not loaded; ensure libopus is installed and discoverable."
                )
    except Exception:
        logger.warning("Could not verify discord.opus; ensure libopus is installed.")


def print_startup_banner() -> None:
    """Print a nice startup banner."""
    banner = """
    ╔══════════════════════════════════════════╗
    ║         蔚-上城人 - LoL Bot             ║
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

        logger.info("Starting 蔚-上城人 Discord Bot...")

        # Perform health checks
        await health_check()
        voice_preflight()

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

        # RSO adapter (uses factory to select real/mock based on config)
        from src.adapters.rso_factory import create_rso_adapter

        rso_adapter = create_rso_adapter(redis_client=redis_adapter)

        # Optional services for /讲道理 (enable when available)
        from src.core.services import CeleryTaskService, MatchHistoryService
        from src.adapters.riot_api import RiotAPIAdapter

        task_service = CeleryTaskService()
        match_history_service = MatchHistoryService(riot_api=RiotAPIAdapter(), db=db_adapter)

        # Discord adapter with services injected (enables /讲道理 registration)
        discord_adapter = DiscordAdapter(
            rso_adapter=rso_adapter,
            db_adapter=db_adapter,
            task_service=task_service,
            match_history_service=match_history_service,
        )

        # RSO callback server
        from src.api.rso_callback import RSOCallbackServer

        callback_server = RSOCallbackServer(
            rso_adapter=rso_adapter,
            db_adapter=db_adapter,
            redis_adapter=redis_adapter,
            discord_adapter=discord_adapter,
        )

        # Start RSO callback server
        settings = get_settings()
        callback_port = int(os.getenv("CALLBACK_PORT", "3000"))
        try:
            await callback_server.start(host="0.0.0.0", port=callback_port)
            logger.info(
                f"RSO callback server listening on port {callback_port} (from env CALLBACK_PORT)"
            )
        except OSError as e:
            # Common on macOS when a stale Python process still holds :3000 (Errno 48)
            if getattr(e, "errno", None) in (48, 98):  # EADDRINUSE (macOS/Linux)
                logger.error(
                    "Port %d is already in use. Another process is listening on :%d.",
                    callback_port,
                    callback_port,
                )
                logger.warning(
                    "Continuing WITHOUT RSO callback server. /bind will be disabled until the port is free."
                )
            else:
                # Unknown bind error: continue without callback server but warn loudly
                logger.error("RSO callback server failed to start: %s", e)
                logger.warning("Continuing WITHOUT RSO callback server due to unexpected error.")

        logger.info("All services initialized successfully")
        logger.info("Bot initialization complete. Connecting to Discord...")

        # Run the Discord bot (async, blocks until shutdown)
        await discord_adapter.start_async()

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        logger.info("Shutting down services...")
        # Stop Discord bot first to prevent new work during teardown
        if "discord_adapter" in locals():
            try:
                await discord_adapter.stop()
            except Exception as e:
                logger.warning(f"Failed to stop Discord adapter cleanly: {e}")
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
