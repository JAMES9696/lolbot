"""
Configuration settings using Pydantic Settings.

All sensitive configuration must be loaded from environment variables.
Never hardcode API keys or credentials in the code.
"""

from pydantic import AliasChoices, Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Ensure .env values take precedence over system environment variables.
    # This prevents accidental overrides from CI/host environments.
    # Order: init kwargs > .env (dotenv) > env vars > file secrets
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ):
        return (
            init_settings,
            dotenv_settings,
            env_settings,
            file_secret_settings,
        )

    # Riot API Configuration
    riot_api_key: str = Field(..., validation_alias=AliasChoices("RIOT_API_KEY"))
    riot_api_base_url: str = Field("https://americas.api.riotgames.com", alias="RIOT_API_BASE_URL")
    riot_api_rate_limit_per_second: int = Field(20, alias="RIOT_API_RATE_LIMIT_PER_SECOND")
    riot_api_rate_limit_per_two_minutes: int = Field(
        100, alias="RIOT_API_RATE_LIMIT_PER_TWO_MINUTES"
    )

    # Discord Configuration
    discord_bot_token: str = Field(
        ..., validation_alias=AliasChoices("DISCORD_BOT_TOKEN", "DISCORD_TOKEN")
    )
    discord_command_prefix: str = Field("/", alias="DISCORD_COMMAND_PREFIX")
    discord_defer_timeout: int = Field(3, alias="DISCORD_DEFER_TIMEOUT")
    discord_application_id: str | None = Field(None, alias="DISCORD_APPLICATION_ID")
    discord_guild_id: str | None = Field(None, alias="DISCORD_GUILD_ID")
    bot_prefix: str = Field("!", alias="BOT_PREFIX")

    # Database Configuration
    database_url: str = Field("postgresql://localhost/lolbot", alias="DATABASE_URL")
    database_pool_size: int = Field(20, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(40, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout: int = Field(30, alias="DATABASE_POOL_TIMEOUT")

    # Redis Configuration
    redis_url: str = Field("redis://localhost:6379", alias="REDIS_URL")
    redis_cache_ttl: int = Field(3600, alias="REDIS_CACHE_TTL")
    redis_match_cache_ttl: int = Field(86400, alias="REDIS_MATCH_CACHE_TTL")
    llm_cache_enabled: bool = Field(True, alias="LLM_CACHE_ENABLED")
    analysis_cache_enabled: bool = Field(True, alias="ANALYSIS_CACHE_ENABLED")

    # Google Gemini Configuration
    gemini_api_key: str | None = Field(None, alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-pro", alias="GEMINI_MODEL")
    gemini_temperature: float = Field(0.7, alias="GEMINI_TEMPERATURE")
    gemini_max_output_tokens: int = Field(2048, alias="GEMINI_MAX_OUTPUT_TOKENS")
    gemini_json_mode_enabled: bool = Field(False, alias="GEMINI_JSON_MODE_ENABLED")

    # OpenAI-compatible (OhMyGPT) Configuration
    # When configured (or when LLM_PROVIDER=openai), the system will use the
    # OpenAI-compatible Chat Completions API at OPENAI_API_BASE for LLM calls.
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    openai_api_base: str | None = Field(None, alias="OPENAI_API_BASE")
    openai_model: str | None = Field(None, alias="OPENAI_MODEL")
    openai_temperature: float = Field(0.7, alias="OPENAI_TEMPERATURE")
    openai_max_tokens: int = Field(2048, alias="OPENAI_MAX_TOKENS")

    # LLM Provider selection (gemini | openai)
    llm_provider: str = Field("gemini", alias="LLM_PROVIDER")

    # FinOps pricing (USD per 1K tokens)
    finops_prompt_token_price_usd: float = Field(0.0005, alias="FINOPS_PROMPT_TOKEN_PRICE_USD")
    finops_completion_token_price_usd: float = Field(
        0.0015, alias="FINOPS_COMPLETION_TOKEN_PRICE_USD"
    )
    finops_monthly_budget_usd: float = Field(100.0, alias="FINOPS_MONTHLY_BUDGET_USD")

    # Chaos Engineering toggles
    chaos_redis_down: bool = Field(False, alias="CHAOS_REDIS_DOWN")
    chaos_llm_latency_ms: int = Field(0, alias="CHAOS_LLM_LATENCY_MS")
    chaos_llm_error_rate: float = Field(0.0, alias="CHAOS_LLM_ERROR_RATE")

    # TTS Configuration (Doubao)
    tts_api_key: str | None = Field(None, alias="TTS_API_KEY")
    tts_api_url: str | None = Field(None, alias="TTS_API_URL")
    tts_app_id: str | None = Field(None, alias="TTS_APP_ID")
    tts_access_token: str | None = Field(None, alias="TTS_ACCESS_TOKEN")
    tts_cluster_id: str | None = Field(None, alias="TTS_CLUSTER_ID")
    tts_user_id: str | None = Field(None, alias="TTS_USER_ID")
    tts_voice_id: str = Field("zh_female_vv_uranus_bigtts", alias="TTS_VOICE_ID")
    tts_timeout_seconds: int = Field(15, alias="TTS_TIMEOUT_SECONDS")
    tts_upload_timeout_seconds: int = Field(10, alias="TTS_UPLOAD_TIMEOUT_SECONDS")

    # Voice Playback Default Parameters
    voice_volume_default: float = Field(0.5, alias="VOICE_VOLUME_DEFAULT")
    voice_normalize_default: bool = Field(False, alias="VOICE_NORMALIZE_DEFAULT")
    voice_max_seconds_default: int | None = Field(90, alias="VOICE_MAX_SECONDS_DEFAULT")
    voice_button_ttl_seconds: int = Field(900, alias="VOICE_BUTTON_TTL_SECONDS")

    # Audio Storage Configuration (Local file serving)
    audio_storage_path: str = Field("static/audio", alias="AUDIO_STORAGE_PATH")
    audio_base_url: str = Field("http://localhost:3000/static/audio", alias="AUDIO_BASE_URL")
    audio_s3_endpoint: str | None = Field(None, alias="AUDIO_S3_ENDPOINT")
    audio_s3_region: str | None = Field(None, alias="AUDIO_S3_REGION")
    audio_s3_bucket: str | None = Field(None, alias="AUDIO_S3_BUCKET")
    audio_s3_access_key: str | None = Field(None, alias="AUDIO_S3_ACCESS_KEY")
    audio_s3_secret_key: str | None = Field(None, alias="AUDIO_S3_SECRET_KEY")
    audio_s3_public_base_url: str | None = Field(
        None,
        alias="AUDIO_S3_PUBLIC_BASE_URL",
        description="Optional override for public audio URL base",
    )
    audio_s3_path_style: bool = Field(True, alias="AUDIO_S3_PATH_STYLE")
    build_visual_storage_path: str = Field("static/builds", alias="BUILD_VISUAL_STORAGE_PATH")
    build_visual_base_url: str = Field(
        "http://localhost:3000/static/builds", alias="BUILD_VISUAL_BASE_URL"
    )

    # S3/CDN Configuration (for TTS audio delivery)
    aws_access_key_id: str | None = Field(None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(None, alias="AWS_SECRET_ACCESS_KEY")
    aws_s3_bucket: str | None = Field(None, alias="AWS_S3_BUCKET")
    aws_s3_region: str = Field("us-east-1", alias="AWS_S3_REGION")
    cdn_base_url: str | None = Field(None, alias="CDN_BASE_URL")
    audio_file_ttl_seconds: int = Field(604800, alias="AUDIO_FILE_TTL_SECONDS")  # 7 days

    # Application Configuration
    app_name: str = Field("蔚-上城人", alias="APP_NAME")
    app_version: str = Field("0.1.0", alias="APP_VERSION")
    app_env: str = Field("development", alias="APP_ENV")
    app_debug: bool = Field(False, alias="APP_DEBUG")
    app_log_level: str = Field("INFO", alias="APP_LOG_LEVEL")

    # Celery Configuration (for /讲道理 async tasks)
    celery_broker_url: str = Field("redis://localhost:6379/0", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field("redis://localhost:6379/1", alias="CELERY_RESULT_BACKEND")
    celery_task_time_limit: int = Field(300, alias="CELERY_TASK_TIME_LIMIT")
    celery_task_soft_time_limit: int = Field(240, alias="CELERY_TASK_SOFT_TIME_LIMIT")
    celery_worker_concurrency: int = Field(4, alias="CELERY_WORKER_CONCURRENCY")
    celery_task_serializer: str = Field("json", alias="CELERY_TASK_SERIALIZER")
    celery_result_serializer: str = Field("json", alias="CELERY_RESULT_SERIALIZER")
    celery_accept_content: str = Field("json", alias="CELERY_ACCEPT_CONTENT")

    # Feature Flags
    feature_voice_enabled: bool = Field(False, alias="FEATURE_VOICE_ENABLED")
    feature_voice_streaming_enabled: bool = Field(False, alias="FEATURE_VOICE_STREAMING")
    feature_ai_analysis_enabled: bool = Field(True, alias="FEATURE_AI_ANALYSIS_ENABLED")
    feature_leaderboard_enabled: bool = Field(True, alias="FEATURE_LEADERBOARD_ENABLED")
    feature_team_build_enrichment_enabled: bool = Field(
        True, alias="FEATURE_TEAM_BUILD_ENRICH_ENABLED"
    )
    feature_opgg_enrichment_enabled: bool = Field(False, alias="FEATURE_OPGG_ENRICH_ENABLED")
    arena_data_version: str = Field(
        "15.5",
        alias="ARENA_DATA_VERSION",
        description="Pinned Arena data version; must match assets/arena/augments.zh_cn.json",
    )
    # V2 experiments and feedback UI
    feature_team_analysis_enabled: bool = Field(False, alias="FEATURE_TEAM_ANALYSIS_ENABLED")
    feature_feedback_enabled: bool = Field(True, alias="FEATURE_FEEDBACK_ENABLED")
    # Team auto TTS playback (post-webhook, no button)
    feature_team_auto_tts_enabled: bool = Field(False, alias="FEATURE_TEAM_AUTO_TTS_ENABLED")
    # UI ASCII-SAFE rendering (avoid emojis/ANSI in code blocks and labels)
    ui_ascii_safe: bool = Field(
        False,
        validation_alias=AliasChoices("UI_ASCII_SAFE", "CHIMERA_ASCII_SAFE"),
    )

    # V2.1 Instructional Analysis (Timeline Evidence)
    feature_v21_prescriptive_enabled: bool = Field(
        default=False,
        alias="FEATURE_V21_PRESCRIPTIVE_ENABLED",
        description="Enable V2.1 Timeline evidence extraction for fact-based improvement suggestions",
    )

    # V2.2 Personalization (User Profile-based Analysis Customization)
    feature_v22_personalization_enabled: bool = Field(
        default=False,
        alias="FEATURE_V22_PERSONALIZATION_ENABLED",
        description="Enable V2.2 user profile loading and personalized analysis tone/suggestions",
    )

    # Security Configuration
    security_rso_client_id: str | None = Field(None, alias="SECURITY_RSO_CLIENT_ID")
    security_rso_client_secret: str | None = Field(None, alias="SECURITY_RSO_CLIENT_SECRET")
    security_rso_redirect_uri: str = Field(
        "http://localhost:3000/callback", alias="SECURITY_RSO_REDIRECT_URI"
    )

    # Mock RSO for development testing (bypasses Production API Key requirement)
    mock_rso_enabled: bool = Field(False, alias="MOCK_RSO_ENABLED")

    # Frontend -> Backend feedback collection endpoint (optional)
    # Example: https://cli2.example.com/api/v1/feedback
    feedback_api_url: str | None = Field(None, alias="FEEDBACK_API_URL")

    # Broadcast webhook authentication for post-game voice announcements
    broadcast_webhook_secret: str | None = Field(None, alias="BROADCAST_WEBHOOK_SECRET")
    # Callback/broadcast server base URL for voice jobs (bot process HTTP server)
    # Default aligns with RSOCallbackServer.start(..., port=3000) to avoid port mismatch.
    broadcast_server_url: str = Field("http://localhost:3000", alias="BROADCAST_SERVER_URL")
    # Alerting → Discord bridge
    alerts_discord_webhook: str | None = Field(None, alias="ALERTS_DISCORD_WEBHOOK")
    alert_webhook_secret: str | None = Field(None, alias="ALERT_WEBHOOK_SECRET")

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env == "development"

    # Backwards-compatible property so existing code using settings.tts_enabled works
    @property
    def tts_enabled(self) -> bool:
        """Feature toggle for TTS synthesis (maps to FEATURE_VOICE_ENABLED).

        Returns:
            True if voice features are enabled via feature flag.
        """
        return bool(self.feature_voice_enabled)


# Global settings instance - will be loaded from environment
# This will raise an error if required env vars are not set
# In development, create a .env file with required settings
# MyPy doesn't understand Pydantic Settings env loading
settings = Settings()  # type: ignore[call-arg]


def get_settings() -> Settings:
    """Get the global settings instance.

    This function provides dependency injection support for settings.
    """
    return settings
