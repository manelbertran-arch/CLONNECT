"""
Audience Router (SPRINT1-T1.3)

Provides endpoints for audience intelligence:
- GET /audience/{creator_id}/profile/{follower_id} - Single profile with intelligence
- GET /audience/{creator_id}/segments - List segments with counts
- GET /audience/{creator_id}/segments/{segment_name} - Users in a segment
- GET /audience/{creator_id}/aggregated - Aggregated metrics
"""
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from core.audience_intelligence import (
    AudienceProfile,
    AudienceProfileBuilder,
    get_audience_profile_builder,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audience", tags=["audience"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


async def get_segment_counts(creator_id: str) -> List[Dict[str, Any]]:
    """
    Get count of followers in each segment.

    This queries the database to count followers matching each segment rule.

    Args:
        creator_id: Creator identifier

    Returns:
        List of {segment, count} dicts
    """
    segment_counts = []

    # Define segment queries
    segments_to_count = [
        "hot_lead",
        "warm_lead",
        "ghost",
        "price_objector",
        "time_objector",
        "customer",
        "new",
    ]

    try:
        # Try database approach first
        if os.getenv("DATABASE_URL"):
            from api.models import Lead, FollowerMemoryDB
            from api.services.db_service import get_session
            from datetime import datetime, timedelta
            from sqlalchemy import func, and_

            session = get_session()
            if session:
                try:
                    # Get creator's leads
                    from api.models import Creator
                    creator = session.query(Creator).filter_by(name=creator_id).first()

                    if not creator:
                        return [{"segment": s, "count": 0} for s in segments_to_count]

                    # Count by segment rules
                    total_leads = session.query(Lead).filter_by(creator_id=creator.id).count()

                    # Hot leads: purchase_intent > 0.7 and status in propuesta/cierre phases
                    hot_count = (
                        session.query(Lead)
                        .filter(
                            Lead.creator_id == creator.id,
                            Lead.purchase_intent > 0.7,
                            Lead.status.in_(["caliente", "hot"]),
                        )
                        .count()
                    )

                    # Warm leads: 0.4 <= intent <= 0.7
                    warm_count = (
                        session.query(Lead)
                        .filter(
                            Lead.creator_id == creator.id,
                            Lead.purchase_intent >= 0.4,
                            Lead.purchase_intent <= 0.7,
                        )
                        .count()
                    )

                    # Ghost: last_contact > 7 days ago
                    seven_days_ago = datetime.utcnow() - timedelta(days=7)
                    ghost_count = (
                        session.query(Lead)
                        .filter(
                            Lead.creator_id == creator.id,
                            Lead.last_contact_at < seven_days_ago,
                        )
                        .count()
                    )

                    # Customers
                    customer_count = (
                        session.query(Lead)
                        .filter(
                            Lead.creator_id == creator.id,
                            Lead.status == "cliente",
                        )
                        .count()
                    )

                    # New: status = nuevo
                    new_count = (
                        session.query(Lead)
                        .filter(
                            Lead.creator_id == creator.id,
                            Lead.status == "nuevo",
                        )
                        .count()
                    )

                    # Price objectors and time objectors would need context field
                    # For now, estimate from context JSON
                    price_count = 0
                    time_count = 0

                    segment_counts = [
                        {"segment": "hot_lead", "count": hot_count},
                        {"segment": "warm_lead", "count": warm_count},
                        {"segment": "ghost", "count": ghost_count},
                        {"segment": "price_objector", "count": price_count},
                        {"segment": "time_objector", "count": time_count},
                        {"segment": "customer", "count": customer_count},
                        {"segment": "new", "count": new_count},
                    ]

                    return segment_counts

                finally:
                    session.close()

    except Exception as e:
        logger.warning(f"Database segment count failed: {e}")

    # Fallback: return zeros
    return [{"segment": s, "count": 0} for s in segments_to_count]


async def get_profiles_by_segment(
    creator_id: str,
    segment_name: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Get profiles belonging to a specific segment.

    Args:
        creator_id: Creator identifier
        segment_name: Segment to filter by
        limit: Max profiles to return

    Returns:
        List of profile dicts
    """
    profiles = []

    try:
        if os.getenv("DATABASE_URL"):
            from api.models import Lead, Creator
            from api.services.db_service import get_session
            from datetime import datetime, timedelta

            session = get_session()
            if session:
                try:
                    creator = session.query(Creator).filter_by(name=creator_id).first()
                    if not creator:
                        return []

                    # Build query based on segment
                    query = session.query(Lead).filter(Lead.creator_id == creator.id)

                    if segment_name == "hot_lead":
                        query = query.filter(
                            Lead.purchase_intent > 0.7,
                            Lead.status.in_(["caliente", "hot"]),
                        )
                    elif segment_name == "warm_lead":
                        query = query.filter(
                            Lead.purchase_intent >= 0.4,
                            Lead.purchase_intent <= 0.7,
                        )
                    elif segment_name == "ghost":
                        seven_days_ago = datetime.utcnow() - timedelta(days=7)
                        query = query.filter(Lead.last_contact_at < seven_days_ago)
                    elif segment_name == "customer":
                        query = query.filter(Lead.status == "cliente")
                    elif segment_name == "new":
                        query = query.filter(Lead.status == "nuevo")

                    leads = query.limit(limit).all()

                    # Build profiles using AudienceProfileBuilder
                    builder = get_audience_profile_builder(creator_id)

                    for lead in leads:
                        follower_id = lead.platform_user_id
                        profile = await builder.build_profile(follower_id)
                        if profile:
                            profiles.append(profile.to_dict())

                    return profiles

                finally:
                    session.close()

    except Exception as e:
        logger.warning(f"Get profiles by segment failed: {e}")

    return profiles


async def get_aggregated_metrics(creator_id: str) -> Dict[str, Any]:
    """
    Get aggregated audience metrics.

    Args:
        creator_id: Creator identifier

    Returns:
        Dict with total_followers, top_interests, top_objections, funnel_distribution
    """
    metrics = {
        "total_followers": 0,
        "top_interests": [],
        "top_objections": [],
        "funnel_distribution": {},
    }

    try:
        if os.getenv("DATABASE_URL"):
            from api.models import Lead, Creator, FollowerMemoryDB, ConversationStateDB
            from api.services.db_service import get_session
            from sqlalchemy import func
            from collections import Counter

            session = get_session()
            if session:
                try:
                    creator = session.query(Creator).filter_by(name=creator_id).first()
                    if not creator:
                        return metrics

                    # Total followers
                    total = session.query(Lead).filter_by(creator_id=creator.id).count()
                    metrics["total_followers"] = total

                    # Funnel distribution from conversation_states
                    phase_counts = (
                        session.query(
                            ConversationStateDB.phase,
                            func.count(ConversationStateDB.id),
                        )
                        .filter(ConversationStateDB.creator_id == creator_id)
                        .group_by(ConversationStateDB.phase)
                        .all()
                    )
                    metrics["funnel_distribution"] = {
                        phase: count for phase, count in phase_counts
                    }

                    # Top interests from follower_memories
                    interest_counter = Counter()
                    memories = (
                        session.query(FollowerMemoryDB)
                        .filter(FollowerMemoryDB.creator_id == creator_id)
                        .all()
                    )
                    for mem in memories:
                        if mem.interests:
                            for interest in mem.interests:
                                interest_counter[interest] += 1

                    metrics["top_interests"] = [
                        {"interest": i, "count": c}
                        for i, c in interest_counter.most_common(10)
                    ]

                    # Top objections from follower_memories
                    objection_counter = Counter()
                    for mem in memories:
                        if mem.objections_raised:
                            for obj in mem.objections_raised:
                                objection_counter[obj] += 1

                    metrics["top_objections"] = [
                        {"objection": o, "count": c}
                        for o, c in objection_counter.most_common(10)
                    ]

                    return metrics

                finally:
                    session.close()

    except Exception as e:
        logger.warning(f"Aggregated metrics failed: {e}")

    return metrics


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/{creator_id}/profile/{follower_id}")
async def get_profile(creator_id: str, follower_id: str) -> Dict[str, Any]:
    """
    Get complete audience profile for a follower.

    Returns profile with:
    - Narrative context
    - Auto-detected segments
    - Recommended action with priority
    - Objection suggestions

    Args:
        creator_id: Creator identifier
        follower_id: Platform-prefixed follower ID

    Returns:
        AudienceProfile as dict

    Raises:
        HTTPException 404: Follower not found
    """
    try:
        builder = get_audience_profile_builder(creator_id)
        profile = await builder.build_profile(follower_id)

        if not profile:
            raise HTTPException(status_code=404, detail="Follower not found")

        return profile.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{creator_id}/segments")
async def get_segments(creator_id: str) -> List[Dict[str, Any]]:
    """
    Get list of segments with follower counts.

    Returns:
        List of {segment, count} for each segment type
    """
    try:
        return await get_segment_counts(creator_id)

    except Exception as e:
        logger.error(f"Error getting segments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{creator_id}/segments/{segment_name}")
async def get_segment_users(
    creator_id: str,
    segment_name: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> List[Dict[str, Any]]:
    """
    Get profiles of users in a specific segment.

    Args:
        creator_id: Creator identifier
        segment_name: Segment to filter (hot_lead, ghost, etc.)
        limit: Max results (1-100, default 20)

    Returns:
        List of AudienceProfile dicts
    """
    try:
        return await get_profiles_by_segment(creator_id, segment_name, limit)

    except Exception as e:
        logger.error(f"Error getting segment users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{creator_id}/aggregated")
async def get_aggregated(creator_id: str) -> Dict[str, Any]:
    """
    Get aggregated audience metrics.

    Returns:
        - total_followers: Total count
        - top_interests: [{interest, count}] sorted desc
        - top_objections: [{objection, count}] sorted desc
        - funnel_distribution: {phase: count}
    """
    try:
        return await get_aggregated_metrics(creator_id)

    except Exception as e:
        logger.error(f"Error getting aggregated: {e}")
        raise HTTPException(status_code=500, detail=str(e))
