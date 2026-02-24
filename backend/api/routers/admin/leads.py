"""
Lead management endpoints.

Handles lead-related operations:
- Lead rescoring and categorization
- Ghost lead management and reactivation
- Duplicate lead diagnosis and merging
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/rescore-leads/{creator_id}")
async def rescore_leads(creator_id: str, admin: str = Depends(require_admin)):
    """
    Re-categorizar todos los leads usando el sistema de embudo estándar.

    Categorías:
    - nuevo: Acaba de llegar, sin señales
    - interesado: Muestra curiosidad, hace preguntas
    - caliente: Pregunta precio o quiere comprar
    - cliente: Ya compró (requiere flag manual o webhook)
    - fantasma: Sin respuesta 7+ días

    Args:
        creator_id: Nombre o UUID del creator

    Returns:
        Estadísticas de leads actualizados por categoría
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message
        from core.lead_categorization import (
            calcular_categoria,
            categoria_a_status_legacy,
        )
        from sqlalchemy import text

        session = SessionLocal()
        try:
            # Get creator
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                creator = (
                    session.query(Creator)
                    .filter(text("id::text = :cid"))
                    .params(cid=creator_id)
                    .first()
                )

            if not creator:
                return {"status": "error", "error": f"Creator not found: {creator_id}"}

            leads = session.query(Lead).filter_by(creator_id=creator.id).all()

            stats = {
                "total_leads": len(leads),
                "leads_updated": 0,
                "por_categoria": {
                    "nuevo": 0,
                    "amigo": 0,
                    "colaborador": 0,
                    "caliente": 0,
                    "cliente": 0,
                    "frío": 0,
                },
                "details": [],
            }

            # Batch pre-fetch all messages for this creator's leads (2 queries instead of N+1)
            from collections import defaultdict

            lead_ids = [lead.id for lead in leads]
            all_messages = (
                session.query(Message)
                .filter(Message.lead_id.in_(lead_ids))
                .order_by(Message.lead_id, Message.created_at)
                .all()
            )
            messages_by_lead = defaultdict(list)
            for msg in all_messages:
                messages_by_lead[msg.lead_id].append(msg)

            for lead in leads:
                messages = messages_by_lead.get(lead.id, [])

                # Convertir a formato esperado por calcular_categoria
                mensajes_dict = [{"role": m.role, "content": m.content or ""} for m in messages]

                # Obtener último mensaje del lead para detectar fantasma
                mensajes_usuario = [m for m in messages if m.role == "user"]
                ultimo_msg_lead = mensajes_usuario[-1].created_at if mensajes_usuario else None

                # Obtener última interacción (cualquier mensaje)
                ultima_interaccion = messages[-1].created_at if messages else None

                # Verificar si es cliente (por ahora manual, luego webhook)
                es_cliente = (
                    getattr(lead, "has_purchased", False)
                    if hasattr(lead, "has_purchased")
                    else False
                )

                # Calcular categoría
                # IMPORTANTE: NO usar lead.last_contact_at como fallback porque
                # puede estar mal seteada (fecha de hoy por el sync).
                # Si no hay mensajes, ultima_interaccion=None y se usará lead_created_at
                resultado = calcular_categoria(
                    mensajes=mensajes_dict,
                    es_cliente=es_cliente,
                    ultimo_mensaje_lead=ultimo_msg_lead,
                    dias_fantasma=7,
                    lead_created_at=lead.first_contact_at,
                    ultima_interaccion=ultima_interaccion,
                )

                # Convertir a status legacy para compatibilidad con frontend actual
                new_status = categoria_a_status_legacy(resultado.categoria)

                # Guardar cambios
                old_status = lead.status
                old_intent = lead.purchase_intent

                lead.status = new_status
                # Recalculate multi-factor score
                try:
                    from services.lead_scoring import recalculate_lead_score
                    recalculate_lead_score(session, str(lead.id))
                except Exception as se:
                    logger.warning(f"Scoring failed: {se}")
                    lead.purchase_intent = resultado.intent_score
                    lead.score = max(0, min(100, int(resultado.intent_score * 100)))

                stats["leads_updated"] += 1
                stats["por_categoria"][resultado.categoria] += 1

                stats["details"].append(
                    {
                        "username": lead.username,
                        "categoria": resultado.categoria,
                        "status_legacy": new_status,
                        "old_status": old_status,
                        "intent_score": resultado.intent_score,
                        "old_intent": old_intent,
                        "razones": resultado.razones,
                        "keywords": resultado.keywords_detectados[:5],
                        "messages_count": len(messages),
                        "first_contact": (
                            str(lead.first_contact_at) if lead.first_contact_at else None
                        ),
                        "last_contact": str(lead.last_contact_at) if lead.last_contact_at else None,
                    }
                )

            session.commit()
            logger.info(f"[Rescore] Updated {stats['leads_updated']} leads for {creator_id}")

            return {"status": "success", "creator_id": creator_id, **stats}

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Rescore failed for {creator_id}: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "error", "error": str(e)}


