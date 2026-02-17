"""
Copilot Service - Modo de aprobación de respuestas del bot.

Este servicio maneja:
1. Guardar respuestas sugeridas como "pending_approval"
2. Aprobar/Editar/Descartar respuestas
3. Enviar mensajes aprobados via Instagram/Telegram
4. Notificar al creador de mensajes pendientes
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


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
                lead = Lead(
                    creator_id=creator.id,
                    platform=platform,
                    platform_user_id=follower_id,
                    username=username,
                    full_name=full_name,
                    status="new",
                    purchase_intent=0.0,
                )
                session.add(lead)
                session.commit()
                pending.lead_id = str(lead.id)

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

    async def get_pending_responses(
        self, creator_id: str, limit: int = 20, offset: int = 0
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
            # Tuple: (id, content, intent, created_at, status, lead_id, platform_user_id, platform, username, full_name)
            results = []
            for row in pending_messages:
                results.append(
                    {
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
                )

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

            # Enviar mensaje
            send_result = await self._send_message(creator=creator, lead=lead, text=final_text)

            if not send_result.get("success"):
                return {"success": False, "error": send_result.get("error", "Failed to send")}

            # Actualizar mensaje en DB
            msg.content = final_text
            msg.status = "edited" if was_edited else "sent"
            msg.approved_at = datetime.now(timezone.utc)
            msg.approved_by = "creator"
            msg.platform_message_id = send_result.get("message_id")

            # Actualizar last_contact del lead
            lead.last_contact_at = datetime.now(timezone.utc)

            session.commit()

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

    async def discard_response(self, creator_id: str, message_id: str) -> Dict[str, Any]:
        """Descartar una respuesta sin enviarla"""
        from api.database import SessionLocal
        from api.models import Message

        session = SessionLocal()
        try:
            msg = session.query(Message).filter_by(id=message_id).first()
            if not msg:
                return {"success": False, "error": "Message not found"}

            msg.status = "discarded"
            msg.approved_at = datetime.now(timezone.utc)
            msg.approved_by = "creator"
            session.commit()

            logger.info(f"[Copilot] Discarded message {message_id}")
            return {"success": True, "message_id": str(msg.id)}

        except Exception as e:
            logger.error(f"[Copilot] Error discarding response: {e}")
            session.rollback()
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    async def _send_message(self, creator, lead, text: str) -> Dict[str, Any]:
        """Enviar mensaje via la plataforma correspondiente"""
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
                result = await send_evolution_message(evo_instance, recipient, text)
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
