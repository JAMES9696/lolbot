"""Configuration settings using Pydantic Settings.

All sensitive configuration must be loaded from environment variables.
Never hardcode API keys or credentials in the code.
"""

from pydantic import AliasChoices, Field
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
    riot_api_key: str = Field(..., validation_alias=AliasChoices("RIOT_API_KEY"))
    riot_api_base_url: str = Field("https://americas.api.riotgames.com", alias="RIOT_API_BASE_URL")
    riot_api_rate_limit_per_second: int = Field(20, alias="RIOT_API_RATE_LIMIT_PER_SECOND")
    riot_api_rate_limit_per_two_minutes: int = Field(100, alias="RIOT_API_RATE_LIMIT_PER_TWO_MINUTES")

    # Discord Configuration
    discord_bot_token: str = Field(..., validation_alias=AliasChoices("DISCORD_BOT_TOKEN", "DISCORD_TOKEN"))
    discord_command_prefix: str = Field("/", alias="DISCORD_COMMAND_PREFIX")
    discord_defer_timeout: int = Field(3, alias="DISCORD_DEFER_TIMEOUT")

    # Database Configuration
    database_url: str = Field("postgresql://localhost/lolbot", alias="DATABASE_URL")
    database_pool_size: int = Field(20, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(40, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout: int = Field(30, alias="DATABASE_POOL_TIMEOUT")

    # Redis Configuration
    redis_url: str = Field("redis://localhost:6379", alias="REDIS_URL")
    redis_cache_ttl: int = Field(3600, alias="REDIS_CACHE_TTL")
    redis_match_cache_ttl: int = Field(86400, alias="REDIS_MATCH_CACHE_TTL")

    # Google Gemini Configuration
    gemini_api_key: str | None = Field(None, alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-pro", alias="GEMINI_MODEL")
    gemini_temperature: float = Field(0.7, alias="GEMINI_TEMPERATURE")
    gemini_max_output_tokens: int = Field(2048, alias="GEMINI_MAX_OUTPUT_TOKENS")

    # TTS Configuration (Doubao)
    tts_api_key: str | None = Field(None, alias="TTS_API_KEY")
    tts_api_url: str | None = Field(None, alias="TTS_API_URL")
    tts_voice_id: str = Field("default", alias="TTS_VOICE_ID")

    # Application Configuration
    app_name: str = Field("Project Chimera", alias="APP_NAME")
    app_version: str = Field("0.1.0", alias="APP_VERSION")
    app_env: str = Field("development", alias="APP_ENV")
    app_debug: bool = Field(False, alias="APP_DEBUG")
    app_log_level: str = Field("INFO", alias="APP_LOG_LEVEL")

    # Celery Configuration
    celery_broker_url: str = Field("redis://localhost:6379/0", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field("redis://localhost:6379/1", alias="CELERY_RESULT_BACKEND")
    celery_task_time_limit: int = Field(300, alias="CELERY_TASK_TIME_LIMIT")
    celery_task_soft_time_limit: int = Field(240, alias="CELERY_TASK_SOFT_TIME_LIMIT")

    # Feature Flags
    feature_voice_enabled: bool = Field(False, alias="FEATURE_VOICE_ENABLED")
    feature_ai_analysis_enabled: bool = Field(True, alias="FEATURE_AI_ANALYSIS_ENABLED")
    feature_leaderboard_enabled: bool = Field(True, alias="FEATURE_LEADERBOARD_ENABLED")

    # Security Configuration
    security_rso_client_id: str | None = Field(None, alias="SECURITY_RSO_CLIENT_ID")
    security_rso_client_secret: str | None = Field(None, alias="SECURITY_RSO_CLIENT_SECRET")
    security_rso_redirect_uri: str = Field("http://localhost:3000/callback", alias="SECURITY_RSO_REDIRECT_URI")

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
settings = Settings(_env_file=".env")

