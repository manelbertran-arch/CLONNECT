"""Add relationship_type and score_updated_at to leads table

Revision ID: 017
Revises: 016
Create Date: 2026-02-15
"""

import sqlalchemy as sa
from alembic import op

revision = "017"
down_revision = "de251aff9bac"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Add relationship_type column
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'leads' AND column_name = 'relationship_type'"
        )
    ).fetchone()
    if not result:
        op.add_column("leads", sa.Column("relationship_type", sa.String(30), server_default="nuevo"))

    # Add score_updated_at column
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'leads' AND column_name = 'score_updated_at'"
        )
    ).fetchone()
    if not result:
        op.add_column("leads", sa.Column("score_updated_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("leads", "score_updated_at")
    op.drop_column("leads", "relationship_type")
