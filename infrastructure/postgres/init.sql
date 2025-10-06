-- Project Chimera - Database Initialization Script
-- Hexagonal Architecture: Database schema for LoL Discord Bot

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For fuzzy text search

-- Create schemas for logical separation
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS audit;

-- Set default search path
SET search_path TO core, public;

-- User profiles table - Core domain entity
CREATE TABLE IF NOT EXISTS core.user_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    discord_id BIGINT UNIQUE NOT NULL,
    discord_username VARCHAR(255) NOT NULL,
    riot_puuid VARCHAR(78) UNIQUE, -- PUUID is exactly 78 characters
    summoner_name VARCHAR(30), -- Riot summoner name max length
    summoner_tag VARCHAR(10), -- Riot tag (e.g., #NA1)
    region VARCHAR(10) CHECK (region IN ('NA1', 'EUW1', 'EUN1', 'KR', 'JP1', 'BR1', 'LA1', 'LA2', 'OC1', 'TR1', 'RU', 'PH2', 'SG2', 'TH2', 'TW2', 'VN2')),
    vip_tier VARCHAR(20) DEFAULT 'free' CHECK (vip_tier IN ('free', 'bronze', 'silver', 'gold', 'platinum', 'diamond')),
    vip_expires_at TIMESTAMP WITH TIME ZONE,
    total_matches_analyzed INTEGER DEFAULT 0,
    total_score_points DECIMAL(10, 2) DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    CONSTRAINT valid_riot_binding CHECK (
        (riot_puuid IS NULL AND summoner_name IS NULL AND summoner_tag IS NULL) OR
        (riot_puuid IS NOT NULL AND summoner_name IS NOT NULL AND summoner_tag IS NOT NULL)
    )
);

-- Match analysis results - Core analytics data
CREATE TABLE IF NOT EXISTS analytics.match_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    match_id VARCHAR(50) UNIQUE NOT NULL, -- Riot match ID format
    user_id UUID NOT NULL REFERENCES core.user_profiles(id) ON DELETE CASCADE,
    game_duration INTEGER NOT NULL, -- Duration in seconds
    game_mode VARCHAR(30) NOT NULL,
    game_version VARCHAR(20) NOT NULL, -- Patch version

    -- Player performance metrics
    player_champion VARCHAR(50) NOT NULL,
    player_role VARCHAR(20) CHECK (player_role IN ('TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY')),
    player_team VARCHAR(10) CHECK (player_team IN ('blue', 'red')),

    -- Scoring system results
    overall_score DECIMAL(5, 2) CHECK (overall_score >= 0 AND overall_score <= 100),
    kda_score DECIMAL(5, 2),
    cs_score DECIMAL(5, 2),
    vision_score DECIMAL(5, 2),
    objective_score DECIMAL(5, 2),
    teamfight_score DECIMAL(5, 2),

    -- LLM analysis results
    llm_analysis_summary TEXT,
    llm_emotional_tone VARCHAR(20) CHECK (llm_emotional_tone IN ('positive', 'neutral', 'negative', 'mixed')),
    llm_key_insights JSONB DEFAULT '[]', -- Array of insights

    -- Match outcome
    is_victory BOOLEAN NOT NULL,
    mvp_candidate BOOLEAN DEFAULT false,

    -- Timestamps
    match_timestamp TIMESTAMP WITH TIME ZONE NOT NULL, -- When the match was played
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Raw data cache (for re-analysis)
    raw_timeline_data JSONB, -- Compressed timeline data
    raw_analysis_metadata JSONB DEFAULT '{}'
);

-- Discord interactions log - For rate limiting and audit
CREATE TABLE IF NOT EXISTS audit.discord_interactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES core.user_profiles(id) ON DELETE CASCADE,
    discord_id BIGINT NOT NULL, -- For non-registered users
    interaction_type VARCHAR(50) NOT NULL,
    command_name VARCHAR(100) NOT NULL,
    command_params JSONB DEFAULT '{}',
    response_time_ms INTEGER,
    is_success BOOLEAN DEFAULT true,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    correlation_id VARCHAR(100) -- For tracing across services
);

