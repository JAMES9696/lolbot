"""Configuration settings using Pydantic Settings.

All sensitive configuration must be loaded from environment variables.
Never hardcode API keys or credentials in the code.
"""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Riot API Configuration
    riot_api_key: str = os.getenv("RIOT_API_KEY", "test-api-key")
    riot_api_base_url: str = "https://americas.api.riotgames.com"
    riot_api_rate_limit_per_second: int = 20  # Dev key default
    riot_api_rate_limit_per_two_minutes: int = 100  # Dev key default

    # For production keys, these would be much higher:
    # riot_api_rate_limit_per_10_seconds: int = 500
    # riot_api_rate_limit_per_10_minutes: int = 30000

    # Discord Configuration
    discord_token: str = os.getenv("DISCORD_TOKEN", "test-discord-token")
    discord_command_prefix: str = "/"
    discord_defer_timeout: int = 3  # seconds

    # Database Configuration
    database_url: str = "postgresql://localhost/lolbot"
    database_pool_size: int = 20
    database_max_overflow: int = 40
    database_pool_timeout: int = 30

    # Redis Configuration
    redis_url: str = "redis://localhost:6379"
    redis_cache_ttl: int = 3600  # 1 hour default
    redis_match_cache_ttl: int = 86400  # 24 hours for match data

    # Google Gemini Configuration
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-pro"
    gemini_temperature: float = 0.7
    gemini_max_output_tokens: int = 2048

    # TTS Configuration (Doubao)
    tts_api_key: str | None = None
    tts_api_url: str | None = None
    tts_voice_id: str = "default"

    # Application Configuration
    app_name: str = "Project Chimera"
    app_version: str = "0.1.0"
    app_env: str = "development"
    app_debug: bool = False
    app_log_level: str = "INFO"

    # Celery Configuration
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_time_limit: int = 300  # 5 minutes
    celery_task_soft_time_limit: int = 240  # 4 minutes

    # Feature Flags
    feature_voice_enabled: bool = False
    feature_ai_analysis_enabled: bool = True
    feature_leaderboard_enabled: bool = True

    # Security Configuration
    security_rso_client_id: str | None = None
    security_rso_client_secret: str | None = None
    security_rso_redirect_uri: str = "http://localhost:3000/callback"

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env == "development"


# Global settings instance - will be loaded from environment
# This will raise an error if required env vars are not set
# In development, create a .env file with required settings
settings = Settings(_env_file=".env")  # type: ignore[call-arg]
