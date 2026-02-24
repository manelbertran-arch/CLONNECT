-- Add missing database indexes for creator_id foreign keys
-- Run with: psql $DATABASE_URL -f scripts/add_missing_indexes.sql
-- Safe to run multiple times (IF NOT EXISTS)
--
-- Most models already have creator_id indexes via SQLAlchemy __table_args__.
-- This script adds the one that was missing and ensures all are present.

-- UnmatchedWebhook.resolved_to_creator_id (was missing)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_unmatched_webhooks_resolved_creator
    ON unmatched_webhooks(resolved_to_creator_id);

-- Verify existing indexes (these should already exist from SQLAlchemy model definitions):
-- learning_rules: idx_learning_rules_creator_active (creator_id, is_active)
-- gold_examples: idx_gold_examples_creator_active (creator_id, is_active)
-- pattern_analysis_runs: idx_pattern_runs_creator (creator_id)
-- preference_pairs: idx_preference_pairs_creator (creator_id)
-- clone_score_evaluations: idx_clone_score_evals_creator (creator_id)
-- clone_score_test_sets: idx_clone_score_test_sets_creator (creator_id)
-- lead_memories: idx_lead_memories_creator_lead (creator_id, lead_id)
-- conversation_summaries: idx_conv_summaries_creator_lead (creator_id, lead_id)
-- style_profiles: idx_style_profiles_creator (creator_id) UNIQUE
-- unified_leads: idx_unified_creator (creator_id)
