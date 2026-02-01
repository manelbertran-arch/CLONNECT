"""
DM History Service - Carga historial de DMs desde Instagram.

Este servicio:
1. Obtiene conversaciones existentes via Meta Graph API
2. Crea leads por cada conversación
3. Calcula scoring inicial
4. Guarda historial de mensajes

FILTROS DE SEGURIDAD:
- max_age_days: Solo importa mensajes de los últimos X días (default: 90)
- Valida mensajes vacíos/whitespace antes de guardar
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Configuración por defecto
DEFAULT_MAX_AGE_DAYS = 90  # Solo mensajes de los últimos 90 días
DEFAULT_MIN_MESSAGE_LENGTH = 1  # Mínimo 1 carácter después de strip()


@dataclass
class ConversationSummary:
    """Resumen de una conversación importada"""
    follower_id: str
    username: str
    message_count: int
    last_message: str
    first_contact: str
    calculated_score: float
    status: str


class DMHistoryService:
    """Servicio para cargar historial de DMs"""

    async def load_dm_history(
        self,
        creator_id: str,
        access_token: str,
        page_id: str,
        ig_user_id: str,
        limit: int = 50,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS
    ) -> Dict[str, Any]:
        """
        Cargar historial de DMs desde Instagram.

        Args:
            creator_id: ID del creador
            access_token: Token de acceso de Meta
            page_id: ID de la página de Facebook
            ig_user_id: ID del usuario de Instagram
            limit: Máximo de conversaciones a cargar (default: 50)
            max_age_days: Solo importar mensajes de los últimos X días (default: 90)

        Returns:
            Dict con estadísticas de la importación
        """
        from core.instagram import InstagramConnector

        # Calcular fecha límite para filtrar mensajes
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        logger.info(f"[DMHistory] Loading DM history for {creator_id} (max_age: {max_age_days} days, cutoff: {cutoff_date.date()})")

        stats = {
            "conversations_found": 0,
            "leads_created": 0,
            "messages_imported": 0,
            "messages_filtered": 0,  # Mensajes filtrados por fecha/vacíos
            "max_age_days": max_age_days,
            "errors": []
        }

        try:
            connector = InstagramConnector(
                access_token=access_token,
                page_id=page_id,
                ig_user_id=ig_user_id
            )

            # Obtener conversaciones
            conversations = await connector.get_conversations(limit=limit)
            stats["conversations_found"] = len(conversations)
            logger.info(f"[DMHistory] Found {len(conversations)} conversations")

            for conv in conversations:
                try:
                    conv_id = conv.get("id")
                    if not conv_id:
                        continue

                    # Obtener mensajes de la conversación
                    messages = await connector.get_conversation_messages(conv_id, limit=50)

                    if not messages:
                        continue

                    # Extraer participant (el otro usuario, no el creador)
                    participant_id = None
                    participant_username = ""

                    for msg in messages:
                        from_data = msg.get("from", {})
                        from_id = from_data.get("id", "")

                        # El participant es quien NO es el page_id ni ig_user_id
                        if from_id and from_id != page_id and from_id != ig_user_id:
                            participant_id = from_id
                            participant_username = from_data.get("username", "")
                            break

                    if not participant_id:
                        # Intentar con to
                        for msg in messages:
                            to_data = msg.get("to", {}).get("data", [{}])[0]
                            to_id = to_data.get("id", "")
                            if to_id and to_id != page_id and to_id != ig_user_id:
                                participant_id = to_id
                                participant_username = to_data.get("username", "")
                                break

                    if not participant_id:
                        logger.warning(f"[DMHistory] Could not find participant in conv {conv_id}")
                        continue

                    # Intentar obtener perfil del usuario (username + display name)
                    participant_full_name = ""
                    try:
                        profile = await connector.get_user_profile(participant_id)
                        if profile:
                            if not participant_username:
                                participant_username = profile.username
                            # Extract display name (e.g., "Nahuel A. Sastre" instead of "ram_peris")
                            participant_full_name = profile.name or ""
                    except Exception as e:
                        logger.warning("Failed to get user profile for %s: %s", participant_id, e)

                    # Crear/actualizar lead y guardar mensajes
                    result = await self._import_conversation(
                        creator_id=creator_id,
                        follower_id=participant_id,
                        username=participant_username,
                        full_name=participant_full_name,
                        messages=messages,
                        page_id=page_id,
                        ig_user_id=ig_user_id,
                        cutoff_date=cutoff_date
                    )

                    if result.get("lead_created"):
                        stats["leads_created"] += 1
                    stats["messages_imported"] += result.get("messages_imported", 0)
                    stats["messages_filtered"] += result.get("messages_filtered", 0)

                except Exception as e:
                    error_msg = f"Error processing conversation: {e}"
                    logger.error(f"[DMHistory] {error_msg}")
                    stats["errors"].append(error_msg)

            await connector.close()

        except Exception as e:
            error_msg = f"Error loading DM history: {e}"
            logger.error(f"[DMHistory] {error_msg}")
            stats["errors"].append(error_msg)

        logger.info(f"[DMHistory] Import complete: {stats}")
        return stats

    async def _import_conversation(
        self,
        creator_id: str,
        follower_id: str,
        username: str,
        full_name: str,
        messages: List[Dict],
        page_id: str,
        ig_user_id: str,
        cutoff_date: datetime = None
    ) -> Dict[str, Any]:
        """
        Importar una conversación a la base de datos.

        Args:
            full_name: Display name from Instagram (e.g., "Nahuel A. Sastre")
            cutoff_date: Solo importar mensajes después de esta fecha
        """
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message
        from core.intent_classifier import classify_intent_simple

        session = SessionLocal()
        result = {"lead_created": False, "messages_imported": 0, "messages_filtered": 0}

        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return result

            # Verificar si el lead ya existe
            lead = session.query(Lead).filter_by(
                creator_id=creator.id,
                platform_user_id=follower_id
            ).first()

            if not lead:
                lead = Lead(
                    creator_id=creator.id,
                    platform="instagram",
                    platform_user_id=follower_id,
                    username=username,
                    full_name=full_name or None,
                    status="new"
                )
                session.add(lead)
                session.commit()
                result["lead_created"] = True
            elif full_name and not lead.full_name:
                # Update existing lead with display name if missing
                lead.full_name = full_name
                session.commit()

            # Procesar mensajes (del más antiguo al más reciente)
            messages_sorted = sorted(
                messages,
                key=lambda m: m.get("created_time", ""),
                reverse=False
            )

            purchase_signals = 0
            total_user_messages = 0

            for msg in messages_sorted:
                msg_id = msg.get("id", "")
                content = msg.get("message", "")
                from_id = msg.get("from", {}).get("id", "")
                created_time = msg.get("created_time", "")

                # =====================================================
                # VALIDACIÓN 1: Mensaje no vacío (GAP 2 FIX)
                # =====================================================
                if not content or not content.strip():
                    result["messages_filtered"] += 1
                    continue

                # Limpiar contenido
                content = content.strip()

                # Validar longitud mínima
                if len(content) < DEFAULT_MIN_MESSAGE_LENGTH:
                    result["messages_filtered"] += 1
                    continue

                # =====================================================
                # VALIDACIÓN 2: Filtro de fecha (GAP 1 FIX)
                # =====================================================
                msg_timestamp = None
                if created_time:
                    try:
                        msg_timestamp = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                    except ValueError as e:
                        logger.warning("Failed to parse message timestamp: %s", e)

                # Si tenemos cutoff_date y el mensaje es muy antiguo, saltarlo
                if cutoff_date and msg_timestamp and msg_timestamp < cutoff_date:
                    result["messages_filtered"] += 1
                    continue

                # Determinar rol
                is_from_creator = from_id in [page_id, ig_user_id]
                role = "assistant" if is_from_creator else "user"

                # Verificar si el mensaje ya existe
                existing = session.query(Message).filter_by(
                    lead_id=lead.id,
                    platform_message_id=msg_id
                ).first()

                if existing:
                    continue

                # Clasificar intent si es mensaje del usuario
                intent = None
                if role == "user":
                    total_user_messages += 1
                    intent = classify_intent_simple(content)

                    # Calcular señales de compra
                    if intent in ["interest_strong", "purchase"]:
                        purchase_signals += 3
                    elif intent in ["interest_soft", "question_product"]:
                        purchase_signals += 1
                    elif intent in ["objection"]:
                        purchase_signals -= 1

                # Usar timestamp ya parseado o parsear ahora
                created_at = msg_timestamp if msg_timestamp else datetime.now(timezone.utc)

                # Crear mensaje
                db_msg = Message(
                    lead_id=lead.id,
                    role=role,
                    content=content,
                    intent=intent,
                    status="sent",
                    platform_message_id=msg_id,
                    created_at=created_at
                )
                session.add(db_msg)
                result["messages_imported"] += 1

            # Calcular score inicial
            if total_user_messages > 0:
                raw_score = purchase_signals / max(total_user_messages, 1)
                purchase_intent = min(1.0, max(0.0, 0.25 + (raw_score * 0.5)))
            else:
                purchase_intent = 0.1

            # Actualizar lead
            lead.purchase_intent = purchase_intent

            # Determinar status basado en score
            if purchase_intent >= 0.6:
                lead.status = "hot"
            elif purchase_intent >= 0.35:
                lead.status = "active"
            else:
                lead.status = "new"

            # Actualizar timestamps
            if messages_sorted:
                first_msg_time = messages_sorted[0].get("created_time")
                last_msg_time = messages_sorted[-1].get("created_time")

                if first_msg_time:
                    try:
                        lead.first_contact_at = datetime.fromisoformat(first_msg_time.replace('Z', '+00:00'))
                    except ValueError as e:
                        logger.warning("Failed to parse first_contact_at: %s", e)

                if last_msg_time:
                    try:
                        lead.last_contact_at = datetime.fromisoformat(last_msg_time.replace('Z', '+00:00'))
                    except ValueError as e:
                        logger.warning("Failed to parse last_contact_at: %s", e)

            session.commit()
            logger.info(
                f"[DMHistory] Imported conversation with {follower_id}: "
                f"{result['messages_imported']} messages imported, "
                f"{result['messages_filtered']} filtered (old/empty), "
                f"score={purchase_intent:.2f}"
            )

        except Exception as e:
            logger.error(f"[DMHistory] Error importing conversation: {e}")
            session.rollback()
        finally:
            session.close()

        return result


# Singleton instance
_dm_history_service: Optional[DMHistoryService] = None


def get_dm_history_service() -> DMHistoryService:
    """Obtener instancia singleton del servicio"""
    global _dm_history_service
    if _dm_history_service is None:
        _dm_history_service = DMHistoryService()
    return _dm_history_service
