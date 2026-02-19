"""add copilot tracking columns to messages table

New columns for copilot autolearning data capture:
- copilot_action: approved/edited/discarded/manual_override
- edit_diff: JSON diff when creator edits a suggestion
- confidence_score: bot confidence for this suggestion
- response_time_ms: ms between suggestion created and creator action

Revision ID: 022
Revises: 021
Create Date: 2026-02-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '022'
down_revision: Union[str, None] = '021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('copilot_action', sa.String(30), nullable=True),
    )
    op.add_column(
        'messages',
        sa.Column('edit_diff', sa.JSON, nullable=True),
    )
    op.add_column(
        'messages',
        sa.Column('confidence_score', sa.Float, nullable=True),
    )
    op.add_column(
        'messages',
        sa.Column('response_time_ms', sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_column('messages', 'response_time_ms')
    op.drop_column('messages', 'confidence_score')
    op.drop_column('messages', 'edit_diff')
    op.drop_column('messages', 'copilot_action')
