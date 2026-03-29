"""Add creator_profiles table for storing CPE profiles in DB.

Revision ID: 042
Revises: 041
Create Date: 2026-03-29

Stores baseline_metrics, bfi_profile, length_by_intent, and other
per-creator profiles as JSONB. Replaces local JSON files so profiles
are available in all environments (Railway, local, CI).
"""

revision = "042"
down_revision = "041"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


def upgrade() -> None:
    op.create_table(
        "creator_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("creator_id", UUID(as_uuid=True), sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("profile_type", sa.String(50), nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("creator_id", "profile_type", name="uq_creator_profiles_creator_type"),
    )


def downgrade() -> None:
    op.drop_table("creator_profiles")
