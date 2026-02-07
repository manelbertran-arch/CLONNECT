"""Add csat_ratings table for metrics system

Revision ID: 015
Revises: 014
Create Date: 2026-02-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "csat_ratings",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("lead_id", UUID(as_uuid=True), nullable=False),
        sa.Column("creator_id", UUID(as_uuid=True), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_csat_rating_range"),
        sa.UniqueConstraint("lead_id", name="uq_csat_lead_id"),
    )
    op.create_index("idx_csat_creator", "csat_ratings", ["creator_id"])
    op.create_index("idx_csat_created", "csat_ratings", ["created_at"])


def downgrade():
    op.drop_index("idx_csat_created")
    op.drop_index("idx_csat_creator")
    op.drop_table("csat_ratings")
