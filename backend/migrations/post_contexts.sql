-- =============================================================================
-- POST CONTEXTS - PostgreSQL Migration
-- =============================================================================
-- Creates the post_contexts table for storing analyzed context from
-- creator's recent Instagram posts (promotions, topics, availability).
--
-- Part of POST-CONTEXT-DETECTION feature (Layer 4 - Temporal State).
-- =============================================================================

-- Create the post_contexts table
CREATE TABLE IF NOT EXISTS post_contexts (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Creator reference
    creator_id VARCHAR(100) NOT NULL,

    -- Promotion fields
    active_promotion TEXT,
    promotion_deadline TIMESTAMP WITH TIME ZONE,
    promotion_urgency TEXT,

    -- Topics and products (JSONB arrays)
    recent_topics JSONB DEFAULT '[]'::jsonb,
    recent_products JSONB DEFAULT '[]'::jsonb,

    -- Availability
    availability_hint TEXT,

    -- Generated instructions for bot
    context_instructions TEXT NOT NULL,

    -- Metadata
    posts_analyzed INTEGER NOT NULL DEFAULT 0,
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    source_posts JSONB DEFAULT '[]'::jsonb,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_post_context_creator UNIQUE (creator_id)
);

-- =============================================================================
-- INDEXES for query performance
-- =============================================================================

-- Primary lookup: by creator
CREATE INDEX IF NOT EXISTS idx_post_contexts_creator
    ON post_contexts(creator_id);

-- Find expired contexts that need refresh
CREATE INDEX IF NOT EXISTS idx_post_contexts_expires
    ON post_contexts(expires_at);

-- Find contexts with active promotions
CREATE INDEX IF NOT EXISTS idx_post_contexts_promotion
    ON post_contexts(creator_id)
    WHERE active_promotion IS NOT NULL;

-- =============================================================================
-- TRIGGER for auto-updating updated_at timestamp
-- =============================================================================

CREATE OR REPLACE FUNCTION update_post_contexts_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_post_contexts_updated_at ON post_contexts;

CREATE TRIGGER trigger_post_contexts_updated_at
    BEFORE UPDATE ON post_contexts
    FOR EACH ROW
    EXECUTE FUNCTION update_post_contexts_timestamp();

-- =============================================================================
-- COMMENTS for documentation
-- =============================================================================

COMMENT ON TABLE post_contexts IS
    'Stores analyzed context from creator Instagram posts for temporal awareness';

COMMENT ON COLUMN post_contexts.active_promotion IS
    'Current active promotion/launch detected from posts';

COMMENT ON COLUMN post_contexts.promotion_urgency IS
    'Urgency level of promotion (e.g., "48h restantes")';

COMMENT ON COLUMN post_contexts.recent_topics IS
    'JSON array of topics mentioned in recent posts';

COMMENT ON COLUMN post_contexts.recent_products IS
    'JSON array of products/services mentioned';

COMMENT ON COLUMN post_contexts.availability_hint IS
    'Availability hint (e.g., "De viaje por Bali")';

COMMENT ON COLUMN post_contexts.context_instructions IS
    'Generated instructions for bot based on analyzed posts';

COMMENT ON COLUMN post_contexts.expires_at IS
    'When this context expires and needs refresh (typically 6h)';

-- =============================================================================
-- ROLLBACK (uncomment to undo migration)
-- =============================================================================
-- DROP TRIGGER IF EXISTS trigger_post_contexts_updated_at ON post_contexts;
-- DROP FUNCTION IF EXISTS update_post_contexts_timestamp();
-- DROP TABLE IF EXISTS post_contexts;
