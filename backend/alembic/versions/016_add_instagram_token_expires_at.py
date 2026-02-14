"""Add instagram_token_expires_at to creators table

Revision ID: 016
Revises: 015
Create Date: 2026-02-14
"""

import sqlalchemy as sa
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade():
    # Column may already exist from raw SQL usage; use IF NOT EXISTS pattern
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'creators' AND column_name = 'instagram_token_expires_at'"
        )
    ).fetchone()
    if not result:
        op.add_column(
            "creators",
            sa.Column("instagram_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    op.drop_column("creators", "instagram_token_expires_at")
