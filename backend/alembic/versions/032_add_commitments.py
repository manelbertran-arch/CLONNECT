"""Create commitments table.

Part of ECHO Engine Sprint 4 — Commitment Tracker.
Tracks promises made by the clone (e.g. "te envío el link mañana")
and ensures follow-up.

Revision ID: 032
Revises: 031
Create Date: 2026-02-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "commitments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("creator_id", UUID(as_uuid=True),
                   sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("lead_id", UUID(as_uuid=True),
                   sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("commitment_text", sa.Text, nullable=False),
        sa.Column("commitment_type", sa.String(30), server_default="promise"),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("source_message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("detected_by", sa.String(20), server_default="llm"),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                   server_default=sa.func.now()),
    )
    op.create_index(
        "idx_commitments_creator_lead",
        "commitments",
        ["creator_id", "lead_id"],
    )
    op.create_index(
        "idx_commitments_status",
        "commitments",
        ["creator_id", "status"],
    )


def downgrade():
    op.drop_index("idx_commitments_status")
    op.drop_index("idx_commitments_creator_lead")
    op.drop_table("commitments")
