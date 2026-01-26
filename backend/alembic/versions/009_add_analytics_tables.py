"""add_analytics_tables

Create analytics tables for daily metrics and funnel tracking.
Migrates from JSON file storage to PostgreSQL for better performance.

Revision ID: 009
Revises: 008
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    """Create analytics tables."""

    # =============================================
    # CREATOR METRICS DAILY - Core metrics per day
    # =============================================
    op.create_table(
        'creator_metrics_daily',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('creator_id', sa.String(100), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),

        # === CONVERSATIONS ===
        sa.Column('total_conversations', sa.Integer(), default=0),
        sa.Column('total_messages', sa.Integer(), default=0),
        sa.Column('unique_users', sa.Integer(), default=0),
        sa.Column('returning_users', sa.Integer(), default=0),
        sa.Column('avg_response_time_seconds', sa.Float(), nullable=True),
        sa.Column('avg_messages_per_conversation', sa.Float(), nullable=True),
        sa.Column('avg_conversation_duration_minutes', sa.Float(), nullable=True),

        # === INTENTS AND SENTIMENT ===
        sa.Column('intent_distribution', JSONB, default={}),
        sa.Column('sentiment_score', sa.Float(), nullable=True),  # -1 to 1
        sa.Column('frustration_rate', sa.Float(), nullable=True),
        sa.Column('purchase_intent_avg', sa.Float(), nullable=True),

        # === FUNNEL ===
        sa.Column('new_leads', sa.Integer(), default=0),
        sa.Column('leads_engaged', sa.Integer(), default=0),
        sa.Column('leads_qualified', sa.Integer(), default=0),
        sa.Column('leads_hot', sa.Integer(), default=0),
        sa.Column('conversions', sa.Integer(), default=0),
        sa.Column('revenue', sa.Numeric(10, 2), default=0),

        # === NURTURING ===
        sa.Column('nurturing_sent', sa.Integer(), default=0),
        sa.Column('nurturing_opened', sa.Integer(), default=0),
        sa.Column('nurturing_responded', sa.Integer(), default=0),
        sa.Column('nurturing_converted', sa.Integer(), default=0),

        # === BOOKINGS ===
        sa.Column('calls_scheduled', sa.Integer(), default=0),
        sa.Column('calls_completed', sa.Integer(), default=0),
        sa.Column('calls_no_show', sa.Integer(), default=0),
        sa.Column('calls_converted', sa.Integer(), default=0),

        # === CONTENT ===
        sa.Column('posts_published', sa.Integer(), default=0),
        sa.Column('total_engagement', sa.Integer(), default=0),
        sa.Column('avg_engagement_rate', sa.Float(), nullable=True),
        sa.Column('dms_from_content', sa.Integer(), default=0),

        # === METADATA ===
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    op.create_index(
        'idx_metrics_daily_creator_date',
        'creator_metrics_daily',
        ['creator_id', 'date'],
        unique=True
    )

    # =============================================
    # PRODUCT ANALYTICS - Per product metrics
    # =============================================
    op.create_table(
        'product_analytics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('product_id', sa.String(100), nullable=False),
        sa.Column('creator_id', sa.String(100), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),

        sa.Column('mentions', sa.Integer(), default=0),
        sa.Column('questions', sa.Integer(), default=0),
        sa.Column('objections', sa.Integer(), default=0),
        sa.Column('link_clicks', sa.Integer(), default=0),
        sa.Column('conversions', sa.Integer(), default=0),
        sa.Column('revenue', sa.Numeric(10, 2), default=0),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index(
        'idx_product_analytics_creator_date',
        'product_analytics',
        ['creator_id', 'product_id', 'date']
    )


def downgrade():
    """Drop analytics tables."""
    op.drop_index('idx_product_analytics_creator_date', table_name='product_analytics')
    op.drop_table('product_analytics')
    op.drop_index('idx_metrics_daily_creator_date', table_name='creator_metrics_daily')
    op.drop_table('creator_metrics_daily')
