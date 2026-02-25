"""
Memory Engine API endpoints.

Provides REST access to per-lead memories:
- GET /memory/stats/{creator_id}           — Memory stats for a creator
- GET /memory/{creator_id}/{lead_id}       — Retrieve active memories
- DELETE /memory/{creator_id}/{lead_id}     — GDPR forget (delete all)
- POST /memory/{creator_id}/consolidate    — Manual decay trigger
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_creator_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/stats/{creator_id}")
async def get_memory_stats(
    creator_id: str,
    _auth=Depends(require_creator_access),
):
    """Get memory engine stats for a creator (fact counts, summary counts)."""
    from services.memory_engine import ENABLE_MEMORY_ENGINE

    if not ENABLE_MEMORY_ENGINE:
        return {"enabled": False, "total_facts": 0, "active_facts": 0, "leads_with_memories": 0, "total_summaries": 0}

    from api.database import SessionLocal
    from api.models import Creator
    from sqlalchemy import text

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        cid = str(creator.id)

        total_facts = session.execute(
            text("SELECT COUNT(*) FROM lead_memories WHERE creator_id = CAST(:cid AS uuid)"),
            {"cid": cid},
        ).scalar() or 0

        active_facts = session.execute(
            text("SELECT COUNT(*) FROM lead_memories WHERE creator_id = CAST(:cid AS uuid) AND is_active = true"),
            {"cid": cid},
        ).scalar() or 0

        leads_with_memories = session.execute(
            text("SELECT COUNT(DISTINCT lead_id) FROM lead_memories WHERE creator_id = CAST(:cid AS uuid) AND is_active = true"),
            {"cid": cid},
        ).scalar() or 0

        total_summaries = session.execute(
            text("SELECT COUNT(*) FROM conversation_summaries WHERE creator_id = CAST(:cid AS uuid)"),
            {"cid": cid},
        ).scalar() or 0

        return {
            "enabled": True,
            "creator_id": creator_id,
            "total_facts": total_facts,
            "active_facts": active_facts,
            "leads_with_memories": leads_with_memories,
            "total_summaries": total_summaries,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Memory] Error getting stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


@router.get("/{creator_id}/{lead_id}")
async def get_lead_memories(
    creator_id: str,
    lead_id: str,
    fact_type: Optional[str] = None,
    _auth=Depends(require_creator_access),
):
    """Get all active memories for a specific lead."""
    from services.memory_engine import ENABLE_MEMORY_ENGINE, get_memory_engine

    if not ENABLE_MEMORY_ENGINE:
        return {"enabled": False, "facts": [], "summary": None}

    from api.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    try:
        query = (
            "SELECT id, fact_type, fact_text, confidence, source_type, "
            "times_accessed, last_accessed_at, is_active, created_at "
            "FROM lead_memories "
            "WHERE creator_id = CAST(:cid AS uuid) "
            "AND lead_id = CAST(:lid AS uuid) "
            "AND is_active = true "
        )
        params = {"cid": creator_id, "lid": lead_id}

        if fact_type:
            query += "AND fact_type = :ftype "
            params["ftype"] = fact_type

        query += "ORDER BY created_at DESC LIMIT 50"

        rows = session.execute(text(query), params).fetchall()

        facts = [
            {
                "id": str(row[0]),
                "fact_type": row[1],
                "fact_text": row[2],
                "confidence": float(row[3]) if row[3] else 0.7,
                "source_type": row[4],
                "times_accessed": row[5],
                "last_accessed_at": str(row[6]) if row[6] else None,
                "created_at": str(row[8]) if row[8] else None,
            }
            for row in rows
        ]

        summary_row = session.execute(
            text(
                "SELECT summary_text, key_topics, commitments_made, "
                "sentiment, message_count, created_at "
                "FROM conversation_summaries "
                "WHERE creator_id = CAST(:cid AS uuid) "
                "AND lead_id = CAST(:lid AS uuid) "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"cid": creator_id, "lid": lead_id},
        ).fetchone()

        summary = None
        if summary_row:
            summary = {
                "summary_text": summary_row[0],
                "key_topics": summary_row[1],
                "commitments_made": summary_row[2],
                "sentiment": summary_row[3],
                "message_count": summary_row[4],
                "created_at": str(summary_row[5]) if summary_row[5] else None,
            }

        return {
            "enabled": True,
            "facts_count": len(facts),
            "facts": facts,
            "summary": summary,
        }

    finally:
        session.close()


@router.delete("/{creator_id}/{lead_id}")
async def forget_lead_memories(
    creator_id: str,
    lead_id: str,
    _auth=Depends(require_creator_access),
):
    """GDPR: Delete ALL memories for a specific lead."""
    from services.memory_engine import ENABLE_MEMORY_ENGINE, get_memory_engine

    if not ENABLE_MEMORY_ENGINE:
        return {"deleted": 0, "message": "Memory Engine is disabled"}

    engine = get_memory_engine()
    deleted = await engine.forget_lead(creator_id, lead_id)

    return {
        "deleted": deleted,
        "message": f"Deleted {deleted} memory records for lead",
    }


@router.post("/{creator_id}/consolidate")
async def consolidate_memories(
    creator_id: str,
    _auth=Depends(require_creator_access),
):
    """Manual trigger: run memory decay for a specific creator."""
    from services.memory_engine import ENABLE_MEMORY_ENGINE, get_memory_engine

    if not ENABLE_MEMORY_ENGINE:
        return {"deactivated": 0, "message": "Memory Engine is disabled"}

    engine = get_memory_engine()
    deactivated = await engine.decay_memories(creator_id)

    return {
        "deactivated": deactivated,
        "message": f"Deactivated {deactivated} stale memories",
    }
