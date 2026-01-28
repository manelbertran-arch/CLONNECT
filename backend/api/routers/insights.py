"""
Insights API Router

SPRINT3-T3.1: Endpoints for daily mission and weekly insights
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from core.insights_engine import InsightsEngine
from api.schemas.insights import TodayMission, WeeklyInsights, WeeklyMetrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/{creator_id}/today", response_model=TodayMission)
async def get_today_mission(creator_id: str, db: Session = Depends(get_db)):
    """
    Get today's mission for a creator.

    Returns:
    - hot_leads: Top 5 leads ready to close
    - potential_revenue: Sum of deal values
    - pending_responses: Conversations awaiting reply
    - today_bookings: Today's scheduled meetings
    """
    try:
        engine = InsightsEngine(creator_id, db)
        return engine.get_today_mission()
    except Exception as e:
        logger.error(f"Error getting today mission for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{creator_id}/weekly", response_model=WeeklyInsights)
async def get_weekly_insights(creator_id: str, db: Session = Depends(get_db)):
    """
    Get weekly insights for a creator.

    Returns 4 insight cards:
    - content: Most asked topic
    - trend: Emerging term with growth %
    - product: Most requested product
    - competition: Competitor mentions
    """
    try:
        engine = InsightsEngine(creator_id, db)
        return engine.get_weekly_insights()
    except Exception as e:
        logger.error(f"Error getting weekly insights for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{creator_id}/metrics", response_model=WeeklyMetrics)
async def get_weekly_metrics(creator_id: str, db: Session = Depends(get_db)):
    """
    Get weekly metrics with deltas vs previous week.

    Returns:
    - revenue: Total revenue this week
    - revenue_delta: % change vs last week
    - sales_count: Number of sales
    - response_rate: Bot response rate
    - hot_leads_count: Number of hot leads
    """
    try:
        engine = InsightsEngine(creator_id, db)
        return engine.get_weekly_metrics()
    except Exception as e:
        logger.error(f"Error getting weekly metrics for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
