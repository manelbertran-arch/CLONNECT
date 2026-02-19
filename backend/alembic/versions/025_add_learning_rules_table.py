"""add learning_rules table for autolearning feedback loop

Stores creator-specific learning rules extracted from copilot actions
(edits, discards, manual overrides). Rules are injected into DM prompts
to autocorrect bot behavior without human intervention.

Revision ID: 025
Revises: 024
Create Date: 2026-02-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("creator_id", UUID(as_uuid=True), sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("pattern", sa.String(50), nullable=False),
        sa.Column("applies_to_relationship_types", JSONB, server_default="[]"),
        sa.Column("applies_to_message_types", JSONB, server_default="[]"),
        sa.Column("applies_to_lead_stages", JSONB, server_default="[]"),
        sa.Column("example_bad", sa.Text(), nullable=True),
        sa.Column("example_good", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="0.5"),
        sa.Column("times_applied", sa.Integer(), server_default="0"),
        sa.Column("times_helped", sa.Integer(), server_default="0"),
        sa.Column("source_message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("superseded_by", UUID(as_uuid=True), sa.ForeignKey("learning_rules.id"), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1"),
    )

    op.create_index(
        "idx_learning_rules_creator_active",
        "learning_rules",
        ["creator_id", "is_active"],
    )
    op.create_index(
        "idx_learning_rules_pattern",
        "learning_rules",
        ["pattern"],
    )


def downgrade():
    op.drop_index("idx_learning_rules_pattern")
    op.drop_index("idx_learning_rules_creator_active")
    op.drop_table("learning_rules")
