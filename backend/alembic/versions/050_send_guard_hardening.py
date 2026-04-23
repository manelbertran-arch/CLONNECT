"""SendGuard hardening: Creator.name UNIQUE + copilot_mode NOT NULL backfill.

Phase 5 of branch `forensic/send-guard-20260423`.

Fixes:
- BUG-02 (CRITICAL): Creator.name is not UNIQUE → cross-tenant consent leak risk
  when two creator rows share a slug. Add UNIQUE constraint. Fails loudly if
  duplicates exist today (DO NOT auto-fix; human cleanup required before migrate).
- BUG-03 (HIGH): Legacy Creator rows may have copilot_mode=NULL, which the guard
  evaluates as `not None == True` → autopilot pass on unconfigured rows. Backfill
  NULL → True (conservative default: assume copilot review-mode) and enforce
  NOT NULL.

Revision ID: 050
Revises: 049
Create Date: 2026-04-23

Safety:
- Not intended for auto-apply in CI. Run manually against staging DB first.
- Gate: pre-check duplicates; abort with an explicit message if any exist.
"""

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None

from alembic import op
from sqlalchemy import text


def upgrade() -> None:
    conn = op.get_bind()

    # ── Pre-check 1: no duplicate Creator.name rows ─────────────────────────
    duplicates = conn.execute(
        text(
            """
            SELECT name, COUNT(*) AS n
            FROM creators
            GROUP BY name
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if duplicates:
        pretty = ", ".join(f"{row.name!r} (x{row.n})" for row in duplicates)
        raise RuntimeError(
            "Migration 050 aborted: duplicate Creator.name rows detected "
            f"— clean up manually before re-running. Duplicates: {pretty}"
        )

    # ── Pre-check 2: report how many NULL copilot_mode rows we'll backfill ──
    null_count = conn.execute(
        text("SELECT COUNT(*) FROM creators WHERE copilot_mode IS NULL")
    ).scalar()
    if null_count:
        # Informational only; backfill is safe (NULL → True = most conservative).
        op.execute(
            "UPDATE creators SET copilot_mode = TRUE WHERE copilot_mode IS NULL"
        )

    # ── Apply constraints ───────────────────────────────────────────────────
    # 1) Creator.name UNIQUE — safe after the pre-check above.
    op.create_unique_constraint("creators_name_key", "creators", ["name"])

    # 2) Creator.copilot_mode NOT NULL + retain default TRUE.
    op.alter_column(
        "creators",
        "copilot_mode",
        nullable=False,
        existing_type=None,
        existing_server_default=None,
    )


def downgrade() -> None:
    op.alter_column(
        "creators",
        "copilot_mode",
        nullable=True,
        existing_type=None,
    )
    op.drop_constraint("creators_name_key", "creators", type_="unique")
