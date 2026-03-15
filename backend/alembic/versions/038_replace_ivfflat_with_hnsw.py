"""Replace IVFFlat index with HNSW for lead_memories.

IVFFlat with lists=100 requires at least 100 rows to work correctly.
HNSW works well with any number of rows and provides better recall.

Revision ID: 038
Revises: 037
Create Date: 2026-02-23

Note: This migration was originally numbered 033 but conflicted with
033_add_personality_docs_table.py (same revision ID). Renumbered to 038
to slot correctly after the applied chain (037).
"""

from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade():
    # Drop the problematic IVFFlat index
    op.execute("DROP INDEX IF EXISTS idx_lead_memories_embedding")

    # Create HNSW index — works with any number of rows, better recall
    op.execute(
        "CREATE INDEX idx_lead_memories_embedding ON lead_memories "
        "USING hnsw (fact_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_lead_memories_embedding")
    op.execute(
        "CREATE INDEX idx_lead_memories_embedding ON lead_memories "
        "USING ivfflat (fact_embedding vector_cosine_ops) WITH (lists = 100)"
    )
