"""add missing indexes for platform_message_id product_creator nurturing_creator kb_creator

Revision ID: de251aff9bac
Revises: 016
Create Date: 2026-02-15 10:10:38.225325

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'de251aff9bac'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_messages_platform_message_id'), 'messages', ['platform_message_id'], unique=False)
    op.create_index(op.f('ix_products_creator_id'), 'products', ['creator_id'], unique=False)
    op.create_index(op.f('ix_nurturing_sequences_creator_id'), 'nurturing_sequences', ['creator_id'], unique=False)
    op.create_index(op.f('ix_knowledge_base_creator_id'), 'knowledge_base', ['creator_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_knowledge_base_creator_id'), table_name='knowledge_base')
    op.drop_index(op.f('ix_nurturing_sequences_creator_id'), table_name='nurturing_sequences')
    op.drop_index(op.f('ix_products_creator_id'), table_name='products')
    op.drop_index(op.f('ix_messages_platform_message_id'), table_name='messages')
