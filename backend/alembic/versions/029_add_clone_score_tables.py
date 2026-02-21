"""add clone_score_evaluations and clone_score_test_sets tables

Tables for the CloneScore Engine (Sprint 2) — 6-dimension quality
evaluation system for creator clones.

Revision ID: 029
Revises: 028
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade():
    # CloneScore evaluation snapshots
    op.create_table(
        "clone_score_evaluations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("creator_id", UUID(as_uuid=True), sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("eval_type", sa.String(20), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("dimension_scores", JSONB(), nullable=False),
        sa.Column("sample_size", sa.Integer(), server_default="1"),
        sa.Column("eval_metadata", JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_clone_score_evals_creator", "clone_score_evaluations", ["creator_id"])
    op.create_index("idx_clone_score_evals_creator_type", "clone_score_evaluations", ["creator_id", "eval_type"])
    op.create_index("idx_clone_score_evals_evaluated_at", "clone_score_evaluations", ["evaluated_at"])

    # CloneScore test sets with ground-truth pairs
    op.create_table(
        "clone_score_test_sets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("creator_id", UUID(as_uuid=True), sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("test_pairs", JSONB(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_clone_score_test_sets_creator", "clone_score_test_sets", ["creator_id"])


def downgrade():
    op.drop_table("clone_score_test_sets")
    op.drop_table("clone_score_evaluations")
