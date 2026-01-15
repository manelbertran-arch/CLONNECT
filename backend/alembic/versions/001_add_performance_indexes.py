"""add_performance_indexes

P2 FIX: Add database indexes for query performance optimization.
These indexes improve query performance for common operations like:
- Filtering leads by creator_id
- Searching leads by status and purchase_intent
- Filtering messages by lead_id
- Sorting by timestamps

Revision ID: 001
Revises:
Create Date: 2026-01-12

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Add performance indexes to frequently queried columns"""

    # Leads table indexes
    op.create_index('idx_leads_creator_id', 'leads', ['creator_id'], if_not_exists=True)
    op.create_index('idx_leads_creator_follower', 'leads', ['creator_id', 'platform_user_id'], if_not_exists=True)
    op.create_index('idx_leads_status', 'leads', ['status'], if_not_exists=True)
    op.create_index('idx_leads_purchase_intent', 'leads', ['purchase_intent'], if_not_exists=True)
    op.create_index('idx_leads_last_contact', 'leads', ['last_contact_at'], if_not_exists=True)
    op.create_index('idx_leads_created_at', 'leads', ['created_at'], if_not_exists=True)

    # Messages table indexes
    op.create_index('idx_messages_lead_id', 'messages', ['lead_id'], if_not_exists=True)
    op.create_index('idx_messages_created_at', 'messages', ['created_at'], if_not_exists=True)
    op.create_index('idx_messages_role', 'messages', ['role'], if_not_exists=True)

    # Creators table indexes
    op.create_index('idx_creators_name', 'creators', ['name'], if_not_exists=True)
    op.create_index('idx_creators_api_key', 'creators', ['api_key'], if_not_exists=True)

    # Products table indexes
    op.create_index('idx_products_creator_id', 'products', ['creator_id'], if_not_exists=True)
    op.create_index('idx_products_is_active', 'products', ['is_active'], if_not_exists=True)

    # Users table indexes
    op.create_index('idx_users_email', 'users', ['email'], if_not_exists=True)

    # Embeddings table indexes (for RAG)
    op.create_index('idx_embeddings_doc_id', 'embeddings', ['doc_id'], if_not_exists=True)


def downgrade():
    """Remove performance indexes"""

    # Leads table indexes
    op.drop_index('idx_leads_creator_id', table_name='leads')
    op.drop_index('idx_leads_creator_follower', table_name='leads')
    op.drop_index('idx_leads_status', table_name='leads')
    op.drop_index('idx_leads_purchase_intent', table_name='leads')
    op.drop_index('idx_leads_last_contact', table_name='leads')
    op.drop_index('idx_leads_created_at', table_name='leads')

    # Messages table indexes
    op.drop_index('idx_messages_lead_id', table_name='messages')
    op.drop_index('idx_messages_created_at', table_name='messages')
    op.drop_index('idx_messages_role', table_name='messages')

    # Creators table indexes
    op.drop_index('idx_creators_name', table_name='creators')
    op.drop_index('idx_creators_api_key', table_name='creators')

    # Products table indexes
    op.drop_index('idx_products_creator_id', table_name='products')
    op.drop_index('idx_products_is_active', table_name='products')

    # Users table indexes
    op.drop_index('idx_users_email', table_name='users')

    # Embeddings table indexes
    op.drop_index('idx_embeddings_doc_id', table_name='embeddings')
