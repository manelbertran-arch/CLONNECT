"""Add doc_d_versions table with metadata JSONB + content_hash (idempotent).

Revision ID: 046
Revises: 045
Create Date: 2026-04-17

Creates doc_d_versions if it doesn't already exist (safe for prod where the
table may have been bootstrapped manually). Adds metadata JSONB and
content_hash columns with IF NOT EXISTS so re-running is harmless.

Columns:
  id                — UUID PK
  creator_id        — UUID FK → creators.id
  doc_d_text        — TEXT, full Doc D snapshot
  trigger           — VARCHAR(80): "weekly_compilation" | "manual_snapshot" | "rollback"
  categories_updated — JSONB list of updated section names
  content_hash      — SHA256 hex digest (64 chars) for dedup
  metadata          — JSONB bag (tag, trigger_detail, previous_version_id, …)
  created_at        — TIMESTAMPTZ server-default NOW()

Indexes:
  idx_doc_d_versions_creator_created — (creator_id, created_at DESC) for
    "latest snapshot per creator" queries.
  idx_doc_d_versions_content_hash_creator — (creator_id, content_hash, created_at)
    for 24h dedup check.
"""

revision = "046"
down_revision = "045"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import inspect


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "doc_d_versions" not in tables:
        op.create_table(
            "doc_d_versions",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("creator_id", sa.UUID(), nullable=False),
            sa.Column("doc_d_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("trigger", sa.String(length=80), nullable=False, server_default="unknown"),
            sa.Column("categories_updated", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("content_hash", sa.String(length=64), nullable=True),
            sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
    else:
        # Table exists (manually bootstrapped) — add missing columns
        existing_cols = {c["name"] for c in inspector.get_columns("doc_d_versions")}
        if "content_hash" not in existing_cols:
            op.add_column(
                "doc_d_versions",
                sa.Column("content_hash", sa.String(length=64), nullable=True),
            )
        if "metadata" not in existing_cols:
            op.add_column(
                "doc_d_versions",
                sa.Column(
                    "metadata",
                    JSONB(),
                    nullable=False,
                    server_default=sa.text("'{}'::jsonb"),
                ),
            )

    # Indexes — guard against re-running on a table that already has them
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("doc_d_versions")}

    if "idx_doc_d_versions_creator_created" not in existing_indexes:
        op.create_index(
            "idx_doc_d_versions_creator_created",
            "doc_d_versions",
            ["creator_id", sa.text("created_at DESC")],
        )
    if "idx_doc_d_versions_content_hash_creator" not in existing_indexes:
        op.create_index(
            "idx_doc_d_versions_content_hash_creator",
            "doc_d_versions",
            ["creator_id", "content_hash", "created_at"],
        )


def downgrade() -> None:
    try:
        op.drop_index("idx_doc_d_versions_content_hash_creator", table_name="doc_d_versions")
    except Exception:
        pass
    try:
        op.drop_index("idx_doc_d_versions_creator_created", table_name="doc_d_versions")
    except Exception:
        pass
    op.drop_table("doc_d_versions")
