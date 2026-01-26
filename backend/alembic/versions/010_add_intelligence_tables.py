"""add_intelligence_tables

Create tables for the Business Intelligence system:
- Predictions (conversion, churn, revenue forecasts)
- Recommendations (content, actions, products)
- Detected topics (conversation clustering)
- Content performance (Instagram analytics)
- Lead intelligence (detailed scoring)
- Weekly reports (LLM-generated insights)

Revision ID: 010
Revises: 009
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    """Create intelligence tables."""

    # =============================================
    # PREDICTIONS - ML predictions for leads/revenue
    # =============================================
    op.create_table(
        'predictions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('creator_id', sa.String(100), nullable=False),
        sa.Column('prediction_type', sa.String(50), nullable=False),
        # Types: 'conversion', 'churn', 'revenue', 'engagement', 'best_time'

        sa.Column('target_date', sa.Date(), nullable=True),
        sa.Column('target_id', sa.String(100), nullable=True),  # lead_id, content_id, etc.

        sa.Column('predicted_value', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('factors', JSONB, default=[]),

        sa.Column('actual_value', sa.Float(), nullable=True),
        sa.Column('was_correct', sa.Boolean(), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        'idx_predictions_creator_type',
        'predictions',
        ['creator_id', 'prediction_type', 'target_date']
    )

    # =============================================
    # RECOMMENDATIONS - Generated suggestions
    # =============================================
    op.create_table(
        'recommendations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('creator_id', sa.String(100), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        # Categories: 'content', 'action', 'product', 'pricing', 'timing'

        sa.Column('priority', sa.String(20), default='medium'),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('reasoning', sa.Text(), nullable=True),

        sa.Column('data_points', JSONB, default={}),
        sa.Column('expected_impact', JSONB, default={}),

        sa.Column('action_type', sa.String(50), nullable=True),
        sa.Column('action_data', JSONB, default={}),

        sa.Column('status', sa.String(20), default='pending'),
        # Status: pending, viewed, acted, dismissed
        sa.Column('acted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result', JSONB, nullable=True),

        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index(
        'idx_recommendations_creator_status',
        'recommendations',
        ['creator_id', 'status', 'priority']
    )

    # =============================================
    # DETECTED TOPICS - Conversation clustering
    # =============================================
    op.create_table(
        'detected_topics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('creator_id', sa.String(100), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),

        sa.Column('topic_label', sa.String(200), nullable=False),
        sa.Column('topic_type', sa.String(50), default='general'),
        # Types: 'question', 'objection', 'interest', 'complaint', 'suggestion'

        sa.Column('message_count', sa.Integer(), default=0),
        sa.Column('unique_users', sa.Integer(), default=0),
        sa.Column('growth_rate', sa.Float(), nullable=True),

        sa.Column('keywords', JSONB, default=[]),
        sa.Column('example_messages', JSONB, default=[]),
        sa.Column('related_products', JSONB, default=[]),

        sa.Column('avg_sentiment', sa.Float(), nullable=True),
        sa.Column('conversion_rate', sa.Float(), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index(
        'idx_detected_topics_creator',
        'detected_topics',
        ['creator_id', 'period_start']
    )

    # =============================================
    # CONTENT PERFORMANCE - Instagram/social metrics
    # =============================================
    op.create_table(
        'content_performance',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('creator_id', sa.String(100), nullable=False),
        sa.Column('content_id', sa.String(100), nullable=False),
        sa.Column('platform', sa.String(20), default='instagram'),

        # === METADATA ===
        sa.Column('content_type', sa.String(50), nullable=True),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('hashtags', JSONB, default=[]),
        sa.Column('mentions', JSONB, default=[]),
        sa.Column('topics_detected', JSONB, default=[]),

        # === ENGAGEMENT METRICS ===
        sa.Column('likes', sa.Integer(), default=0),
        sa.Column('comments', sa.Integer(), default=0),
        sa.Column('shares', sa.Integer(), default=0),
        sa.Column('saves', sa.Integer(), default=0),
        sa.Column('reach', sa.Integer(), default=0),
        sa.Column('impressions', sa.Integer(), default=0),
        sa.Column('video_views', sa.Integer(), default=0),
        sa.Column('avg_watch_time_seconds', sa.Float(), nullable=True),

        # === CALCULATED METRICS ===
        sa.Column('engagement_rate', sa.Float(), nullable=True),
        sa.Column('virality_score', sa.Float(), nullable=True),
        sa.Column('save_rate', sa.Float(), nullable=True),

        # === COMMENT ANALYSIS ===
        sa.Column('comment_sentiment_avg', sa.Float(), nullable=True),
        sa.Column('comment_topics', JSONB, default=[]),
        sa.Column('questions_in_comments', sa.Integer(), default=0),

        # === BUSINESS CORRELATION ===
        sa.Column('dms_generated_24h', sa.Integer(), default=0),
        sa.Column('dms_generated_48h', sa.Integer(), default=0),
        sa.Column('dms_generated_7d', sa.Integer(), default=0),
        sa.Column('leads_generated', sa.Integer(), default=0),
        sa.Column('conversions_attributed', sa.Integer(), default=0),
        sa.Column('revenue_attributed', sa.Numeric(10, 2), default=0),

        # === PREDICTIONS ===
        sa.Column('predicted_engagement', sa.Float(), nullable=True),
        sa.Column('performance_vs_predicted', sa.Float(), nullable=True),

        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index(
        'idx_content_perf_creator',
        'content_performance',
        ['creator_id', 'platform', 'posted_at']
    )

    op.create_index(
        'idx_content_perf_content_id',
        'content_performance',
        ['creator_id', 'content_id'],
        unique=True
    )

    # =============================================
    # LEAD INTELLIGENCE - Detailed lead scoring
    # =============================================
    op.create_table(
        'lead_intelligence',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('creator_id', sa.String(100), nullable=False),
        sa.Column('lead_id', sa.String(100), nullable=False),

        # === SCORES ===
        sa.Column('engagement_score', sa.Float(), default=0),
        sa.Column('intent_score', sa.Float(), default=0),
        sa.Column('fit_score', sa.Float(), default=0),
        sa.Column('urgency_score', sa.Float(), default=0),
        sa.Column('overall_score', sa.Float(), default=0),

        # === PREDICTIONS ===
        sa.Column('conversion_probability', sa.Float(), nullable=True),
        sa.Column('predicted_value', sa.Numeric(10, 2), nullable=True),
        sa.Column('churn_risk', sa.Float(), nullable=True),
        sa.Column('best_contact_time', sa.Time(), nullable=True),
        sa.Column('best_contact_day', sa.String(10), nullable=True),

        # === INSIGHTS ===
        sa.Column('interests', JSONB, default=[]),
        sa.Column('objections', JSONB, default=[]),
        sa.Column('products_interested', JSONB, default=[]),
        sa.Column('content_engaged', JSONB, default=[]),

        # === RECOMMENDATIONS ===
        sa.Column('recommended_action', sa.String(100), nullable=True),
        sa.Column('recommended_product', sa.String(100), nullable=True),
        sa.Column('talking_points', JSONB, default=[]),

        sa.Column('last_calculated', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index(
        'idx_lead_intel_creator',
        'lead_intelligence',
        ['creator_id', 'overall_score']
    )

    op.create_index(
        'idx_lead_intel_lead',
        'lead_intelligence',
        ['creator_id', 'lead_id'],
        unique=True
    )

    # =============================================
    # WEEKLY REPORTS - LLM-generated insights
    # =============================================
    op.create_table(
        'weekly_reports',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('creator_id', sa.String(100), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('week_end', sa.Date(), nullable=False),

        # === METRICS SUMMARY ===
        sa.Column('metrics_summary', JSONB, default={}),
        sa.Column('funnel_summary', JSONB, default={}),

        # === COMPARISONS ===
        sa.Column('vs_previous_week', JSONB, default={}),
        sa.Column('vs_previous_month', JSONB, default={}),
        sa.Column('vs_average', JSONB, default={}),

        # === TOP PERFORMERS ===
        sa.Column('top_content', JSONB, default=[]),
        sa.Column('top_products', JSONB, default=[]),
        sa.Column('hot_leads', JSONB, default=[]),

        # === ANALYSIS ===
        sa.Column('topics_trending', JSONB, default=[]),
        sa.Column('topics_declining', JSONB, default=[]),
        sa.Column('objections_analysis', JSONB, default={}),
        sa.Column('sentiment_analysis', JSONB, default={}),

        # === PREDICTIONS ===
        sa.Column('next_week_forecast', JSONB, default={}),
        sa.Column('conversion_predictions', JSONB, default=[]),
        sa.Column('churn_risks', JSONB, default=[]),

        # === RECOMMENDATIONS ===
        sa.Column('content_recommendations', JSONB, default=[]),
        sa.Column('action_recommendations', JSONB, default=[]),
        sa.Column('product_recommendations', JSONB, default=[]),

        # === LLM SUMMARY ===
        sa.Column('executive_summary', sa.Text(), nullable=True),
        sa.Column('key_wins', JSONB, default=[]),
        sa.Column('areas_to_improve', JSONB, default=[]),
        sa.Column('this_week_focus', JSONB, default=[]),

        # === ALERTS ===
        sa.Column('alerts', JSONB, default=[]),

        # === META ===
        sa.Column('llm_model_used', sa.String(50), nullable=True),
        sa.Column('processing_time_seconds', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        'idx_weekly_reports_creator',
        'weekly_reports',
        ['creator_id', 'week_start'],
        unique=True
    )


def downgrade():
    """Drop intelligence tables."""
    op.drop_index('idx_weekly_reports_creator', table_name='weekly_reports')
    op.drop_table('weekly_reports')

    op.drop_index('idx_lead_intel_lead', table_name='lead_intelligence')
    op.drop_index('idx_lead_intel_creator', table_name='lead_intelligence')
    op.drop_table('lead_intelligence')

    op.drop_index('idx_content_perf_content_id', table_name='content_performance')
    op.drop_index('idx_content_perf_creator', table_name='content_performance')
    op.drop_table('content_performance')

    op.drop_index('idx_detected_topics_creator', table_name='detected_topics')
    op.drop_table('detected_topics')

    op.drop_index('idx_recommendations_creator_status', table_name='recommendations')
    op.drop_table('recommendations')

    op.drop_index('idx_predictions_creator_type', table_name='predictions')
    op.drop_table('predictions')
