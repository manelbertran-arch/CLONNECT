"""ARC3 Phase 1: creator_style_distill table — StyleDistillCache.

Stores distilled (compressed) versions of creator Doc D (style_prompt).
Each row represents a distilled version for a specific (creator, doc_d_hash,
prompt_version) triple. SHADOW phase — table exists but is not read in prod
until USE_DISTILLED_DOC_D=true is enabled (Phase 3).

Revision ID: 048
Revises: 047
Create Date: 2026-04-19
"""

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect, text


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if "creator_style_distill" in inspector.get_table_names():
        return  # already applied (idempotent)

    op.execute(text("""
        CREATE TABLE creator_style_distill (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
            doc_d_hash TEXT NOT NULL,
            doc_d_chars INT NOT NULL,
            doc_d_version INT NOT NULL,
            distilled_short TEXT NOT NULL,
            distilled_med TEXT,
            distilled_chars INT NOT NULL,
            distill_model TEXT NOT NULL,
            distill_prompt_version INT NOT NULL,
            quality_score FLOAT,
            human_validated BOOL DEFAULT false,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(creator_id, doc_d_hash, distill_prompt_version)
        )
    """))

    op.execute(text("""
        CREATE INDEX idx_style_distill_creator_hash
            ON creator_style_distill(creator_id, doc_d_hash)
    """))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if "creator_style_distill" not in inspector.get_table_names():
        return

    op.execute(text("DROP INDEX IF EXISTS idx_style_distill_creator_hash"))
    op.drop_table("creator_style_distill")
