"""Add indexes to messages table for performance

Revision ID: 013
Revises: 012
Create Date: 2026-02-06

The get_leads query was taking 39+ seconds because it queries
last message for each lead without proper indexes.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    # Index for finding messages by lead_id (most common query)
    op.create_index(
        "ix_messages_lead_id",
        "messages",
        ["lead_id"],
        if_not_exists=True,
    )

    # Composite index for finding latest message per lead
    # This speeds up: SELECT MAX(created_at) FROM messages WHERE lead_id = X
    op.create_index(
        "ix_messages_lead_id_created_at",
        "messages",
        ["lead_id", "created_at"],
        if_not_exists=True,
    )

    # Index for conversation queries (if conversation_id is used)
    op.create_index(
        "ix_messages_conversation_id",
        "messages",
        ["conversation_id"],
        if_not_exists=True,
    )


def downgrade():
    op.drop_index("ix_messages_lead_id", table_name="messages")
    op.drop_index("ix_messages_lead_id_created_at", table_name="messages")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
