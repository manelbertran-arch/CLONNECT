"""Add security_events table (QW3 — security alerting).

Revision ID: 045
Revises: 044
Create Date: 2026-04-16

Persistent log for prompt_injection and sensitive_content detection events.
GDPR-compliant: stores SHA256 content hash, never raw message content.

Columns:
  id              — autoincrement PK
  creator_id      — slug (e.g. "iris_bertran"); not a UUID (see CLAUDE.md)
  sender_id       — Instagram platform_user_id (raw numeric, no "ig_" prefix)
  event_type      — "prompt_injection" | "sensitive_content" | "rate_limit_summary"
  severity        — "INFO" | "WARNING" | "CRITICAL"
  content_hash    — SHA256 hex digest (64 chars) of the triggering message
  message_length  — int, raw character length of the message
  event_metadata  — JSONB bag (pattern snippet, sensitive_category, suppressed_count, …)
  created_at      — server-default NOW(), timezone-aware

Indexes:
  idx_security_events_creator_sender_type_time — composite for "recent events
    for this lead" queries. Postgres can scan ASC indexes backward for
    newest-first queries, so DESC modifier is not needed.
  created_at single-column index enables time-window reports.
"""

revision = "045"
down_revision = "044"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # Single-column indexes are omitted on purpose — the composite
        # idx_security_events_creator_sender_type_time covers the common
        # query shapes (by creator, or by creator+sender, or by
        # creator+sender+type) via leading-column use.
        sa.Column("creator_id", sa.String(length=100), nullable=False),
        sa.Column("sender_id", sa.String(length=100), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("message_length", sa.Integer(), nullable=True),
        sa.Column("event_metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_security_events_creator_sender_type_time",
        "security_events",
        ["creator_id", "sender_id", "event_type", "created_at"],
    )
    op.create_index(
        "idx_security_events_created_at",
        "security_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_security_events_created_at", table_name="security_events")
    op.drop_index("idx_security_events_creator_sender_type_time", table_name="security_events")
    op.drop_table("security_events")
