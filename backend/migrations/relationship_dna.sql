-- =============================================================================
-- RELATIONSHIP DNA - PostgreSQL Migration
-- =============================================================================
-- Creates the relationship_dna table for storing personalized communication
-- context between creators and their leads.
--
-- Part of RELATIONSHIP-DNA feature.
-- =============================================================================

-- Create the relationship_dna table
CREATE TABLE IF NOT EXISTS relationship_dna (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign keys (references creators and follower_memories)
    creator_id VARCHAR(100) NOT NULL,
    follower_id VARCHAR(255) NOT NULL,

    -- Relationship classification
    relationship_type VARCHAR(50) NOT NULL DEFAULT 'DESCONOCIDO',
    trust_score FLOAT DEFAULT 0.0,
    depth_level INTEGER DEFAULT 0,

    -- Vocabulary specific to this relationship (JSONB for efficient querying)
    vocabulary_uses JSONB DEFAULT '[]'::jsonb,
    vocabulary_avoids JSONB DEFAULT '[]'::jsonb,
    emojis JSONB DEFAULT '[]'::jsonb,

    -- Interaction patterns observed from conversation history
    avg_message_length INTEGER,
    questions_frequency FLOAT,
    multi_message_frequency FLOAT,
    tone_description TEXT,

    -- Shared context extracted from conversations
    recurring_topics JSONB DEFAULT '[]'::jsonb,
    private_references JSONB DEFAULT '[]'::jsonb,

    -- Generated instructions for the bot
    bot_instructions TEXT,

    -- Golden examples for few-shot learning
    golden_examples JSONB DEFAULT '[]'::jsonb,

    -- Metadata for tracking analysis state
    total_messages_analyzed INTEGER DEFAULT 0,
    last_analyzed_at TIMESTAMP WITH TIME ZONE,
    version INTEGER DEFAULT 1,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT uq_relationship_dna_creator_follower
        UNIQUE (creator_id, follower_id),

    CONSTRAINT chk_trust_score_range
        CHECK (trust_score >= 0.0 AND trust_score <= 1.0),

    CONSTRAINT chk_depth_level_range
        CHECK (depth_level >= 0 AND depth_level <= 4),

    CONSTRAINT chk_questions_frequency_range
        CHECK (questions_frequency IS NULL OR (questions_frequency >= 0.0 AND questions_frequency <= 1.0)),

    CONSTRAINT chk_multi_message_frequency_range
        CHECK (multi_message_frequency IS NULL OR (multi_message_frequency >= 0.0 AND multi_message_frequency <= 1.0)),

    CONSTRAINT chk_relationship_type_valid
        CHECK (relationship_type IN (
            'FAMILIA',
            'INTIMA',
            'AMISTAD_CERCANA',
            'AMISTAD_CASUAL',
            'CLIENTE',
            'COLABORADOR',
            'DESCONOCIDO'
        ))
);

-- =============================================================================
-- INDEXES for query performance
-- =============================================================================

-- Primary lookup: creator + follower
CREATE INDEX IF NOT EXISTS idx_relationship_dna_creator_follower
    ON relationship_dna(creator_id, follower_id);

-- Filter by relationship type
CREATE INDEX IF NOT EXISTS idx_relationship_dna_type
    ON relationship_dna(relationship_type);

-- Find stale DNAs that need re-analysis
CREATE INDEX IF NOT EXISTS idx_relationship_dna_needs_analysis
    ON relationship_dna(creator_id, last_analyzed_at)
    WHERE last_analyzed_at IS NULL OR last_analyzed_at < NOW() - INTERVAL '30 days';

-- Find by creator for dashboard views
CREATE INDEX IF NOT EXISTS idx_relationship_dna_creator
    ON relationship_dna(creator_id);

-- =============================================================================
-- TRIGGER for auto-updating updated_at timestamp
-- =============================================================================

CREATE OR REPLACE FUNCTION update_relationship_dna_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_relationship_dna_updated_at ON relationship_dna;

CREATE TRIGGER trigger_relationship_dna_updated_at
    BEFORE UPDATE ON relationship_dna
    FOR EACH ROW
    EXECUTE FUNCTION update_relationship_dna_timestamp();

-- =============================================================================
-- COMMENTS for documentation
-- =============================================================================

COMMENT ON TABLE relationship_dna IS
    'Stores relationship-specific context for personalized communication per lead';

COMMENT ON COLUMN relationship_dna.relationship_type IS
    'Classification: FAMILIA, INTIMA, AMISTAD_CERCANA, AMISTAD_CASUAL, CLIENTE, COLABORADOR, DESCONOCIDO';

COMMENT ON COLUMN relationship_dna.vocabulary_uses IS
    'JSON array of words/phrases to use with this lead';

COMMENT ON COLUMN relationship_dna.vocabulary_avoids IS
    'JSON array of words/phrases to avoid with this lead';

COMMENT ON COLUMN relationship_dna.golden_examples IS
    'JSON array of {lead: string, creator: string} example exchanges';

COMMENT ON COLUMN relationship_dna.bot_instructions IS
    'Generated natural language instructions for the bot when talking to this lead';

-- =============================================================================
-- ROLLBACK (uncomment to undo migration)
-- =============================================================================
-- DROP TRIGGER IF EXISTS trigger_relationship_dna_updated_at ON relationship_dna;
-- DROP FUNCTION IF EXISTS update_relationship_dna_timestamp();
-- DROP TABLE IF EXISTS relationship_dna;
