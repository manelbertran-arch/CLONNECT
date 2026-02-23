"""Add personality_docs table for persistent Doc D/E storage.

Revision ID: 033
Revises: 032_add_commitments
Create Date: 2026-02-23

Problem: Railway uses an ephemeral filesystem. personality_extraction saves
Doc D (bot configuration) and Doc E (copilot rules) only to disk. Every deploy
wipes these files, losing all extracted personality data.

Solution: Store the full markdown content of each doc in PostgreSQL so it
survives deploys. personality_loader reads from DB first, falls back to disk.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "personality_docs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("creator_id", sa.String(), nullable=False),
        sa.Column("doc_type", sa.String(10), nullable=False),   # doc_d | doc_e
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("creator_id", "doc_type", name="uq_personality_docs_creator_type"),
    )
    op.create_index(
        "ix_personality_docs_creator_id",
        "personality_docs",
        ["creator_id"],
    )


def downgrade():
    op.drop_index("ix_personality_docs_creator_id", table_name="personality_docs")
    op.drop_table("personality_docs")
