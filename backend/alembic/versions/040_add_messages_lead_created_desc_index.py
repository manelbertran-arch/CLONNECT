"""Add (lead_id, created_at DESC) index on messages for DISTINCT ON last-message query.

Revision ID: 040
Revises: 039
Create Date: 2026-03-17

Background:
  conversations endpoint was doing a MAX(created_at) subquery + JOIN to find the
  last message per lead. With 1500+ leads, this caused 10+ second queries that
  exhausted the DB connection pool.

  Replaced with DISTINCT ON (lead_id) ORDER BY lead_id, created_at DESC which
  needs a supporting index to avoid a full sort of the filtered message set.

Index added:
  messages (lead_id, created_at DESC) WHERE deleted_at IS NULL
    — covers the DISTINCT ON query in get_conversations
    — partial index keeps it small (excludes deleted messages)
"""

from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_lead_created_desc
        ON messages (lead_id, created_at DESC)
        WHERE deleted_at IS NULL
    """)


def downgrade():
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_messages_lead_created_desc")
