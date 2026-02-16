"""add index on creators.whatsapp_phone_id for multi-tenant webhook routing

Revision ID: 019
Revises: 018
Create Date: 2026-02-16

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '019'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f('ix_creators_whatsapp_phone_id'),
        'creators',
        ['whatsapp_phone_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_creators_whatsapp_phone_id'), table_name='creators')
