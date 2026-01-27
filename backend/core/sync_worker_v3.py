"""
Sync Worker V3 - Sistema de 2 fases para sincronización con Instagram API.

ARQUITECTURA DE 2 FASES:

FASE 1 - QUICK SYNC (durante onboarding, máx 3 min):
- Solo últimos 30 días
- Máximo 50 conversaciones
- Máximo 20 mensajes por conversación
- Timeout de 3 minutos
- El usuario espera esto, pero es RÁPIDO

FASE 2 - DEEP SYNC (background real, horas):
- TODAS las conversaciones (paginación completa)
- TODOS los mensajes
- Sin límite de tiempo
- Auto-recovery de rate limits
- Persistente (sobrevive restart del servidor)
- El usuario usa el dashboard mientras esto corre

FLUJO:
1. Usuario hace "Crear Clon"
2. Quick Sync (2-3 min) → Usuario va al dashboard
3. Deep Sync (background) → Completa TODO el historial
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURACIÓN
# =============================================================================


class SyncMode(Enum):
    QUICK = "quick"  # Onboarding: rápido, limitado
    DEEP = "deep"  # Background: completo, sin límites


@dataclass
class SyncConfig:
    """Configuración del sync"""

    mode: SyncMode = SyncMode.DEEP

    # Límites
    max_conversations: Optional[int] = None  # None = sin límite
    max_messages_per_conv: Optional[int] = None  # None = sin límite
    max_days: Optional[int] = None  # None = todo el historial

    # Timing
    delay_between_calls: float = 2.0
    batch_size: int = 10
    batch_pause: float = 30.0
    rate_limit_pause: float = 300.0  # 5 minutos
    timeout_seconds: Optional[int] = None  # None = sin timeout

    # Comportamiento
    auto_resume: bool = True
    stop_on_error: bool = False
    max_retries: int = 3


# Configuración para QUICK SYNC (onboarding)
QUICK_SYNC_CONFIG = SyncConfig(
    mode=SyncMode.QUICK,
    max_conversations=50,  # Solo últimas 50
    max_messages_per_conv=20,  # Solo últimos 20 mensajes
    max_days=30,  # Solo últimos 30 días
    delay_between_calls=1.5,  # Más rápido
    batch_size=20,
    batch_pause=10.0,
    timeout_seconds=180,  # Máximo 3 minutos
    auto_resume=False,  # No auto-resume, hay timeout
)


# Configuración para DEEP SYNC (background) - OPTIMIZADA
DEEP_SYNC_CONFIG = SyncConfig(
    mode=SyncMode.DEEP,
    max_conversations=None,  # TODAS (paginar hasta el final)
    max_messages_per_conv=200,  # Últimos 200 msgs por conversación (era None)
    max_days=None,  # Todo el historial
    delay_between_calls=2.0,  # Optimizado (era 4.0)
    batch_size=15,  # Optimizado (era 10)
    batch_pause=30.0,  # Optimizado (era 60.0)
    rate_limit_pause=180.0,  # 3 min (era 300 / 5 min)
    timeout_seconds=None,  # Sin timeout
    auto_resume=True,  # SIEMPRE continúa
)


class RateLimitError(Exception):
    """Error cuando Instagram API devuelve rate limit."""

    pass


# =============================================================================
# FUNCIONES DE PAGINACIÓN (CRÍTICO - OBTENER TODAS LAS CONVERSACIONES)
# =============================================================================


async def get_all_conversations_paginated(
    access_token: str,
    ig_user_id: str,
    ig_page_id: Optional[str] = None,
    max_conversations: Optional[int] = None,
    max_days: Optional[int] = None,
) -> List[Dict]:
    """
    Obtiene TODAS las conversaciones paginando hasta el final.
    Instagram devuelve ~50 por página.

    Args:
        access_token: Token de acceso de Instagram
        ig_user_id: ID del usuario de Instagram
        ig_page_id: ID de la página (si existe)
        max_conversations: Límite de conversaciones (None = sin límite)
        max_days: Solo conversaciones de los últimos N días (None = todas)

    Returns:
        Lista de todas las conversaciones
    """
    all_conversations = []

    # Determinar API base y endpoint
    if ig_page_id:
        api_base = "https://graph.facebook.com/v21.0"
        endpoint_id = ig_page_id
        extra_params = {"platform": "instagram"}
    else:
        api_base = "https://graph.instagram.com/v21.0"
        endpoint_id = ig_user_id
        extra_params = {}

    url = f"{api_base}/{endpoint_id}/conversations"
    params = {
        **extra_params,
        "access_token": access_token,
        "fields": "id,participants,updated_time",
        "limit": 50,  # Máximo por página
    }

    # Calcular fecha de corte si hay límite de días
    cutoff_date = None
    if max_days:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_days)

    page = 0
    consecutive_old = 0  # Contador de páginas con todas conversaciones antiguas

    async with httpx.AsyncClient(timeout=60.0) as client:
        while url:
            page += 1
            logger.info(f"[Pagination] Fetching conversations page {page} from {url[:80]}...")

            try:
                if page == 1:
                    logger.info(f"[Pagination] Params: {list(params.keys())}")
                    response = await client.get(url, params=params)
                else:
                    response = await client.get(url)  # URL ya tiene params

                logger.info(f"[Pagination] Response status: {response.status_code}")

                # Check rate limit
                if response.status_code == 429:
                    logger.warning(f"[Pagination] Rate limit 429 on page {page}, waiting 5 min...")
                    await asyncio.sleep(300)
                    continue

                if response.status_code != 200:
                    try:
                        error_data = response.json()
                        error_code = error_data.get("error", {}).get("code")
                        logger.error(f"[Pagination] API error: {error_data}")
                        if error_code in [4, 17]:
                            logger.warning(
                                f"[Pagination] Rate limit code {error_code}, waiting 5 min..."
                            )
                            await asyncio.sleep(300)
                            continue
                    except Exception:
                        logger.error(f"[Pagination] Non-JSON error response: {response.text[:200]}")
                    break  # Stop on non-rate-limit error

                data = response.json()
                logger.info(f"[Pagination] Got data with {len(data.get('data', []))} conversations")

            except httpx.HTTPStatusError as e:
                logger.error(f"[Pagination] HTTP error on page {page}: {e}")
                raise
            except Exception as e:
                logger.error(f"[Pagination] Error on page {page}: {e}")
                import traceback

                logger.error(traceback.format_exc())
                raise

            # Procesar conversaciones de esta página
            page_conversations = data.get("data", [])

            if not page_conversations:
                logger.info(f"[Pagination] Page {page} empty, done.")
                break

            # Filtrar por fecha si hay límite
            filtered = []
            old_count = 0
            for conv in page_conversations:
                updated_time = conv.get("updated_time")
                if updated_time and cutoff_date:
                    try:
                        conv_time = datetime.fromisoformat(updated_time.replace("+0000", "+00:00"))
                        if conv_time < cutoff_date:
                            old_count += 1
                            continue  # Skip old conversation
                    except Exception:
                        pass  # Include if can't parse
                filtered.append(conv)

            all_conversations.extend(filtered)

            logger.info(
                f"[Pagination] Page {page}: {len(page_conversations)} total, "
                f"{len(filtered)} recent, {old_count} old. "
                f"Running total: {len(all_conversations)}"
            )

            # Si todas las conversaciones de esta página son antiguas, probablemente no hay más recientes
            if old_count == len(page_conversations) and len(page_conversations) > 0:
                consecutive_old += 1
                if consecutive_old >= 2:  # 2 páginas seguidas con todo antiguo
                    logger.info("[Pagination] 2 pages of old conversations, stopping.")
                    break
            else:
                consecutive_old = 0

            # Check si alcanzamos el límite
            if max_conversations and len(all_conversations) >= max_conversations:
                all_conversations = all_conversations[:max_conversations]
                logger.info(f"[Pagination] Reached max_conversations limit: {max_conversations}")
                break

            # ¿Hay más páginas?
            paging = data.get("paging", {})
            url = paging.get("next")  # None si no hay más

            # Delay para evitar rate limit
            if url:
                await asyncio.sleep(2)  # 2 segundos entre páginas

    logger.info(f"[Pagination] TOTAL conversations fetched: {len(all_conversations)}")
    return all_conversations


async def get_conversation_messages_paginated(
    access_token: str,
    conversation_id: str,
    ig_page_id: Optional[str] = None,
    max_messages: Optional[int] = None,
) -> List[Dict]:
    """
    Obtiene TODOS los mensajes de una conversación paginando.

    Args:
        access_token: Token de acceso
        conversation_id: ID de la conversación
        ig_page_id: ID de la página (determina qué API usar)
        max_messages: Límite de mensajes (None = todos)

    Returns:
        Lista de todos los mensajes
    """
    all_messages = []

    # Determinar API base
    if ig_page_id:
        api_base = "https://graph.facebook.com/v21.0"
    else:
        api_base = "https://graph.instagram.com/v21.0"

    url = f"{api_base}/{conversation_id}/messages"
    params = {
        "fields": "id,message,from,to,created_time,attachments,story,share",
        "access_token": access_token,
        "limit": 50,
    }

    page = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while url:
            page += 1

            try:
                if page == 1:
                    response = await client.get(url, params=params)
                else:
                    response = await client.get(url)

                # Check rate limit
                if response.status_code != 200:
                    error_data = response.json().get("error", {})
                    error_code = error_data.get("code")
                    if error_code in [4, 17]:
                        raise RateLimitError(error_data.get("message", "Rate limit"))
                    logger.warning(f"[Messages] API error: {error_data}")
                    break

                data = response.json()
                page_messages = data.get("data", [])

                if not page_messages:
                    break

                all_messages.extend(page_messages)

                # Check límite
                if max_messages and len(all_messages) >= max_messages:
                    all_messages = all_messages[:max_messages]
                    break

                # ¿Más páginas?
                url = data.get("paging", {}).get("next")

            except RateLimitError:
                raise
            except Exception as e:
                logger.error(f"[Messages] Error fetching page {page}: {e}")
                break

    return all_messages


# =============================================================================
# FUNCIONES DE GUARDADO EN BD
# =============================================================================


async def save_lead_and_messages(
    session,
    creator,
    conversation_id: str,
    messages: List[Dict],
    creator_ids: set,
) -> Dict[str, Any]:
    """
    Guarda el lead y mensajes en la BD.

    Returns:
        Dict con estadísticas: messages_saved, lead_created
    """
    from api.models import Lead, Message

    result = {"messages_saved": 0, "lead_created": False}

    if not messages:
        return result

    # Encontrar el follower (participante que NO es el creator)
    follower_id = None
    follower_username = None

    for msg in messages:
        from_data = msg.get("from", {})
        from_id = from_data.get("id")
        if from_id and from_id not in creator_ids:
            follower_id = from_id
            follower_username = from_data.get("username", "unknown")
            break

    # Buscar en "to" si no encontramos en "from"
    if not follower_id:
        for msg in messages:
            to_data = msg.get("to", {}).get("data", [])
            for recipient in to_data:
                if recipient.get("id") not in creator_ids:
                    follower_id = recipient.get("id")
                    follower_username = recipient.get("username", "unknown")
                    break
            if follower_id:
                break

    if not follower_id:
        return result  # No encontramos follower

    # Calcular timestamps
    all_timestamps = []
    user_timestamps = []

    for msg in messages:
        created_time = msg.get("created_time")
        if created_time:
            try:
                ts = datetime.fromisoformat(created_time.replace("+0000", "+00:00"))
                all_timestamps.append(ts)

                from_id = msg.get("from", {}).get("id")
                if from_id and from_id not in creator_ids:
                    user_timestamps.append(ts)
            except Exception:
                pass

    first_contact = min(all_timestamps) if all_timestamps else None
    last_user_contact = max(user_timestamps) if user_timestamps else None

    # Get or create lead
    lead = (
        session.query(Lead)
        .filter_by(
            creator_id=creator.id,
            platform="instagram",
            platform_user_id=follower_id,
        )
        .first()
    )

    if not lead:
        lead = Lead(
            creator_id=creator.id,
            platform="instagram",
            platform_user_id=follower_id,
            username=follower_username,
            status="new",
            first_contact_at=first_contact,
            last_contact_at=last_user_contact or first_contact,
        )
        session.add(lead)
        session.flush()  # Get the ID
        result["lead_created"] = True
    else:
        # Update timestamps if newer
        if first_contact and (not lead.first_contact_at or first_contact < lead.first_contact_at):
            lead.first_contact_at = first_contact
        if last_user_contact and (
            not lead.last_contact_at or last_user_contact > lead.last_contact_at
        ):
            lead.last_contact_at = last_user_contact

    # Save messages
    for msg in messages:
        msg_id = msg.get("id")
        msg_text = msg.get("message", "")

        if not msg_id:
            continue

        # Skip if exists
        existing = session.query(Message).filter_by(platform_message_id=msg_id).first()
        if existing:
            continue

        # Determine role
        from_data = msg.get("from", {})
        is_from_creator = from_data.get("id") in creator_ids
        role = "assistant" if is_from_creator else "user"

        new_msg = Message(
            lead_id=lead.id,
            role=role,
            content=msg_text or "",
            platform_message_id=msg_id,
        )

        # Set timestamp
        created_time = msg.get("created_time")
        if created_time:
            try:
                new_msg.created_at = datetime.fromisoformat(created_time.replace("+0000", "+00:00"))
            except Exception:
                pass

        session.add(new_msg)
        result["messages_saved"] += 1

    session.commit()
    return result


async def update_sync_state(session, creator_id: str, updates: Dict):
    """Actualiza el estado del sync en la BD."""
    from api.models import SyncState

    state = session.query(SyncState).filter_by(creator_id=creator_id).first()
    if not state:
        state = SyncState(creator_id=creator_id)
        session.add(state)

    for key, value in updates.items():
        if hasattr(state, key):
            setattr(state, key, value)

    session.commit()
    return state


# =============================================================================
# QUICK SYNC - Rápido para onboarding (máx 3 min)
# =============================================================================


async def run_quick_sync(creator_id: str) -> Dict[str, Any]:
    """
    QUICK SYNC: Rápido para onboarding (máx 3 minutos).
    Carga datos suficientes para que el bot funcione.

    Returns:
        Dict con resultado del sync
    """
    from api.database import SessionLocal
    from api.models import Creator

    config = QUICK_SYNC_CONFIG
    start_time = datetime.now(timezone.utc)

    result = {
        "mode": "quick",
        "conversations_synced": 0,
        "messages_saved": 0,
        "leads_created": 0,
        "completed": False,
        "timed_out": False,
        "error": None,
    }

    logger.info(f"[QuickSync] Starting for {creator_id} (max {config.timeout_seconds}s)")
    print(f"[QuickSync] ====== STARTING for {creator_id} ======", flush=True)

    session = SessionLocal()
    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            print(f"[QuickSync] ERROR: Creator {creator_id} not found!", flush=True)
            result["error"] = "Creator not found"
            return result
        if not creator.instagram_token:
            print(f"[QuickSync] ERROR: Creator {creator_id} has no token!", flush=True)
            result["error"] = "No Instagram token"
            return result

        access_token = creator.instagram_token
        ig_user_id = creator.instagram_user_id or creator.instagram_page_id
        ig_page_id = creator.instagram_page_id
        creator_ids = {ig_user_id, ig_page_id} - {None}

        print(
            f"[QuickSync] Creator found: ig_user_id={ig_user_id}, page_id={ig_page_id}", flush=True
        )
        logger.info(f"[QuickSync] Creator: ig_user_id={ig_user_id}, page_id={ig_page_id}")

        # Update state
        await update_sync_state(
            session,
            creator_id,
            {
                "status": "running",
                "conversations_synced": 0,
                "messages_saved": 0,
            },
        )

        # Get conversations (limited)
        print(
            f"[QuickSync] Fetching conversations (max {config.max_conversations}, last {config.max_days} days)",
            flush=True,
        )
        logger.info(
            f"[QuickSync] Fetching conversations (max {config.max_conversations}, last {config.max_days} days)"
        )

        try:
            conversations = await get_all_conversations_paginated(
                access_token=access_token,
                ig_user_id=ig_user_id,
                ig_page_id=ig_page_id,
                max_conversations=config.max_conversations,
                max_days=config.max_days,
            )
            print(f"[QuickSync] Got {len(conversations)} conversations", flush=True)
        except Exception as conv_error:
            print(f"[QuickSync] ERROR getting conversations: {conv_error}", flush=True)
            logger.error(f"[QuickSync] ERROR getting conversations: {conv_error}")
            import traceback

            print(traceback.format_exc(), flush=True)
            result["error"] = str(conv_error)
            return result

        logger.info(f"[QuickSync] Got {len(conversations)} conversations to process")

        # Process conversations
        for i, conv in enumerate(conversations):
            # Check timeout
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if config.timeout_seconds and elapsed > config.timeout_seconds:
                logger.warning(
                    f"[QuickSync] Timeout after {elapsed:.0f}s, processed {i}/{len(conversations)}"
                )
                result["timed_out"] = True
                break

            conv_id = conv.get("id")
            if not conv_id:
                continue

            try:
                # Get messages (limited)
                messages = await get_conversation_messages_paginated(
                    access_token=access_token,
                    conversation_id=conv_id,
                    ig_page_id=ig_page_id,
                    max_messages=config.max_messages_per_conv,
                )

                # Save to DB
                save_result = await save_lead_and_messages(
                    session=session,
                    creator=creator,
                    conversation_id=conv_id,
                    messages=messages,
                    creator_ids=creator_ids,
                )

                result["conversations_synced"] += 1
                result["messages_saved"] += save_result["messages_saved"]
                if save_result["lead_created"]:
                    result["leads_created"] += 1

                # Update state periodically
                if result["conversations_synced"] % 5 == 0:
                    await update_sync_state(
                        session,
                        creator_id,
                        {
                            "conversations_synced": result["conversations_synced"],
                            "messages_saved": result["messages_saved"],
                        },
                    )

                await asyncio.sleep(config.delay_between_calls)

            except RateLimitError:
                logger.warning(f"[QuickSync] Rate limit at conv {i}, stopping quick sync")
                result["error"] = "rate_limit"
                break
            except Exception as e:
                logger.error(f"[QuickSync] Error on conv {conv_id}: {e}")
                if config.stop_on_error:
                    raise
                continue

        result["completed"] = not result["timed_out"] and not result.get("error")

        # Final state update
        await update_sync_state(
            session,
            creator_id,
            {
                "status": "quick_complete" if result["completed"] else "quick_partial",
                "conversations_synced": result["conversations_synced"],
                "messages_saved": result["messages_saved"],
            },
        )

        logger.info(
            f"[QuickSync] Done for {creator_id}: "
            f"{result['conversations_synced']} convs, {result['messages_saved']} msgs, "
            f"{result['leads_created']} leads"
        )

    except Exception as e:
        logger.error(f"[QuickSync] Fatal error: {e}")
        result["error"] = str(e)
    finally:
        session.close()

    return result


# =============================================================================
# DEEP SYNC - Background completo (sin límites)
# =============================================================================


async def run_deep_sync_background(creator_id: str):
    """
    DEEP SYNC: Corre en background REAL hasta completar TODO.
    - Sin límites de conversaciones/mensajes
    - Auto-recovery de rate limits
    - Nunca para hasta completar
    - Persistente (puede resumir si el servidor reinicia)
    """
    from api.database import SessionLocal
    from api.models import Creator

    config = DEEP_SYNC_CONFIG

    logger.info(f"[DeepSync] ====== STARTING for {creator_id} (background, NO LIMITS) ======")

    session = SessionLocal()
    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator or not creator.instagram_token:
            logger.error(f"[DeepSync] Creator {creator_id} not found or no token")
            return

        access_token = creator.instagram_token
        ig_user_id = creator.instagram_user_id or creator.instagram_page_id
        ig_page_id = creator.instagram_page_id
        creator_ids = {ig_user_id, ig_page_id} - {None}

        # Initialize state
        await update_sync_state(
            session,
            creator_id,
            {
                "status": "deep_running",
                "last_error": None,
            },
        )

        # Get ALL conversations (with full pagination)
        logger.info("[DeepSync] Fetching ALL conversations (no limits)...")

        all_conversations = await get_all_conversations_paginated(
            access_token=access_token,
            ig_user_id=ig_user_id,
            ig_page_id=ig_page_id,
            max_conversations=None,  # NO LIMIT
            max_days=None,  # ALL HISTORY
        )

        total = len(all_conversations)
        logger.info(f"[DeepSync] Got {total} TOTAL conversations to process")

        await update_sync_state(
            session,
            creator_id,
            {
                "conversations_total": total,
                "conversations_synced": 0,
            },
        )

        synced = 0
        messages_total = 0
        leads_created = 0
        rate_limit_hits = 0
        batch_count = 0

        # Process all conversations
        for i, conv in enumerate(all_conversations):
            conv_id = conv.get("id")
            if not conv_id:
                continue

            retry_count = 0
            while retry_count < config.max_retries:
                try:
                    # Get messages with configured limit (200 for optimization)
                    messages = await get_conversation_messages_paginated(
                        access_token=access_token,
                        conversation_id=conv_id,
                        ig_page_id=ig_page_id,
                        max_messages=config.max_messages_per_conv,  # Limit to 200
                    )

                    # Save to DB
                    save_result = await save_lead_and_messages(
                        session=session,
                        creator=creator,
                        conversation_id=conv_id,
                        messages=messages,
                        creator_ids=creator_ids,
                    )

                    synced += 1
                    messages_total += save_result["messages_saved"]
                    if save_result["lead_created"]:
                        leads_created += 1

                    batch_count += 1

                    # Update progress
                    if synced % 5 == 0:
                        progress_pct = round(synced * 100 / total, 1) if total > 0 else 0
                        logger.info(f"[DeepSync] Progress: {synced}/{total} ({progress_pct}%)")

                        await update_sync_state(
                            session,
                            creator_id,
                            {
                                "conversations_synced": synced,
                                "messages_saved": messages_total,
                            },
                        )

                    await asyncio.sleep(config.delay_between_calls)
                    break  # Success, exit retry loop

                except RateLimitError as e:
                    rate_limit_hits += 1
                    logger.warning(
                        f"[DeepSync] Rate limit #{rate_limit_hits} at {synced}/{total}. "
                        f"Waiting {config.rate_limit_pause}s..."
                    )

                    await update_sync_state(
                        session,
                        creator_id,
                        {
                            "status": "deep_rate_limited",
                            "last_error": str(e),
                            "rate_limit_until": (
                                datetime.now(timezone.utc)
                                + timedelta(seconds=config.rate_limit_pause)
                            ),
                        },
                    )

                    # WAIT AND CONTINUE (real auto-resume)
                    await asyncio.sleep(config.rate_limit_pause)

                    await update_sync_state(
                        session,
                        creator_id,
                        {
                            "status": "deep_running",
                            "rate_limit_until": None,
                        },
                    )

                    retry_count += 1
                    continue

                except Exception as e:
                    logger.error(f"[DeepSync] Error on conv {conv_id}: {e}")
                    retry_count += 1
                    if retry_count >= config.max_retries:
                        if config.stop_on_error:
                            raise
                        break  # Skip this conversation
                    await asyncio.sleep(5)  # Brief pause before retry

            # Batch pause
            if batch_count >= config.batch_size:
                logger.info(f"[DeepSync] Batch complete, pausing {config.batch_pause}s...")
                await asyncio.sleep(config.batch_pause)
                batch_count = 0

        # COMPLETED
        await update_sync_state(
            session,
            creator_id,
            {
                "status": "deep_completed",
                "conversations_synced": synced,
                "conversations_total": total,
                "messages_saved": messages_total,
                "last_error": None,
            },
        )

        logger.info(
            f"[DeepSync] ====== COMPLETED for {creator_id} ======"
            f"\n  Conversations: {synced}/{total}"
            f"\n  Messages: {messages_total}"
            f"\n  Leads created: {leads_created}"
            f"\n  Rate limit hits: {rate_limit_hits}"
        )

    except Exception as e:
        logger.error(f"[DeepSync] Fatal error: {e}")
        import traceback

        logger.error(traceback.format_exc())

        await update_sync_state(
            session,
            creator_id,
            {
                "status": "deep_error",
                "last_error": str(e),
            },
        )
    finally:
        session.close()


# =============================================================================
# FUNCIONES DE ESTADO Y PROGRESO
# =============================================================================


def get_sync_progress(creator_id: str) -> Dict[str, Any]:
    """
    Retorna el progreso del sync (quick + deep).
    El frontend puede mostrar esto en el dashboard.
    """
    from api.database import SessionLocal
    from api.models import SyncState

    session = SessionLocal()
    try:
        state = session.query(SyncState).filter_by(creator_id=creator_id).first()

        if not state:
            return {"status": "not_started"}

        total = state.conversations_total or 0
        synced = state.conversations_synced or 0
        progress_pct = round(synced * 100 / total, 1) if total > 0 else 0

        response = {
            "status": state.status,
            "quick_sync": {
                "status": (
                    "completed"
                    if state.status in ["quick_complete", "deep_running", "deep_completed"]
                    else "pending"
                ),
            },
            "deep_sync": {
                "status": state.status if state.status.startswith("deep_") else "pending",
                "progress_percent": progress_pct,
                "conversations": f"{synced}/{total}",
                "messages": state.messages_saved or 0,
            },
        }

        if state.status == "deep_rate_limited" and state.rate_limit_until:
            remaining = (state.rate_limit_until - datetime.now(timezone.utc)).total_seconds()
            response["deep_sync"]["rate_limit_remaining"] = max(0, int(remaining))

        return response

    finally:
        session.close()


# =============================================================================
# LEGACY COMPATIBILITY - Funciones existentes que otros módulos pueden usar
# =============================================================================


async def start_sync_for_creator(creator_id: str) -> Dict[str, Any]:
    """
    Legacy function - ahora inicia deep sync en background.
    """
    logger.info(f"[SyncWorker] start_sync_for_creator called for {creator_id}")

    # Start deep sync in background
    asyncio.create_task(run_deep_sync_background(creator_id))

    return {
        "status": "started",
        "message": "Deep sync started in background",
    }


# Keep old function name for compatibility
SYNC_CONFIG = DEEP_SYNC_CONFIG
