"""Database adapter using asyncpg for PostgreSQL.

This adapter handles all database operations asynchronously using asyncpg,
which provides high-performance async PostgreSQL connectivity.
"""

import json
import logging
import asyncio
import random
from datetime import UTC, datetime
from typing import Any

import asyncpg

from src.config.settings import settings
from src.core.ports import DatabasePort
from src.core.observability import llm_debug_wrapper

logger = logging.getLogger(__name__)


class DatabaseAdapter(DatabasePort):
    """Database adapter implementation using asyncpg.

    Features:
    - Async connection pooling for high concurrency
    - JSONB support for complex match data
    - Timezone-aware timestamps
    - Proper error handling and logging
    """

    def __init__(self) -> None:
        """Initialize database adapter."""
        self._pool: Any = None  # asyncpg.Pool (untyped library)
        logger.info("Database adapter initialized")

    async def connect(self) -> None:
        """Create database connection pool.

        This should be called once at application startup.
        """
        if self._pool is not None:
            logger.warning("Database pool already exists")
            return

        try:
            self._pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=10,
                max_size=settings.database_pool_size,
                max_inactive_connection_lifetime=300,
                command_timeout=settings.database_pool_timeout,
            )
            logger.info("Database connection pool created successfully")

            # Create tables if they don't exist
            await self._initialize_schema()

        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise

    async def disconnect(self) -> None:
        """Close database connection pool.

        This should be called at application shutdown.
        """
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Database connection pool closed")

    async def _initialize_schema(self) -> None:
        """Initialize database schema.

        Creates required tables if they don't exist.
        """
        if not self._pool:
            raise RuntimeError("Database pool not initialized")

        async with self._pool.acquire() as conn:
            # Create user_bindings table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_bindings (
                    discord_id VARCHAR(255) PRIMARY KEY,
                    puuid VARCHAR(255) NOT NULL UNIQUE,
                    summoner_name VARCHAR(255) NOT NULL,
                    summoner_id VARCHAR(255) NOT NULL,
                    region VARCHAR(10) NOT NULL DEFAULT 'na1',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_user_bindings_puuid
                ON user_bindings(puuid);

                CREATE INDEX IF NOT EXISTS idx_user_bindings_updated
                ON user_bindings(updated_at);
            """
            )

            # Create match_data table with JSONB columns
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS match_data (
                    match_id VARCHAR(255) PRIMARY KEY,
                    region VARCHAR(10) NOT NULL,
                    game_creation BIGINT NOT NULL,
                    game_duration INTEGER NOT NULL,
                    match_data JSONB NOT NULL,
                    timeline_data JSONB,
                    analysis_data JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_match_data_creation
                ON match_data(game_creation DESC);

                CREATE INDEX IF NOT EXISTS idx_match_data_region
                ON match_data(region);

                -- GIN index for JSONB queries
                CREATE INDEX IF NOT EXISTS idx_match_data_participants
                ON match_data USING gin ((match_data->'metadata'->'participants'));
            """
            )

            # Create match_participants table for efficient queries
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS match_participants (
                    id SERIAL PRIMARY KEY,
                    match_id VARCHAR(255) NOT NULL REFERENCES match_data(match_id) ON DELETE CASCADE,
                    puuid VARCHAR(255) NOT NULL,
                    champion_id INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    win BOOLEAN NOT NULL,
                    kills INTEGER NOT NULL,
                    deaths INTEGER NOT NULL,
                    assists INTEGER NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(match_id, puuid)
                );

                CREATE INDEX IF NOT EXISTS idx_match_participants_puuid
                ON match_participants(puuid);

                CREATE INDEX IF NOT EXISTS idx_match_participants_match
                ON match_participants(match_id);
            """
            )

            # Create match_analytics table for V1 scoring results (P3)
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS match_analytics (
                    id SERIAL PRIMARY KEY,
                    match_id VARCHAR(255) NOT NULL UNIQUE,
                    puuid VARCHAR(255) NOT NULL,
                    region VARCHAR(10) NOT NULL,

                    -- Analysis status tracking
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    error_message TEXT,

                    -- V1 Scoring Results (JSONB for flexibility)
                    score_data JSONB NOT NULL,

                    -- P4: LLM analysis results (to be populated later)
                    llm_narrative TEXT,
                    llm_metadata JSONB,

                    -- Metadata
                    algorithm_version VARCHAR(20) DEFAULT 'v1',
                    processing_duration_ms FLOAT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                    -- Foreign key to match_data
                    CONSTRAINT fk_match_analytics_match
                        FOREIGN KEY (match_id) REFERENCES match_data(match_id)
                        ON DELETE CASCADE
                );

                -- Indexes for efficient queries
                CREATE INDEX IF NOT EXISTS idx_match_analytics_match_id
                    ON match_analytics(match_id);

                CREATE INDEX IF NOT EXISTS idx_match_analytics_puuid
                    ON match_analytics(puuid);

                CREATE INDEX IF NOT EXISTS idx_match_analytics_status
                    ON match_analytics(status);

                CREATE INDEX IF NOT EXISTS idx_match_analytics_created
                    ON match_analytics(created_at DESC);

                -- GIN index for JSONB score_data queries
                CREATE INDEX IF NOT EXISTS idx_match_analytics_score_data
                    ON match_analytics USING gin (score_data);
            """
            )

            logger.info("Database schema initialized")

            # V2.2 Personalization profile table (create if missing)
            try:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        discord_user_id VARCHAR(255) PRIMARY KEY,
                        puuid VARCHAR(255) NOT NULL,
                        profile_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                        last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );

                    CREATE INDEX IF NOT EXISTS idx_user_profiles_puuid
                        ON user_profiles(puuid);
                    CREATE INDEX IF NOT EXISTS idx_user_profiles_updated
                        ON user_profiles(last_updated DESC);
                    """
                )
            except Exception as e:
                logger.error(f"Failed to ensure user_profiles table: {e}")

            # A/B testing and feedback tables (V1.2)
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ab_experiment_metadata (
                    id BIGSERIAL PRIMARY KEY,
                    match_id VARCHAR(255) NOT NULL,
                    discord_user_id VARCHAR(255) NOT NULL,
                    ab_cohort VARCHAR(1) NOT NULL CHECK (ab_cohort IN ('A','B')),
                    variant_id VARCHAR(255) NOT NULL,
                    prompt_version VARCHAR(4) NOT NULL,
                    prompt_template VARCHAR(255) NOT NULL,
                    ab_seed VARCHAR(255) NOT NULL,
                    llm_input_tokens INTEGER,
                    llm_output_tokens INTEGER,
                    llm_api_cost_usd DOUBLE PRECISION,
                    llm_latency_ms INTEGER,
                    total_processing_time_ms INTEGER,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_ab_meta_match
                    ON ab_experiment_metadata(match_id);
                CREATE INDEX IF NOT EXISTS idx_ab_meta_user
                    ON ab_experiment_metadata(discord_user_id);

                CREATE TABLE IF NOT EXISTS feedback_events (
                    id BIGSERIAL PRIMARY KEY,
                    match_id VARCHAR(255) NOT NULL,
                    discord_user_id VARCHAR(255) NOT NULL,
                    feedback_type VARCHAR(32) NOT NULL,
                    prompt_variant VARCHAR(1),
                    variant_id VARCHAR(255),
                    feedback_value INTEGER,
                    feedback_comment TEXT,
                    interaction_id VARCHAR(255),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_feedback_match
                    ON feedback_events(match_id);
                CREATE INDEX IF NOT EXISTS idx_feedback_user
                    ON feedback_events(discord_user_id);
                CREATE INDEX IF NOT EXISTS idx_feedback_interaction
                    ON feedback_events(interaction_id);
                """
            )

    @llm_debug_wrapper(
        capture_result=True,
        capture_args=True,
        log_level="INFO",
        add_metadata={"layer": "db", "table": "user_bindings", "op": "upsert"},
    )
    async def save_user_binding(self, discord_id: str, puuid: str, summoner_name: str) -> bool:
        """Save Discord ID to PUUID binding.

        Args:
            discord_id: Discord user ID
            puuid: Riot PUUID
            summoner_name: Summoner name

        Returns:
            True if successful, False otherwise
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return False

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_bindings (
                        discord_id, puuid, summoner_name, summoner_id,
                        region, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (discord_id)
                    DO UPDATE SET
                        puuid = EXCLUDED.puuid,
                        summoner_name = EXCLUDED.summoner_name,
                        updated_at = EXCLUDED.updated_at
                    """,
                    discord_id,
                    puuid,
                    summoner_name,
                    puuid,  # Using PUUID as summoner_id for now
                    "na1",  # Default region
                    datetime.now(UTC),
                    datetime.now(UTC),
                )
                logger.info(f"Saved binding for Discord ID {discord_id} -> {puuid}")
                return True

        except asyncpg.UniqueViolationError:
            logger.warning(f"PUUID {puuid} already bound to another Discord account")
            return False
        except Exception as e:
            logger.error(f"Error saving user binding: {e}")
            return False

    @llm_debug_wrapper(
        capture_result=True,
        capture_args=True,
        log_level="INFO",
        add_metadata={"layer": "db", "table": "ab_experiment_metadata", "op": "insert"},
    )
    async def save_ab_experiment_metadata(self, metadata: dict[str, Any]) -> bool:
        """Insert A/B experiment metadata for a given analysis request.

        Args:
            metadata: Dict matching ab_experiment_metadata columns

        Returns:
            True on success
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return False

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO ab_experiment_metadata (
                        match_id, discord_user_id, ab_cohort, variant_id,
                        prompt_version, prompt_template, ab_seed,
                        llm_input_tokens, llm_output_tokens, llm_api_cost_usd,
                        llm_latency_ms, total_processing_time_ms, created_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7,
                        $8, $9, $10, $11, $12, $13
                    )
                    """,
                    metadata.get("match_id"),
                    metadata.get("discord_user_id"),
                    metadata.get("ab_cohort"),
                    metadata.get("variant_id"),
                    metadata.get("prompt_version"),
                    metadata.get("prompt_template"),
                    metadata.get("ab_seed"),
                    metadata.get("llm_input_tokens"),
                    metadata.get("llm_output_tokens"),
                    metadata.get("llm_api_cost_usd"),
                    metadata.get("llm_latency_ms"),
                    metadata.get("total_processing_time_ms"),
                    datetime.now(UTC),
                )
                return True
        except Exception as e:
            logger.error(f"Error inserting A/B metadata: {e}")
            return False

    @llm_debug_wrapper(
        capture_result=True,
        capture_args=True,
        log_level="INFO",
        add_metadata={"layer": "db", "table": "feedback_events", "op": "insert"},
    )
    async def insert_feedback_event(self, payload: dict[str, Any]) -> bool:
        """Insert feedback event from CLI 1.

        Args:
            payload: Dict with feedback fields; minimally requires
                     match_id, discord_user_id, feedback_type.
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return False

        try:
            async with self._pool.acquire() as conn:
                # Compute numeric value if not provided
                fb_value = payload.get("feedback_value")
                if fb_value is None:
                    ft = (payload.get("feedback_type") or "").lower()
                    if ft in ("up", "thumbs_up", "like"):
                        fb_value = 1
                    elif ft in ("down", "thumbs_down", "dislike"):
                        fb_value = -1
                    elif ft in ("star", "favorite"):
                        fb_value = 1  # treat star as positive by default
                    else:
                        fb_value = 0

                await conn.execute(
                    """
                    INSERT INTO feedback_events (
                        match_id, discord_user_id, feedback_type,
                        prompt_variant, variant_id, feedback_value,
                        feedback_comment, interaction_id, created_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9
                    )
                    """,
                    payload.get("match_id"),
                    payload.get("discord_user_id"),
                    payload.get("feedback_type"),
                    payload.get("prompt_variant"),
                    payload.get("variant_id"),
                    fb_value,
                    payload.get("feedback_comment"),
                    payload.get("interaction_id"),
                    datetime.now(UTC),
                )
                return True
        except Exception as e:
            logger.error(f"Error inserting feedback event: {e}")
            return False

    async def get_user_binding(self, discord_id: str) -> dict[str, Any] | None:
        """Get user binding by Discord ID.

        Args:
            discord_id: Discord user ID

        Returns:
            User binding data if found, None otherwise
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return None

        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT discord_id, puuid, summoner_name, summoner_id,
                           region, created_at, updated_at
                    FROM user_bindings
                    WHERE discord_id = $1
                    """,
                    discord_id,
                )

                if row:
                    return dict(row)
                return None

        except Exception as e:
            logger.error(f"Error fetching user binding for {discord_id}: {e}")
            return None

    async def delete_user_binding(self, discord_id: str) -> bool:
        """Delete user binding by Discord ID.

        Args:
            discord_id: Discord user ID

        Returns:
            True if successful, False otherwise
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return False

        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM user_bindings
                    WHERE discord_id = $1
                    """,
                    discord_id,
                )

                # Check if any row was deleted
                deleted = result.split()[-1] != "0"
                if deleted:
                    logger.info(f"Deleted binding for Discord ID {discord_id}")
                else:
                    logger.warning(f"No binding found for Discord ID {discord_id}")
                return deleted

        except Exception as e:
            logger.error(f"Error deleting user binding for {discord_id}: {e}")
            return False

    async def save_match_data(
        self,
        match_id: str,
        match_data: dict[str, Any],
        timeline_data: dict[str, Any],
    ) -> bool:
        """Save match and timeline data to database.

        Args:
            match_id: Match ID
            match_data: Match data from Riot API
            timeline_data: Timeline data from Riot API

        Returns:
            True if successful, False otherwise
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return False

        max_retries = 3
        base_delay = 0.1

        for attempt in range(max_retries):
            try:
                async with self._pool.acquire() as conn:
                    # Start a transaction
                    async with conn.transaction():
                        # Extract basic match info
                        info = match_data.get("info", {})

                        # Save main match data
                        await conn.execute(
                            """
                            INSERT INTO match_data (
                                match_id, region, game_creation, game_duration,
                                match_data, timeline_data, created_at, updated_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT (match_id)
                            DO UPDATE SET
                                match_data = EXCLUDED.match_data,
                                timeline_data = EXCLUDED.timeline_data,
                                updated_at = EXCLUDED.updated_at
                            """,
                            match_id,
                            info.get("platformId", "NA1").lower(),
                            info.get("gameCreation", 0),
                            info.get("gameDuration", 0),
                            json.dumps(match_data),  # Convert to JSON for JSONB
                            json.dumps(timeline_data) if timeline_data else None,
                            datetime.now(UTC),
                            datetime.now(UTC),
                        )

                        # Save participant data for efficient queries
                        participants = info.get("participants", [])
                        for participant in participants:
                            await conn.execute(
                                """
                                INSERT INTO match_participants (
                                    match_id, puuid, champion_id, team_id,
                                    win, kills, deaths, assists, created_at
                                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                                ON CONFLICT (match_id, puuid) DO NOTHING
                                """,
                                match_id,
                                participant.get("puuid"),
                                participant.get("championId", 0),
                                participant.get("teamId", 0),
                                participant.get("win", False),
                                participant.get("kills", 0),
                                participant.get("deaths", 0),
                                participant.get("assists", 0),
                                datetime.now(UTC),
                            )

                logger.info(f"Saved match data for {match_id}")
                return True

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed saving match data for {match_id}: {e}")
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt) + random.uniform(0, 0.2)
                    await asyncio.sleep(delay)
                else:
                    return False

    async def get_match_data(self, match_id: str) -> dict[str, Any] | None:
        """Retrieve cached match data from database.

        Args:
            match_id: Match ID to retrieve

        Returns:
            Match data if found, None otherwise
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return None

        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT match_data, timeline_data, analysis_data,
                           created_at, updated_at
                    FROM match_data
                    WHERE match_id = $1
                    """,
                    match_id,
                )

                if row:
                    md = row["match_data"]
                    tl = row["timeline_data"]
                    an = row["analysis_data"]
                    # Defensive decode if driver returns JSONB as text
                    import json as _json

                    if isinstance(md, str):
                        try:
                            md = _json.loads(md)
                        except Exception:
                            pass
                    if isinstance(tl, str):
                        try:
                            tl = _json.loads(tl)
                        except Exception:
                            pass
                    if isinstance(an, str):
                        try:
                            an = _json.loads(an)
                        except Exception:
                            pass
                    return {
                        "match_data": md,
                        "timeline_data": tl,
                        "analysis_data": an,
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                return None

        except Exception as e:
            logger.error(f"Error fetching match data for {match_id}: {e}")
            return None

    async def get_recent_matches_for_user(
        self, puuid: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get recent matches for a user from database.

        Args:
            puuid: Player PUUID
            limit: Maximum number of matches to return

        Returns:
            List of match data
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return []

        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT m.match_id, m.match_data, m.game_creation,
                           mp.champion_id, mp.win, mp.kills, mp.deaths, mp.assists
                    FROM match_data m
                    JOIN match_participants mp ON m.match_id = mp.match_id
                    WHERE mp.puuid = $1
                    ORDER BY m.game_creation DESC
                    LIMIT $2
                    """,
                    puuid,
                    limit,
                )

                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Error fetching recent matches for {puuid}: {e}")
            return []

    async def update_match_analysis(self, match_id: str, analysis_data: dict[str, Any]) -> bool:
        """Update match with analysis results.

        Args:
            match_id: Match ID
            analysis_data: Analysis results to store

        Returns:
            True if successful, False otherwise
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return False

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE match_data
                    SET analysis_data = $1, updated_at = $2
                    WHERE match_id = $3
                    """,
                    json.dumps(analysis_data),
                    datetime.now(UTC),
                    match_id,
                )
                logger.info(f"Updated analysis for match {match_id}")
                return True

        except Exception as e:
            logger.error(f"Error updating analysis for {match_id}: {e}")
            return False

    async def save_analysis_result(
        self,
        match_id: str,
        puuid: str,
        score_data: dict[str, Any],
        region: str = "na1",
        status: str = "completed",
        processing_duration_ms: float | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Save match analysis results to match_analytics table.

        Args:
            match_id: Match ID
            puuid: Player PUUID who requested analysis
            score_data: V1 scoring algorithm output (MatchAnalysisOutput)
            region: Riot region
            status: Analysis status ('pending', 'completed', 'failed')
            processing_duration_ms: Time taken for analysis
            error_message: Error message if status is 'failed'

        Returns:
            True if successful, False otherwise
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return False

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO match_analytics (
                        match_id, puuid, region, status, score_data,
                        processing_duration_ms, error_message, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (match_id)
                    DO UPDATE SET
                        status = EXCLUDED.status,
                        score_data = EXCLUDED.score_data,
                        processing_duration_ms = EXCLUDED.processing_duration_ms,
                        error_message = EXCLUDED.error_message,
                        updated_at = EXCLUDED.updated_at
                    """,
                    match_id,
                    puuid,
                    region,
                    status,
                    json.dumps(score_data),
                    processing_duration_ms,
                    error_message,
                    datetime.now(UTC),
                    datetime.now(UTC),
                )
                logger.info(f"Saved analysis result for match {match_id}")
                return True

        except Exception as e:
            logger.error(f"Error saving analysis result for {match_id}: {e}")
            return False

    async def get_analysis_result(self, match_id: str) -> dict[str, Any] | None:
        """Retrieve analysis result by match ID.

        Args:
            match_id: Match ID to retrieve

        Returns:
            Analysis result if found, None otherwise
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return None

        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT match_id, puuid, region, status, score_data,
                           llm_narrative, llm_metadata, algorithm_version,
                           processing_duration_ms, error_message,
                           created_at, updated_at
                    FROM match_analytics
                    WHERE match_id = $1
                    """,
                    match_id,
                )

                if row:
                    return dict(row)
                return None

        except Exception as e:
            logger.error(f"Error fetching analysis result for {match_id}: {e}")
            return None

    async def update_llm_narrative(
        self, match_id: str, llm_narrative: str, llm_metadata: dict[str, Any] | None = None
    ) -> bool:
        """Update analysis with LLM-generated narrative (P4).

        Args:
            match_id: Match ID
            llm_narrative: Generated narrative text from LLM
            llm_metadata: Optional metadata about LLM generation

        Returns:
            True if successful, False otherwise
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return False

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE match_analytics
                    SET llm_narrative = $1, llm_metadata = $2, updated_at = $3
                    WHERE match_id = $4
                    """,
                    llm_narrative,
                    json.dumps(llm_metadata) if llm_metadata else None,
                    datetime.now(UTC),
                    match_id,
                )
                logger.info(f"Updated LLM narrative for match {match_id}")
                return True

        except Exception as e:
            logger.error(f"Error updating LLM narrative for {match_id}: {e}")
            return False

    async def update_analysis_status(
        self,
        match_id: str,
        status: str,
        error_message: str | None = None,
    ) -> bool:
        """Update analysis task status in match_analytics table.

        Used by P4 task orchestration to track workflow state:
        - 'pending': Initial state (task queued)
        - 'processing': Scoring stage in progress
        - 'analyzing': LLM inference in progress
        - 'completed': All stages succeeded
        - 'failed': Any stage failed (error_message set)

        Args:
            match_id: Match ID
            status: New status value
            error_message: Optional error description if status is 'failed'

        Returns:
            True if successful, False otherwise
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return False

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE match_analytics
                    SET status = $1, error_message = $2, updated_at = $3
                    WHERE match_id = $4
                    """,
                    status,
                    error_message,
                    datetime.now(UTC),
                    match_id,
                )
                logger.info(f"Updated analysis status for {match_id}: {status}")
                return True

        except Exception as e:
            logger.error(f"Error updating analysis status for {match_id}: {e}")
            return False

    # =============================================================================
    # User Profile Operations (V2.2)
    # =============================================================================

    async def get_user_profile(self, discord_user_id: str) -> dict[str, Any] | None:
        """Get user profile by Discord user ID.

        Args:
            discord_user_id: Discord user ID

        Returns:
            Profile data dict (JSONB), or None if not found
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return None

        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT profile_data
                    FROM user_profiles
                    WHERE discord_user_id = $1
                    """,
                    discord_user_id,
                )
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching user profile for {discord_user_id}: {e}")
            return None

    async def save_user_profile(
        self,
        discord_user_id: str,
        puuid: str,
        profile_data: dict[str, Any],
    ) -> bool:
        """Save or update user profile (upsert operation).

        Args:
            discord_user_id: Discord user ID
            puuid: Riot PUUID
            profile_data: Complete profile data as dict (JSONB)

        Returns:
            True if successful, False otherwise
        """
        if not self._pool:
            logger.error("Database pool not initialized")
            return False

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_profiles (discord_user_id, puuid, profile_data, last_updated)
                    VALUES ($1, $2, $3::jsonb, $4)
                    ON CONFLICT (discord_user_id)
                    DO UPDATE SET
                        profile_data = EXCLUDED.profile_data,
                        last_updated = EXCLUDED.last_updated
                    """,
                    discord_user_id,
                    puuid,
                    json.dumps(profile_data),
                    datetime.now(UTC),
                )
                logger.info(f"User profile saved for {discord_user_id}")
                return True
        except Exception as e:
            logger.error(f"Error saving user profile for {discord_user_id}: {e}")
            return False

    async def health_check(self) -> bool:
        """Check database connectivity.

        Returns:
            True if database is accessible, False otherwise
        """
        if not self._pool:
            return False

        try:
            async with self._pool.acquire() as conn:
                result: int | None = await conn.fetchval("SELECT 1")
                return bool(result == 1)
        except Exception:
            return False
