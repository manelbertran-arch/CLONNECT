"""add gold_examples table for few-shot prompt injection

Stores high-quality creator response examples for injection into DM prompts
as few-shot examples. Sources: approved, minor edits, manual overrides.

Revision ID: 028
Revises: 027
Create Date: 2026-02-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gold_examples",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("creator_id", UUID(as_uuid=True), sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("creator_response", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(50), nullable=True),
        sa.Column("lead_stage", sa.String(30), nullable=True),
        sa.Column("relationship_type", sa.String(30), nullable=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("source_message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("quality_score", sa.Float(), server_default="0.5"),
        sa.Column("times_used", sa.Integer(), server_default="0"),
        sa.Column("times_helpful", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_gold_examples_creator_active", "gold_examples", ["creator_id", "is_active"])
    op.create_index("idx_gold_examples_creator_intent", "gold_examples", ["creator_id", "intent", "is_active"])


def downgrade():
    op.drop_table("gold_examples")
