"""
DM Router - Endpoints for direct message management
Extracted from main.py as part of refactoring
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Database availability check
try:
    from api import db_service

    USE_DB = True
except Exception:
    USE_DB = False
    logger.warning("Database service not available in dm router")

import httpx

# Core imports
from core.dm_agent_v2 import DMResponderAgent
from core.instagram_handler import get_instagram_handler
from core.whatsapp import get_whatsapp_handler

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

router = APIRouter(prefix="/dm", tags=["dm"])


# ---------------------------------------------------------
# PYDANTIC MODELS
# ---------------------------------------------------------
class ProcessDMRequest(BaseModel):
    creator_id: str
    sender_id: str
    message: str
    message_id: str = ""


class SendMessageRequest(BaseModel):
    """Request to send a manual message to a follower"""

    follower_id: str
    message: str


class UpdateLeadStatusRequest(BaseModel):
    """Request to update lead status in pipeline"""

    status: str  # cold, warm, hot, customer


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------
def get_dm_agent(creator_id: str) -> DMResponderAgent:
    """Factory para crear DM agent"""
    return DMResponderAgent(creator_id=creator_id)


# ---------------------------------------------------------
# DM ENDPOINTS
# ---------------------------------------------------------
@router.post("/process")
async def process_dm(payload: ProcessDMRequest):
    """Procesar un DM manualmente (para testing)"""
    try:
        agent = get_dm_agent(payload.creator_id)

        result = await agent.process_dm(
            message=payload.message,
            sender_id=payload.sender_id,
            metadata={"message_id": payload.message_id},
        )

        return {
            "status": "ok",
            "response": result.content,
            "intent": result.intent,
            "lead_stage": result.lead_stage,
            "confidence": result.confidence,
            "tokens_used": result.tokens_used,
        }

    except Exception as e:
        logger.error(f"Error processing DM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{creator_id}")
async def get_conversations(creator_id: str, limit: int = 50):
    """Listar conversaciones del creador - OPTIMIZED with caching"""
    import time as _time

    from api.cache import api_cache

    # Check cache first (60s TTL - matches startup.py cache refresh)
    cache_key = f"conversations:{creator_id}:{limit}"
    cached = api_cache.get(cache_key)
    if cached:
        logger.info(f"[CONV] {creator_id}: cache HIT (key={cache_key})")
        return cached
    logger.info(f"[CONV] {creator_id}: cache MISS (key={cache_key})")

    start_time = _time.time()

    try:
        if USE_DB:
            from api.models import Creator, Lead, Message
            from api.services.db_service import get_session
            from sqlalchemy import desc, func, not_

            session = get_session()
            if session:
                try:
                    creator = session.query(Creator).filter_by(name=creator_id).first()
                    if not creator:
                        return {"status": "ok", "conversations": [], "count": 0}

                    # OPTIMIZED: Single query for leads with message counts
                    msg_count_subq = (
                        session.query(Message.lead_id, func.count(Message.id).label("msg_count"))
                        .filter(Message.role == "user")
                        .group_by(Message.lead_id)
                        .subquery()
                    )

                    results = (
                        session.query(
                            Lead,
                            func.coalesce(msg_count_subq.c.msg_count, 0).label("total_messages"),
                        )
                        .outerjoin(msg_count_subq, Lead.id == msg_count_subq.c.lead_id)
                        .filter(
                            Lead.creator_id == creator.id,
                            not_(Lead.status.in_(["archived", "spam"])),
                        )
                        .order_by(Lead.last_contact_at.desc())
                        .limit(limit)
                        .all()
                    )

                    # OPTIMIZED: Get last message for each lead in ONE query
                    lead_ids = [lead.id for lead, _ in results]

                    # Subquery to get the latest message per lead
                    last_msg_subq = (
                        session.query(
                            Message.lead_id, func.max(Message.created_at).label("max_date")
                        )
                        .filter(Message.lead_id.in_(lead_ids))
                        .group_by(Message.lead_id)
                        .subquery()
                    )

                    last_messages_query = (
                        session.query(Message)
                        .join(
                            last_msg_subq,
                            (Message.lead_id == last_msg_subq.c.lead_id)
                            & (Message.created_at == last_msg_subq.c.max_date),
                        )
                        .all()
                    )

                    # Build lookup dict for last messages
                    last_msg_by_lead = {msg.lead_id: msg for msg in last_messages_query}

                    conversations = []
                    for lead, msg_count in results:
                        ctx = lead.context or {}

                        # Get last message from pre-fetched data
                        last_msg = last_msg_by_lead.get(lead.id)
                        last_messages = []
                        last_message_preview = None
                        last_message_role = None

                        if last_msg:
                            last_messages = [
                                {
                                    "role": last_msg.role,
                                    "content": last_msg.content[:200] if last_msg.content else "",
                                    "timestamp": (
                                        last_msg.created_at.isoformat()
                                        if last_msg.created_at
                                        else None
                                    ),
                                }
                            ]
                            # Instagram-like UX fields
                            content = last_msg.content or ""
                            last_message_preview = (
                                content[:50] + "..." if len(content) > 50 else content
                            )
                            last_message_role = last_msg.role

                        # is_unread: Check if last user message is after last_read_at
                        last_read_at = ctx.get("last_read_at")
                        last_user_msg_time = (
                            last_msg.created_at.isoformat()
                            if last_msg and last_msg.role == "user" and last_msg.created_at
                            else None
                        )
                        if last_read_at and last_user_msg_time:
                            # Compare timestamps - unread if user message is after read time
                            is_unread = last_user_msg_time > last_read_at
                        else:
                            # Fallback: unread if last message is from user
                            is_unread = last_message_role == "user"
                        # is_verified: from context JSON (populated by Instagram API)
                        is_verified = ctx.get("is_verified", False)

                        conversations.append(
                            {
                                "follower_id": lead.platform_user_id,
                                "id": str(lead.id),
                                "username": lead.username or lead.platform_user_id,
                                "name": lead.full_name or lead.username or "",
                                "platform": lead.platform or "instagram",
                                "profile_pic_url": lead.profile_pic_url,
                                "total_messages": msg_count,
                                "purchase_intent": lead.purchase_intent or 0.0,
                                "purchase_intent_score": lead.purchase_intent or 0.0,
                                "status": lead.status or "new",
                                "is_lead": True,
                                "last_contact": (
                                    lead.last_contact_at.isoformat()
                                    if lead.last_contact_at
                                    else None
                                ),
                                "last_messages": last_messages,
                                # Instagram-like UX fields (FIX 2026-02-02)
                                "last_message_preview": last_message_preview,
                                "last_message_role": last_message_role,
                                "is_unread": is_unread,
                                "is_verified": is_verified,
                                # CRM fields
                                "email": ctx.get("email") or lead.email or "",
                                "phone": ctx.get("phone") or lead.phone or "",
                                "notes": ctx.get("notes") or lead.notes or "",
                            }
                        )

                    elapsed = _time.time() - start_time
                    logger.info(
                        f"[CONV] {creator_id}: {len(conversations)} conversations in {elapsed:.2f}s (DB query)"
                    )
                    result = {
                        "status": "ok",
                        "conversations": conversations,
                        "count": len(conversations),
                    }
                    # Cache for 60 seconds (matches startup.py refresh cycle)
                    api_cache.set(cache_key, result, ttl_seconds=60)
                    return result
                finally:
                    session.close()

        # Fallback to JSON if PostgreSQL not available
        agent = get_dm_agent(creator_id)
        conversations = await agent.get_all_conversations(limit)
        filtered = [c for c in conversations if not c.get("archived") and not c.get("spam")]
        return {"status": "ok", "conversations": filtered, "count": len(filtered)}

    except Exception as e:
        logger.error(f"get_conversations error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/{creator_id}/{follower_id}/mark-read")
async def mark_conversation_read(creator_id: str, follower_id: str):
    """Mark a conversation as read by updating last_read_at in lead context"""
    if not USE_DB:
        return {"status": "ok", "message": "No database - skipped"}

    try:
        from api.models import Creator, Lead
        from api.services.db_service import get_session

        session = get_session()
        if not session:
            return {"status": "error", "message": "No database session"}

        try:
            # Find creator
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"status": "error", "message": "Creator not found"}

            # Find lead by platform_user_id
            lead = (
                session.query(Lead)
                .filter(
                    Lead.creator_id == creator.id,
                    Lead.platform_user_id == follower_id,
                )
                .first()
            )

            if lead:
                # Update context with last_read_at timestamp
                context = lead.context or {}
                context["last_read_at"] = datetime.now(timezone.utc).isoformat()
                lead.context = context
                session.commit()
                logger.info(f"[MarkRead] {creator_id}/{follower_id} marked as read")
                return {"status": "ok", "message": "Conversation marked as read"}
            else:
                return {"status": "error", "message": "Lead not found"}

        finally:
            session.close()

    except Exception as e:
        logger.error(f"mark_conversation_read error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/{creator_id}")
async def debug_messages(creator_id: str):
    """Debug endpoint to diagnose message count issue"""
    debug_info = {
        "creator_id": creator_id,
        "use_db": USE_DB,
        "creator_found": False,
        "total_leads": 0,
        "total_messages_all": 0,
        "total_messages_user": 0,
        "leads_with_messages": [],
        "sample_messages": [],
    }

    if not USE_DB:
        return {"status": "error", "message": "Database not available", "debug": debug_info}

    try:
        from api.models import Creator, Lead, Message
        from api.services.db_service import get_session
        from sqlalchemy import func

        session = get_session()
        if not session:
            return {"status": "error", "message": "No session", "debug": debug_info}

        try:
            # Check if creator exists
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                debug_info["error"] = f"Creator '{creator_id}' not found"
                # List all creators
                all_creators = session.query(Creator).all()
                debug_info["available_creators"] = [c.name for c in all_creators]
                return {"status": "error", "message": "Creator not found", "debug": debug_info}

            debug_info["creator_found"] = True
            debug_info["creator_uuid"] = str(creator.id)

            # Count leads for this creator
            leads = session.query(Lead).filter_by(creator_id=creator.id).all()
            debug_info["total_leads"] = len(leads)

            # Get lead UUIDs
            lead_ids = [lead.id for lead in leads]
            debug_info["lead_uuids"] = [str(lid) for lid in lead_ids[:5]]  # First 5

            # Count ALL messages for these leads
            if lead_ids:
                all_msg_count = session.query(Message).filter(Message.lead_id.in_(lead_ids)).count()
                debug_info["total_messages_all"] = all_msg_count

                # Count only user messages
                user_msg_count = (
                    session.query(Message)
                    .filter(Message.lead_id.in_(lead_ids), Message.role == "user")
                    .count()
                )
                debug_info["total_messages_user"] = user_msg_count

                # Get message counts per lead
                for lead in leads[:5]:  # First 5 leads
                    lead_all = session.query(Message).filter_by(lead_id=lead.id).count()
                    lead_user = (
                        session.query(Message).filter_by(lead_id=lead.id, role="user").count()
                    )
                    debug_info["leads_with_messages"].append(
                        {
                            "lead_id": str(lead.id),
                            "platform_user_id": lead.platform_user_id,
                            "username": lead.username,
                            "all_messages": lead_all,
                            "user_messages": lead_user,
                        }
                    )

                # Get sample messages
                sample_msgs = (
                    session.query(Message).filter(Message.lead_id.in_(lead_ids)).limit(5).all()
                )
                for msg in sample_msgs:
                    debug_info["sample_messages"].append(
                        {
                            "id": str(msg.id),
                            "lead_id": str(msg.lead_id),
                            "role": msg.role,
                            "content_preview": msg.content[:50] if msg.content else "",
                        }
                    )

                # Check for orphan messages (messages not associated with any of this creator's leads)
                all_msgs_in_db = session.query(Message).count()
                msgs_for_creator = (
                    session.query(Message).filter(Message.lead_id.in_(lead_ids)).count()
                    if lead_ids
                    else 0
                )
                orphan_msgs = all_msgs_in_db - msgs_for_creator
                debug_info["orphan_messages"] = orphan_msgs
                debug_info["all_messages_in_db"] = all_msgs_in_db
                debug_info["messages_for_this_creator"] = msgs_for_creator

                # Get sample orphan messages if any
                if orphan_msgs > 0 and lead_ids:
                    orphan_sample = (
                        session.query(Message).filter(~Message.lead_id.in_(lead_ids)).limit(5).all()
                    )
                    debug_info["orphan_sample"] = [
                        {
                            "id": str(msg.id),
                            "lead_id": str(msg.lead_id),
                            "role": msg.role,
                            "content_preview": msg.content[:50] if msg.content else "",
                        }
                        for msg in orphan_sample
                    ]

            return {"status": "ok", "debug": debug_info}

        finally:
            session.close()

    except Exception as e:
        debug_info["exception"] = str(e)
        logger.error(f"debug_messages error: {e}")
        return {"status": "error", "message": str(e), "debug": debug_info}


@router.get("/metrics/{creator_id}")
async def get_dm_metrics(creator_id: str):
    """Obtener metricas del agent"""
    try:
        agent = get_dm_agent(creator_id)
        metrics = await agent.get_metrics()
        return {"status": "ok", **metrics}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/follower/{creator_id}/{follower_id}")
async def get_follower_detail(creator_id: str, follower_id: str):
    """Obtener detalle de un seguidor con mensajes incluyendo metadata.

    OPTIMIZED: Query DB directly for leads, skip slow JSON file reads.
    Only fallback to agent for non-leads.
    """
    import time as _time

    from api.cache import api_cache

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

        # FAST PATH: Try DB first for leads (skip slow JSON reads)
        if USE_DB:
            try:
                from api.models import Creator, Lead, Message
                from api.services.db_service import get_session

                session = get_session()
                if session:
                    try:
                        creator = session.query(Creator).filter_by(name=creator_id).first()
                        if creator:
                            lead = (
                                session.query(Lead)
                                .filter_by(creator_id=creator.id, platform_user_id=follower_id)
                                .first()
                            )
                            if lead:
                                # Build detail directly from DB - no JSON file reads!
                                messages = (
                                    session.query(Message)
                                    .filter_by(lead_id=lead.id)
                                    .order_by(Message.created_at.desc())
                                    .limit(50)
                                    .all()
                                )
                                messages = messages[::-1]  # Chronological order

                                detail = {
                                    "follower_id": lead.platform_user_id,
                                    "username": lead.username,
                                    "name": lead.name,
                                    "platform": lead.platform or "instagram",
                                    "profile_pic_url": lead.profile_pic_url,
                                    "total_messages": len(messages),
                                    "purchase_intent_score": lead.purchase_intent_score or 0,
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
                                            "role": m.role,
                                            "content": m.content,
                                            "timestamp": m.created_at.isoformat() if m.created_at else None,
                                            "metadata": m.msg_metadata or {},
                                        }
                                        for m in messages
                                    ],
                                }
                                logger.info(f"[FOLLOWER] {creator_id}/{follower_id}: DB FAST PATH ({_time.time()-start:.3f}s)")
                    finally:
                        session.close()
            except Exception as e:
                logger.warning(f"[FOLLOWER] DB fast path failed: {e}")

        # SLOW PATH: Fallback to agent for non-leads (reads JSON files)
        if detail is None:
            agent = get_dm_agent(creator_id)
            detail = await agent.get_follower_detail(follower_id)
            if not detail:
                raise HTTPException(status_code=404, detail="Follower not found")
            logger.info(f"[FOLLOWER] {creator_id}/{follower_id}: AGENT PATH ({_time.time()-start:.3f}s)")

        result = {"status": "ok", **detail}

        # Cache the result (15s TTL)
        api_cache.set(cache_key, result, ttl_seconds=60)
        logger.info(f"[FOLLOWER] {creator_id}/{follower_id}: CACHED in {_time.time()-start:.3f}s")

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send/{creator_id}")
async def send_manual_message(creator_id: str, request: SendMessageRequest):
    """
    Send a manual message to a follower.

    The message will be sent via the appropriate platform (Telegram, Instagram, WhatsApp)
    based on the follower_id prefix:
    - tg_* -> Telegram
    - ig_* -> Instagram
    - wa_* -> WhatsApp

    The message is also saved in the conversation history.
    """
    try:
        follower_id = request.follower_id
        message_text = request.message

        if not message_text.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        # Detect platform from follower_id prefix
        if follower_id.startswith("tg_"):
            platform = "telegram"
            chat_id = follower_id.replace("tg_", "")
        elif follower_id.startswith("ig_"):
            platform = "instagram"
            recipient_id = follower_id.replace("ig_", "")
        elif follower_id.startswith("wa_"):
            platform = "whatsapp"
            phone = follower_id.replace("wa_", "")
        else:
            # Assume Instagram for legacy IDs without prefix
            platform = "instagram"
            recipient_id = follower_id

        sent = False

        # Send via appropriate platform
        if platform == "telegram" and TELEGRAM_BOT_TOKEN:
            try:
                telegram_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        telegram_api,
                        json={"chat_id": int(chat_id), "text": message_text, "parse_mode": "HTML"},
                    )
                    if resp.status_code == 200:
                        sent = True
                        logger.info(f"Manual message sent to Telegram chat {chat_id}")
            except Exception as e:
                logger.error(f"Error sending Telegram message: {e}")

        elif platform == "instagram":
            try:
                handler = get_instagram_handler()
                if handler.connector:
                    sent = await handler.send_response(recipient_id, message_text)
                    if sent:
                        logger.info(f"Manual message sent to Instagram {recipient_id}")
            except Exception as e:
                logger.error(f"Error sending Instagram message: {e}")

        elif platform == "whatsapp":
            try:
                wa_handler = get_whatsapp_handler()
                if wa_handler and wa_handler.connector:
                    result = await wa_handler.connector.send_message(phone, message_text)
                    sent = "error" not in result
                    if sent:
                        logger.info(f"Manual message sent to WhatsApp {phone}")
            except Exception as e:
                logger.error(f"Error sending WhatsApp message: {e}")

        # Save the message in conversation history
        agent = get_dm_agent(creator_id)
        await agent.save_manual_message(follower_id, message_text, sent)

        return {
            "status": "ok",
            "sent": sent,
            "platform": platform,
            "follower_id": follower_id,
            "message_preview": (
                message_text[:100] + "..." if len(message_text) > 100 else message_text
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending manual message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


# ============ CONVERSATION ACTIONS ============


@router.post("/conversations/{creator_id}/{conversation_id}/archive")
async def archive_conversation_endpoint(creator_id: str, conversation_id: str):
    # Try PostgreSQL first
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service

            success = db_service.archive_conversation(creator_id, conversation_id)
            if success:
                return {"status": "ok", "archived": True}
        except Exception as e:
            logger.warning(f"PostgreSQL archive failed: {e}")
    # Fallback to JSON files
    try:
        file_path = f"data/followers/{creator_id}/{conversation_id}.json"
        if not os.path.exists(file_path):
            return {"status": "error", "message": "Conversation not found"}
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["archived"] = True
        data["is_lead"] = False
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return {"status": "ok", "archived": True}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/conversations/{creator_id}/{conversation_id}/spam")
async def mark_conversation_spam_endpoint(creator_id: str, conversation_id: str):
    # Try PostgreSQL first
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service

            success = db_service.mark_conversation_spam(creator_id, conversation_id)
            if success:
                return {"status": "ok", "spam": True}
        except Exception as e:
            logger.warning(f"PostgreSQL spam failed: {e}")
    # Fallback to JSON files
    try:
        file_path = f"data/followers/{creator_id}/{conversation_id}.json"
        if not os.path.exists(file_path):
            return {"status": "error", "message": "Conversation not found"}
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["spam"] = True
        data["is_lead"] = False
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Invalidate cache
        agent = get_dm_agent(creator_id)
        cache_key = f"{creator_id}:{conversation_id}"
        if cache_key in agent.memory_store._cache:
            del agent.memory_store._cache[cache_key]
        return {"status": "ok", "spam": True}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.delete("/conversations/{creator_id}/{conversation_id}")
async def delete_conversation_endpoint(creator_id: str, conversation_id: str):
    # Try PostgreSQL first
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service

            success = db_service.delete_conversation(creator_id, conversation_id)
            if success:
                return {"status": "ok", "deleted": conversation_id}
        except Exception as e:
            logger.warning(f"PostgreSQL delete failed: {e}")
    # Fallback to JSON files
    try:
        file_path = f"data/followers/{creator_id}/{conversation_id}.json"
        if not os.path.exists(file_path):
            return {"status": "error", "message": "Conversation not found"}
        os.remove(file_path)
        return {"status": "ok", "deleted": conversation_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============ ARCHIVED/SPAM MANAGEMENT ============


@router.get("/conversations/{creator_id}/archived")
async def get_archived_conversations(creator_id: str):
    """Get all archived and spam conversations"""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.models import Creator, Lead, Message
            from api.services import db_service
            from api.services.db_service import get_session

            session = get_session()
            if not session:
                return {"status": "error", "conversations": []}

            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    return {"status": "ok", "conversations": []}

                leads = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id)
                    .filter(Lead.status.in_(["archived", "spam"]))
                    .order_by(Lead.last_contact_at.desc())
                    .all()
                )

                conversations = []
                for lead in leads:
                    # Only count user messages, not bot responses
                    msg_count = (
                        session.query(Message).filter_by(lead_id=lead.id, role="user").count()
                    )
                    conversations.append(
                        {
                            "id": str(lead.id),
                            "follower_id": lead.platform_user_id or str(lead.id),
                            "username": lead.username,
                            "name": lead.full_name,
                            "platform": lead.platform or "instagram",
                            "status": lead.status,
                            "total_messages": msg_count,
                            "purchase_intent": lead.purchase_intent or 0.0,
                            "last_contact": (
                                lead.last_contact_at.isoformat() if lead.last_contact_at else None
                            ),
                        }
                    )

                return {"status": "ok", "conversations": conversations}
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Get archived failed: {e}")
            return {"status": "error", "message": str(e), "conversations": []}
    return {"status": "ok", "conversations": []}


@router.post("/conversations/{creator_id}/{conversation_id}/restore")
async def restore_conversation(creator_id: str, conversation_id: str):
    """Restore an archived/spam conversation back to 'new' status"""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service

            count = db_service.reset_conversation_status(creator_id, conversation_id)
            if count > 0:
                return {"status": "ok", "restored": True}
            return {"status": "error", "message": "Conversation not found or not archived/spam"}
        except Exception as e:
            logger.warning(f"Restore failed: {e}")
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Database not configured"}


@router.post("/conversations/{creator_id}/reset")
async def reset_conversations(creator_id: str):
    """Reset all archived/spam conversations back to 'new' status"""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service

            count = db_service.reset_conversation_status(creator_id)
            return {"status": "ok", "reset_count": count}
        except Exception as e:
            logger.warning(f"Reset failed: {e}")
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Database not configured"}


@router.post("/conversations/{creator_id}/sync-messages")
async def sync_messages_from_json_endpoint(creator_id: str):
    """Sync all messages from JSON files to PostgreSQL (one-time migration)"""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services.data_sync import sync_messages_from_json

            stats = sync_messages_from_json(creator_id)
            return {"status": "ok", **stats}
        except Exception as e:
            logger.warning(f"Message sync failed: {e}")
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Database not configured"}


@router.post("/conversations/{creator_id}/sync-timestamps")
async def sync_last_contact_timestamps(creator_id: str):
    """Sync last_contact_at for all leads based on their actual last message time."""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if not USE_DB:
        return {"status": "error", "message": "Database not configured"}

    try:
        from api.models import Creator, Lead, Message
        from api.services.db_service import get_session
        from sqlalchemy import func

        session = get_session()
        if not session:
            return {"status": "error", "message": "Could not get database session"}

        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"status": "error", "message": f"Creator {creator_id} not found"}

            # Get all leads with their actual last message time
            leads_with_last_msg = (
                session.query(
                    Lead.id,
                    Lead.username,
                    Lead.last_contact_at,
                    func.max(Message.created_at).label("last_msg_time"),
                )
                .outerjoin(Message, Lead.id == Message.lead_id)
                .filter(Lead.creator_id == creator.id)
                .group_by(Lead.id)
                .all()
            )

            updated = 0
            for lead_id, username, last_contact, last_msg_time in leads_with_last_msg:
                if last_msg_time and (not last_contact or last_msg_time > last_contact):
                    session.query(Lead).filter_by(id=lead_id).update(
                        {"last_contact_at": last_msg_time}
                    )
                    updated += 1
                    logger.info(
                        f"[SyncTimestamps] Updated {username}: {last_contact} -> {last_msg_time}"
                    )

            session.commit()
            return {
                "status": "ok",
                "leads_checked": len(leads_with_last_msg),
                "leads_updated": updated,
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[SyncTimestamps] Error: {e}")
        return {"status": "error", "message": str(e)}
