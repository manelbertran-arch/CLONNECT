"""
Audiencia API Router

SPRINT4-T4.1: Aggregated audience data endpoints for "Tu Audiencia" page
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import get_db
from core.audience_aggregator import AudienceAggregator
from api.schemas.audiencia import (
    TopicsResponse,
    ObjectionsResponse,
    CompetitionResponse,
    TrendsResponse,
    ContentRequestsResponse,
    PerceptionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audiencia", tags=["audiencia"])


@router.get("/{creator_id}/topics", response_model=TopicsResponse)
async def get_topics(creator_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """
    Tab 1: De qué hablan
    Aggregates interests and conversation topics.
    """
    try:
        aggregator = AudienceAggregator(creator_id, db)
        return aggregator.get_topics(limit=limit)
    except Exception as e:
        logger.error(f"Error getting topics for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{creator_id}/passions", response_model=TopicsResponse)
async def get_passions(creator_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """
    Tab 2: Qué les apasiona
    Topics with high engagement (long messages, deep questions).
    """
    try:
        aggregator = AudienceAggregator(creator_id, db)
        return aggregator.get_passions(limit=limit)
    except Exception as e:
        logger.error(f"Error getting passions for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{creator_id}/frustrations", response_model=ObjectionsResponse)
async def get_frustrations(creator_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """
    Tab 3: Qué les frustra
    Aggregated objections and complaints.
    """
    try:
        aggregator = AudienceAggregator(creator_id, db)
        return aggregator.get_frustrations(limit=limit)
    except Exception as e:
        logger.error(f"Error getting frustrations for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{creator_id}/competition", response_model=CompetitionResponse)
async def get_competition(creator_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """
    Tab 4: Qué competencia mencionan
    @mentions of competitors in messages.
    """
    try:
        aggregator = AudienceAggregator(creator_id, db)
        return aggregator.get_competition(limit=limit)
    except Exception as e:
        logger.error(f"Error getting competition for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{creator_id}/trends", response_model=TrendsResponse)
async def get_trends(creator_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """
    Tab 5: Qué tendencias emergen
    Terms with growth this week vs last week.
    """
    try:
        aggregator = AudienceAggregator(creator_id, db)
        return aggregator.get_trends(limit=limit)
    except Exception as e:
        logger.error(f"Error getting trends for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{creator_id}/content-requests", response_model=ContentRequestsResponse)
async def get_content_requests(creator_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """
    Tab 6: Qué contenido piden
    Questions grouped by topic.
    """
    try:
        aggregator = AudienceAggregator(creator_id, db)
        return aggregator.get_content_requests(limit=limit)
    except Exception as e:
        logger.error(f"Error getting content requests for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{creator_id}/purchase-objections", response_model=ObjectionsResponse)
async def get_purchase_objections(creator_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """
    Tab 7: Por qué no compran
    Purchase-related objections with suggestions.
    """
    try:
        aggregator = AudienceAggregator(creator_id, db)
        return aggregator.get_purchase_objections(limit=limit)
    except Exception as e:
        logger.error(f"Error getting purchase objections for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{creator_id}/perception", response_model=PerceptionResponse)
async def get_perception(creator_id: str, db: Session = Depends(get_db)):
    """
    Tab 8: Qué piensan de ti
    Sentiment analysis about the creator.
    """
    try:
        aggregator = AudienceAggregator(creator_id, db)
        return aggregator.get_perception()
    except Exception as e:
        logger.error(f"Error getting perception for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
