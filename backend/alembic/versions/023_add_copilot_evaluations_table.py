"""add copilot_evaluations table for autolearning

Stores daily and weekly evaluation snapshots used by the
autolearning engine to track pattern changes and calibrate
confidence thresholds over time.

Revision ID: 023
Revises: 022
Create Date: 2026-02-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '023'
down_revision: Union[str, None] = '022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use raw SQL with IF NOT EXISTS to handle table already created by SQLAlchemy auto-create
    op.execute("""
        CREATE TABLE IF NOT EXISTS copilot_evaluations (
            id UUID DEFAULT uuid_generate_v4() NOT NULL PRIMARY KEY,
            creator_id UUID NOT NULL REFERENCES creators(id),
            eval_type VARCHAR(20) NOT NULL,
            eval_date DATE NOT NULL,
            metrics JSON NOT NULL,
            patterns JSON,
            recommendations JSON,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
    """)
    # Create index only if it doesn't exist
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_copilot_evaluations_unique
        ON copilot_evaluations (creator_id, eval_type, eval_date)
    """)
    # Ensure creator_id index exists
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_copilot_evaluations_creator_id
        ON copilot_evaluations (creator_id)
    """)


def downgrade() -> None:
    op.drop_index('ix_copilot_evaluations_unique', table_name='copilot_evaluations')
    op.drop_table('copilot_evaluations')
