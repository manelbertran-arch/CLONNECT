"""
Sync Worker - Sistema de cola inteligente para sincronización con Instagram API.

Características:
- Procesa 1 conversación cada N segundos (configurable)
- Pausa automática ante rate limits
- Guarda progreso después de cada job
- Continúa automáticamente sin intervención manual
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SyncConfig:
    """Configuración del sync worker."""

    delay_between_calls: int = 3  # Segundos entre cada llamada API
    rate_limit_pause: int = 300  # Segundos de pausa si rate limit (5 min)
    max_retries: int = 3  # Reintentos por conversación
    batch_size: int = 10  # Procesar N conversaciones, luego pausar
    batch_pause: int = 30  # Segundos de pausa entre batches


# Configuración global
SYNC_CONFIG = SyncConfig()

# Estado del worker
_worker_running = False
_worker_task = None


async def get_or_create_sync_state(session, creator_id: str):
    """Obtiene o crea el estado de sync para un creator."""
    from api.models import SyncState

    state = session.query(SyncState).filter_by(creator_id=creator_id).first()
    if not state:
        state = SyncState(creator_id=creator_id, status="idle")
        session.add(state)
        session.commit()
    return state


async def add_conversations_to_queue(session, creator_id: str, conversations: List[Dict]) -> int:
    """Añade conversaciones a la cola de sync."""
    from api.models import SyncQueue

    added = 0
    for conv in conversations:
        conv_id = conv.get("id")
        if not conv_id:
            continue

        # Verificar si ya existe
        existing = (
            session.query(SyncQueue)
            .filter_by(creator_id=creator_id, conversation_id=conv_id)
            .first()
        )

        if not existing:
            job = SyncQueue(creator_id=creator_id, conversation_id=conv_id, status="pending")
            session.add(job)
            added += 1
        elif existing.status == "failed" and existing.attempts < SYNC_CONFIG.max_retries:
            # Reintentar jobs fallidos
            existing.status = "pending"
            added += 1

    session.commit()
    return added


async def get_next_pending_job(session, creator_id: Optional[str] = None):
    """Obtiene el siguiente job pendiente de la cola."""
    from api.models import SyncQueue

    query = session.query(SyncQueue).filter_by(status="pending")
    if creator_id:
        query = query.filter_by(creator_id=creator_id)

    return query.order_by(SyncQueue.created_at).first()


async def process_single_conversation(
    session, job, creator, access_token: str, creator_ids: set
) -> Dict[str, Any]:
    """
    Procesa una única conversación.
    Returns dict con resultado.

    Args:
        creator_ids: Set of creator's Instagram IDs (both page_id and user_id)
                    to correctly identify messages from the creator
    """
    from datetime import datetime

    import httpx
    from api.models import Lead, Message

    result = {"success": False, "messages_saved": 0, "lead_created": False, "error": None}

    # Elegir API según si tenemos page_id o no
    # Facebook API requiere page_id, Instagram API usa ig_user_id
    if creator.instagram_page_id:
        api_base = "https://graph.facebook.com/v21.0"
    else:
        api_base = "https://graph.instagram.com/v21.0"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch messages for this conversation
            msg_resp = await client.get(
                f"{api_base}/{job.conversation_id}/messages",
                params={
                    "fields": "id,message,from,to,created_time",
                    "access_token": access_token,
                    "limit": 50,
                },
            )

            if msg_resp.status_code != 200:
                error_data = msg_resp.json().get("error", {})
                error_code = error_data.get("code")

                # Check for rate limit
                if error_code in [4, 17] or error_data.get("error_subcode") == 1349210:
                    raise RateLimitError(error_data.get("message", "Rate limit"))

                result["error"] = f"API error: {error_data.get('message', 'Unknown')}"
                return result

            messages = msg_resp.json().get("data", [])
            if not messages:
                result["success"] = True
                return result

            # Find the follower (non-creator participant)
            follower_id = None
            follower_username = None
            follower_full_name = None

            for msg in messages:
                from_data = msg.get("from", {})
                from_id = from_data.get("id")
                # Follower is someone whose ID is NOT in creator_ids
                if from_id and from_id not in creator_ids:
                    follower_id = from_id
                    follower_username = from_data.get("username", "unknown")
                    follower_full_name = from_data.get("name", "")  # Display name from Meta API
                    break

            if not follower_id:
                for msg in messages:
                    to_data = msg.get("to", {}).get("data", [])
                    for recipient in to_data:
                        if recipient.get("id") not in creator_ids:
                            follower_id = recipient.get("id")
                            follower_username = recipient.get("username", "unknown")
                            follower_full_name = recipient.get("name", "")
                            break
                    if follower_id:
                        break

            if not follower_id:
                result["success"] = True
                return result

            # Parse timestamps - separar mensajes de usuario vs creator
            all_msg_timestamps = []
            user_msg_timestamps = []

            for msg in messages:
                if msg.get("created_time"):
                    try:
                        ts = datetime.fromisoformat(msg["created_time"].replace("+0000", "+00:00"))
                        all_msg_timestamps.append(ts)

                        # Solo contar mensajes del follower (no del creator)
                        from_id = msg.get("from", {}).get("id")
                        if from_id and from_id not in creator_ids:
                            user_msg_timestamps.append(ts)
                    except ValueError as e:
                        logger.warning("Failed to parse message timestamp: %s", e)

            first_msg_time = min(all_msg_timestamps) if all_msg_timestamps else None
            # IMPORTANTE: last_contact_at debe ser el último mensaje del USUARIO
            # para que FANTASMA funcione correctamente
            last_user_msg_time = max(user_msg_timestamps) if user_msg_timestamps else None

            # Get or create lead - check both with and without ig_ prefix to avoid duplicates
            lead = (
                session.query(Lead)
                .filter(
                    Lead.creator_id == creator.id,
                    Lead.platform == "instagram",
                    Lead.platform_user_id.in_([follower_id, f"ig_{follower_id}"]),
                )
                .first()
            )

            if not lead:
                lead = Lead(
                    creator_id=creator.id,
                    platform="instagram",
                    platform_user_id=follower_id,
                    username=follower_username,
                    full_name=follower_full_name or None,
                    status="new",
                    first_contact_at=first_msg_time,
                    # IMPORTANTE: usar último mensaje del USUARIO para fantasma
                    last_contact_at=last_user_msg_time or first_msg_time,
                )
                session.add(lead)
                session.commit()
                result["lead_created"] = True
            else:
                # Update timestamps
                if first_msg_time and (
                    not lead.first_contact_at or first_msg_time < lead.first_contact_at
                ):
                    lead.first_contact_at = first_msg_time
                # IMPORTANTE: solo actualizar si hay mensaje del USUARIO más reciente
                if last_user_msg_time and (
                    not lead.last_contact_at or last_user_msg_time > lead.last_contact_at
                ):
                    lead.last_contact_at = last_user_msg_time
                # Update full_name if missing
                if follower_full_name and not lead.full_name:
                    lead.full_name = follower_full_name

            # Save messages
            for msg in messages:
                msg_id = msg.get("id")
                msg_text = msg.get("message", "")

                if not msg_text or not msg_id:
                    continue

                existing = session.query(Message).filter_by(platform_message_id=msg_id).first()

                if existing:
                    continue

                from_data = msg.get("from", {})
                # Check if sender is the creator (could be user_id OR page_id)
                is_from_creator = from_data.get("id") in creator_ids
                role = "assistant" if is_from_creator else "user"

                new_msg = Message(
                    lead_id=lead.id, role=role, content=msg_text, platform_message_id=msg_id
                )

                msg_time = msg.get("created_time")
                if msg_time:
                    try:
                        new_msg.created_at = datetime.fromisoformat(
                            msg_time.replace("+0000", "+00:00")
                        )
                    except ValueError as e:
                        logger.warning("Failed to parse message created_at: %s", e)

                session.add(new_msg)
                result["messages_saved"] += 1

            session.commit()

            # Auto-categorizar lead después de guardar mensajes
            if result["messages_saved"] > 0:
                try:
                    from core.lead_categorization import (
                        calcular_categoria,
                        categoria_a_status_legacy,
                    )

                    # Obtener mensajes del lead para categorización
                    lead_messages = (
                        session.query(Message)
                        .filter_by(lead_id=lead.id)
                        .order_by(Message.created_at)
                        .all()
                    )
                    mensajes_para_cat = [
                        {"role": m.role, "content": m.content or ""} for m in lead_messages
                    ]

                    # Calcular categoría
                    cat_result = calcular_categoria(
                        mensajes=mensajes_para_cat,
                        es_cliente=lead.status == "customer",
                        ultimo_mensaje_lead=lead.last_contact_at,
                        lead_created_at=lead.first_contact_at,
                    )

                    # Actualizar lead
                    new_status = categoria_a_status_legacy(cat_result.categoria)
                    if lead.status != new_status:
                        lead.status = new_status
                        lead.purchase_intent = cat_result.intent_score
                        session.commit()
                        logger.info(
                            f"Lead {lead.username} auto-categorizado: {cat_result.categoria} (intent: {cat_result.intent_score:.2f})"
                        )

                except Exception as cat_error:
                    logger.warning(f"Error en auto-categorización: {cat_error}")

            result["success"] = True
            return result

    except RateLimitError:
        raise
    except Exception as e:
        result["error"] = str(e)
        return result


class RateLimitError(Exception):
    """Error cuando Instagram API devuelve rate limit."""



async def run_sync_worker_iteration(session, creator_id: str) -> Dict[str, Any]:
    """
    Ejecuta una iteración del worker para un creator específico.
    Procesa jobs hasta completar o hit rate limit.
    """
    from api.models import Creator

    result = {
        "jobs_processed": 0,
        "messages_saved": 0,
        "leads_created": 0,
        "rate_limited": False,
        "completed": False,
        "error": None,
    }

    # Get sync state
    state = await get_or_create_sync_state(session, creator_id)

    # Check rate limit
    if state.rate_limit_until:
        if datetime.now(timezone.utc) < state.rate_limit_until.replace(tzinfo=timezone.utc):
            result["rate_limited"] = True
            return result
        else:
            # Rate limit expired, clear it
            state.rate_limit_until = None
            state.status = "running"
            session.commit()

    # Get creator info
    creator = session.query(Creator).filter_by(name=creator_id).first()
    if not creator or not creator.instagram_token:
        result["error"] = "Creator or token not found"
        return result

    # IMPORTANT: Instagram has TWO IDs for the same account:
    # - page_id: appears in message from.id
    # - user_id: used for API calls
    # We need both to correctly identify creator's messages
    ig_user_id = creator.instagram_user_id or creator.instagram_page_id
    ig_page_id = creator.instagram_page_id
    creator_ids = {ig_user_id, ig_page_id} - {None}  # Set of all creator IDs
    access_token = creator.instagram_token

    # Process jobs in batches
    jobs_in_batch = 0

    while True:
        # Get next job
        job = await get_next_pending_job(session, creator_id)

        if not job:
            # No more jobs
            state.status = "completed"
            state.last_sync_at = datetime.now(timezone.utc)
            session.commit()
            result["completed"] = True
            break

        # Mark as processing
        job.status = "processing"
        job.attempts += 1
        state.current_conversation = job.conversation_id
        session.commit()

        try:
            # Process the conversation
            conv_result = await process_single_conversation(
                session, job, creator, access_token, creator_ids
            )

            if conv_result["success"]:
                job.status = "done"
                job.processed_at = datetime.now(timezone.utc)
                state.conversations_synced += 1
                state.messages_saved += conv_result["messages_saved"]
                result["messages_saved"] += conv_result["messages_saved"]
                if conv_result["lead_created"]:
                    result["leads_created"] += 1
            else:
                if job.attempts >= SYNC_CONFIG.max_retries:
                    job.status = "failed"
                    job.last_error = conv_result["error"]
                    state.error_count += 1
                else:
                    job.status = "pending"  # Retry later
                    job.last_error = conv_result["error"]

            result["jobs_processed"] += 1
            session.commit()

        except RateLimitError as e:
            # Rate limit hit - pause this creator
            job.status = "pending"
            job.attempts -= 1  # Don't count rate limit as attempt
            state.status = "rate_limited"
            state.rate_limit_until = datetime.now(timezone.utc) + timedelta(
                seconds=SYNC_CONFIG.rate_limit_pause
            )
            state.last_error = str(e)
            session.commit()

            logger.warning(
                f"[SyncWorker] Rate limit for {creator_id}, pausing {SYNC_CONFIG.rate_limit_pause}s"
            )
            result["rate_limited"] = True
            break

        except Exception as e:
            job.status = "failed"
            job.last_error = str(e)
            state.error_count += 1
            session.commit()
            logger.error(f"[SyncWorker] Error processing job {job.id}: {e}")

        # Throttle between calls
        await asyncio.sleep(SYNC_CONFIG.delay_between_calls)

        # Batch pause
        jobs_in_batch += 1
        if jobs_in_batch >= SYNC_CONFIG.batch_size:
            logger.info(f"[SyncWorker] Batch complete, pausing {SYNC_CONFIG.batch_pause}s")
            await asyncio.sleep(SYNC_CONFIG.batch_pause)
            jobs_in_batch = 0

    return result


async def start_sync_for_creator(creator_id: str) -> Dict[str, Any]:
    """
    Inicia el proceso de sync para un creator.
    1. Obtiene lista de conversaciones
    2. Añade a la cola
    3. Inicia el procesamiento

    Returns inmediatamente (no-bloqueante).
    """
    import httpx
    from api.database import SessionLocal
    from api.models import Creator

    result = {"status": "error", "conversations_queued": 0, "message": ""}

    session = SessionLocal()
    try:
        # Check rate limit
        state = await get_or_create_sync_state(session, creator_id)

        if state.rate_limit_until:
            if datetime.now(timezone.utc) < state.rate_limit_until.replace(tzinfo=timezone.utc):
                minutes_left = int(
                    (
                        state.rate_limit_until.replace(tzinfo=timezone.utc)
                        - datetime.now(timezone.utc)
                    ).total_seconds()
                    / 60
                )
                result["status"] = "rate_limited"
                result["message"] = f"Rate limited. Retry in {minutes_left} minutes."
                return result

        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator or not creator.instagram_token:
            result["message"] = "Creator or token not found"
            return result

        ig_user_id = creator.instagram_user_id or creator.instagram_page_id
        page_id = creator.instagram_page_id
        access_token = creator.instagram_token

        # Fetch conversation list (single API call)
        # Estrategia dual: usar page_id con Facebook API si existe,
        # sino usar ig_user_id con Instagram API
        async with httpx.AsyncClient(timeout=30.0) as client:
            if page_id:
                # Facebook Pages API - requiere page_id
                api_base = "https://graph.facebook.com/v21.0"
                conv_resp = await client.get(
                    f"{api_base}/{page_id}/conversations",
                    params={
                        "platform": "instagram",
                        "access_token": access_token,
                        "limit": 50,
                        "fields": "id,updated_time",
                    },
                )
            else:
                # Instagram API - usa ig_user_id directamente
                api_base = "https://graph.instagram.com/v21.0"
                conv_resp = await client.get(
                    f"{api_base}/{ig_user_id}/conversations",
                    params={"access_token": access_token, "limit": 50, "fields": "id,updated_time"},
                )

            if conv_resp.status_code != 200:
                error_data = conv_resp.json().get("error", {})

                if error_data.get("code") in [4, 17]:
                    state.status = "rate_limited"
                    state.rate_limit_until = datetime.now(timezone.utc) + timedelta(
                        seconds=SYNC_CONFIG.rate_limit_pause
                    )
                    session.commit()
                    result["status"] = "rate_limited"
                    result["message"] = "Rate limited fetching conversations"
                    return result

                result["message"] = f"API error: {error_data.get('message', 'Unknown')}"
                return result

            conversations = conv_resp.json().get("data", [])

        # Add to queue
        added = await add_conversations_to_queue(session, creator_id, conversations)

        # Update state
        state.status = "running"
        state.conversations_total = len(conversations)
        state.conversations_synced = 0
        state.messages_saved = 0
        state.error_count = 0
        session.commit()

        result["status"] = "started"
        result["conversations_queued"] = added
        result["message"] = f"Queued {added} conversations. Check /sync-status for progress."

        return result

    except Exception as e:
        logger.error(f"[SyncWorker] Error starting sync: {e}")
        result["message"] = str(e)
        return result

    finally:
        session.close()


def get_sync_status(creator_id: str) -> Dict[str, Any]:
    """Obtiene el estado actual del sync para un creator."""
    from api.database import SessionLocal
    from api.models import SyncQueue, SyncState

    session = SessionLocal()
    try:
        state = session.query(SyncState).filter_by(creator_id=creator_id).first()

        if not state:
            return {
                "status": "not_started",
                "progress": "0/0",
                "message": "No sync started for this creator",
            }

        # Count pending jobs
        pending = (
            session.query(SyncQueue).filter_by(creator_id=creator_id, status="pending").count()
        )

        failed = session.query(SyncQueue).filter_by(creator_id=creator_id, status="failed").count()

        # Calculate progress
        total = state.conversations_total or 0
        synced = state.conversations_synced or 0
        progress_pct = int((synced / total * 100)) if total > 0 else 0

        result = {
            "status": state.status,
            "progress": f"{synced}/{total}",
            "progress_percent": progress_pct,
            "pending_jobs": pending,
            "failed_jobs": failed,
            "messages_saved": state.messages_saved or 0,
            "error_count": state.error_count or 0,
            "current_conversation": state.current_conversation,
            "last_sync": state.last_sync_at.isoformat() if state.last_sync_at else None,
            "last_error": state.last_error,
        }

        if state.rate_limit_until:
            if datetime.now(timezone.utc) < state.rate_limit_until.replace(tzinfo=timezone.utc):
                seconds_left = int(
                    (
                        state.rate_limit_until.replace(tzinfo=timezone.utc)
                        - datetime.now(timezone.utc)
                    ).total_seconds()
                )
                result["rate_limit_seconds"] = seconds_left
                result["rate_limit_until"] = state.rate_limit_until.isoformat()

        return result

    finally:
        session.close()
