"""Add is_active column to preference_pairs for quality filtering.

Revision ID: 041
Revises: 040
Create Date: 2026-03-26

Allows filtering out low-quality preference pairs before DPO export.
Existing rows default to true (assumed valid).
"""

revision = "041"
down_revision = "040"

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        "preference_pairs",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_index(
        "idx_preference_pairs_active",
        "preference_pairs",
        ["creator_id", "is_active"],
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("idx_preference_pairs_active", table_name="preference_pairs")
    op.drop_column("preference_pairs", "is_active")
