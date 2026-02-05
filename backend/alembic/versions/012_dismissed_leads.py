"""Add dismissed_leads table for blocklist

Revision ID: 012
Revises: 011
Create Date: 2026-02-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dismissed_leads",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "creator_id",
            UUID(as_uuid=True),
            sa.ForeignKey("creators.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform_user_id", sa.String(255), nullable=False),
        sa.Column("username", sa.String(255)),  # For debug/reference
        sa.Column(
            "dismissed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column("reason", sa.String(50), server_default="manual_delete"),
    )

    # Unique index to avoid duplicates
    op.create_index(
        "ix_dismissed_leads_creator_platform",
        "dismissed_leads",
        ["creator_id", "platform_user_id"],
        unique=True,
    )

    # Index for fast lookups
    op.create_index("ix_dismissed_leads_platform_user_id", "dismissed_leads", ["platform_user_id"])


def downgrade():
    op.drop_index("ix_dismissed_leads_platform_user_id")
    op.drop_index("ix_dismissed_leads_creator_platform")
    op.drop_table("dismissed_leads")
