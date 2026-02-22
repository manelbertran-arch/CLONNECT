"""Create style_profiles table.

Part of ECHO Engine Sprint 1 — Style Analyzer.
Stores data-driven style profiles extracted from creator messages.

Revision ID: 031
Revises: 030
Create Date: 2026-02-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "style_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                   server_default=sa.text("gen_random_uuid()")),
        sa.Column("creator_id", UUID(as_uuid=True),
                   sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("profile_data", JSONB, nullable=False),
        sa.Column("version", sa.Integer, default=1),
        sa.Column("confidence", sa.Float, default=0.5),
        sa.Column("messages_analyzed", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                   server_default=sa.func.now()),
    )
    op.create_index(
        "idx_style_profiles_creator",
        "style_profiles",
        ["creator_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("idx_style_profiles_creator")
    op.drop_table("style_profiles")
