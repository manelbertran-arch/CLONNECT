"""
Copilot lifecycle — create and list pending responses.

Handles the creation of pending suggestions (with dedup, anti-zombie,
lead scoring) and the optimized listing of pending responses.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from core.copilot.models import PendingResponse, is_non_text_message

logger = logging.getLogger(__name__)


async def create_pending_response_impl(
    service,
    creator_id: str,
    lead_id: str,
    follower_id: str,
    platform: str,
    user_message: str,
    user_message_id: str,
    suggested_response: str,
    intent: str,
    confidence: float,
    username: str = "",
    full_name: str = "",
    msg_metadata: dict = None,
) -> PendingResponse:
    """
    Crear una respuesta pendiente de aprobación.
    Guarda en PostgreSQL y cache en memoria.
    """
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    pending_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    pending = PendingResponse(
        id=pending_id,
        lead_id=lead_id,
        follower_id=follower_id,
        platform=platform,
        user_message=user_message,
        user_message_id=user_message_id,
        suggested_response=suggested_response,
        intent=intent,
        confidence=confidence,
        created_at=now.isoformat(),
        username=username,
        full_name=full_name,
    )

    # Guardar en DB
    session = SessionLocal()
    try:
        # Buscar el lead
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            logger.error(f"Creator {creator_id} not found")
            return pending

        # ── DEDUP CHECK #1: platform_message_id already in DB ──
        # Prevents duplicates from webhook retries (Meta/Telegram resend)
        if user_message_id:
            existing_user_msg = (
                session.query(Message.id)
                .filter(Message.platform_message_id == user_message_id)
                .first()
            )
            if existing_user_msg:
                logger.info(
                    f"[Copilot:Dedup] user_message_id {user_message_id} already in DB — skipping"
                )
                return pending

        # ── CHECK: non-text messages (media, attachments) ──
        # Don't generate copilot suggestions for media the bot can't understand
        if is_non_text_message(user_message):
            logger.info(
                f"[Copilot:Skip] Non-text message detected: '{user_message[:50]}' — skipping suggestion"
            )
            return pending

        # Check both with and without ig_ prefix to avoid duplicates
        lead = (
            session.query(Lead)
            .filter(
                Lead.creator_id == creator.id,
                Lead.platform_user_id.in_([follower_id, f"ig_{follower_id}"]),
            )
            .first()
        )

        if not lead:
            # Crear lead si no existe
            # Extract phone number for WhatsApp leads
            phone_number = None
            if platform == "whatsapp" and follower_id.startswith("wa_"):
                phone_number = "+" + follower_id[3:]  # wa_34639066982 → +34639066982

            lead = Lead(
                creator_id=creator.id,
                platform=platform,
                platform_user_id=follower_id,
                username=username,
                full_name=full_name,
                phone=phone_number,
                source=f"{platform}_dm",
                status="new",
                purchase_intent=0.0,
            )
            session.add(lead)
            session.commit()
            pending.lead_id = str(lead.id)
        elif platform == "whatsapp" and not lead.phone and follower_id.startswith("wa_"):
            # Backfill phone for existing WhatsApp leads that are missing it
            lead.phone = "+" + follower_id[3:]

        # ── CHECK: creator already replied to this lead recently ──
        # If creator sent a manual response in the last 2 hours, skip suggestion
        two_hours_ago = now - timedelta(hours=2)
        if service.has_creator_reply_after(lead.id, two_hours_ago, session):
            logger.info(
                f"[Copilot:Skip] Creator already replied to lead {lead.id} — skipping suggestion"
            )
            # Still save the user message
            user_msg = Message(
                lead_id=lead.id,
                role="user",
                content=user_message,
                intent=intent,
                status="sent",
                platform_message_id=user_message_id,
                msg_metadata=msg_metadata,
            )
            session.add(user_msg)
            lead.last_contact_at = now
            session.commit()
            pending.lead_id = str(lead.id)
            return pending

        # ── DEDUP CHECK #2: lead already has pending_approval ──
        # Prevents multiple suggestions stacking up for the same lead
        existing_pending = (
            session.query(Message)
            .filter(
                Message.lead_id == lead.id,
                Message.role == "assistant",
                Message.status == "pending_approval",
            )
            .first()
        )
        if existing_pending:
            logger.info(
                f"[Copilot:Dedup] Lead {lead.id} already has pending suggestion "
                f"{existing_pending.id} — preserving existing, scheduling regen"
            )
            # Still save the user message so no messages are lost
            user_msg = Message(
                lead_id=lead.id,
                role="user",
                content=user_message,
                intent=intent,
                status="sent",
                platform_message_id=user_message_id,
                msg_metadata=msg_metadata,
            )
            session.add(user_msg)

            # DO NOT overwrite existing pending suggestion — preserve the
            # first (often best) response. Schedule a debounced regeneration
            # that will fire after DEBOUNCE_SECONDS of silence with full context.

            # Update lead scoring
            lead.last_contact_at = now
            try:
                from services.lead_scoring import recalculate_lead_score

                recalculate_lead_score(session, str(lead.id))
            except Exception as score_err:
                logger.warning(f"[Copilot] Scoring failed: {score_err}")

            session.commit()
            pending.id = str(existing_pending.id)
            pending.lead_id = str(lead.id)

            # Invalidate caches
            try:
                from api.cache import api_cache

                api_cache.invalidate(f"conversations:{creator_id}")
                api_cache.invalidate(f"follower_detail:{creator_id}:{follower_id}")
            except Exception as e:
                logger.debug(f"[COPILOT] cache invalidation failed: {e}")

            # Notify frontend
            try:
                from api.routers.events import notify_creator

                await notify_creator(
                    creator_id,
                    "new_message",
                    {"follower_id": follower_id, "role": "user"},
                )
            except Exception as e:
                logger.debug(f"[COPILOT] SSE notify failed: {e}")

            # Schedule debounced regeneration (cancels any previous timer)
            from core.copilot.messaging import schedule_debounced_regen_impl

            schedule_debounced_regen_impl(
                service,
                creator_id=creator_id,
                follower_id=follower_id,
                platform=platform,
                pending_message_id=str(existing_pending.id),
                lead_id=str(lead.id),
                username=username,
            )

            return pending

        # Update last contact time (must be set before scoring)
        lead.last_contact_at = now

        # Comprehensive lead scoring (considers message count, recency, etc.)
        try:
            from services.lead_scoring import recalculate_lead_score

            recalculate_lead_score(session, str(lead.id))
        except Exception as score_err:
            logger.warning(f"[Copilot] Scoring failed, using fallback: {score_err}")
            # Fallback to old intent-based scoring
            lead.purchase_intent = service._calculate_purchase_intent(
                current_intent=lead.purchase_intent or 0.0, message_intent=intent
            )
            lead.status = service._calculate_lead_status(lead.purchase_intent)

        # Guardar mensaje del usuario
        user_msg = Message(
            lead_id=lead.id,
            role="user",
            content=user_message,
            intent=intent,
            status="sent",
            platform_message_id=user_message_id,
            msg_metadata=msg_metadata,
        )
        session.add(user_msg)

        # Guardar respuesta sugerida como pendiente
        # Store best_of_n candidates on bot message for preference pair extraction
        bot_meta = {}
        if msg_metadata and msg_metadata.get("best_of_n"):
            bot_meta["best_of_n"] = msg_metadata["best_of_n"]
        bot_msg = Message(
            lead_id=lead.id,
            role="assistant",
            content=suggested_response,
            suggested_response=suggested_response,  # Guardar original
            status="pending_approval",
            intent=intent,
            confidence_score=confidence,
            msg_metadata=bot_meta if bot_meta else None,
        )
        session.add(bot_msg)
        session.commit()

        pending.id = str(bot_msg.id)
        pending.lead_id = str(lead.id)

        # Cache en memoria
        cache_key = f"{creator_id}:{pending.id}"
        service._pending_responses[cache_key] = pending

        # Invalidate conversation caches so new user message appears
        try:
            from api.cache import api_cache

            api_cache.invalidate(f"conversations:{creator_id}")
            api_cache.invalidate(f"follower_detail:{creator_id}:{follower_id}")
        except Exception as cache_err:
            logger.debug(f"[Copilot] Cache invalidation failed: {cache_err}")

        # Notify frontend via SSE
        try:
            from api.routers.events import notify_creator

            await notify_creator(
                creator_id,
                "new_message",
                {"follower_id": follower_id, "role": "user"},
            )
        except Exception as sse_err:
            logger.debug(f"[Copilot] SSE notification failed: {sse_err}")

        logger.info(f"[Copilot] Created pending response {pending.id} for {follower_id}")

    except Exception as e:
        logger.error(f"[Copilot] Error creating pending response: {e}")
        session.rollback()
    finally:
        session.close()

    return pending


async def get_pending_responses_impl(
    service, creator_id: str, limit: int = 20, offset: int = 0, include_context: bool = False
) -> Dict:
    """Obtener respuestas pendientes - OPTIMIZADO para velocidad"""
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    session = SessionLocal()
    try:
        # Get creator_id directly to avoid extra query
        creator = session.query(Creator.id).filter_by(name=creator_id).first()
        if not creator:
            return {"pending": [], "total_count": 0, "has_more": False}
        creator_db_id = creator[0]

        # OPTIMIZED: Select only needed columns, skip expensive count()
        # Using with_entities for faster query
        pending_messages = (
            session.query(
                Message.id,
                Message.content,
                Message.intent,
                Message.created_at,
                Message.status,
                Message.lead_id,
                Lead.platform_user_id,
                Lead.platform,
                Lead.username,
                Lead.full_name,
                Message.msg_metadata,
                Message.confidence_score,
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator_db_id,
                Message.status == "pending_approval",
                Message.role == "assistant",
            )
            .order_by(Message.created_at.desc())
            .offset(offset)
            .limit(limit + 1)  # Fetch one extra to check has_more
            .all()
        )

        # Check if there are more results
        has_more = len(pending_messages) > limit
        if has_more:
            pending_messages = pending_messages[:limit]

        # Get lead_ids for user message lookup
        lead_ids = list(set(row.lead_id for row in pending_messages))
        user_msg_lookup = {}
        if lead_ids:
            # Get only latest user message content per lead (select minimal columns)
            user_messages = (
                session.query(Message.lead_id, Message.content)
                .filter(Message.lead_id.in_(lead_ids), Message.role == "user")
                .order_by(Message.lead_id, Message.created_at.desc())
                .limit(limit * 10)
                .all()
            )
            seen_leads = set()
            for lead_id, content in user_messages:
                if lead_id not in seen_leads:
                    user_msg_lookup[str(lead_id)] = content
                    seen_leads.add(lead_id)

        # Build results from tuple rows (faster than ORM objects)
        results = []
        for row in pending_messages:
            item = {
                "id": str(row.id),
                "lead_id": str(row.lead_id),
                "follower_id": row.platform_user_id,
                "platform": row.platform,
                "username": row.username or "",
                "full_name": row.full_name or "",
                "user_message": user_msg_lookup.get(str(row.lead_id), ""),
                "suggested_response": row.content,
                "intent": row.intent or "",
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "status": row.status,
                "confidence": row.confidence_score,
            }
            # Extract best_of_n candidates
            bon = (row.msg_metadata or {}).get("best_of_n", {})
            if bon.get("candidates"):
                item["candidates"] = [
                    {"content": c["content"], "temperature": c["temperature"],
                     "confidence": c.get("confidence", 0), "rank": c.get("rank", 0)}
                    for c in bon["candidates"]
                ]
            if include_context:
                item["conversation_context"] = service._get_conversation_context(
                    session, row.lead_id
                )
            results.append(item)

        return {
            "pending": results,
            "total_count": len(results),  # Approximate count (skip expensive COUNT query)
            "has_more": has_more,
        }

    except Exception as e:
        logger.error(f"[Copilot] Error getting pending responses: {e}")
        return {"pending": [], "total_count": 0, "has_more": False}
    finally:
        session.close()
