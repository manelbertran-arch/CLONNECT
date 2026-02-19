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
    op.create_table(
        'copilot_evaluations',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('creator_id', sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('creators.id'), nullable=False, index=True),
        sa.Column('eval_type', sa.String(20), nullable=False),  # daily, weekly
        sa.Column('eval_date', sa.Date, nullable=False),
        sa.Column('metrics', sa.JSON, nullable=False),  # approval_rate, edit_rate, etc.
        sa.Column('patterns', sa.JSON),  # detected patterns
        sa.Column('recommendations', sa.JSON),  # suggested threshold changes
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Unique constraint: one evaluation per creator per type per date
    op.create_index(
        'ix_copilot_evaluations_unique',
        'copilot_evaluations',
        ['creator_id', 'eval_type', 'eval_date'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_copilot_evaluations_unique', table_name='copilot_evaluations')
    op.drop_table('copilot_evaluations')
