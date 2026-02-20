"""add source column to learning_rules table

Tracks where a learning rule originated from:
- realtime: extracted per copilot action (existing behavior)
- pattern_batch: extracted by LLM-as-Judge pattern analyzer
- consolidation: merged from multiple similar rules

Revision ID: 027
Revises: 026
Create Date: 2026-02-20
"""

from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "learning_rules",
        sa.Column("source", sa.String(30), server_default="realtime", nullable=True),
    )


def downgrade():
    op.drop_column("learning_rules", "source")
