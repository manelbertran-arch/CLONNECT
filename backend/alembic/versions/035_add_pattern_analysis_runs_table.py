"""Add pattern_analysis_runs table for Pattern Analyzer audit trail.

Revision ID: 035
Revises: 034
Create Date: 2026-02-23

Problem: pattern_analyzer.py runs entirely in memory — results (pairs analyzed,
rules created) are never persisted. There is no way to know when pattern analysis
last ran for a creator or whether it's producing rules.

Solution: pattern_analysis_runs table records every run. run_pattern_analysis()
inserts one row per execution so callers can track analysis cadence.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pattern_analysis_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creator_id", UUID(as_uuid=True), sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("pairs_analyzed", sa.Integer(), server_default="0"),
        sa.Column("rules_created", sa.Integer(), server_default="0"),
        sa.Column("groups_processed", sa.Integer(), server_default="0"),
        sa.Column("details", JSONB, server_default="{}"),
    )
    op.create_index("idx_pattern_runs_creator", "pattern_analysis_runs", ["creator_id"])
    op.create_index("idx_pattern_runs_ran_at", "pattern_analysis_runs", ["ran_at"])


def downgrade():
    op.drop_index("idx_pattern_runs_ran_at", table_name="pattern_analysis_runs")
    op.drop_index("idx_pattern_runs_creator", table_name="pattern_analysis_runs")
    op.drop_table("pattern_analysis_runs")
