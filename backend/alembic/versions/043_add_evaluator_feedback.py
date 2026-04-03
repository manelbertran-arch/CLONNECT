"""Add evaluator_feedback table for structured human evaluator feedback.

Revision ID: 043
Revises: 042
Create Date: 2026-04-02

Captures scores, corrections, and error identifications from human evaluators.
Each record with ideal_response auto-generates a preference pair + gold example.
"""

revision = "043"
down_revision = "042"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


def upgrade() -> None:
    op.create_table(
        "evaluator_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creator_id", UUID(as_uuid=True), sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("evaluator_id", sa.String(50), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_message_id", UUID(as_uuid=True), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("bot_response", sa.Text(), nullable=False),
        sa.Column("conversation_history", JSONB, nullable=True),
        sa.Column("intent_detected", sa.String(50), nullable=True),
        sa.Column("coherencia", sa.Integer(), nullable=True),
        sa.Column("lo_enviarias", sa.Integer(), nullable=True),
        sa.Column("ideal_response", sa.Text(), nullable=True),
        sa.Column("error_tags", JSONB, nullable=True),
        sa.Column("error_free_text", sa.Text(), nullable=True),
        sa.Column("doc_d_version", sa.String(50), nullable=True),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("system_prompt_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("idx_evaluator_feedback_creator", "evaluator_feedback", ["creator_id"])
    op.create_index("idx_evaluator_feedback_creator_evaluator", "evaluator_feedback", ["creator_id", "evaluator_id"])
    op.create_index("idx_evaluator_feedback_created", "evaluator_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_evaluator_feedback_created", table_name="evaluator_feedback")
    op.drop_index("idx_evaluator_feedback_creator_evaluator", table_name="evaluator_feedback")
    op.drop_index("idx_evaluator_feedback_creator", table_name="evaluator_feedback")
    op.drop_table("evaluator_feedback")
