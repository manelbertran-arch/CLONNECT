"""
Ghost Reactivation Service - Reactiva automáticamente leads fantasma.

Un lead fantasma es alguien que no ha respondido en 7+ días.
Este servicio:
1. Detecta leads fantasma
2. Les envía un mensaje de reactivación (RE_ENGAGEMENT)
3. Evita spam: solo 1 mensaje de reactivación por lead
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Tracking de leads ya reactivados (evitar spam)
_reactivated_leads: Dict[str, datetime] = {}

# =============================================================================
# PROTECTED BLOCK: Ghost Reactivation Configuration
# Modified: 2026-01-16
# Reason: Configuración anti-spam para reactivación automática de leads fantasma
# Do not modify without considering rate limits and user experience
# =============================================================================
REACTIVATION_CONFIG = {
    "min_days_ghost": 7,           # Mínimo días sin respuesta para ser fantasma
    "max_days_ghost": 90,          # Máximo días (muy viejo = no molestar)
    "cooldown_days": 30,           # No reactivar el mismo lead en X días
    "max_per_cycle": 5,            # Máximo leads a reactivar por ciclo
    "enabled": True,               # Activar/desactivar
}

# Mensajes de reactivación (se eligen aleatoriamente)
REACTIVATION_MESSAGES = [
    "¡Hola! Hace tiempo que no hablamos. ¿Cómo va todo? Si necesitas algo, aquí estoy 🙌",
    "Hey! ¿Todo bien por ahí? Me acordé de ti y quería saber cómo estás.",
    "¡Hola! Espero que estés genial. Si alguna vez quieres retomar la conversación, aquí me tienes.",
]


def _get_reactivation_key(creator_id: str, lead_id: str) -> str:
    """Genera key única para tracking de reactivación."""
    return f"{creator_id}:{lead_id}"


def _was_recently_reactivated(creator_id: str, lead_id: str) -> bool:
    """Verifica si un lead fue reactivado recientemente."""
    key = _get_reactivation_key(creator_id, lead_id)

    if key not in _reactivated_leads:
        return False

    last_reactivation = _reactivated_leads[key]
    cooldown = timedelta(days=REACTIVATION_CONFIG["cooldown_days"])

    return datetime.now(timezone.utc) - last_reactivation < cooldown


def _mark_as_reactivated(creator_id: str, lead_id: str):
    """Marca un lead como reactivado."""
    key = _get_reactivation_key(creator_id, lead_id)
    _reactivated_leads[key] = datetime.now(timezone.utc)


def get_ghost_leads_for_reactivation(creator_id: str) -> List[Dict[str, Any]]:
    """
    Obtiene leads fantasma que necesitan reactivación.

    Returns:
        Lista de leads con info necesaria para reactivar
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message
        from sqlalchemy import text

        session = SessionLocal()
        try:
            # Get creator
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                creator = session.query(Creator).filter(
                    text("id::text = :cid")
                ).params(cid=creator_id).first()

            if not creator:
                logger.warning(f"[GHOST] Creator not found: {creator_id}")
                return []

            # Get leads (limit to 500 — only 5 ghosts returned per cycle)
            leads = session.query(Lead).filter_by(creator_id=creator.id).limit(500).all()

            ghosts = []
            now = datetime.now(timezone.utc)
            min_days = REACTIVATION_CONFIG["min_days_ghost"]
            max_days = REACTIVATION_CONFIG["max_days_ghost"]

            for lead in leads:
                # Skip if no first_contact
                if not lead.first_contact_at:
                    continue

                # Calculate days since last contact
                last_contact = lead.last_contact_at or lead.first_contact_at
                if last_contact.tzinfo is None:
                    last_contact = last_contact.replace(tzinfo=timezone.utc)

                days_since = (now - last_contact).days

                # Check if in ghost range
                if days_since < min_days:
                    continue  # Too recent
                if days_since > max_days:
                    continue  # Too old

                # Check if already reactivated recently
                if _was_recently_reactivated(creator_id, str(lead.id)):
                    continue

                # Check if has pending nurturing
                from core.nurturing import get_nurturing_manager
                manager = get_nurturing_manager()
                existing = manager.get_all_followups(creator_id, status="pending")
                has_pending = any(
                    fu.follower_id == lead.platform_user_id
                    for fu in existing
                )
                if has_pending:
                    continue

                ghosts.append({
                    "lead_id": str(lead.id),
                    "platform_user_id": lead.platform_user_id,
                    "username": lead.username,
                    "platform": lead.platform,
                    "days_since_contact": days_since,
                    "last_contact": last_contact.isoformat(),
                })

            # Sort by days (prioritize older ghosts within range)
            ghosts.sort(key=lambda x: x["days_since_contact"], reverse=True)

            # Limit per cycle
            max_per_cycle = REACTIVATION_CONFIG["max_per_cycle"]
            return ghosts[:max_per_cycle]

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[GHOST] Error getting ghost leads: {e}")
        import traceback
        traceback.print_exc()
        return []


