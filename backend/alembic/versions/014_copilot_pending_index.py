"""Add partial index for copilot pending messages

Revision ID: 014
Revises: 013
Create Date: 2026-02-06

Optimizes the /copilot/{creator}/pending endpoint which queries:
- messages WHERE status='pending_approval' AND role='assistant'
- ORDER BY created_at DESC

A partial index only includes matching rows, making it very small and fast.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade():
    # Partial index for copilot pending messages
    # Only indexes rows where status='pending_approval' AND role='assistant'
    # This makes the index very small and queries very fast
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_messages_copilot_pending
        ON messages (lead_id, created_at DESC)
        WHERE status = 'pending_approval' AND role = 'assistant'
    """)

    # Index for user messages lookup (used to get latest user message per lead)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_messages_user_by_lead
        ON messages (lead_id, created_at DESC)
        WHERE role = 'user'
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_messages_copilot_pending")
    op.execute("DROP INDEX IF EXISTS ix_messages_user_by_lead")
