"""Add performance indexes and strip thumbnail_base64 from messages JSONB.

Revision ID: 039
Revises: 038
Create Date: 2026-03-15

Background:
  pg_stat_user_tables showed messages table with 121K sequential scans
  reading 20.7 billion rows. Root causes:
    1. conversations endpoint used global message subqueries (no lead_id filter)
    2. preference_pairs missing indexes on commonly queried columns
    3. nurturing_followups missing composite index for cron job queries

  Additionally: 415 messages stored base64-encoded thumbnails directly in
  msg_metadata JSONB = 751 MB of binary data transferred on every metadata
  query. Cloudinary thumbnail_url is already stored separately — no data loss.

Indexes added:
  messages:
    - (lead_id, role, status) — covers msg_count and pending_copilot subqueries
      after conversations endpoint refactor (which adds lead_id IN filter)

  preference_pairs:
    - source_message_id — for lookups by source message
    - (creator_id, intent) — for analytics queries grouped by intent
    - (creator_id, lead_stage) — for analytics queries grouped by lead_stage

  nurturing_followups:
    - (creator_id, status, scheduled_for) — cron job queries
      "WHERE creator_id = X AND status = 'pending' AND scheduled_for <= now()"

Data migration:
  Strip thumbnail_base64 from messages.msg_metadata for all 415 affected rows.
  Saves ~751 MB of stored data and reduces transfer on every msg_metadata query.
"""

from alembic import op


revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade():
    # --- Data migration: strip 751 MB of base64 thumbnail data from JSONB ---
    # 415 rows contain thumbnail_base64 in msg_metadata. Cloudinary thumbnail_url
    # is already stored separately. This reduces DB size by ~751 MB.
    op.execute("""
        UPDATE messages
        SET msg_metadata = msg_metadata - 'thumbnail_base64'
        WHERE (msg_metadata ->> 'thumbnail_base64') IS NOT NULL;
    """)

    # messages: composite index covering role+status filters with lead_id
    # After conversations endpoint fix, subqueries filter by lead_id IN (...)
    # + role/status — this index covers those targeted scans.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_lead_role_status
        ON messages (lead_id, role, status);
    """)

    # preference_pairs: source_message_id lookups
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_preference_pairs_source_message_id
        ON preference_pairs (source_message_id)
        WHERE source_message_id IS NOT NULL;
    """)

    # preference_pairs: analytics by creator+intent
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_preference_pairs_creator_intent
        ON preference_pairs (creator_id, intent)
        WHERE intent IS NOT NULL;
    """)

    # preference_pairs: analytics by creator+lead_stage
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_preference_pairs_creator_lead_stage
        ON preference_pairs (creator_id, lead_stage)
        WHERE lead_stage IS NOT NULL;
    """)

    # nurturing_followups: cron job query pattern
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_nurturing_followups_creator_status_scheduled
        ON nurturing_followups (creator_id, status, scheduled_at);
    """)


def downgrade():
    op.drop_index("idx_messages_lead_role_status", table_name="messages")
    op.drop_index("idx_preference_pairs_source_message_id", table_name="preference_pairs")
    op.drop_index("idx_preference_pairs_creator_intent", table_name="preference_pairs")
    op.drop_index("idx_preference_pairs_creator_lead_stage", table_name="preference_pairs")
    op.drop_index("idx_nurturing_followups_creator_status_scheduled", table_name="nurturing_followups")