@router.get("/lead-categories")
async def get_lead_categories(admin: str = Depends(require_admin)):
    """
    Obtener configuración de categorías de leads para el frontend.

    Retorna colores, iconos, labels y descripciones de cada categoría.
    """
    from core.lead_categorization import CATEGORIAS_CONFIG

    return {"status": "success", "categories": CATEGORIAS_CONFIG}


@router.get("/ghost-stats/{creator_id}")
async def get_ghost_stats(creator_id: str, admin: str = Depends(require_admin)):
    """
    Obtiene estadísticas de leads fantasma y estado de reactivación.

    Muestra:
    - Configuración actual
    - Leads fantasma pendientes de reactivar
    - Total reactivados
    """
    try:
        from core.ghost_reactivation import get_reactivation_stats

        return get_reactivation_stats(creator_id)
    except Exception as e:
        return {"error": str(e)}


@router.post("/ghost-reactivate/{creator_id}")
async def reactivate_ghosts(creator_id: str, dry_run: bool = False, admin: str = Depends(require_admin)):
    """
    Reactiva manualmente leads fantasma de un creator.

    Args:
        creator_id: ID del creator
        dry_run: Si True, solo muestra qué haría sin enviar

    Returns:
        Resultado de la reactivación
    """
    try:
        from core.ghost_reactivation import reactivate_ghost_leads

        result = await reactivate_ghost_leads(creator_id, dry_run=dry_run)
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Ghost reactivation failed for {creator_id}: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/ghost-config")
async def configure_ghost_reactivation(
    enabled: bool = None,
    min_days: int = None,
    max_days: int = None,
    cooldown_days: int = None,
    max_per_cycle: int = None,
    admin: str = Depends(require_admin),
):
    """
    Configura parámetros de reactivación de fantasmas.

    Args:
        enabled: Activar/desactivar reactivación automática
        min_days: Días mínimos sin respuesta para ser fantasma (default: 7)
        max_days: Días máximos (muy viejo = no molestar) (default: 90)
        cooldown_days: No reactivar mismo lead en X días (default: 30)
        max_per_cycle: Máximo leads por ciclo del scheduler (default: 5)

    Returns:
        Configuración actualizada
    """
    try:
        from core.ghost_reactivation import configure_reactivation

        config = configure_reactivation(
            enabled=enabled,
            min_days=min_days,
            max_days=max_days,
            cooldown_days=cooldown_days,
            max_per_cycle=max_per_cycle,
        )
        return {"status": "success", "config": config}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/ghost-config")
async def get_ghost_config(admin: str = Depends(require_admin)):
    """Obtiene la configuración actual de reactivación."""
    try:
        from core.ghost_reactivation import REACTIVATION_CONFIG

        return {"status": "success", "config": REACTIVATION_CONFIG}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/diagnose-duplicate-leads/{creator_id}")
