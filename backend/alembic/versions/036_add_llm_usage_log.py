"""Add llm_usage_log table for per-call token tracking.

Revision ID: 036
Revises: 035
Create Date: 2026-03-11

Problem: LLM token usage is logged to stdout but never persisted.
There is no way to know actual spend by provider, model, or call type.

Solution: llm_usage_log records every successful LLM call with tokens_in,
tokens_out, latency_ms, provider, and model. Inserted fire-and-forget
from gemini_provider.py — never blocks generation.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "llm_usage_log",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("call_type", sa.String(50), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("idx_llm_usage_created_at", "llm_usage_log", ["created_at"])
    op.create_index("idx_llm_usage_provider_model", "llm_usage_log", ["provider", "model"])


def downgrade():
    op.drop_index("idx_llm_usage_provider_model", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_created_at", table_name="llm_usage_log")
    op.drop_table("llm_usage_log")
