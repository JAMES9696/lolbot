-- Migration: Add multi-account support (方案C)
-- Created: 2025-10-14
-- Purpose: Enable users to bind multiple Riot accounts to one Discord ID

-- Create user_accounts table for multi-account management
CREATE TABLE IF NOT EXISTS core.user_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_profile_id UUID NOT NULL REFERENCES core.user_profiles(id) ON DELETE CASCADE,
    discord_id BIGINT NOT NULL,
    riot_puuid VARCHAR(78) NOT NULL, -- PUUID is exactly 78 characters
    summoner_name VARCHAR(100) NOT NULL, -- Format: "GameName#TAG"
    region VARCHAR(10) NOT NULL CHECK (region IN ('na1', 'euw1', 'eun1', 'kr', 'jp1', 'br1', 'la1', 'la2', 'oc1', 'tr1', 'ru', 'ph2', 'sg2', 'th2', 'tw2', 'vn2')),
    is_primary BOOLEAN DEFAULT false,
    nickname VARCHAR(50), -- Optional user-defined alias (e.g., "主号", "冲分号")
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT unique_discord_puuid UNIQUE (discord_id, riot_puuid), -- Same Discord user can't bind same PUUID twice
    CONSTRAINT unique_puuid_global UNIQUE (riot_puuid) -- Same PUUID can't be bound to multiple Discord users
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_accounts_discord_id ON core.user_accounts(discord_id);
CREATE INDEX IF NOT EXISTS idx_user_accounts_puuid ON core.user_accounts(riot_puuid);
CREATE INDEX IF NOT EXISTS idx_user_accounts_primary ON core.user_accounts(discord_id, is_primary) WHERE is_primary = true;
CREATE INDEX IF NOT EXISTS idx_user_accounts_created ON core.user_accounts(discord_id, created_at ASC);

-- Trigger: Ensure only ONE primary account per Discord user
-- When is_primary is set to true, automatically unset all other accounts for that discord_id
CREATE OR REPLACE FUNCTION enforce_single_primary_account()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_primary = true THEN
        -- Unset is_primary for all other accounts of this Discord user
        UPDATE core.user_accounts
        SET is_primary = false, updated_at = CURRENT_TIMESTAMP
        WHERE discord_id = NEW.discord_id
          AND id != NEW.id
          AND is_primary = true;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_enforce_single_primary
    BEFORE INSERT OR UPDATE OF is_primary ON core.user_accounts
    FOR EACH ROW
    WHEN (NEW.is_primary = true)
    EXECUTE FUNCTION enforce_single_primary_account();

-- Trigger: Auto-update updated_at timestamp
CREATE TRIGGER update_user_accounts_updated_at
    BEFORE UPDATE ON core.user_accounts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT ALL PRIVILEGES ON core.user_accounts TO chimera_user;

-- Comments for documentation
COMMENT ON TABLE core.user_accounts IS 'Stores multiple Riot account bindings per Discord user (方案C implementation)';
COMMENT ON COLUMN core.user_accounts.is_primary IS 'Primary account is used as default for commands like /analyze';
COMMENT ON COLUMN core.user_accounts.nickname IS 'User-defined alias for easy identification (e.g., "主号", "大号", "冲分号")';
COMMENT ON CONSTRAINT unique_puuid_global ON core.user_accounts IS 'Prevents PUUID theft - one PUUID can only be bound to one Discord user';
