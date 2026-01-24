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
from typing import Any, Dict, List, Optional

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

            lead = (
                session.query(Lead)
                .filter_by(creator_id=creator.id, platform_user_id=follower_id)
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

            # Update lead scoring based on intent
            lead.purchase_intent = self._calculate_purchase_intent(
                current_intent=lead.purchase_intent or 0.0, message_intent=intent
            )
            lead.status = self._calculate_lead_status(lead.purchase_intent)
            lead.last_contact_at = now

            # Guardar mensaje del usuario
            user_msg = Message(
                lead_id=lead.id,
                role="user",
                content=user_message,
                intent=intent,
                status="sent",
                platform_message_id=user_message_id,
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

            logger.info(f"[Copilot] Created pending response {pending.id} for {follower_id}")

        except Exception as e:
            logger.error(f"[Copilot] Error creating pending response: {e}")
            session.rollback()
        finally:
            session.close()

        return pending

    async def get_pending_responses(
        self, creator_id: str, limit: int = 50, offset: int = 0
    ) -> Dict:
        """Obtener todas las respuestas pendientes de un creador con paginación"""
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"pending": [], "total_count": 0, "has_more": False}

            # Build base query
            base_query = (
                session.query(Message, Lead)
                .join(Lead, Message.lead_id == Lead.id)
                .filter(
                    Lead.creator_id == creator.id,
                    Message.status == "pending_approval",
                    Message.role == "assistant",
                )
            )

            # Get total count
            total_count = base_query.count()

            # Get paginated messages
            pending_messages = (
                base_query.order_by(Message.created_at.desc()).offset(offset).limit(limit).all()
            )

            results = []
            for msg, lead in pending_messages:
                # Obtener el mensaje del usuario más reciente
                user_msg = (
                    session.query(Message)
                    .filter(Message.lead_id == lead.id, Message.role == "user")
                    .order_by(Message.created_at.desc())
                    .first()
                )

                results.append(
                    {
                        "id": str(msg.id),
                        "lead_id": str(lead.id),
                        "follower_id": lead.platform_user_id,
                        "platform": lead.platform,
                        "username": lead.username or "",
                        "full_name": lead.full_name or "",
                        "user_message": user_msg.content if user_msg else "",
                        "suggested_response": msg.content,
                        "intent": msg.intent or "",
                        "created_at": msg.created_at.isoformat() if msg.created_at else "",
                        "status": msg.status,
                    }
                )

            return {
                "pending": results,
                "total_count": total_count,
                "has_more": offset + len(results) < total_count,
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

        if not access_token or not page_id:
            return {"success": False, "error": "Instagram not connected"}

        connector = InstagramConnector(
            access_token=access_token, page_id=page_id, ig_user_id=ig_user_id
        )

        try:
            result = await connector.send_message(recipient_id=lead.platform_user_id, text=text)

            if "error" in result:
                return {"success": False, "error": result["error"]}

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

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json={"chat_id": chat_id, "text": text})
            result = response.json()

            if not result.get("ok"):
                return {"success": False, "error": result.get("description", "Failed")}

            return {
                "success": True,
                "message_id": str(result.get("result", {}).get("message_id", "")),
            }

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