async def diagnose_duplicate_leads(creator_id: str, admin: str = Depends(require_admin)):
    """
    Diagnose duplicate leads (same username with different platform_user_id).
    Also creates a backup of the leads table.
    """
    from api.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    try:
        # Get creator
        from api.models import Creator

        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

        # 1. Count duplicates for this creator
        result = session.execute(
            text(
                """
                SELECT COUNT(*) FROM (
                    SELECT username FROM leads
                    WHERE username IS NOT NULL AND username != ''
                    AND creator_id = :creator_id
                    GROUP BY username
                    HAVING COUNT(*) > 1
                ) as dupes
            """
            ),
            {"creator_id": str(creator.id)},
        )
        dupe_count = result.scalar()

        # 2. Get duplicate details with message counts
        result = session.execute(
            text(
                """
                SELECT l.username, l.platform_user_id, l.id,
                       (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) as msg_count,
                       l.updated_at::date as updated
                FROM leads l
                WHERE l.creator_id = :creator_id
                AND l.username IN (
                    SELECT username FROM leads
                    WHERE username IS NOT NULL AND username != ''
                    AND creator_id = :creator_id
                    GROUP BY username
                    HAVING COUNT(*) > 1
                )
                ORDER BY l.username, msg_count DESC
            """
            ),
            {"creator_id": str(creator.id)},
        )
        rows = result.fetchall()

        duplicates = {}
        for row in rows:
            username = row[0]
            if username not in duplicates:
                duplicates[username] = []
            duplicates[username].append(
                {
                    "platform_user_id": row[1],
                    "lead_id": str(row[2]),
                    "message_count": row[3],
                    "updated": str(row[4]) if row[4] else None,
                }
            )

        # 3. Create backup
        backup_created = False
        try:
            session.execute(text("DROP TABLE IF EXISTS leads_backup_20260204"))
            session.execute(text("CREATE TABLE leads_backup_20260204 AS SELECT * FROM leads"))
            session.commit()
            backup_count = session.execute(
                text("SELECT COUNT(*) FROM leads_backup_20260204")
            ).scalar()
            backup_created = True
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            backup_count = 0

        return {
            "status": "ok",
            "creator_id": creator_id,
            "duplicate_usernames_count": dupe_count,
            "total_duplicate_rows": len(rows),
            "duplicates": duplicates,
            "backup": {
                "created": backup_created,
                "table": "leads_backup_20260204",
                "rows": backup_count,
            },
        }

    finally:
        session.close()


@router.post("/merge-duplicate-leads/{creator_id}")
async def merge_duplicate_leads(creator_id: str, admin: str = Depends(require_admin)):
    """
    Merge duplicate leads (same username with different platform_user_id).
    Moves messages from ig_xxx leads to xxx leads, then deletes the ig_xxx leads.
    """
    from api.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    try:
        # Get creator
        from api.models import Creator

        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

        creator_uuid = str(creator.id)

        # Step 1: Count before
        leads_before = session.execute(
            text("SELECT COUNT(*) FROM leads WHERE creator_id = :cid"),
            {"cid": creator_uuid},
        ).scalar()

        # Step 2: Find duplicates
        duplicates = session.execute(
            text(
                """
                SELECT l.id, l.username, l.platform_user_id,
                       (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) as msg_count
                FROM leads l
                WHERE l.creator_id = :cid
                AND l.platform_user_id LIKE 'ig_%'
                AND EXISTS (
                    SELECT 1 FROM leads l2
                    WHERE l2.platform_user_id = REPLACE(l.platform_user_id, 'ig_', '')
                    AND l2.creator_id = l.creator_id
                )
            """
            ),
            {"cid": creator_uuid},
        ).fetchall()

        messages_moved = 0
        leads_deleted = 0
        details = []

        for dup in duplicates:
            dup_id = str(dup[0])
            username = dup[1]
            dup_platform_id = dup[2]
            dup_msg_count = dup[3]
            original_platform_id = dup_platform_id.replace("ig_", "")

            # Find original lead
            original = session.execute(
                text(
                    """
                    SELECT id FROM leads
                    WHERE platform_user_id = :pid AND creator_id = :cid
                """
                ),
                {"pid": original_platform_id, "cid": creator_uuid},
            ).fetchone()

            if original:
                original_id = str(original[0])

                # Move messages if any
                if dup_msg_count > 0:
                    session.execute(
                        text("UPDATE messages SET lead_id = :new_id WHERE lead_id = :old_id"),
                        {"new_id": original_id, "old_id": dup_id},
                    )
                    messages_moved += dup_msg_count

                # Delete duplicate lead
                session.execute(
                    text("DELETE FROM leads WHERE id = :lid"),
                    {"lid": dup_id},
                )
                leads_deleted += 1

                details.append(
                    {
                        "username": username,
                        "deleted_platform_id": dup_platform_id,
                        "kept_platform_id": original_platform_id,
                        "messages_moved": dup_msg_count,
                    }
                )

        session.commit()

        # Step 3: Count after
        leads_after = session.execute(
            text("SELECT COUNT(*) FROM leads WHERE creator_id = :cid"),
            {"cid": creator_uuid},
        ).scalar()

        return {
            "status": "ok",
            "creator_id": creator_id,
            "leads_before": leads_before,
            "leads_after": leads_after,
            "leads_deleted": leads_deleted,
            "messages_moved": messages_moved,
            "details": details,
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error merging duplicates: {e}")
        raise HTTPException(status_code=500, detail=str(e))
