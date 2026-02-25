"""
Dangerous/destructive admin endpoints — Lead cleanup operations.

Endpoints:
- cleanup_test_leads
- delete_lead_by_platform_id
- cleanup_orphan_leads
"""

import logging

from api.auth import require_admin
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from .shared import DEMO_RESET_ENABLED

logger = logging.getLogger(__name__)
router = APIRouter()


@router.delete("/cleanup-test-leads/{creator_id}")
async def cleanup_test_leads(creator_id: str, admin: str = Depends(require_admin)):
    """
    Eliminar leads de test y leads sin username.

    Requires admin API key (X-API-Key header).

    Elimina:
    - Leads sin username (NULL o vacío)
    - Leads con username que empieza con 'test'
    - Leads con platform_user_id que empieza con 'test'
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message
        from sqlalchemy import or_

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"status": "error", "error": f"Creator not found: {creator_id}"}

            test_leads = (
                session.query(Lead)
                .filter(
                    Lead.creator_id == creator.id,
                    or_(
                        Lead.username.is_(None),
                        Lead.username == "",
                        Lead.username.like("test%"),
                        Lead.platform_user_id.like("test%"),
                    ),
                )
                .all()
            )

            deleted_leads = []
            deleted_messages = 0

            for lead in test_leads:
                msg_count = session.query(Message).filter_by(lead_id=lead.id).delete()
                deleted_messages += msg_count
                deleted_leads.append(
                    {"id": str(lead.id), "username": lead.username, "messages_deleted": msg_count}
                )
                session.delete(lead)

            session.commit()

            return {
                "status": "success",
                "creator": creator_id,
                "leads_deleted": len(deleted_leads),
                "messages_deleted": deleted_messages,
                "details": deleted_leads[:10],
            }

        except Exception as e:
            session.rollback()
            return {"status": "error", "error": str(e)}
        finally:
            session.close()

    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.delete("/delete-lead-by-platform-id/{creator_id}/{platform_user_id}")
async def delete_lead_by_platform_id(
    creator_id: str, platform_user_id: str, admin: str = Depends(require_admin)
):
    """
    Delete a specific lead by platform_user_id, including all its messages.
    Use this to clean up leads that were incorrectly created (e.g., old creator IDs).

    Requires admin API key (X-API-Key header).
    """
    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    results = {"status": "ok", "deleted_lead": None, "deleted_messages_count": 0}

    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

        lead_info = session.execute(
            text(
                """
                SELECT l.id, l.username, l.platform_user_id,
                       (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) as msg_count
                FROM leads l
                WHERE l.creator_id = :cid AND l.platform_user_id = :puid
            """
            ),
            {"cid": str(creator.id), "puid": platform_user_id},
        ).fetchone()

        if not lead_info:
            return {
                "status": "not_found",
                "message": f"No lead found with platform_user_id={platform_user_id}",
            }

        lead_id, username, puid, msg_count = lead_info

        session.execute(text("DELETE FROM messages WHERE lead_id = :lid"), {"lid": str(lead_id)})
        session.execute(text("DELETE FROM leads WHERE id = :lid"), {"lid": str(lead_id)})

        session.commit()

        results["deleted_lead"] = {
            "id": str(lead_id),
            "username": username,
            "platform_user_id": puid,
        }
        results["deleted_messages_count"] = msg_count

        logger.info(f"Deleted lead {username} ({platform_user_id}) with {msg_count} messages")

        return results

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.post("/cleanup-orphan-leads")
async def cleanup_orphan_leads(
    confirm: str = None, dry_run: bool = True, admin: str = Depends(require_admin)
):
    """
    Clean up orphan leads:
    1. Delete duplicate with ig_ prefix and 0 messages
    2. Check and delete lead without profile if message not important

    Requires admin API key (X-API-Key header).

    SAFETY: Requires confirm=DELETE_ORPHAN_LEADS and dry_run=false to actually delete.
    By default runs in dry_run mode showing what WOULD be deleted.
    """
    from api.database import SessionLocal

    if confirm != "DELETE_ORPHAN_LEADS" or dry_run:
        session = SessionLocal()
        try:
            zero_msg_leads = session.execute(
                text(
                    """
                    SELECT l.id, l.platform_user_id, l.username
                    FROM leads l
                    WHERE l.creator_id = (SELECT id FROM creators WHERE name = 'stefano_bonanno')
                    AND (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) = 0
                    AND l.platform_user_id LIKE 'ig_%'
                    LIMIT 50
                """
                )
            ).fetchall()

            return {
                "mode": "dry_run",
                "would_delete": len(zero_msg_leads),
                "sample": [
                    {"id": str(r[0]), "platform_user_id": r[1], "username": r[2]}
                    for r in zero_msg_leads[:10]
                ],
                "to_execute": "POST /admin/cleanup-orphan-leads?confirm=DELETE_ORPHAN_LEADS&dry_run=false",
            }
        finally:
            session.close()

    session = SessionLocal()
    try:
        result = session.execute(
            text(
                """
                DELETE FROM leads
                WHERE id IN (
                    SELECT l.id FROM leads l
                    WHERE l.creator_id = (SELECT id FROM creators WHERE name = 'stefano_bonanno')
                    AND (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) = 0
                    AND l.platform_user_id LIKE 'ig_%'
                )
            """
            )
        )
        deleted_count = result.rowcount
        session.commit()

        logger.warning(f"Cleaned up {deleted_count} orphan leads")

        return {"status": "success", "deleted_count": deleted_count}

    except Exception as e:
        session.rollback()
        logger.error(f"Error cleaning orphan leads: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()
