"""
Configuration management using Pydantic Settings.
All sensitive configuration loaded from environment variables.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Discord Configuration
    discord_bot_token: str = Field(
        ...,
        description="Discord Bot Token from Discord Developer Portal",
        alias="DISCORD_BOT_TOKEN",
    )

    discord_application_id: str | None = Field(
        None,
        description="Discord Application ID for slash commands",
        alias="DISCORD_APPLICATION_ID",
    )

    discord_guild_id: str | None = Field(
        None, description="Optional: Guild ID for development testing", alias="DISCORD_GUILD_ID"
    )

    # Riot API Configuration (for future integration)
    riot_api_key: str | None = Field(None, description="Riot Games API Key", alias="RIOT_API_KEY")

    riot_region: str = Field("na1", description="Default Riot API region", alias="RIOT_REGION")

    # Database Configuration (for future integration)
    database_url: str | None = Field(
        None, description="PostgreSQL database connection URL", alias="DATABASE_URL"
    )

    redis_url: str = Field(
        "redis://localhost:6379",
        description="Redis connection URL for caching and task queue",
        alias="REDIS_URL",
    )

    # RSO OAuth Configuration (for future integration)
    riot_client_id: str | None = Field(
        None, description="Riot OAuth Client ID for RSO", alias="RIOT_CLIENT_ID"
    )

    riot_client_secret: str | None = Field(
        None, description="Riot OAuth Client Secret for RSO", alias="RIOT_CLIENT_SECRET"
    )

    riot_redirect_uri: str | None = Field(
        None, description="OAuth redirect URI for RSO callback", alias="RIOT_REDIRECT_URI"
    )

    # Bot Configuration
    bot_prefix: str = Field(
        "!", description="Command prefix for text commands (if any)", alias="BOT_PREFIX"
    )

    debug_mode: bool = Field(False, description="Enable debug logging", alias="DEBUG_MODE")

    log_level: str = Field("INFO", description="Logging level", alias="LOG_LEVEL")


# Singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
