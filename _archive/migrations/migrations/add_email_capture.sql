-- Migration: Add email capture system tables and columns
-- Run this on PostgreSQL

-- 1. Add email_capture_config to creators table
ALTER TABLE creators
ADD COLUMN IF NOT EXISTS email_capture_config JSONB DEFAULT NULL;

-- 2. Create unified_profiles table
CREATE TABLE IF NOT EXISTS unified_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    phone VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Create platform_identities table
CREATE TABLE IF NOT EXISTS platform_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unified_profile_id UUID REFERENCES unified_profiles(id),
    creator_id UUID REFERENCES creators(id),
    platform VARCHAR(50) NOT NULL,
    platform_user_id VARCHAR(255) NOT NULL,
    username VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create unique index for platform + platform_user_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_platform_identity_unique
ON platform_identities(platform, platform_user_id);

-- 4. Create email_ask_tracking table
CREATE TABLE IF NOT EXISTS email_ask_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID REFERENCES creators(id),
    platform VARCHAR(50) NOT NULL,
    platform_user_id VARCHAR(255) NOT NULL,
    ask_level INTEGER DEFAULT 0,
    last_asked_at TIMESTAMP WITH TIME ZONE,
    declined_count INTEGER DEFAULT 0,
    captured_email VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for fast lookups
CREATE INDEX IF NOT EXISTS idx_email_ask_tracking_lookup
ON email_ask_tracking(platform, platform_user_id);

-- Done!
SELECT 'Migration complete: email_capture_config, unified_profiles, platform_identities, email_ask_tracking' as status;
