"""Add last_consolidated_at column to creators table.

Revision ID: 044
Revises: 043
Create Date: 2026-04-12

CC-faithful: consolidationLock.ts stores lastConsolidatedAt as lock file mtime.
Clonnect adaptation: dedicated column on creators table (per-creator, no fake rows
in lead_memories). Replaces the _consolidation_timestamp fact_type hack.
"""

revision = "044"
down_revision = "043"

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        "creators",
        sa.Column("last_consolidated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Migrate existing _consolidation_timestamp rows to the new column,
    # then clean them up.
    op.execute(
        """
        UPDATE creators c
        SET last_consolidated_at = sub.ts
        FROM (
            SELECT creator_id, MAX(created_at) AS ts
            FROM lead_memories
            WHERE fact_type = '_consolidation_timestamp' AND is_active = true
            GROUP BY creator_id
        ) sub
        WHERE c.id = sub.creator_id
        """
    )
    # Deactivate old fake rows
    op.execute(
        """
        UPDATE lead_memories
        SET is_active = false, updated_at = NOW()
        WHERE fact_type = '_consolidation_timestamp'
        """
    )


def downgrade() -> None:
    op.drop_column("creators", "last_consolidated_at")
