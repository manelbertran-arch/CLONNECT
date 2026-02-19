"""cleanup duplicate pending_approval messages

For each lead that has multiple pending_approval messages, keep the latest
one and delete the rest. Also discard any pending_approval older than 7 days.

Revision ID: 021
Revises: 020
Create Date: 2026-02-19

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '021'
down_revision: Union[str, None] = '020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. For each lead with multiple pending_approval messages,
    #    keep the newest and delete the rest.
    op.execute(
        """
        DELETE FROM messages
        WHERE id IN (
            SELECT m.id
            FROM messages m
            INNER JOIN (
                SELECT lead_id, MAX(created_at) AS max_created
                FROM messages
                WHERE role = 'assistant'
                  AND status = 'pending_approval'
                GROUP BY lead_id
                HAVING COUNT(*) > 1
            ) dupes ON m.lead_id = dupes.lead_id
            WHERE m.role = 'assistant'
              AND m.status = 'pending_approval'
              AND m.created_at < dupes.max_created
        )
        """
    )

    # 2. Auto-discard stale pending_approval messages older than 7 days
    op.execute(
        """
        UPDATE messages
        SET status = 'discarded',
            approved_by = 'auto_cleanup'
        WHERE role = 'assistant'
          AND status = 'pending_approval'
          AND created_at < NOW() - INTERVAL '7 days'
        """
    )


def downgrade() -> None:
    # Data cleanup migration — no structural changes to revert
    pass