async def reactivate_ghost_leads(creator_id: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    Reactiva leads fantasma para un creator.

    Args:
        creator_id: ID del creator
        dry_run: Si True, no envía mensajes reales

    Returns:
        Dict con resultados de la reactivación
    """
    if not REACTIVATION_CONFIG["enabled"]:
        return {"status": "disabled", "message": "Ghost reactivation is disabled"}

    result = {
        "creator_id": creator_id,
        "ghosts_found": 0,
        "scheduled": 0,
        "errors": 0,
        "details": []
    }

    # Get ghost leads (run sync DB query in thread to avoid blocking event loop)
    ghosts = await asyncio.to_thread(get_ghost_leads_for_reactivation, creator_id)
    result["ghosts_found"] = len(ghosts)

    if not ghosts:
        logger.info(f"[GHOST] No ghost leads to reactivate for {creator_id}")
        return result

    logger.info(f"[GHOST] Found {len(ghosts)} ghost leads for {creator_id}")

    # Schedule reactivation for each
    from core.nurturing import get_nurturing_manager, SequenceType
    import random

    manager = get_nurturing_manager()

    for ghost in ghosts:
        try:
            follower_id = ghost["platform_user_id"]
            username = ghost["username"]
            days = ghost["days_since_contact"]

            if dry_run:
                logger.info(f"[GHOST] DRY RUN: Would reactivate {username} ({days} days)")
                result["details"].append({
                    "username": username,
                    "days_since_contact": days,
                    "status": "dry_run"
                })
                continue

            # Schedule RE_ENGAGEMENT nurturing (run in thread — saves 520+ rows to DB)
            followups = await asyncio.to_thread(
                manager.schedule_followup,
                creator_id=creator_id,
                follower_id=follower_id,
                sequence_type=SequenceType.RE_ENGAGEMENT.value,
                product_name="",
                start_step=0
            )

            if followups:
                _mark_as_reactivated(creator_id, ghost["lead_id"])
                result["scheduled"] += 1
                result["details"].append({
                    "username": username,
                    "days_since_contact": days,
                    "status": "scheduled"
                })
                logger.info(f"[GHOST] Scheduled reactivation for {username} ({days} days ghost)")
            else:
                result["errors"] += 1
                result["details"].append({
                    "username": username,
                    "days_since_contact": days,
                    "status": "error",
                    "error": "Failed to schedule"
                })

        except Exception as e:
            result["errors"] += 1
            result["details"].append({
                "username": ghost.get("username", "unknown"),
                "status": "error",
                "error": str(e)
            })
            logger.error(f"[GHOST] Error reactivating {ghost}: {e}")

    return result


async def run_ghost_reactivation_cycle():
    """
    Ejecuta un ciclo de reactivación para todos los creators.
    Llamado por el scheduler de nurturing.
    """
    if not REACTIVATION_CONFIG["enabled"]:
        return {"status": "disabled"}

    results = {
        "total_ghosts": 0,
        "total_scheduled": 0,
        "creators_processed": 0,
        "errors": 0
    }

    try:
        from api.database import SessionLocal
        from api.models import Creator

        if SessionLocal is None:
            logger.debug("[GHOST] Database not configured, skipping reactivation cycle")
            return {"status": "no_database", **results}

        def _get_active_creator_names():
            session = SessionLocal()
            try:
                creators = session.query(Creator).filter(
                    Creator.instagram_token != None
                ).all()
                return [c.name for c in creators]
            finally:
                session.close()

        creator_names = await asyncio.to_thread(_get_active_creator_names)

        for creator_name in creator_names:
            try:
                result = await reactivate_ghost_leads(creator_name)
                results["total_ghosts"] += result.get("ghosts_found", 0)
                results["total_scheduled"] += result.get("scheduled", 0)
                results["creators_processed"] += 1
            except Exception as e:
                results["errors"] += 1
                logger.error(f"[GHOST] Error for creator {creator_name}: {e}")

    except Exception as e:
        logger.error(f"[GHOST] Error in reactivation cycle: {e}")
        results["errors"] += 1

    if results["total_scheduled"] > 0:
        logger.info(
            f"[GHOST] Cycle complete: {results['total_scheduled']} ghosts scheduled "
            f"for reactivation across {results['creators_processed']} creators"
        )

    return results


def configure_reactivation(
    enabled: bool = None,
    min_days: int = None,
    max_days: int = None,
    cooldown_days: int = None,
    max_per_cycle: int = None
) -> Dict[str, Any]:
    """
    Configura los parámetros de reactivación.

    Returns:
        Configuración actual
    """
    if enabled is not None:
        REACTIVATION_CONFIG["enabled"] = enabled
    if min_days is not None:
        REACTIVATION_CONFIG["min_days_ghost"] = min_days
    if max_days is not None:
        REACTIVATION_CONFIG["max_days_ghost"] = max_days
    if cooldown_days is not None:
        REACTIVATION_CONFIG["cooldown_days"] = cooldown_days
    if max_per_cycle is not None:
        REACTIVATION_CONFIG["max_per_cycle"] = max_per_cycle

    return REACTIVATION_CONFIG.copy()


def get_reactivation_stats(creator_id: str) -> Dict[str, Any]:
    """
    Obtiene estadísticas de reactivación para un creator.
    """
    ghosts = get_ghost_leads_for_reactivation(creator_id)

    # Count total reactivated
    reactivated_count = sum(
        1 for key in _reactivated_leads
        if key.startswith(f"{creator_id}:")
    )

    return {
        "config": REACTIVATION_CONFIG.copy(),
        "pending_ghosts": len(ghosts),
        "total_reactivated": reactivated_count,
        "ghosts": ghosts[:10]  # First 10 for preview
    }