-- API rate limiting table
CREATE TABLE IF NOT EXISTS audit.rate_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    identifier VARCHAR(255) NOT NULL, -- Can be user_id, IP, or API key
    endpoint VARCHAR(255) NOT NULL,
    request_count INTEGER DEFAULT 0,
    window_start TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    window_duration_seconds INTEGER DEFAULT 60,
    max_requests INTEGER DEFAULT 100,
    UNIQUE(identifier, endpoint, window_start)
);

-- Create indexes for performance
CREATE INDEX idx_user_profiles_discord_id ON core.user_profiles(discord_id);
CREATE INDEX idx_user_profiles_riot_puuid ON core.user_profiles(riot_puuid);
CREATE INDEX idx_user_profiles_active ON core.user_profiles(is_active, last_active_at DESC);

CREATE INDEX idx_match_analyses_user_id ON analytics.match_analyses(user_id);
CREATE INDEX idx_match_analyses_match_id ON analytics.match_analyses(match_id);
CREATE INDEX idx_match_analyses_timestamp ON analytics.match_analyses(match_timestamp DESC);
CREATE INDEX idx_match_analyses_scores ON analytics.match_analyses(overall_score DESC);

CREATE INDEX idx_discord_interactions_user ON audit.discord_interactions(user_id, created_at DESC);
CREATE INDEX idx_discord_interactions_correlation ON audit.discord_interactions(correlation_id);

CREATE INDEX idx_rate_limits_lookup ON audit.rate_limits(identifier, endpoint, window_start DESC);

-- Create update trigger for updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_user_profiles_updated_at
    BEFORE UPDATE ON core.user_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create stored procedure for rate limit checking
CREATE OR REPLACE FUNCTION audit.check_rate_limit(
    p_identifier VARCHAR(255),
    p_endpoint VARCHAR(255),
    p_max_requests INTEGER DEFAULT 100,
    p_window_seconds INTEGER DEFAULT 60
)
RETURNS BOOLEAN AS $$
DECLARE
    v_current_count INTEGER;
    v_window_start TIMESTAMP WITH TIME ZONE;
BEGIN
    v_window_start := CURRENT_TIMESTAMP - (p_window_seconds || ' seconds')::INTERVAL;

    SELECT COALESCE(SUM(request_count), 0) INTO v_current_count
    FROM audit.rate_limits
    WHERE identifier = p_identifier
      AND endpoint = p_endpoint
      AND window_start >= v_window_start;

    IF v_current_count >= p_max_requests THEN
        RETURN FALSE; -- Rate limit exceeded
    END IF;

    INSERT INTO audit.rate_limits (identifier, endpoint, request_count, max_requests, window_duration_seconds)
    VALUES (p_identifier, p_endpoint, 1, p_max_requests, p_window_seconds)
    ON CONFLICT (identifier, endpoint, window_start)
    DO UPDATE SET request_count = audit.rate_limits.request_count + 1;

    RETURN TRUE; -- Request allowed
END;
$$ LANGUAGE plpgsql;

-- Grant permissions (adjust as needed for your application user)
GRANT USAGE ON SCHEMA core TO chimera_user;
GRANT USAGE ON SCHEMA analytics TO chimera_user;
GRANT USAGE ON SCHEMA audit TO chimera_user;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA core TO chimera_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA analytics TO chimera_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA audit TO chimera_user;

GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA core TO chimera_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA analytics TO chimera_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA audit TO chimera_user;

-- Insert sample data for development (optional)
-- Uncomment below for test data

/*
INSERT INTO core.user_profiles (discord_id, discord_username, riot_puuid, summoner_name, summoner_tag, region)
VALUES
    (123456789012345678, 'TestUser#0001', 'test-puuid-1234567890123456789012345678901234567890123456789012345678901234567890', 'TestSummoner', 'NA1', 'NA1');
*/
