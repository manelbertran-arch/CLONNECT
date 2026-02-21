"""add lead_memories and conversation_summaries tables

Tables for the Memory Engine (Sprint 3) — per-lead fact extraction
with pgvector semantic recall and Ebbinghaus decay.

Revision ID: 030
Revises: 029
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade():
    # Lead memories with pgvector embeddings
    op.create_table(
        "lead_memories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creator_id", UUID(as_uuid=True), sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("lead_id", UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("fact_type", sa.String(30), nullable=False),
        sa.Column("fact_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.7"),
        sa.Column("source_message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.String(30), server_default="'extracted'"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("superseded_by", UUID(as_uuid=True), nullable=True),
        sa.Column("times_accessed", sa.Integer(), server_default="0"),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_lead_memories_creator_lead", "lead_memories", ["creator_id", "lead_id"])
    op.create_index("idx_lead_memories_active", "lead_memories", ["creator_id", "lead_id", "is_active"])
    op.create_index("idx_lead_memories_type", "lead_memories", ["creator_id", "lead_id", "fact_type"])

    # Add pgvector column via raw SQL (Alembic doesn't support vector type natively)
    op.execute("ALTER TABLE lead_memories ADD COLUMN fact_embedding vector(1536)")

    # IVFFlat index for fast cosine similarity search
    # NOTE: requires at least 1 row to build; index is created but empty until data arrives
    op.execute(
        "CREATE INDEX idx_lead_memories_embedding ON lead_memories "
        "USING ivfflat (fact_embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # Conversation summaries
    op.create_table(
        "conversation_summaries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("creator_id", UUID(as_uuid=True), sa.ForeignKey("creators.id"), nullable=False),
        sa.Column("lead_id", UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("key_topics", JSONB(), server_default="[]"),
        sa.Column("commitments_made", JSONB(), server_default="[]"),
        sa.Column("sentiment", sa.String(20), server_default="'neutral'"),
        sa.Column("message_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_conv_summaries_creator_lead", "conversation_summaries", ["creator_id", "lead_id"])


def downgrade():
    op.drop_table("conversation_summaries")
    op.execute("DROP INDEX IF EXISTS idx_lead_memories_embedding")
    op.drop_table("lead_memories")
