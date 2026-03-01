"""replace IVFFlat index with HNSW for lead_memories

IVFFlat with lists=100 requires at least 100 rows to work correctly.
HNSW works well with any number of rows and provides better recall.

Revision ID: 033
Revises: 032
Create Date: 2026-02-23
"""

from alembic import op

revision = "033"
down_revision = "032"
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
