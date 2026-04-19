"""ARC2 A2.1: arc2_lead_memories table — unified 5-type schema with pgvector.

Creates arc2_lead_memories as a NEW table (separate from the legacy
lead_memories table used by MemoryEngine). The legacy table remains
untouched. ARC2 migration scripts (Worker A2.3) will migrate data later.

Vector dim: 1536 — matches existing pgvector setup in migration 030.

Revision ID: 047
Revises: 046
Create Date: 2026-04-19
"""

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import inspect, text


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # pgvector must be enabled — idempotent
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    if "arc2_lead_memories" in inspector.get_table_names():
        return  # already applied

    # Main table
    op.execute(text("""
        CREATE TABLE arc2_lead_memories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            creator_id UUID NOT NULL REFERENCES creators(id),
            lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            memory_type TEXT NOT NULL CHECK (memory_type IN (
                'identity', 'interest', 'objection',
                'intent_signal', 'relationship_state'
            )),
            content TEXT NOT NULL,
            why TEXT,
            how_to_apply TEXT,
            body_extras JSONB NOT NULL DEFAULT '{}',
            embedding vector(1536),
            source_message_id UUID REFERENCES messages(id),
            confidence FLOAT NOT NULL DEFAULT 1.0
                CHECK (confidence >= 0.0 AND confidence <= 1.0),
            last_writer TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ,
            superseded_by UUID REFERENCES arc2_lead_memories(id),
            UNIQUE (creator_id, lead_id, memory_type, content),
            CONSTRAINT chk_arc2_objection_body
                CHECK (memory_type != 'objection'
                       OR (why IS NOT NULL AND how_to_apply IS NOT NULL)),
            CONSTRAINT chk_arc2_relationship_state_body
                CHECK (memory_type != 'relationship_state'
                       OR (why IS NOT NULL AND how_to_apply IS NOT NULL))
        )
    """))

    # updated_at trigger
    op.execute(text("""
        CREATE OR REPLACE FUNCTION arc2_lead_memories_set_updated_at()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$
    """))
    op.execute(text("""
        CREATE TRIGGER trg_arc2_lead_memories_updated_at
        BEFORE UPDATE ON arc2_lead_memories
        FOR EACH ROW EXECUTE FUNCTION arc2_lead_memories_set_updated_at()
    """))

    # Indexes
    op.create_index(
        "idx_arc2_lead_memories_lead",
        "arc2_lead_memories", ["creator_id", "lead_id"],
        postgresql_where=text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_arc2_lead_memories_type",
        "arc2_lead_memories", ["creator_id", "lead_id", "memory_type"],
        postgresql_where=text("deleted_at IS NULL"),
    )
    # HNSW — works with any row count (matches migration 038 precedent)
    op.execute(text(
        "CREATE INDEX idx_arc2_lead_memories_embedding "
        "ON arc2_lead_memories "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if "arc2_lead_memories" not in inspector.get_table_names():
        return

    op.execute(text("DROP INDEX IF EXISTS idx_arc2_lead_memories_embedding"))
    op.execute(text("DROP TRIGGER IF EXISTS trg_arc2_lead_memories_updated_at ON arc2_lead_memories"))
    op.execute(text("DROP FUNCTION IF EXISTS arc2_lead_memories_set_updated_at"))

    try:
        op.drop_index("idx_arc2_lead_memories_type", table_name="arc2_lead_memories")
    except Exception:
        pass
    try:
        op.drop_index("idx_arc2_lead_memories_lead", table_name="arc2_lead_memories")
    except Exception:
        pass

    op.drop_table("arc2_lead_memories")
    # NOTE: vector extension NOT dropped — may be used by lead_memories (migration 030)
