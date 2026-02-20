"""add preference_pairs table for DPO/RLHF training data

Stores (chosen, rejected) pairs from every copilot action + Best-of-N
candidate rankings. Used by pattern analyzer and future model training.

Revision ID: 026
Revises: 025
Create Date: 2026-02-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "preference_pairs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("creator_id", UUID(as_uuid=True), sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("source_message_id", UUID(as_uuid=True), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("chosen", sa.Text(), nullable=True),
        sa.Column("rejected", sa.Text(), nullable=True),
        sa.Column("user_message", sa.Text(), nullable=True),
        sa.Column("system_prompt_hash", sa.String(64), nullable=True),
        sa.Column("conversation_context", JSONB, server_default="[]"),
        sa.Column("intent", sa.String(50), nullable=True),
        sa.Column("lead_stage", sa.String(50), nullable=True),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("chosen_temperature", sa.Float(), nullable=True),
        sa.Column("rejected_temperature", sa.Float(), nullable=True),
        sa.Column("chosen_confidence", sa.Float(), nullable=True),
        sa.Column("rejected_confidence", sa.Float(), nullable=True),
        sa.Column("confidence_delta", sa.Float(), nullable=True),
        sa.Column("edit_diff", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("batch_analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_preference_pairs_creator", "preference_pairs", ["creator_id"])
    op.create_index("idx_preference_pairs_action", "preference_pairs", ["action_type"])
    op.create_index("idx_preference_pairs_created", "preference_pairs", ["created_at"])
    op.create_index(
        "idx_preference_pairs_unanalyzed",
        "preference_pairs",
        ["creator_id", "batch_analyzed_at"],
        postgresql_where=sa.text("batch_analyzed_at IS NULL"),
    )


def downgrade():
    op.drop_table("preference_pairs")
