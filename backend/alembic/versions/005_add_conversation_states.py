"""add_conversation_states

Phase 2.1: Persist ConversationState to PostgreSQL.
This migration creates the conversation_states table to store
the sales funnel state machine state across server restarts.

Revision ID: 005
Revises: 004
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    """Create conversation_states table"""
    op.create_table(
        'conversation_states',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('creator_id', sa.String(100), nullable=False, index=True),
        sa.Column('follower_id', sa.String(255), nullable=False, index=True),
        sa.Column('phase', sa.String(50), default='inicio'),
        sa.Column('message_count', sa.Integer, default=0),
        sa.Column('context', postgresql.JSON, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Composite unique index for creator_id + follower_id (one state per pair)
    op.create_index(
        'idx_conversation_states_creator_follower',
        'conversation_states',
        ['creator_id', 'follower_id'],
        unique=True
    )


def downgrade():
    """Drop conversation_states table"""
    op.drop_index('idx_conversation_states_creator_follower', table_name='conversation_states')
    op.drop_table('conversation_states')
