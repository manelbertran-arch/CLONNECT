"""Add partial unique index on (lead_id, platform_message_id) where not null.

Revision ID: 037
Revises: 036
Create Date: 2026-03-14

Problem: No DB-level deduplication for messages. If Evolution API replays
messages on reconnect (and in-memory dedup is lost on redeploy), the same
message can be inserted multiple times for the same lead.

Solution: Partial unique index on (lead_id, platform_message_id) WHERE
platform_message_id IS NOT NULL. NULLs are excluded so media messages
without an ID (stickers, historical imports with no ID) are unaffected.
The same outgoing broadcast message (same platform_message_id) can still
appear for different leads (different lead_id), which is correct.
"""

from alembic import op


revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_lead_platform_message_id
        ON messages (lead_id, platform_message_id)
        WHERE platform_message_id IS NOT NULL;
    """)


def downgrade():
    op.drop_index("uq_messages_lead_platform_message_id", table_name="messages")
