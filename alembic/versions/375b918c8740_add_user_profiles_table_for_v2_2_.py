"""Add user_profiles table for V2.2 personalization

Revision ID: 375b918c8740
Revises:
Create Date: 2025-10-07 01:04:42.968648

"""
from typing import Union
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "375b918c8740"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Create user_profiles table for V2.2 personalization."""
    # Create user_profiles table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            discord_user_id TEXT PRIMARY KEY,
            puuid TEXT NOT NULL,
            profile_data JSONB NOT NULL,
            last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """
    )

    # Create index on puuid for faster lookups by Riot PUUID
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_profiles_puuid
        ON user_profiles(puuid);
    """
    )

    # Create index on last_updated for profile staleness queries
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_profiles_last_updated
        ON user_profiles(last_updated DESC);
    """
    )


def downgrade() -> None:
    """Downgrade schema: Drop user_profiles table."""
    # Drop indexes first
    op.execute("DROP INDEX IF EXISTS idx_user_profiles_last_updated;")
    op.execute("DROP INDEX IF EXISTS idx_user_profiles_puuid;")

    # Drop table
    op.execute("DROP TABLE IF EXISTS user_profiles;")
