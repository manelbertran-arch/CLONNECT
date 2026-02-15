"""
Intelligence API endpoints - Business Intelligence and Predictive Analytics.

Provides:
- Dashboard: Combined KPIs, predictions, and recommendations
- Predictions: Conversion, churn, revenue forecasts
- Recommendations: Content, actions, products
- Weekly Reports: LLM-generated comprehensive insights
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime, timezone
import logging

from api.database import get_db
from core.intelligence import IntelligenceEngine, ENABLE_INTELLIGENCE

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/{creator_id}/dashboard")
async def get_intelligent_dashboard(
    creator_id: str,
    days: int = Query(30, ge=7, le=90, description="Days of history to analyze"),
    db: Session = Depends(get_db)
):
    """
    Get intelligent dashboard with KPIs, predictions, and recommendations.

    Returns a comprehensive view combining:
    - Pattern analysis (temporal, conversation, conversion)
    - Predictions (hot leads, churn risks)
    - Top recommendations by priority
    - Revenue forecast
    """
    if not ENABLE_INTELLIGENCE:
        return {
            "status": "disabled",
            "message": "Intelligence features are disabled"
        }

    engine = IntelligenceEngine(creator_id)

    # Gather data in parallel-like fashion
    patterns = await engine.analyze_patterns(db, days)
    conversion_predictions = await engine.predict_conversions(db)
    churn_risks = await engine.predict_churn_risk(db)
    revenue_forecast = await engine.forecast_revenue(db, 4)

    content_recs = await engine.generate_content_recommendations(db)
    action_recs = await engine.generate_action_recommendations(db)

    # Combine all recommendations and sort by priority
    all_recommendations = content_recs + action_recs
    priority_order = {"high": 0, "medium": 1, "low": 2}
    all_recommendations.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 3))

    return {
        "status": "ok",
        "creator_id": creator_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_period_days": days,
        "patterns": patterns,
        "predictions": {
            "hot_leads": conversion_predictions[:5],
            "total_hot_leads": len(conversion_predictions),
            "churn_risks": churn_risks[:5],
            "total_at_risk": len(churn_risks),
            "revenue_forecast": revenue_forecast
        },
        "recommendations": all_recommendations[:6],
        "kpis": {
            "peak_activity_hour": patterns.get("temporal", {}).get("peak_activity_hour"),
            "peak_activity_day": patterns.get("temporal", {}).get("peak_activity_day"),
            "avg_messages_per_user": patterns.get("conversation", {}).get("avg_messages_per_user"),
            "intent_distribution": patterns.get("conversation", {}).get("intent_distribution", {})
        }
    }


@router.get("/{creator_id}/predictions")
async def get_predictions(
    creator_id: str,
    prediction_type: Optional[str] = Query(None, description="Filter by: conversion, churn, revenue"),
    db: Session = Depends(get_db)
):
    """
    Get all predictions for a creator.

    Types:
    - conversion: Leads likely to convert
    - churn: Leads at risk of being lost
    - revenue: Revenue forecast for upcoming weeks
    """
    if not ENABLE_INTELLIGENCE:
        return {"status": "disabled", "message": "Intelligence features are disabled"}

    engine = IntelligenceEngine(creator_id)

    response = {
        "status": "ok",
        "creator_id": creator_id,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

    if prediction_type is None or prediction_type == "conversion":
        response["conversion_predictions"] = await engine.predict_conversions(db)

    if prediction_type is None or prediction_type == "churn":
        response["churn_predictions"] = await engine.predict_churn_risk(db)

    if prediction_type is None or prediction_type == "revenue":
        response["revenue_forecast"] = await engine.forecast_revenue(db, 4)

    return response


@router.get("/{creator_id}/recommendations")
async def get_recommendations(
    creator_id: str,
    category: Optional[str] = Query(None, description="Filter by: content, action, product, timing"),
    db: Session = Depends(get_db)
):
    """
    Get recommendations for a creator.

    Categories:
    - content: Content creation ideas
    - action: Immediate actions to take
    - product: Product development opportunities
    - timing: Optimal posting times
    """
    if not ENABLE_INTELLIGENCE:
        return {"status": "disabled", "message": "Intelligence features are disabled"}

    engine = IntelligenceEngine(creator_id)

    content_recs = await engine.generate_content_recommendations(db)
    action_recs = await engine.generate_action_recommendations(db)
    product_recs = await engine.generate_product_recommendations(db)

    all_recs = content_recs + action_recs + product_recs

    if category:
        all_recs = [r for r in all_recs if r.get("category") == category]

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    all_recs.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 3))

    return {
        "status": "ok",
        "creator_id": creator_id,
        "category_filter": category,
        "count": len(all_recs),
        "recommendations": all_recs
    }


@router.get("/{creator_id}/report/weekly")
async def get_weekly_report(
    creator_id: str,
    week_end: Optional[date] = Query(None, description="End date of week (defaults to last Sunday)"),
    db: Session = Depends(get_db)
):
    """
    Get the weekly intelligence report.

    Returns a comprehensive report including:
    - Metrics summary for the week
    - Comparison vs previous week
    - Pattern analysis
    - Predictions (hot leads, churn, revenue)
    - All recommendations
    - LLM-generated executive summary
    """
    if not ENABLE_INTELLIGENCE:
        return {"status": "disabled", "message": "Intelligence features are disabled"}

    engine = IntelligenceEngine(creator_id)

    report = await engine.generate_weekly_report(db, week_end)

    return {
        "status": "ok",
        "creator_id": creator_id,
        "report": report
    }


@router.post("/{creator_id}/report/generate")
async def generate_weekly_report(
    creator_id: str,
    week_end: Optional[date] = Query(None, description="End date of week"),
    db: Session = Depends(get_db)
):
    """
    Generate a new weekly report on demand.

    This creates and stores a new report in the database.
    """
    if not ENABLE_INTELLIGENCE:
        return {"status": "disabled", "message": "Intelligence features are disabled"}

    engine = IntelligenceEngine(creator_id)

    # Generate the report
    report = await engine.generate_weekly_report(db, week_end)

    # Store in database
    try:
        from sqlalchemy import text

        period = report.get("period", {})
        week_start = period.get("start")
        week_end_str = period.get("end")

        insert_query = text("""
            INSERT INTO weekly_reports (
                creator_id, week_start, week_end,
                metrics_summary, vs_previous_week,
                conversion_predictions, churn_risks,
                content_recommendations, action_recommendations,
                executive_summary, key_wins, areas_to_improve, this_week_focus
            ) VALUES (
                :creator_id, :week_start, :week_end,
                :metrics_summary, :vs_previous_week,
                :conversion_predictions, :churn_risks,
                :content_recommendations, :action_recommendations,
                :executive_summary, :key_wins, :areas_to_improve, :this_week_focus
            )
            ON CONFLICT (creator_id, week_start) DO UPDATE SET
                metrics_summary = EXCLUDED.metrics_summary,
                vs_previous_week = EXCLUDED.vs_previous_week,
                conversion_predictions = EXCLUDED.conversion_predictions,
                churn_risks = EXCLUDED.churn_risks,
                content_recommendations = EXCLUDED.content_recommendations,
                action_recommendations = EXCLUDED.action_recommendations,
                executive_summary = EXCLUDED.executive_summary,
                key_wins = EXCLUDED.key_wins,
                areas_to_improve = EXCLUDED.areas_to_improve,
                this_week_focus = EXCLUDED.this_week_focus
            RETURNING id
        """)

        import json
        result = db.execute(insert_query, {
            "creator_id": creator_id,
            "week_start": week_start,
            "week_end": week_end_str,
            "metrics_summary": json.dumps(report.get("metrics_summary", {})),
            "vs_previous_week": json.dumps(report.get("vs_previous_week", {})),
            "conversion_predictions": json.dumps(report.get("predictions", {}).get("hot_leads", [])),
            "churn_risks": json.dumps(report.get("predictions", {}).get("churn_risks", [])),
            "content_recommendations": json.dumps(report.get("recommendations", {}).get("content", [])),
            "action_recommendations": json.dumps(report.get("recommendations", {}).get("actions", [])),
            "executive_summary": report.get("executive_summary", ""),
            "key_wins": json.dumps(report.get("key_wins", [])),
            "areas_to_improve": json.dumps(report.get("areas_to_improve", [])),
            "this_week_focus": json.dumps(report.get("this_week_focus", []))
        })
        db.commit()

        report_id = result.fetchone()[0]
        logger.info(f"Weekly report stored with ID {report_id} for {creator_id}")

        return {
            "status": "ok",
            "message": "Report generated and stored",
            "report_id": report_id,
            "creator_id": creator_id,
            "report": report
        }

    except Exception as e:
        logger.error(f"Error storing weekly report: {e}")
        db.rollback()
        return {
            "status": "ok",
            "message": "Report generated but not stored",
            "error": str(e),
            "creator_id": creator_id,
            "report": report
        }


@router.get("/{creator_id}/patterns")
async def get_patterns(
    creator_id: str,
    days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db)
):
    """
    Get detailed pattern analysis.

    Returns:
    - Temporal patterns: Best hours and days for activity
    - Conversation patterns: Intent distribution, message stats
    - Conversion patterns: Top products mentioned
    """
    if not ENABLE_INTELLIGENCE:
        return {"status": "disabled", "message": "Intelligence features are disabled"}

    engine = IntelligenceEngine(creator_id)

    patterns = await engine.analyze_patterns(db, days)

    return {
        "status": "ok",
        "creator_id": creator_id,
        "analysis_period_days": days,
        "patterns": patterns
    }
