"""
Unified leads endpoints — cross-platform identity resolution.

Provides read access to UnifiedLeads (grouped view of leads across
Instagram, WhatsApp, Telegram) and manual merge/unmerge operations.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/leads", tags=["unified-leads"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChannelLeadSummary(BaseModel):
    id: str
    platform: str
    platform_user_id: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    profile_pic_url: Optional[str] = None
    status: Optional[str] = None
    score: int = 0
    last_contact_at: Optional[str] = None


class UnifiedLeadResponse(BaseModel):
    id: str
    creator_id: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    profile_pic_url: Optional[str] = None
    unified_score: float = 0
    status: Optional[str] = None
    platforms: List[str] = []
    channel_leads: List[ChannelLeadSummary] = []
    first_contact_at: Optional[str] = None
    last_contact_at: Optional[str] = None
    created_at: Optional[str] = None


class MergeRequest(BaseModel):
    lead_ids: List[str]


class UnmergeRequest(BaseModel):
    unified_lead_id: str
    lead_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{creator_id}/unified")
async def list_unified_leads(creator_id: str, limit: int = 100, offset: int = 0):
    """List all UnifiedLeads for a creator with their channel leads."""
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, UnifiedLead

        session = SessionLocal()
        if not session:
            raise HTTPException(status_code=500, detail="Database not available")

        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                raise HTTPException(status_code=404, detail="Creator not found")

            unified_leads = (
                session.query(UnifiedLead)
                .filter(UnifiedLead.creator_id == creator.id)
                .order_by(UnifiedLead.last_contact_at.desc().nullslast())
                .offset(offset)
                .limit(limit)
                .all()
            )

            total = (
                session.query(UnifiedLead)
                .filter(UnifiedLead.creator_id == creator.id)
                .count()
            )

            results = []
            for ul in unified_leads:
                channel_leads = (
                    session.query(Lead)
                    .filter(Lead.unified_lead_id == ul.id)
                    .limit(100)
                    .all()
                )
                platforms = list({cl.platform for cl in channel_leads})

                results.append(UnifiedLeadResponse(
                    id=str(ul.id),
                    creator_id=str(ul.creator_id),
                    display_name=ul.display_name,
                    email=ul.email,
                    phone=ul.phone,
                    profile_pic_url=ul.profile_pic_url,
                    unified_score=ul.unified_score or 0,
                    status=ul.status,
                    platforms=platforms,
                    channel_leads=[
                        ChannelLeadSummary(
                            id=str(cl.id),
                            platform=cl.platform,
                            platform_user_id=cl.platform_user_id,
                            username=cl.username,
                            full_name=cl.full_name,
                            profile_pic_url=cl.profile_pic_url,
                            status=cl.status,
                            score=cl.score or 0,
                            last_contact_at=cl.last_contact_at.isoformat() if cl.last_contact_at else None,
                        )
                        for cl in channel_leads
                    ],
                    first_contact_at=ul.first_contact_at.isoformat() if ul.first_contact_at else None,
                    last_contact_at=ul.last_contact_at.isoformat() if ul.last_contact_at else None,
                    created_at=ul.created_at.isoformat() if ul.created_at else None,
                ))

            return {"total": total, "items": results}

        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UNIFIED] list error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{creator_id}/unified/{unified_id}")
async def get_unified_lead(creator_id: str, unified_id: str):
    """Get a single UnifiedLead with all its channel leads."""
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, UnifiedLead

        session = SessionLocal()
        if not session:
            raise HTTPException(status_code=500, detail="Database not available")

        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                raise HTTPException(status_code=404, detail="Creator not found")

            unified = (
                session.query(UnifiedLead)
                .filter(UnifiedLead.id == unified_id, UnifiedLead.creator_id == creator.id)
                .first()
            )
            if not unified:
                raise HTTPException(status_code=404, detail="Unified lead not found")

            channel_leads = (
                session.query(Lead)
                .filter(Lead.unified_lead_id == unified.id)
                .limit(100)
                .all()
            )
            platforms = list({cl.platform for cl in channel_leads})

            return UnifiedLeadResponse(
                id=str(unified.id),
                creator_id=str(unified.creator_id),
                display_name=unified.display_name,
                email=unified.email,
                phone=unified.phone,
                profile_pic_url=unified.profile_pic_url,
                unified_score=unified.unified_score or 0,
                status=unified.status,
                platforms=platforms,
                channel_leads=[
                    ChannelLeadSummary(
                        id=str(cl.id),
                        platform=cl.platform,
                        platform_user_id=cl.platform_user_id,
                        username=cl.username,
                        full_name=cl.full_name,
                        profile_pic_url=cl.profile_pic_url,
                        status=cl.status,
                        score=cl.score or 0,
                        last_contact_at=cl.last_contact_at.isoformat() if cl.last_contact_at else None,
                    )
                    for cl in channel_leads
                ],
                first_contact_at=unified.first_contact_at.isoformat() if unified.first_contact_at else None,
                last_contact_at=unified.last_contact_at.isoformat() if unified.last_contact_at else None,
                created_at=unified.created_at.isoformat() if unified.created_at else None,
            )

        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UNIFIED] get error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{creator_id}/merge")
async def merge_leads(creator_id: str, request: MergeRequest):
    """Manually merge multiple leads into one UnifiedLead."""
    from core.identity_resolver import manual_merge

    if len(request.lead_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 lead_ids to merge")

    unified_id = await manual_merge(creator_id, request.lead_ids)
    if not unified_id:
        raise HTTPException(status_code=400, detail="Merge failed — leads not found or invalid")

    return {"status": "merged", "unified_lead_id": unified_id}


@router.post("/{creator_id}/unmerge")
async def unmerge_lead(creator_id: str, request: UnmergeRequest):
    """Separate a lead from its UnifiedLead group."""
    from core.identity_resolver import manual_unmerge

    success = await manual_unmerge(creator_id, request.unified_lead_id, request.lead_id)
    if not success:
        raise HTTPException(status_code=400, detail="Unmerge failed — check IDs")

    return {"status": "unmerged", "lead_id": request.lead_id}
