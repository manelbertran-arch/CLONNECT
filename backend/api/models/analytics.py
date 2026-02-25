"""Analytics models: CreatorMetricsDaily, Prediction, Recommendation, DetectedTopic, WeeklyReport, CSATRating."""
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

try:
    from api.database import Base
except ImportError:
    from database import Base


class CreatorMetricsDaily(Base):
    """
    Daily aggregated metrics per creator.
    Populated by background jobs analyzing conversations, leads, and sales.
    """

    __tablename__ = "creator_metrics_daily"
    __table_args__ = (
        UniqueConstraint("creator_id", "date", name="uq_metrics_daily_creator_date"),
        Index("idx_metrics_daily_creator_date", "creator_id", "date"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    date = Column(Date, nullable=False)

    # Conversations
    total_conversations = Column(Integer, default=0)
    total_messages = Column(Integer, default=0)
    unique_users = Column(Integer, default=0)
    returning_users = Column(Integer, default=0)
    avg_response_time_seconds = Column(Float)
    avg_messages_per_conversation = Column(Float)
    avg_conversation_duration_minutes = Column(Float)

    # Intents and sentiment
    intent_distribution = Column(JSON, default=dict)
    sentiment_score = Column(Float)  # -1 to 1
    frustration_rate = Column(Float)
    purchase_intent_avg = Column(Float)

    # Funnel
    new_leads = Column(Integer, default=0)
    leads_engaged = Column(Integer, default=0)
    leads_qualified = Column(Integer, default=0)
    leads_hot = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    revenue = Column(Float, default=0)

    # Nurturing
    nurturing_sent = Column(Integer, default=0)
    nurturing_opened = Column(Integer, default=0)
    nurturing_responded = Column(Integer, default=0)
    nurturing_converted = Column(Integer, default=0)

    # Bookings
    calls_scheduled = Column(Integer, default=0)
    calls_completed = Column(Integer, default=0)
    calls_no_show = Column(Integer, default=0)
    calls_converted = Column(Integer, default=0)

    # Content
    posts_published = Column(Integer, default=0)
    total_engagement = Column(Integer, default=0)
    avg_engagement_rate = Column(Float)
    dms_from_content = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Prediction(Base):
    """
    ML predictions for leads and revenue.
    Types: conversion, churn, revenue, engagement, best_time
    """

    __tablename__ = "predictions"
    __table_args__ = (
        Index("idx_predictions_creator_type", "creator_id", "prediction_type", "target_date"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    prediction_type = Column(
        String(50), nullable=False
    )  # conversion, churn, revenue, engagement, best_time

    target_date = Column(Date)
    target_id = Column(String(100))  # lead_id, content_id, etc.

    predicted_value = Column(Float, nullable=False)
    confidence = Column(Float)
    factors = Column(JSON, default=list)  # Contributing factors

    actual_value = Column(Float)  # For validation
    was_correct = Column(Boolean)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    validated_at = Column(DateTime(timezone=True))


class Recommendation(Base):
    """
    Generated recommendations for creators.
    Categories: content, action, product, pricing, timing
    """

    __tablename__ = "recommendations"
    __table_args__ = (
        Index("idx_recommendations_creator_status", "creator_id", "status", "priority"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    category = Column(String(50), nullable=False)  # content, action, product, pricing, timing

    priority = Column(String(20), default="medium")  # low, medium, high
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    reasoning = Column(Text)

    data_points = Column(JSON, default=dict)
    expected_impact = Column(JSON, default=dict)

    action_type = Column(String(50))
    action_data = Column(JSON, default=dict)

    status = Column(String(20), default="pending")  # pending, viewed, acted, dismissed
    acted_at = Column(DateTime(timezone=True))
    result = Column(JSON)

    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DetectedTopic(Base):
    """
    Detected topics from conversation analysis.
    Types: question, objection, interest, complaint, suggestion
    """

    __tablename__ = "detected_topics"
    __table_args__ = (
        Index("idx_detected_topics_creator", "creator_id", "period_start"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    topic_label = Column(String(200), nullable=False)
    topic_type = Column(
        String(50), default="general"
    )  # question, objection, interest, complaint, suggestion

    message_count = Column(Integer, default=0)
    unique_users = Column(Integer, default=0)
    growth_rate = Column(Float)

    keywords = Column(JSON, default=list)
    example_messages = Column(JSON, default=list)
    related_products = Column(JSON, default=list)

    avg_sentiment = Column(Float)
    conversion_rate = Column(Float)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WeeklyReport(Base):
    """
    Weekly intelligence reports with LLM-generated insights.
    Contains metrics, comparisons, predictions, and recommendations.
    """

    __tablename__ = "weekly_reports"
    __table_args__ = (
        UniqueConstraint("creator_id", "week_start", name="uq_weekly_reports_creator_week"),
        Index("idx_weekly_reports_creator", "creator_id", "week_start"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    week_start = Column(Date, nullable=False)
    week_end = Column(Date, nullable=False)

    # Metrics summary
    metrics_summary = Column(JSON, default=dict)
    funnel_summary = Column(JSON, default=dict)

    # Comparisons
    vs_previous_week = Column(JSON, default=dict)
    vs_previous_month = Column(JSON, default=dict)
    vs_average = Column(JSON, default=dict)

    # Top performers
    top_content = Column(JSON, default=list)
    top_products = Column(JSON, default=list)
    hot_leads = Column(JSON, default=list)

    # Analysis
    topics_trending = Column(JSON, default=list)
    topics_declining = Column(JSON, default=list)
    objections_analysis = Column(JSON, default=dict)
    sentiment_analysis = Column(JSON, default=dict)

    # Predictions
    next_week_forecast = Column(JSON, default=dict)
    conversion_predictions = Column(JSON, default=list)
    churn_risks = Column(JSON, default=list)

    # Recommendations
    content_recommendations = Column(JSON, default=list)
    action_recommendations = Column(JSON, default=list)
    product_recommendations = Column(JSON, default=list)

    # LLM Summary
    executive_summary = Column(Text)
    key_wins = Column(JSON, default=list)
    areas_to_improve = Column(JSON, default=list)
    this_week_focus = Column(JSON, default=list)

    # Alerts
    alerts = Column(JSON, default=list)

    # Meta
    llm_model_used = Column(String(50))
    processing_time_seconds = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True))
    opened_at = Column(DateTime(timezone=True))


class CSATRating(Base):
    """Customer satisfaction ratings for metrics system"""

    __tablename__ = "csat_ratings"
    __table_args__ = (
        UniqueConstraint("lead_id", name="uq_csat_lead_id"),
        {"extend_existing": True},
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)
    feedback = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
