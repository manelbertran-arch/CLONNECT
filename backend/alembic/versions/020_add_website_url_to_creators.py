"""add website_url column to creators table

Revision ID: 020
Revises: 019
Create Date: 2026-02-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '020'
down_revision: Union[str, None] = '019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('creators', sa.Column('website_url', sa.String(500), nullable=True))
    # Backfill from knowledge_about JSON
    op.execute(
        """
        UPDATE creators
        SET website_url = knowledge_about->>'website_url'
        WHERE knowledge_about->>'website_url' IS NOT NULL
        AND website_url IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column('creators', 'website_url')
