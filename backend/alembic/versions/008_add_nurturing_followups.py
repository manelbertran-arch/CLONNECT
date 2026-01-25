"""add_nurturing_followups

Create nurturing_followups table for persistent follow-up storage.
Replaces JSON file storage with PostgreSQL for better scalability and querying.

Revision ID: 008
Revises: 007
Create Date: 2026-01-25

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    """Create nurturing_followups table with indexes for efficient querying."""
    op.create_table(
        "nurturing_followups",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("creator_id", sa.String(100), nullable=False),
        sa.Column("follower_id", sa.String(100), nullable=False),
        sa.Column("sequence_type", sa.String(50), nullable=False),
        sa.Column("step", sa.Integer, nullable=False, default=0),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message_template", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", JSONB, nullable=True, default={}),  # Renamed from metadata - reserved in SQLAlchemy
    )

    # Index for getting pending followups by creator (most common query)
    op.create_index(
        "ix_nurturing_followups_creator_status", "nurturing_followups", ["creator_id", "status"]
    )

    # Index for time-based queries (scheduled_at)
    op.create_index("ix_nurturing_followups_scheduled_at", "nurturing_followups", ["scheduled_at"])

    # Index for follower lookups (cancellation, history)
    op.create_index(
        "ix_nurturing_followups_follower", "nurturing_followups", ["creator_id", "follower_id"]
    )

    # Index for sequence type queries
    op.create_index(
        "ix_nurturing_followups_sequence_type", "nurturing_followups", ["sequence_type", "status"]
    )


def downgrade():
    """Drop nurturing_followups table and indexes."""
    op.drop_index("ix_nurturing_followups_sequence_type")
    op.drop_index("ix_nurturing_followups_follower")
    op.drop_index("ix_nurturing_followups_scheduled_at")
    op.drop_index("ix_nurturing_followups_creator_status")
    op.drop_table("nurturing_followups")
