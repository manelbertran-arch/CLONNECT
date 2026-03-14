"""
DM Followers - Follower/lead detail endpoints
(get_follower_detail, update_follower_status)
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Database availability check
try:
    pass

    USE_DB = True
except Exception:
    USE_DB = False
    logger.warning("Database service not available in dm followers router")

router = APIRouter()


# Frontend-visible metadata keys (strips internal fields + oversized base64)
_META_KEEP = {
    "type", "url", "emoji", "link", "permalink", "caption",
    "permanent_url", "thumbnail_url", "preview_url",
    "animated_gif_url", "author_username", "platform",
    "duration", "render_as_sticker", "link_preview",
    "carousel_items", "items", "reacted_to_mid",
    "transcription", "transcript_summary", "transcript_full", "transcript_raw",
    "audio_intel", "filename", "width", "height",
}
_BASE64_MAX = 5_000_000  # ~3.7 MB decoded -- matches media_capture_service limit


def _slim_metadata(meta: dict | None) -> dict:
    """Return only the metadata fields the frontend needs, capping base64."""
    if not meta:
        return {}
    out: dict = {}
    for k, v in meta.items():
        if k not in _META_KEEP:
            continue
        # Cap thumbnail_base64 inside nested items too
        out[k] = v
    # thumbnail_base64 is needed but can be huge -- include only if small
    tb = meta.get("thumbnail_base64")
    if tb and len(tb) <= _BASE64_MAX:
        out["thumbnail_base64"] = tb
    return out


class UpdateLeadStatusRequest(BaseModel):
    """Request to update lead status in pipeline"""

    status: str  # cold, warm, hot, customer


@router.get("/follower/{creator_id}/{follower_id}")
async def get_follower_detail(creator_id: str, follower_id: str):
    """Obtener detalle de un seguidor con mensajes incluyendo metadata.

    OPTIMIZED: Query DB directly for leads, skip slow JSON file reads.
    Only fallback to agent for non-leads.
    """
    import time as _time

    from api.cache import api_cache
    from .conversations import _media_description

    start = _time.time()

    # Check cache first (15s TTL - shorter for active conversations)
    cache_key = f"follower_detail:{creator_id}:{follower_id}"
    cached = api_cache.get(cache_key)
    if cached:
        logger.info(f"[FOLLOWER] {creator_id}/{follower_id}: cache HIT ({_time.time()-start:.3f}s)")
        return cached
    logger.info(f"[FOLLOWER] {creator_id}/{follower_id}: cache MISS")

    try:
        detail = None

        # FAST PATH: Try DB first for leads (runs in thread to avoid blocking event loop)
        if USE_DB:
            try:
                import asyncio as _asyncio
                from api.models import Creator, Lead, Message
                from api.services.db_service import get_session

                def _db_fast_path():
                    from sqlalchemy import text as _text
                    session = get_session()
                    if not session:
                        return None
                    try:
                        creator = session.query(Creator).filter_by(name=creator_id).first()
                        if not creator:
                            return None
                        lead = (
                            session.query(Lead)
                            .filter_by(creator_id=creator.id, platform_user_id=follower_id)
                            .first()
                        )
                        if not lead:
                            return None
                        # Strip heavy JSONB fields at DB level to avoid transferring large blobs.
                        # audio_intel / thumbnail_base64 / best_of_n / transcript_raw / transcript_full
                        # can be MB each; with 50 messages that can be 50+ MB transferred.
                        sql = _text("""
                            SELECT
                                role, content, status, platform_message_id,
                                created_at, deleted_at,
                                CASE WHEN msg_metadata IS NOT NULL
                                    THEN msg_metadata
                                        - 'audio_intel'
                                        - 'thumbnail_base64'
                                        - 'best_of_n'
                                        - 'transcript_raw'
                                        - 'transcript_full'
                                    ELSE NULL
                                END AS msg_metadata
                            FROM messages
                            WHERE lead_id = :lead_id
                              AND status IN ('sent', 'edited')
                            ORDER BY created_at DESC
                            LIMIT 50
                        """)
                        rows = session.execute(sql, {"lead_id": lead.id}).mappings().fetchall()
                        rows = rows[::-1]  # Chronological order
                        return {
                            "follower_id": lead.platform_user_id,
                            "username": lead.username,
                            "name": lead.full_name or lead.username,
                            "platform": lead.platform or "instagram",
                            "profile_pic_url": lead.profile_pic_url,
                            "total_messages": len(rows),
                            "purchase_intent_score": lead.purchase_intent or 0,
                            "score": lead.score or 0,
                            "relationship_type": lead.relationship_type or "nuevo",
                            "is_lead": True,
                            "is_customer": lead.status == "cliente",
                            "status": lead.status,
                            "email": lead.email,
                            "phone": lead.phone,
                            "notes": lead.notes,
                            "deal_value": lead.deal_value,
                            "tags": lead.tags or [],
                            "last_messages": [
                                {
                                    "role": r["role"],
                                    "content": (
                                        r["content"]
                                        or _media_description(r["msg_metadata"])
                                        or "Sent an attachment"
                                    ),
                                    "timestamp": r["created_at"].isoformat() if r["created_at"] else None,
                                    "platform_message_id": r["platform_message_id"],
                                    "metadata": _slim_metadata(r["msg_metadata"]),
                                    **({"deleted_at": r["deleted_at"].isoformat()} if r["deleted_at"] else {}),
                                }
                                for r in rows
                            ],
                        }
                    finally:
                        session.close()

                detail = await _asyncio.to_thread(_db_fast_path)
                if detail is not None:
                    logger.info(f"[FOLLOWER] {creator_id}/{follower_id}: DB FAST PATH ({_time.time()-start:.3f}s)")
            except Exception as e:
                logger.warning(f"[FOLLOWER] DB fast path failed: {e}")

        # SLOW PATH: Fallback to agent for non-leads (reads JSON files)
        if detail is None:
            from .processing import get_dm_agent

            agent = get_dm_agent(creator_id)
            detail = await agent.get_follower_detail(follower_id)
            if not detail:
                raise HTTPException(status_code=404, detail="Follower not found")
            # Slim metadata on agent-returned messages too
            for msg in detail.get("last_messages", []):
                if "metadata" in msg:
                    msg["metadata"] = _slim_metadata(msg["metadata"])
            logger.info(f"[FOLLOWER] {creator_id}/{follower_id}: AGENT PATH ({_time.time()-start:.3f}s)")

        result = {"status": "ok", **detail}

        # Cache the result (10s TTL — short for real-time chat UX)
        api_cache.set(cache_key, result, ttl_seconds=3)
        logger.info(f"[FOLLOWER] {creator_id}/{follower_id}: CACHED in {_time.time()-start:.3f}s")

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/follower/{creator_id}/{follower_id}/status")
async def update_follower_status(
    creator_id: str, follower_id: str, request: UpdateLeadStatusRequest
):
    """
    Update the lead status for a follower (for drag & drop in pipeline).

    IMPORTANT: This does NOT change the purchase_intent_score!
    The score reflects actual user behavior and should not be modified by manual categorization.

    Valid status values:
    - cold: New follower, low intent
    - warm: Engaged follower, medium intent
    - hot: High purchase intent
    - customer: Has made a purchase
    """
    from .processing import get_dm_agent

    try:
        valid_statuses = ["cold", "warm", "hot", "customer"]
        status = request.status.lower()

        if status not in valid_statuses:
            raise HTTPException(
                status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}"
            )

        agent = get_dm_agent(creator_id)

        # Get current follower data to preserve the real score
        follower = await agent.memory_store.get(creator_id, follower_id)
        if not follower:
            raise HTTPException(status_code=404, detail="Follower not found")

        # Preserve the existing purchase_intent_score - DON'T CHANGE IT
        current_score = follower.purchase_intent_score

        # Only set is_customer if status is "customer"
        is_customer = (status == "customer") or follower.is_customer

        # Update status WITHOUT changing the score
        success = await agent.update_follower_status(
            follower_id=follower_id,
            status=status,
            purchase_intent=current_score,  # Keep the real score!
            is_customer=is_customer,
        )

        if not success:
            raise HTTPException(status_code=404, detail="Follower not found")

        logger.info(
            f"Updated status for {follower_id} to {status} (score preserved: {current_score:.0%})"
        )

        return {
            "status": "ok",
            "follower_id": follower_id,
            "new_status": status,
            "purchase_intent": current_score,  # Return the real score
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating follower status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
