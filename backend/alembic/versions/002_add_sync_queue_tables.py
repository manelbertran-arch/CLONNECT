"""add_sync_queue_tables

Add tables for intelligent sync queue system:
- sync_queue: Individual conversation sync jobs
- sync_state: Global sync state per creator

Revision ID: 002
Revises: 001
Create Date: 2026-01-15

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    """Create sync queue tables"""

    # Create sync_queue table
    op.create_table(
        'sync_queue',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('creator_id', sa.String(100), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(255), nullable=False),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('attempts', sa.Integer(), server_default='0'),
        sa.Column('last_error', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True)),
    )

    # Create index for queue lookups
    op.create_index('idx_sync_queue_status', 'sync_queue', ['status'])
    op.create_index('idx_sync_queue_creator_status', 'sync_queue', ['creator_id', 'status'])

    # Create sync_state table
    op.create_table(
        'sync_state',
        sa.Column('creator_id', sa.String(100), primary_key=True),
        sa.Column('status', sa.String(20), server_default='idle'),
        sa.Column('last_sync_at', sa.DateTime(timezone=True)),
        sa.Column('rate_limit_until', sa.DateTime(timezone=True)),
        sa.Column('conversations_synced', sa.Integer(), server_default='0'),
        sa.Column('conversations_total', sa.Integer(), server_default='0'),
        sa.Column('messages_saved', sa.Integer(), server_default='0'),
        sa.Column('current_conversation', sa.String(255)),
        sa.Column('error_count', sa.Integer(), server_default='0'),
        sa.Column('last_error', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    """Drop sync queue tables"""
    op.drop_table('sync_state')
    op.drop_table('sync_queue')
