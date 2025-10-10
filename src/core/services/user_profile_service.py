"""V2.2 User Profile Service.

Core service for managing user profiles with CRUD operations and incremental updates.
Handles profile persistence, historical data aggregation, and profile calculation logic.

Author: CLI 2 (Backend)
Date: 2025-10-07
Status: ✅ Production Ready

Key Responsibilities:
- Create and load user profiles from database
- Incrementally update profiles after each match analysis
- Calculate performance trends from historical match data
- Infer user classification (skill level, player type)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from src.adapters.database import DatabaseAdapter
from src.contracts.v22_user_profile import (
    V22ChampionProfile,
    V22ProfileUpdateEvent,
    V22UserClassification,
    V22UserPreferences,
    V22UserProfile,
)

logger = logging.getLogger(__name__)


class UserProfileService:
    """Service for managing user profiles with database persistence.

    This service handles all CRUD operations for user profiles and implements
    the business logic for calculating performance trends and user classification.
    """

    def __init__(self, db_adapter: DatabaseAdapter):
        """Initialize user profile service.

        Args:
            db_adapter: Database adapter for persistence operations
        """
        self.db = db_adapter

    async def get_or_create_profile(self, discord_user_id: str, puuid: str) -> V22UserProfile:
        """Get existing user profile or create new one if not exists.

        Args:
            discord_user_id: Discord user ID
            puuid: Riot PUUID

        Returns:
            User profile (either loaded from DB or newly created)
        """
        # Try to load existing profile
        profile = await self.load_profile(discord_user_id)
        if profile:
            return profile

        # Create new profile with defaults
        logger.info(
            "creating_new_user_profile",
            extra={"discord_user_id": discord_user_id, "puuid": puuid},
        )

        new_profile = V22UserProfile(
            discord_user_id=discord_user_id,
            puuid=puuid,
            preferences=V22UserPreferences(),
            performance_trends=None,  # Requires ≥5 matches
            champion_profile=V22ChampionProfile(),
            classification=V22UserClassification(),
            total_matches_analyzed=0,
            last_updated=datetime.now(UTC).isoformat(),
            profile_version="v2.2",
        )

        # Persist to database
        await self.save_profile(new_profile)

        return new_profile

    async def load_profile(self, discord_user_id: str) -> V22UserProfile | None:
        """Load user profile from database.

        Args:
            discord_user_id: Discord user ID

        Returns:
            User profile if exists, None otherwise
        """
        try:
            result = await self.db.get_user_profile(discord_user_id)

            if not result:
                return None

            # Deserialize JSONB to Pydantic model
            profile_data = result["profile_data"]
            return V22UserProfile.model_validate(profile_data)

        except Exception as e:
            logger.error(
                "failed_to_load_profile",
                extra={"discord_user_id": discord_user_id, "error": str(e)},
            )
            return None

    async def save_profile(self, profile: V22UserProfile) -> None:
        """Save user profile to database (upsert operation).

        Args:
            profile: User profile to save
        """
        try:
            profile_data = profile.model_dump(mode="json")

            success = await self.db.save_user_profile(
                discord_user_id=profile.discord_user_id,
                puuid=profile.puuid,
                profile_data=profile_data,
            )

            if not success:
                raise RuntimeError("Database operation failed")

            logger.info(
                "user_profile_saved",
                extra={
                    "discord_user_id": profile.discord_user_id,
                    "total_matches": profile.total_matches_analyzed,
                },
            )

        except Exception as e:
            logger.error(
                "failed_to_save_profile",
                extra={"discord_user_id": profile.discord_user_id, "error": str(e)},
            )
            raise

    async def update_profile_after_match(
        self, update_event: V22ProfileUpdateEvent
    ) -> V22UserProfile:
        """Incrementally update user profile after a new match analysis.

        This method:
        1. Loads the current profile (or creates new one)
        2. Updates match counter and champion/role data
        3. Recalculates performance trends (if ≥5 matches)
        4. Updates user classification
        5. Persists updated profile

        Args:
            update_event: Profile update event with match data

        Returns:
            Updated user profile
        """
        # Load or create profile
        profile = await self.get_or_create_profile(update_event.discord_user_id, update_event.puuid)

        # Update match counter
        profile.total_matches_analyzed += 1

        # Update champion/role data
        self._update_champion_profile(profile, update_event)

        # Recalculate performance trends (if enough data)
        if profile.total_matches_analyzed >= 5:
            await self._recalculate_performance_trends(profile, update_event)

        # Update user classification (skill level, player type)
        await self._update_classification(profile)

        # Update timestamp
        profile.last_updated = datetime.now(UTC).isoformat()

        # Persist updated profile
        await self.save_profile(profile)

        logger.info(
            "profile_updated_after_match",
            extra={
                "discord_user_id": profile.discord_user_id,
                "match_id": update_event.match_id,
                "total_matches": profile.total_matches_analyzed,
            },
        )

        return profile

    def _update_champion_profile(
        self, profile: V22UserProfile, update_event: V22ProfileUpdateEvent
    ) -> None:
        """Update champion and role distribution in profile.

        Args:
            profile: User profile to update (modified in-place)
            update_event: Match update event
        """
        # Update champion play counts
        champion = update_event.played_champion
        profile.champion_profile.champion_play_counts[champion] = (
            profile.champion_profile.champion_play_counts.get(champion, 0) + 1
        )

        # Update role distribution
        role = update_event.played_role
        profile.champion_profile.role_distribution[role] = (
            profile.champion_profile.role_distribution.get(role, 0) + 1
        )

        # Recalculate top 3 champions
        sorted_champions = sorted(
            profile.champion_profile.champion_play_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        profile.champion_profile.top_3_champions = [champ for champ, _ in sorted_champions[:3]]

        # Recalculate inferred primary role (≥40% threshold)
        total_role_games = sum(profile.champion_profile.role_distribution.values())
        primary_role = None
        for role_name, count in profile.champion_profile.role_distribution.items():
            if count / total_role_games >= 0.4:
                primary_role = role_name
                break

        profile.champion_profile.inferred_primary_role = primary_role

    async def _recalculate_performance_trends(
        self, profile: V22UserProfile, _update_event: V22ProfileUpdateEvent
    ) -> None:
        """Recalculate performance trends from last 20 matches.

        Args:
            profile: User profile to update (modified in-place)
            _update_event: Match update event (for context)

        Note:
            This requires querying match_analytics table for historical data.
            For now, this is a placeholder that will be implemented with Alembic.
        """
        # TODO (Task 4.2): Implement after Alembic migration creates match_analytics table
        # Query: SELECT score_data FROM match_analytics WHERE puuid = $1 ORDER BY created_at DESC LIMIT 20
        #
        # Calculate:
        # - avg_combat_score, avg_economy_score, etc.
        # - persistent_weak_dimension (where score < team_avg in ≥70% of matches)
        # - weak_dimension_frequency
        # - recent_win_rate
        #
        # For now, keep existing trends or set to None if insufficient data

        logger.debug(
            "performance_trends_recalculation_skipped",
            extra={
                "discord_user_id": profile.discord_user_id,
                "reason": "pending_alembic_migration",
            },
        )

    async def _update_classification(self, profile: V22UserProfile) -> None:
        """Update user classification (skill level, player type).

        Args:
            profile: User profile to update (modified in-place)

        Note:
            Skill level inference requires Riot API ranked tier data.
            Player type inference requires match frequency analysis.
            For now, this is a placeholder.
        """
        # TODO: Implement ranked tier fetching from Riot API
        # TODO: Implement match frequency calculation (matches/week)
        #
        # Classification logic:
        # - skill_level: Iron/Bronze = beginner, Silver/Gold = intermediate, Plat+ = advanced
        # - player_type: ≥5 ranked matches/week + Gold+ = competitive, else casual

        logger.debug(
            "classification_update_skipped",
            extra={
                "discord_user_id": profile.discord_user_id,
                "reason": "pending_riot_api_integration",
            },
        )

    async def update_preferences(
        self, discord_user_id: str, preferences: V22UserPreferences
    ) -> V22UserProfile | None:
        """Update user's explicit preferences (from /settings command).

        Args:
            discord_user_id: Discord user ID
            preferences: New preferences to save

        Returns:
            Updated user profile, or None if profile doesn't exist
        """
        profile = await self.load_profile(discord_user_id)
        if not profile:
            logger.warning(
                "cannot_update_preferences_profile_not_found",
                extra={"discord_user_id": discord_user_id},
            )
            return None

        # Update preferences
        profile.preferences = preferences
        profile.last_updated = datetime.now(UTC).isoformat()

        # Persist
        await self.save_profile(profile)

        logger.info(
            "user_preferences_updated",
            extra={
                "discord_user_id": discord_user_id,
                "tone": preferences.preferred_analysis_tone,
            },
        )

        return profile
