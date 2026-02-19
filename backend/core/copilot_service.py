"""
Copilot Service - Modo de aprobación de respuestas del bot.

Este servicio maneja:
1. Guardar respuestas sugeridas como "pending_approval"
2. Aprobar/Editar/Descartar respuestas
3. Enviar mensajes aprobados via Instagram/Telegram
4. Notificar al creador de mensajes pendientes
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Media detection patterns — these are not real text and should not get copilot suggestions
_MEDIA_HASH_PATTERN = re.compile(r"^[A-Za-z0-9+/=]{15,}$")
_ATTACHMENT_PLACEHOLDERS = {
    "sent an attachment",
    "[media]",
    "[imagen]",
    "[video]",
    "[audio]",
    "[sticker]",
    "[file]",
    "[gif]",
    "[document]",
    "[contact]",
    "[location]",
}


def is_non_text_message(content: str) -> bool:
    """Detect media keys, attachment placeholders, and non-text content."""
    if not content or not content.strip():
        return True

    stripped = content.strip()

    # Evolution API media keys (hash-like strings without spaces)
    if _MEDIA_HASH_PATTERN.match(stripped):
        return True

    # Attachment placeholders from Instagram/WhatsApp
    if stripped.lower() in _ATTACHMENT_PLACEHOLDERS:
        return True

    # "Sent a photo/video/reel" from IG handler
    if stripped.lower().startswith("sent a "):
        return True

    # "Shared a post/reel" from IG handler
    if stripped.lower().startswith("shared a "):
        return True

    return False


@dataclass
class PendingResponse:
    """Respuesta pendiente de aprobación"""

    id: str
    lead_id: str
    follower_id: str
    platform: str  # instagram, telegram
    user_message: str
    user_message_id: str
    suggested_response: str
    intent: str
    confidence: float
    created_at: str
    username: str = ""
    full_name: str = ""


class CopilotService:
    """Servicio para manejar el modo Copilot"""

    _MAX_CACHE_ENTRIES = 500  # Prevent unbounded growth
    _CACHE_EVICTION_TTL = 3600  # Evict entries older than 1 hour

    def __init__(self):
        self._pending_responses: Dict[str, PendingResponse] = {}  # In-memory cache
        self._copilot_mode_cache: Dict[str, bool] = (
            {}
        )  # FIX P1: Cache copilot mode to avoid duplicate DB queries
        self._copilot_mode_cache_ttl: Dict[str, float] = {}  # Cache timestamps
        self._CACHE_TTL = 60  # 60 second cache

    def _calculate_purchase_intent(self, current_intent: float, message_intent: str) -> float:
        """
        Calculate updated purchase intent based on message intent.
        Score thresholds: New (0-25%), Warm (25-50%), Hot (50-75%), Customer (75%+)
        """
        intent_scores = {
            "interest_strong": 0.75,  # Hot
            "purchase": 0.85,  # Very Hot
            "interest_soft": 0.50,  # Warm
            "question_product": 0.35,  # Active
            "greeting": 0.10,  # New
            "objection": -0.10,  # Decrease
            "other": 0.05,  # Slight increase
        }

        # DEFENSIVE: Ensure message_intent is a string
        if not isinstance(message_intent, str):
            message_intent = str(message_intent) if message_intent else "other"

        intent_key = message_intent.lower().replace("Intent.", "")
        score_change = intent_scores.get(intent_key, 0.05)

        if score_change < 0:
            # Decrease
            new_intent = max(0.0, current_intent + score_change)
        else:
            # Increase - take the max between current and new
            new_intent = max(current_intent, score_change)

        return min(1.0, new_intent)

    def _calculate_lead_status(self, purchase_intent: float) -> str:
        """Calculate lead status based on purchase intent score."""
        if purchase_intent >= 0.75:
            return "hot"
        elif purchase_intent >= 0.35:
            return "active"
        elif purchase_intent >= 0.15:
            return "warm"
        return "new"

    def _calculate_edit_diff(self, original: str, edited: str) -> dict:
        """Calculate diff between original suggestion and creator's edit."""
        if not original or not edited:
            return {"length_delta": 0, "categories": []}

        categories = []
        length_delta = len(edited) - len(original)

        if length_delta < -10:
            categories.append("shortened")
        elif length_delta > 10:
            categories.append("lengthened")

        # Check if questions were removed
        orig_questions = original.count("?")
        edit_questions = edited.count("?")
        if orig_questions > edit_questions:
            categories.append("removed_question")

        # Check if emojis were removed
        import re
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF"
            "\U00002600-\U000027BF\U0001FA00-\U0001FA6F]+",
            flags=re.UNICODE,
        )
        orig_emojis = len(emoji_pattern.findall(original))
        edit_emojis = len(emoji_pattern.findall(edited))
        if orig_emojis > edit_emojis:
            categories.append("removed_emoji")
        elif edit_emojis > orig_emojis:
            categories.append("added_emoji")

        # Check for complete rewrite (low similarity)
        orig_words = set(original.lower().split())
        edit_words = set(edited.lower().split())
        if orig_words and edit_words:
            overlap = len(orig_words & edit_words) / max(len(orig_words), len(edit_words))
            if overlap < 0.3:
                categories.append("complete_rewrite")
            elif overlap < 0.6:
                categories.append("major_edit")

        return {
            "length_delta": length_delta,
            "original_length": len(original),
            "edited_length": len(edited),
            "categories": categories,
        }

    async def create_pending_response(
        self,
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
            from datetime import timedelta

            two_hours_ago = now - timedelta(hours=2)
            if self.has_creator_reply_after(lead.id, two_hours_ago, session):
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
                    f"{existing_pending.id} — saving user message only"
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

                # Update the existing pending suggestion with the new response
                # (so the creator sees the latest suggestion for the latest message)
                existing_pending.content = suggested_response
                existing_pending.suggested_response = suggested_response
                existing_pending.intent = intent
                existing_pending.created_at = now

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
                except Exception:
                    pass

                # Notify frontend
                try:
                    from api.routers.events import notify_creator

                    await notify_creator(
                        creator_id,
                        "new_message",
                        {"follower_id": follower_id, "role": "user"},
                    )
                except Exception:
                    pass

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
                lead.purchase_intent = self._calculate_purchase_intent(
                    current_intent=lead.purchase_intent or 0.0, message_intent=intent
                )
                lead.status = self._calculate_lead_status(lead.purchase_intent)

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
            bot_msg = Message(
                lead_id=lead.id,
                role="assistant",
                content=suggested_response,
                suggested_response=suggested_response,  # Guardar original
                status="pending_approval",
                intent=intent,
                confidence_score=confidence,
            )
            session.add(bot_msg)
            session.commit()

            pending.id = str(bot_msg.id)
            pending.lead_id = str(lead.id)

            # Cache en memoria
            cache_key = f"{creator_id}:{pending.id}"
            self._pending_responses[cache_key] = pending

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

    def _get_conversation_context(
        self, session, lead_id, max_messages: int = 15, before_timestamp=None
    ) -> list:
        """
        Get conversation context for a lead using session-based detection.

        A "session" is a group of messages separated by >24h gaps.
        Returns the last 2 sessions, up to max_messages total.
        Messages are returned in chronological order (oldest first).
        Adds session_break markers when gaps >24h are detected.

        Args:
            before_timestamp: If set, only include messages before this datetime.
        """
        from api.models import Message

        # Fetch recent messages (up to 50 to find session boundaries)
        query = session.query(Message.role, Message.content, Message.created_at).filter(
            Message.lead_id == lead_id,
            Message.status.in_(["sent", "edited", "pending_approval"]),
        )
        if before_timestamp:
            query = query.filter(Message.created_at < before_timestamp)

        recent = query.order_by(Message.created_at.desc()).limit(50).all()

        if not recent:
            return []

        # Detect session boundaries (gap >24h between consecutive messages)
        # Messages are in desc order, so we walk backwards in time
        sessions: list[list] = [[]]
        for i, msg in enumerate(recent):
            sessions[-1].append(msg)
            if i + 1 < len(recent):
                gap = (msg.created_at - recent[i + 1].created_at).total_seconds()
                if gap > 86400:  # >24h gap = new session boundary
                    if len(sessions) >= 2:
                        break  # We have 2 sessions, stop
                    sessions.append([])

        # Flatten last 2 sessions and reverse to chronological order
        context_msgs = []
        for s in reversed(sessions):
            context_msgs.extend(reversed(s))

        # Trim to max_messages (keep most recent)
        if len(context_msgs) > max_messages:
            context_msgs = context_msgs[-max_messages:]

        # Build output with session break markers
        result = []
        for i, msg in enumerate(context_msgs):
            item = {
                "role": msg.role,
                "content": msg.content or "",
                "timestamp": msg.created_at.isoformat() if msg.created_at else "",
            }
            # Detect session breaks: gap >24h from previous message
            if i > 0 and msg.created_at and context_msgs[i - 1].created_at:
                gap = (msg.created_at - context_msgs[i - 1].created_at).total_seconds()
                if gap > 86400:
                    item["session_break"] = True
                    item["session_label"] = msg.created_at.isoformat()
            result.append(item)

        return result

    async def get_pending_responses(
        self, creator_id: str, limit: int = 20, offset: int = 0, include_context: bool = False
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
                }
                if include_context:
                    item["conversation_context"] = self._get_conversation_context(
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

    async def approve_response(
        self, creator_id: str, message_id: str, edited_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Aprobar (y opcionalmente editar) una respuesta y enviarla.

        Returns:
            Dict con status y detalles del envío
        """
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"success": False, "error": "Creator not found"}

            # Buscar el mensaje
            msg = session.query(Message).filter_by(id=message_id).first()
            if not msg:
                return {"success": False, "error": "Message not found"}

            if msg.status != "pending_approval":
                return {"success": False, "error": f"Message status is {msg.status}, not pending"}

            # Obtener lead
            lead = session.query(Lead).filter_by(id=msg.lead_id).first()
            if not lead:
                return {"success": False, "error": "Lead not found"}

            # Determinar texto final
            final_text = edited_text if edited_text else msg.content
            was_edited = edited_text is not None and edited_text != msg.suggested_response

            # Send message — pass copilot_action so guard knows this is approved
            send_result = await self._send_message(
                creator=creator, lead=lead, text=final_text,
                copilot_action="edited" if was_edited else "approved",
            )

            if not send_result.get("success"):
                return {"success": False, "error": send_result.get("error", "Failed to send")}

            # Actualizar mensaje en DB
            now = datetime.now(timezone.utc)
            msg.content = final_text
            msg.status = "edited" if was_edited else "sent"
            msg.approved_at = now
            msg.approved_by = "creator"
            msg.platform_message_id = send_result.get("message_id")

            # Copilot tracking (Phase 2)
            msg.copilot_action = "edited" if was_edited else "approved"
            if msg.created_at:
                delta = now - msg.created_at
                msg.response_time_ms = int(delta.total_seconds() * 1000)
            if was_edited and msg.suggested_response:
                msg.edit_diff = self._calculate_edit_diff(
                    msg.suggested_response, final_text
                )

            # Actualizar last_contact del lead
            lead.last_contact_at = now

            session.commit()

            # Autolearning hook: fire-and-forget rule extraction
            try:
                import asyncio as _aio
                from services.autolearning_analyzer import analyze_creator_action

                _aio.create_task(analyze_creator_action(
                    action="edited" if was_edited else "approved",
                    creator_id=creator_id,
                    creator_db_id=creator.id,
                    suggested_response=msg.suggested_response,
                    final_response=final_text if was_edited else None,
                    edit_diff=msg.edit_diff if was_edited else None,
                    intent=msg.intent,
                    lead_stage=lead.status,
                    relationship_type=getattr(lead, "relationship_type", None),
                    source_message_id=msg.id,
                ))
            except Exception as learn_err:
                logger.debug(f"[Copilot] Autolearning hook failed: {learn_err}")

            # Invalidate caches so approved message appears in conversation
            try:
                from api.cache import api_cache

                api_cache.invalidate(f"conversations:{creator_id}")
                api_cache.invalidate(f"follower_detail:{creator_id}:{lead.platform_user_id}")
            except Exception as cache_err:
                logger.debug(f"[Copilot] Cache invalidation failed: {cache_err}")

            # Notify frontend via SSE
            try:
                from api.routers.events import notify_creator

                await notify_creator(
                    creator_id,
                    "message_approved",
                    {
                        "follower_id": lead.platform_user_id,
                        "message_id": str(msg.id),
                    },
                )
            except Exception as sse_err:
                logger.debug(f"[Copilot] SSE notification failed: {sse_err}")

            # Update follower memory with the APPROVED response
            # (not saved during process_dm in copilot mode to prevent phantom context)
            try:
                from core.dm_agent_v2 import get_dm_agent

                agent = get_dm_agent(creator_id)
                follower = await agent.memory_store.get(
                    creator_id, lead.platform_user_id
                )
                if follower:
                    now_iso = datetime.now(timezone.utc).isoformat()
                    follower.last_messages.append(
                        {"role": "assistant", "content": final_text, "timestamp": now_iso}
                    )
                    follower.last_messages = follower.last_messages[-20:]
                    agent.memory_store._save_to_json(follower)
                    logger.debug(f"[Copilot] Updated memory for {lead.platform_user_id}")
            except Exception as mem_err:
                logger.debug(f"[Copilot] Memory update failed (non-blocking): {mem_err}")

            logger.info(
                f"[Copilot] Approved and sent message {message_id} to {lead.platform_user_id}"
            )

            return {
                "success": True,
                "message_id": str(msg.id),
                "platform_message_id": send_result.get("message_id"),
                "was_edited": was_edited,
                "final_text": final_text,
            }

        except Exception as e:
            logger.error(f"[Copilot] Error approving response: {e}")
            session.rollback()
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    async def discard_response(
        self, creator_id: str, message_id: str, discard_reason: str = None
    ) -> Dict[str, Any]:
        """Descartar una respuesta sin enviarla."""
        from api.database import SessionLocal
        from api.models import Message

        session = SessionLocal()
        try:
            msg = session.query(Message).filter_by(id=message_id).first()
            if not msg:
                return {"success": False, "error": "Message not found"}

            now = datetime.now(timezone.utc)
            msg.status = "discarded"
            msg.approved_at = now
            msg.approved_by = "creator"

            # Copilot tracking (Phase 2)
            msg.copilot_action = "discarded"
            if msg.created_at:
                delta = now - msg.created_at
                msg.response_time_ms = int(delta.total_seconds() * 1000)

            # A10: Persist discard_reason in msg_metadata (no migration needed)
            if discard_reason:
                meta = msg.msg_metadata or {}
                meta["discard_reason"] = discard_reason
                meta["discarded_at"] = now.isoformat()
                msg.msg_metadata = meta

            session.commit()

            # Autolearning hook: fire-and-forget rule extraction from discard
            try:
                import asyncio as _aio
                from services.autolearning_analyzer import analyze_creator_action

                # Look up creator for db_id
                from api.models import Creator as _Cr
                _creator = session.query(_Cr).filter_by(name=creator_id).first()
                if _creator:
                    _aio.create_task(analyze_creator_action(
                        action="discarded",
                        creator_id=creator_id,
                        creator_db_id=_creator.id,
                        suggested_response=msg.suggested_response,
                        discard_reason=discard_reason,
                        intent=msg.intent,
                        source_message_id=msg.id,
                    ))
            except Exception as learn_err:
                logger.debug(f"[Copilot] Autolearning discard hook failed: {learn_err}")

            logger.info(f"[Copilot] Discarded message {message_id} reason={discard_reason}")
            return {"success": True, "message_id": str(msg.id)}

        except Exception as e:
            logger.error(f"[Copilot] Error discarding response: {e}")
            session.rollback()
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    async def _send_message(self, creator, lead, text: str, copilot_action: str = None) -> Dict[str, Any]:
        """Send message via platform — GUARDED by send_guard."""
        from core.send_guard import SendBlocked, check_send_permission

        try:
            approved = copilot_action in ("approved", "edited")
            check_send_permission(creator.name, approved=approved, caller="copilot_service")
        except SendBlocked as e:
            return {"success": False, "error": str(e), "blocked": True}

        try:
            if lead.platform == "instagram":
                return await self._send_instagram_message(creator, lead, text)
            elif lead.platform == "telegram":
                return await self._send_telegram_message(creator, lead, text)
            elif lead.platform == "whatsapp":
                return await self._send_whatsapp_message(creator, lead, text)
            else:
                return {"success": False, "error": f"Unknown platform: {lead.platform}"}
        except Exception as e:
            logger.error(f"[Copilot] Error sending message: {e}")
            return {"success": False, "error": str(e)}

    async def _send_instagram_message(self, creator, lead, text: str) -> Dict[str, Any]:
        """Enviar mensaje via Instagram API"""
        import os

        from core.instagram import InstagramConnector

        # Use DB values with fallback to env vars (same as InstagramHandler)
        access_token = creator.instagram_token or os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        page_id = creator.instagram_page_id or os.getenv("INSTAGRAM_PAGE_ID", "")
        ig_user_id = creator.instagram_user_id or os.getenv("INSTAGRAM_USER_ID", "")

        # DEBUG: Log all values to identify 'auto' issue
        logger.info("[Copilot] _send_instagram_message DEBUG:")
        logger.info(f"[Copilot]   creator.name = {creator.name}")
        logger.info(f"[Copilot]   creator.instagram_page_id = {creator.instagram_page_id}")
        logger.info(f"[Copilot]   creator.instagram_user_id = {creator.instagram_user_id}")
        logger.info(f"[Copilot]   lead.platform_user_id = {lead.platform_user_id}")
        logger.info(f"[Copilot]   page_id (final) = {page_id}")
        logger.info(f"[Copilot]   ig_user_id (final) = {ig_user_id}")

        if not access_token or not page_id:
            return {"success": False, "error": "Instagram not connected"}

        # Validate page_id is not garbage value
        if page_id == "auto" or len(page_id) < 5:
            logger.error(
                f"[Copilot] Invalid page_id: '{page_id}' - creator may not have Instagram connected"
            )
            return {"success": False, "error": f"Invalid Instagram page_id: '{page_id}'"}

        connector = InstagramConnector(
            access_token=access_token, page_id=page_id, ig_user_id=ig_user_id
        )

        try:
            # Strip "ig_" prefix - platform_user_id format is "ig_123456" but API needs just "123456"
            recipient_id = lead.platform_user_id
            if recipient_id.startswith("ig_"):
                recipient_id = recipient_id[3:]  # Remove "ig_" prefix

            # Validate recipient_id is not garbage
            if recipient_id == "auto" or not recipient_id or len(recipient_id) < 5:
                logger.error(f"[Copilot] Invalid recipient_id: '{recipient_id}'")
                return {"success": False, "error": f"Invalid recipient_id: '{recipient_id}'"}

            logger.info(f"[Copilot] Sending Instagram message to {recipient_id} via connector")
            result = await connector.send_message(recipient_id=recipient_id, text=text)
            logger.info(f"[Copilot] Instagram API response: {result}")

            if "error" in result:
                # Instagram API returns error as dict: {"message": "...", "code": X}
                error_info = result["error"]
                if isinstance(error_info, dict):
                    error_msg = f"{error_info.get('message', 'Unknown error')} (code: {error_info.get('code', 'N/A')})"
                else:
                    error_msg = str(error_info)
                logger.error(f"[Copilot] Instagram send error: {error_msg}")
                return {"success": False, "error": error_msg}

            return {"success": True, "message_id": result.get("message_id", "")}
        finally:
            await connector.close()

    async def _send_telegram_message(self, creator, lead, text: str) -> Dict[str, Any]:
        """Enviar mensaje via Telegram API"""
        import httpx
        from core.telegram_registry import get_telegram_registry

        # Try registry first (bots.json), fallback to creator.telegram_bot_token
        registry = get_telegram_registry()
        bot_token = registry.get_token_for_creator(creator.name)

        if not bot_token:
            # Fallback to creator table
            bot_token = creator.telegram_bot_token

        if not bot_token:
            return {"success": False, "error": "Telegram not connected"}

        # Extract chat_id from follower_id (format: tg_123456)
        chat_id = lead.platform_user_id.replace("tg_", "")

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json={"chat_id": chat_id, "text": text})
            result = response.json()

            if not result.get("ok"):
                return {"success": False, "error": result.get("description", "Failed")}

            return {
                "success": True,
                "message_id": str(result.get("result", {}).get("message_id", "")),
            }

    async def _send_whatsapp_message(self, creator, lead, text: str) -> Dict[str, Any]:
        """Enviar mensaje via Evolution API (Baileys) or WhatsApp Cloud API fallback."""
        import os

        # Extract phone number from follower_id (format: wa_34612345678)
        recipient = lead.platform_user_id
        if recipient.startswith("wa_"):
            recipient = recipient[3:]

        if not recipient or len(recipient) < 5:
            return {"success": False, "error": f"Invalid WhatsApp recipient: '{recipient}'"}

        # Try Evolution API first (Baileys)
        try:
            from api.routers.messaging_webhooks import EVOLUTION_INSTANCE_MAP
            from services.evolution_api import send_evolution_message

            evo_instance = None
            for inst_name, cid in EVOLUTION_INSTANCE_MAP.items():
                if cid == creator.name:
                    evo_instance = inst_name
                    break

            if evo_instance:
                logger.info(f"[Copilot] Sending WhatsApp via Evolution [{evo_instance}] to {recipient}")
                result = await send_evolution_message(evo_instance, recipient, text, approved=True)
                msg_id = result.get("key", {}).get("id", "")
                logger.info(f"[Copilot] Evolution API response: {result}")
                return {"success": True, "message_id": msg_id}
        except Exception as evo_err:
            logger.warning(f"[Copilot] Evolution API send failed, trying Cloud API: {evo_err}")

        # Fallback to official WhatsApp Cloud API
        from core.whatsapp import WhatsAppConnector

        wa_token = creator.whatsapp_token or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        wa_phone_id = creator.whatsapp_phone_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

        if not wa_token or not wa_phone_id:
            return {"success": False, "error": "WhatsApp not connected (no Evolution instance or Cloud API)"}

        connector = WhatsAppConnector(
            phone_number_id=wa_phone_id,
            access_token=wa_token,
        )

        try:
            logger.info(f"[Copilot] Sending WhatsApp message to {recipient} via Cloud API")
            result = await connector.send_message(recipient, text)
            logger.info(f"[Copilot] WhatsApp API response: {result}")

            if "error" in result:
                error_info = result["error"]
                if isinstance(error_info, dict):
                    error_msg = f"{error_info.get('message', 'Unknown error')} (code: {error_info.get('code', 'N/A')})"
                else:
                    error_msg = str(error_info)
                logger.error(f"[Copilot] WhatsApp send error: {error_msg}")
                return {"success": False, "error": error_msg}

            msg_id = ""
            if "messages" in result and result["messages"]:
                msg_id = result["messages"][0].get("id", "")

            return {"success": True, "message_id": msg_id}
        finally:
            await connector.close()

    def _evict_stale_cache_entries(self, now: float):
        """Remove cache entries older than _CACHE_EVICTION_TTL and enforce max size."""
        if len(self._copilot_mode_cache) <= self._MAX_CACHE_ENTRIES:
            return
        # Evict entries older than eviction TTL
        stale_keys = [
            k for k, t in self._copilot_mode_cache_ttl.items()
            if now - t > self._CACHE_EVICTION_TTL
        ]
        for k in stale_keys:
            self._copilot_mode_cache.pop(k, None)
            self._copilot_mode_cache_ttl.pop(k, None)
        # If still over limit, evict oldest entries
        if len(self._copilot_mode_cache) > self._MAX_CACHE_ENTRIES:
            sorted_keys = sorted(self._copilot_mode_cache_ttl, key=self._copilot_mode_cache_ttl.get)
            excess = len(self._copilot_mode_cache) - self._MAX_CACHE_ENTRIES
            for k in sorted_keys[:excess]:
                self._copilot_mode_cache.pop(k, None)
                self._copilot_mode_cache_ttl.pop(k, None)

    def auto_discard_pending_for_lead(self, lead_id, session=None) -> int:
        """
        Auto-discard all pending_approval suggestions for a lead.

        Called when the creator manually replies (via phone/IG echo/WA fromMe),
        which means the bot suggestion is no longer needed.

        Returns count of discarded suggestions.
        """
        from api.models import Message

        close_session = False
        if session is None:
            from api.database import SessionLocal

            session = SessionLocal()
            close_session = True

        try:
            pending = (
                session.query(Message)
                .filter(
                    Message.lead_id == lead_id,
                    Message.role == "assistant",
                    Message.status == "pending_approval",
                )
                .all()
            )

            count = 0
            for msg in pending:
                msg.status = "discarded"
                msg.copilot_action = "manual_override"
                count += 1

            if count > 0:
                session.commit()
                logger.info(
                    f"[Copilot] Auto-discarded {count} pending suggestion(s) for lead {lead_id}"
                )

            return count
        except Exception as e:
            logger.error(f"[Copilot] Auto-discard error for lead {lead_id}: {e}")
            if close_session:
                session.rollback()
            return 0
        finally:
            if close_session:
                session.close()

    def has_creator_reply_after(self, lead_id, since_time, session=None) -> bool:
        """
        Check if the creator manually replied to a lead after a given time.

        Used to prevent generating copilot suggestions for messages the creator
        already answered.
        """
        from api.models import Message

        close_session = False
        if session is None:
            from api.database import SessionLocal

            session = SessionLocal()
            close_session = True

        try:
            reply = (
                session.query(Message.id)
                .filter(
                    Message.lead_id == lead_id,
                    Message.role == "assistant",
                    Message.approved_by == "creator_manual",
                    Message.created_at > since_time,
                )
                .first()
            )
            return reply is not None
        except Exception as e:
            logger.error(f"[Copilot] has_creator_reply check error: {e}")
            return False
        finally:
            if close_session:
                session.close()

    def is_copilot_enabled(self, creator_id: str) -> bool:
        """
        Verificar si el creador tiene modo Copilot activado.
        FIX P1: Uses cache to avoid duplicate DB queries (saves 0.3-0.5s per request).
        """
        import time

        # Check cache first
        now = time.time()
        if creator_id in self._copilot_mode_cache:
            cache_time = self._copilot_mode_cache_ttl.get(creator_id, 0)
            if now - cache_time < self._CACHE_TTL:
                return self._copilot_mode_cache[creator_id]

        # Cache miss - query DB
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator:
                result = getattr(creator, "copilot_mode", True)
                if result is None:
                    result = True  # Default to True if NULL
            else:
                result = True

            # Evict stale entries before adding new one
            self._evict_stale_cache_entries(now)

            # Update cache
            self._copilot_mode_cache[creator_id] = result
            self._copilot_mode_cache_ttl[creator_id] = now

            return result
        except Exception as e:
            logger.error(f"Error checking copilot mode: {e}")
            return True
        finally:
            session.close()

    def invalidate_copilot_cache(self, creator_id: str):
        """Invalidate cache when copilot mode is changed"""
        self._copilot_mode_cache.pop(creator_id, None)
        self._copilot_mode_cache_ttl.pop(creator_id, None)


# Singleton instance
_copilot_service: Optional[CopilotService] = None


def get_copilot_service() -> CopilotService:
    """Obtener instancia singleton del servicio Copilot"""
    global _copilot_service
    if _copilot_service is None:
        _copilot_service = CopilotService()
    return _copilot_service
