"""add_conversation_embeddings

Phase 2.4: Add conversation_embeddings table for semantic memory with pgvector.
This table stores message embeddings for semantic search over conversation history.
Allows the bot to remember and recall context from ANY point in the conversation history.

Use case: User asks "What did I tell you about my business 2 months ago?"
-> Semantic search finds relevant messages by meaning, not just recency.

Revision ID: 008
Revises: 007
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    """Create conversation_embeddings table with pgvector support"""

    # Create table with vector column for embeddings
    op.create_table(
        'conversation_embeddings',
        # Primary key - Integer for efficiency (many rows expected)
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),

        # Identifiers - same pattern as other tables
        sa.Column('creator_id', sa.String(100), nullable=False),
        sa.Column('follower_id', sa.String(255), nullable=False),

        # Message data
        sa.Column('message_role', sa.String(20), nullable=False),  # 'user' or 'assistant'
        sa.Column('content', sa.Text(), nullable=False),

        # Embedding vector - 1536 dimensions for text-embedding-3-small
        # Note: Vector type added via raw SQL to use pgvector syntax

        # Metadata
        sa.Column('msg_metadata', postgresql.JSON, default={}),  # intent, products, etc.

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Add vector column using pgvector syntax
    op.execute('''
        ALTER TABLE conversation_embeddings
        ADD COLUMN embedding vector(1536) NOT NULL
    ''')

    # Index for filtering by creator+follower (most common query pattern)
    op.create_index(
        'idx_conv_emb_creator_follower',
        'conversation_embeddings',
        ['creator_id', 'follower_id']
    )

    # Individual indexes for flexibility
    op.create_index(
        'idx_conv_emb_creator_id',
        'conversation_embeddings',
        ['creator_id']
    )

    op.create_index(
        'idx_conv_emb_follower_id',
        'conversation_embeddings',
        ['follower_id']
    )

    # IVFFlat index for vector similarity search
    # lists = 100 is reasonable for expected data size (100-10K rows per creator-follower pair)
    # Use cosine distance (vector_cosine_ops) since we normalize for similarity
    op.execute('''
        CREATE INDEX idx_conv_emb_vector
        ON conversation_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    ''')

    # Index on created_at for time-based filtering
    op.create_index(
        'idx_conv_emb_created_at',
        'conversation_embeddings',
        ['created_at']
    )


def downgrade():
    """Drop conversation_embeddings table"""
    op.drop_index('idx_conv_emb_created_at', table_name='conversation_embeddings')
    op.drop_index('idx_conv_emb_vector', table_name='conversation_embeddings')
    op.drop_index('idx_conv_emb_follower_id', table_name='conversation_embeddings')
    op.drop_index('idx_conv_emb_creator_id', table_name='conversation_embeddings')
    op.drop_index('idx_conv_emb_creator_follower', table_name='conversation_embeddings')
    op.drop_table('conversation_embeddings')
