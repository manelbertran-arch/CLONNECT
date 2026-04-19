"""ARC3 Phase 2: context_compactor_shadow_log table.

Stores shadow decisions from PromptSliceCompactor — what the compactor
*would have* done, without altering the actual prompt. Used to calibrate
ratios before Phase 3 live activation.

Revision ID: 049
Revises: 048
Create Date: 2026-04-19
"""

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None

from alembic import op
from sqlalchemy import inspect, text


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if "context_compactor_shadow_log" in inspector.get_table_names():
        return  # idempotent

    op.execute(text("""
        CREATE TABLE context_compactor_shadow_log (
            id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            creator_id         UUID        NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
            lead_id            UUID        REFERENCES leads(id) ON DELETE SET NULL,
            sender_id          TEXT,
            turn_id            UUID,
            timestamp          TIMESTAMP   NOT NULL DEFAULT NOW(),
            total_budget_chars INT         NOT NULL,
            actual_chars_before INT        NOT NULL,
            shadow_chars_after INT         NOT NULL,
            compaction_applied BOOLEAN     NOT NULL DEFAULT false,
            reason             VARCHAR(50) NOT NULL DEFAULT 'OK',
            sections_truncated JSONB       NOT NULL DEFAULT '[]',
            distill_applied    BOOLEAN     NOT NULL DEFAULT false,
            divergence_chars   INT         NOT NULL DEFAULT 0,
            model              VARCHAR(100)
        )
    """))

    op.execute(text("""
        CREATE INDEX idx_shadow_creator
            ON context_compactor_shadow_log(creator_id)
    """))

    op.execute(text("""
        CREATE INDEX idx_shadow_created
            ON context_compactor_shadow_log(timestamp DESC)
    """))

    op.execute(text("""
        CREATE INDEX idx_shadow_compaction
            ON context_compactor_shadow_log(compaction_applied)
            WHERE compaction_applied = true
    """))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if "context_compactor_shadow_log" not in inspector.get_table_names():
        return

    op.execute(text("DROP INDEX IF EXISTS idx_shadow_compaction"))
    op.execute(text("DROP INDEX IF EXISTS idx_shadow_created"))
    op.execute(text("DROP INDEX IF EXISTS idx_shadow_creator"))
    op.drop_table("context_compactor_shadow_log")
