"""webhook_multi_creator_routing

Add support for multi-creator webhook routing with:
- Indexes on instagram_page_id and instagram_user_id
- New instagram_additional_ids JSONB field for legacy/secondary IDs
- Webhook tracking fields
- unmatched_webhooks table for debugging

Revision ID: 011_webhook_multi_creator
Revises: 010_add_intelligence_tables
Create Date: 2026-02-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers
revision = "011_webhook_multi_creator"
down_revision = "010_add_intelligence_tables"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add indexes to existing columns for faster lookups
    op.create_index(
        "ix_creators_instagram_page_id",
        "creators",
        ["instagram_page_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_creators_instagram_user_id",
        "creators",
        ["instagram_user_id"],
        unique=False,
        if_not_exists=True,
    )

    # 2. Add new columns to creators table
    op.add_column(
        "creators", sa.Column("instagram_additional_ids", JSONB, server_default="[]", nullable=True)
    )
    op.add_column(
        "creators", sa.Column("webhook_last_received", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "creators", sa.Column("webhook_count", sa.Integer, server_default="0", nullable=True)
    )

    # 3. Create unmatched_webhooks table
    op.create_table(
        "unmatched_webhooks",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("instagram_ids", JSONB, nullable=False),
        sa.Column("payload_summary", JSONB, nullable=True),
        sa.Column("resolved", sa.Boolean, server_default="false", nullable=False),
        sa.Column(
            "resolved_to_creator_id",
            UUID(as_uuid=True),
            sa.ForeignKey("creators.id"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # 4. Add indexes to unmatched_webhooks
    op.create_index(
        "ix_unmatched_webhooks_resolved",
        "unmatched_webhooks",
        ["resolved"],
        postgresql_where=sa.text("NOT resolved"),
    )
    op.create_index(
        "ix_unmatched_webhooks_instagram_ids",
        "unmatched_webhooks",
        ["instagram_ids"],
        postgresql_using="gin",
    )


def downgrade():
    # Drop unmatched_webhooks table and indexes
    op.drop_index("ix_unmatched_webhooks_instagram_ids", table_name="unmatched_webhooks")
    op.drop_index("ix_unmatched_webhooks_resolved", table_name="unmatched_webhooks")
    op.drop_table("unmatched_webhooks")

    # Drop new columns from creators
    op.drop_column("creators", "webhook_count")
    op.drop_column("creators", "webhook_last_received")
    op.drop_column("creators", "instagram_additional_ids")

    # Drop indexes (keep columns, just remove indexes)
    op.drop_index("ix_creators_instagram_user_id", table_name="creators")
    op.drop_index("ix_creators_instagram_page_id", table_name="creators")
