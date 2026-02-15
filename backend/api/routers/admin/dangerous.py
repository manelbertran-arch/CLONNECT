"""
Dangerous/destructive admin endpoints.

All endpoints in this module require admin authentication and handle
destructive operations like delete, reset, nuclear options.

These are the 12 endpoints protected with require_admin.
"""

import json
import logging
import shutil
from pathlib import Path

from api.auth import require_admin
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from .shared import DEMO_RESET_ENABLED, validate_fk_column, validate_table_name

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reset-db")
async def reset_all_data(admin: str = Depends(require_admin)):
    """
    Reset ALL data in the database and JSON files.
    Returns the creator to a fresh state with:
    - No leads, messages, products, sequences
    - Bot set to Paused
    - Onboarding at 0%

    Requires admin API key (X-API-Key header).
    """
    if not DEMO_RESET_ENABLED:
        raise HTTPException(
            status_code=403, detail="Demo reset is disabled. Set ENABLE_DEMO_RESET=true to enable."
        )

    results = {"database": {}, "json_files": {}, "status": "success"}

    # 1. Reset PostgreSQL database using SQLAlchemy
    try:
        from api.database import DATABASE_URL, SessionLocal

        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import (
                    Creator,
                    KnowledgeBase,
                    Lead,
                    Message,
                    NurturingSequence,
                    Product,
                )

                msg_count = session.query(Message).delete()
                results["database"]["messages"] = msg_count

                lead_count = session.query(Lead).delete()
                results["database"]["leads"] = lead_count

                prod_count = session.query(Product).delete()
                results["database"]["products"] = prod_count

                seq_count = session.query(NurturingSequence).delete()
                results["database"]["nurturing_sequences"] = seq_count

                kb_count = session.query(KnowledgeBase).delete()
                results["database"]["knowledge_base"] = kb_count

                creators = session.query(Creator).all()
                for creator in creators:
                    creator.bot_active = False
                results["database"]["creators_reset"] = len(creators)

                session.commit()
                logger.info(f"Database reset complete: {results['database']}")

            except Exception as e:
                session.rollback()
                logger.error(f"Database reset failed: {e}")
                results["database"]["error"] = str(e)
            finally:
                session.close()
    except Exception as e:
        logger.warning(f"Database not available: {e}")
        results["database"]["error"] = str(e)

    # 2. Reset JSON files
    data_dirs = [
        Path("data"),
        Path("data/creators"),
        Path("data/products"),
        Path("data/followers"),
        Path("data/nurturing"),
        Path("data/payments"),
        Path("data/analytics"),
        Path("data/gdpr"),
        Path("data/calendar"),
    ]

    json_deleted = 0
    for data_dir in data_dirs:
        if data_dir.exists():
            for json_file in data_dir.glob("*.json"):
                try:
                    if "leads" in json_file.name:
                        json_file.write_text('{"leads": []}')
                    elif "messages" in json_file.name:
                        json_file.write_text('{"messages": []}')
                    elif "conversations" in json_file.name:
                        json_file.write_text('{"conversations": []}')
                    elif "products" in json_file.name:
                        json_file.write_text('{"products": []}')
                    elif "sales" in json_file.name:
                        json_file.write_text('{"clicks": [], "sales": []}')
                    elif "metrics" in json_file.name:
                        json_file.write_text(
                            '{"messages_today": 0, "leads_today": 0, "hot_leads_count": 0, "total_messages": 0, "total_leads": 0}'
                        )
                    elif "followups" in json_file.name:
                        json_file.write_text("[]")
                    elif "nurturing" in json_file.name or "sequences" in json_file.name:
                        json_file.write_text('{"sequences": [], "enrolled": []}')
                    elif "payments" in json_file.name or "purchases" in json_file.name:
                        json_file.write_text('{"purchases": [], "revenue": 0}')
                    elif "config" in json_file.name:
                        try:
                            with open(json_file) as f:
                                config = json.load(f)
                            config["clone_active"] = False
                            config["is_active"] = False
                            config.pop("products", None)
                            json_file.write_text(json.dumps(config, indent=2))
                        except (json.JSONDecodeError, IOError) as e:
                            logger.debug("Ignored (json.JSONDecodeError, IOError) in with open(json_file) as f:: %s", e)
                    else:
                        json_file.write_text("{}")
                    json_deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to reset {json_file}: {e}")

    followers_dir = Path("data/followers")
    if followers_dir.exists():
        for creator_dir in followers_dir.iterdir():
            if creator_dir.is_dir():
                try:
                    shutil.rmtree(creator_dir)
                    json_deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to clean {creator_dir}: {e}")

    results["json_files"]["reset_count"] = json_deleted

    logger.info(f"Full reset complete: {results}")
    return results


@router.delete("/delete-user/{email}")
async def delete_user_by_email(email: str, admin: str = Depends(require_admin)):
    """Delete a user AND associated creator by email (for testing/reset purposes).

    Requires admin API key (X-API-Key header).
    """
    if not DEMO_RESET_ENABLED:
        raise HTTPException(status_code=403, detail="Demo reset is disabled")

    try:
        from api.database import SessionLocal
        from api.models import Creator, KnowledgeBase, Lead, Message, Product, User, UserCreator

        session = SessionLocal()
        try:
            deleted = {"user": None, "creator": None}

            user = session.query(User).filter_by(email=email).first()
            if user:
                user_creator = session.query(UserCreator).filter_by(user_id=user.id).first()
                if user_creator:
                    creator = session.query(Creator).filter_by(id=user_creator.creator_id).first()
                    if creator:
                        session.query(Message).filter(
                            Message.lead_id.in_(
                                session.query(Lead.id).filter_by(creator_id=creator.id)
                            )
                        ).delete(synchronize_session=False)
                        session.query(Lead).filter_by(creator_id=creator.id).delete()
                        session.query(Product).filter_by(creator_id=creator.id).delete()
                        session.query(KnowledgeBase).filter_by(creator_id=creator.id).delete()
                        session.delete(creator)
                        deleted["creator"] = creator.name

                    session.delete(user_creator)

                session.delete(user)
                deleted["user"] = email

            session.commit()
            return {"status": "success", "deleted": deleted}

        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nuclear-reset")
async def nuclear_reset(confirm: str = "", admin: str = Depends(require_admin)):
    """
    NUCLEAR OPTION: Delete absolutely everything from the database.
    Requires confirm=DELETE_EVERYTHING to execute.

    Requires admin API key (X-API-Key header).
    """
    if confirm != "DELETE_EVERYTHING":
        return {
            "error": "Safety check failed",
            "usage": "POST /admin/nuclear-reset?confirm=DELETE_EVERYTHING",
            "warning": "This will DELETE ALL DATA including creators, leads, messages, products, etc.",
        }

    if not DEMO_RESET_ENABLED:
        raise HTTPException(status_code=403, detail="Demo reset is disabled")

    try:
        from api.database import SessionLocal

        session = SessionLocal()
        deleted = {}

        try:
            tables = [
                "messages",
                "lead_activities",
                "lead_tasks",
                "leads",
                "sync_queue",
                "sync_state",
                "products",
                "nurturing_sequences",
                "knowledge_base",
                "email_ask_tracking",
                "platform_identities",
                "unified_profiles",
                "user_creators",
                "rag_documents",
                "creators",
                "users",
            ]

            for table in tables:
                try:
                    validate_table_name(table)
                    # Table name validated against whitelist; quoted as defense in depth
                    result = session.execute(text(f'DELETE FROM "{table}"'))
                    deleted[table] = result.rowcount
                except Exception as e:
                    deleted[table] = f"error: {str(e)[:50]}"

            session.commit()
            logger.warning("NUCLEAR RESET: All data deleted!")

            return {"status": "success", "message": "All data has been deleted", "deleted": deleted}

        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear-messages/{creator_id}")
async def clear_messages(creator_id: str, confirm: str = None, admin: str = Depends(require_admin)):
    """
    Delete all messages for a creator to allow re-import with new features.

    DANGER: This permanently deletes ALL messages. Requires confirmation.

    Requires admin API key (X-API-Key header).
    """
    if confirm != "DELETE_ALL_MESSAGES":
        return {
            "error": "Safety check failed",
            "usage": f"DELETE /admin/clear-messages/{creator_id}?confirm=DELETE_ALL_MESSAGES",
            "warning": "This will PERMANENTLY delete ALL messages for this creator. This action cannot be undone.",
        }

    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            lead_ids = [
                lead.id for lead in session.query(Lead).filter_by(creator_id=creator.id).all()
            ]

            if not lead_ids:
                return {
                    "status": "ok",
                    "deleted_messages": 0,
                    "note": "No leads found for this creator",
                }

            deleted_count = (
                session.query(Message)
                .filter(Message.lead_id.in_(lead_ids))
                .delete(synchronize_session=False)
            )

            session.commit()
            logger.warning(f"Cleared {deleted_count} messages for creator {creator_id}")

            return {
                "status": "success",
                "creator_id": creator_id,
                "deleted_messages": deleted_count,
                "leads_affected": len(lead_ids),
            }

        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Error clearing messages: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sync-reset/{creator_id}")
async def sync_reset(creator_id: str, admin: str = Depends(require_admin)):
    """
    Resetea el estado del sync para un creator.
    Limpia la cola y el estado.

    Requires admin API key (X-API-Key header).
    """
    from api.database import SessionLocal
    from api.models import SyncQueue, SyncState

    session = SessionLocal()
    try:
        deleted_jobs = session.query(SyncQueue).filter_by(creator_id=creator_id).delete()
        deleted_state = session.query(SyncState).filter_by(creator_id=creator_id).delete()
        session.commit()
        return {"status": "reset", "jobs_deleted": deleted_jobs, "state_deleted": deleted_state}
    finally:
        session.close()


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


@router.post("/reset-creator/{creator_id}")
async def reset_creator(creator_id: str, admin: str = Depends(require_admin)):
    """
    Full reset for a creator - empties everything for demo.

    Requires admin API key (X-API-Key header).

    Resets:
    - All leads and conversations/messages
    - All products
    - All nurturing sequences
    - Knowledge base
    - Tone profile
    - RAG content index
    - Bot status (paused)
    - Onboarding status (not completed)

    Keeps:
    - Creator record (user, credentials, connections)
    - Instagram/WhatsApp tokens
    """
    if not DEMO_RESET_ENABLED:
        raise HTTPException(
            status_code=403, detail="Demo reset is disabled. Set ENABLE_DEMO_RESET=true to enable."
        )

    results = {
        "creator_id": creator_id,
        "deleted": {
            "leads": 0,
            "messages": 0,
            "products": 0,
            "sequences": 0,
            "knowledge_base": 0,
            "email_tracking": 0,
            "platform_identities": 0,
            "tone_profile": False,
            "rag_documents": 0,
            "bot_paused": False,
            "onboarding_reset": False,
        },
    }

    # 1. Database reset using SQLAlchemy
    try:
        from api.database import DATABASE_URL, SessionLocal

        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import (
                    Creator,
                    KnowledgeBase,
                    Lead,
                    Message,
                    NurturingSequence,
                    Product,
                )

                # Find creator by name
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    # Try by ID if it's a UUID
                    try:
                        from uuid import UUID

                        creator = session.query(Creator).filter_by(id=UUID(creator_id)).first()
                    except ValueError as e:
                        logger.debug("Ignored ValueError in from uuid import UUID: %s", e)

                if creator:
                    creator_uuid = creator.id

                    # Delete messages for this creator's leads
                    leads = session.query(Lead).filter_by(creator_id=creator_uuid).all()
                    lead_ids = [lead.id for lead in leads]

                    if lead_ids:
                        msg_count = (
                            session.query(Message)
                            .filter(Message.lead_id.in_(lead_ids))
                            .delete(synchronize_session="fetch")
                        )
                        results["deleted"]["messages"] = msg_count

                        # Delete lead_activities and lead_tasks first (FK constraint)
                        try:
                            from api.models import LeadActivity, LeadTask

                            activity_count = (
                                session.query(LeadActivity)
                                .filter(LeadActivity.lead_id.in_(lead_ids))
                                .delete(synchronize_session="fetch")
                            )
                            results["deleted"]["lead_activities"] = activity_count

                            task_count = (
                                session.query(LeadTask)
                                .filter(LeadTask.lead_id.in_(lead_ids))
                                .delete(synchronize_session="fetch")
                            )
                            results["deleted"]["lead_tasks"] = task_count
                        except Exception as e:
                            logger.warning(f"Could not delete lead activities/tasks: {e}")

                    # Delete leads
                    lead_count = session.query(Lead).filter_by(creator_id=creator_uuid).delete()
                    results["deleted"]["leads"] = lead_count

                    # Delete products
                    prod_count = session.query(Product).filter_by(creator_id=creator_uuid).delete()
                    results["deleted"]["products"] = prod_count

                    # Delete sequences
                    seq_count = (
                        session.query(NurturingSequence).filter_by(creator_id=creator_uuid).delete()
                    )
                    results["deleted"]["sequences"] = seq_count

                    # Delete knowledge base
                    kb_count = (
                        session.query(KnowledgeBase).filter_by(creator_id=creator_uuid).delete()
                    )
                    results["deleted"]["knowledge_base"] = kb_count

                    # Delete email tracking for this creator
                    try:
                        from api.models import EmailAskTracking, PlatformIdentity

                        email_tracking_count = (
                            session.query(EmailAskTracking)
                            .filter_by(creator_id=creator_uuid)
                            .delete()
                        )
                        results["deleted"]["email_tracking"] = email_tracking_count

                        # Delete platform identities (but keep unified profiles - they're cross-creator)
                        identity_count = (
                            session.query(PlatformIdentity)
                            .filter_by(creator_id=creator_uuid)
                            .delete()
                        )
                        results["deleted"]["platform_identities"] = identity_count
                    except Exception as e:
                        logger.warning(f"Could not delete email tracking tables: {e}")

                    # Reset bot and onboarding status
                    creator.bot_active = False
                    creator.onboarding_completed = False
                    creator.copilot_mode = True  # Reset to default copilot mode
                    results["deleted"]["bot_paused"] = True
                    results["deleted"]["onboarding_reset"] = True

                    session.commit()
                    logger.info(f"Database reset complete for {creator_id}")
                else:
                    results["error"] = f"Creator '{creator_id}' not found in database"

            except Exception as e:
                session.rollback()
                logger.error(f"Database reset failed: {e}")
                results["error"] = str(e)
            finally:
                session.close()
    except Exception as e:
        logger.warning(f"Database not available: {e}")

    # 2. Delete Tone Profile
    try:
        from core.tone_service import clear_cache, delete_tone_profile

        if delete_tone_profile(creator_id):
            results["deleted"]["tone_profile"] = True
            logger.info(f"Tone profile deleted for {creator_id}")
        clear_cache(creator_id)
    except Exception as e:
        logger.warning(f"Could not delete tone profile: {e}")

    # 3. Clear RAG documents for this creator
    try:
        from core.rag import get_hybrid_rag

        rag = get_hybrid_rag()
        deleted_docs = rag.delete_by_creator(creator_id)
        results["deleted"]["rag_documents"] = deleted_docs
        logger.info(f"RAG documents deleted for {creator_id}: {deleted_docs}")
    except Exception as e:
        logger.warning(f"Could not clear RAG: {e}")

    # 4. JSON files reset
    data_dir = Path("data")
    json_patterns = [
        f"leads_{creator_id}.json",
        f"messages_{creator_id}.json",
        f"conversations_{creator_id}.json",
        f"metrics_{creator_id}.json",
        f"sales_{creator_id}.json",
        f"{creator_id}_products.json",
        f"{creator_id}_config.json",
        f"{creator_id}_sales.json",
    ]

    for pattern in json_patterns:
        # Check in data dir and subdirs
        for subdir in ["", "creators", "products", "followers"]:
            filepath = data_dir / subdir / pattern if subdir else data_dir / pattern
            if filepath.exists():
                try:
                    if "products" in pattern:
                        filepath.write_text("[]")
                    elif "config" in pattern:
                        try:
                            with open(filepath) as f:
                                config = json.load(f)
                            config["clone_active"] = False
                            config["is_active"] = False
                            filepath.write_text(json.dumps(config, indent=2))
                        except (json.JSONDecodeError, IOError):
                            filepath.unlink()
                    else:
                        filepath.unlink()
                except Exception as e:
                    logger.warning(f"Failed to reset {filepath}: {e}")

    # 5. Clean follower directory for this creator
    followers_dir = data_dir / "followers" / creator_id
    if followers_dir.exists():
        try:
            shutil.rmtree(followers_dir)
        except OSError as e:
            logger.warning("Failed to remove followers dir: %s", e)

    logger.info(f"Full reset complete for {creator_id}: {results}")
    return {"status": "success", **results}


@router.post("/reset-demo-data/{creator_id}")
async def reset_demo_data(creator_id: str, admin: str = Depends(require_admin)):
    """
    Legacy endpoint - redirects to reset-creator.

    Requires admin API key (X-API-Key header).
    """
    return await reset_creator(creator_id, admin)


@router.delete("/creators/{creator_name}")
async def delete_creator(creator_name: str, admin: str = Depends(require_admin)):
    """
    Completely delete a creator and all associated data.
    Use with caution - this is irreversible!

    Requires admin API key (X-API-Key header).
    """
    if not DEMO_RESET_ENABLED:
        raise HTTPException(
            status_code=403, detail="Demo reset is disabled. Set ENABLE_DEMO_RESET=true to enable."
        )

    results = {
        "creator_name": creator_name,
        "deleted": {
            "leads": 0,
            "messages": 0,
            "products": 0,
            "sequences": 0,
            "knowledge_base": 0,
            "creator": False,
        },
    }

    try:
        from api.database import SessionLocal

        session = SessionLocal()
        try:
            from api.models import Creator, KnowledgeBase, Lead, Message, NurturingSequence, Product

            # Find creator by name
            creator = session.query(Creator).filter_by(name=creator_name).first()
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator '{creator_name}' not found")

            creator_uuid = creator.id

            # Delete messages for this creator's leads
            leads = session.query(Lead).filter_by(creator_id=creator_uuid).all()
            lead_ids = [lead.id for lead in leads]

            if lead_ids:
                msg_count = (
                    session.query(Message)
                    .filter(Message.lead_id.in_(lead_ids))
                    .delete(synchronize_session="fetch")
                )
                results["deleted"]["messages"] = msg_count

            # Delete leads
            lead_count = session.query(Lead).filter_by(creator_id=creator_uuid).delete()
            results["deleted"]["leads"] = lead_count

            # Delete products
            prod_count = session.query(Product).filter_by(creator_id=creator_uuid).delete()
            results["deleted"]["products"] = prod_count

            # Delete sequences
            seq_count = session.query(NurturingSequence).filter_by(creator_id=creator_uuid).delete()
            results["deleted"]["sequences"] = seq_count

            # Delete knowledge base
            kb_count = session.query(KnowledgeBase).filter_by(creator_id=creator_uuid).delete()
            results["deleted"]["knowledge_base"] = kb_count

            # Delete email tracking and platform identities
            try:
                from api.models import EmailAskTracking, PlatformIdentity

                session.query(EmailAskTracking).filter_by(creator_id=creator_uuid).delete()
                session.query(PlatformIdentity).filter_by(creator_id=creator_uuid).delete()
            except Exception as e:
                logger.warning(f"Could not delete email tracking: {e}")

            # Delete user_creators associations (FK constraint)
            try:
                from api.models import UserCreator

                session.query(UserCreator).filter_by(creator_id=creator_uuid).delete()
                results["deleted"]["user_creators"] = True
            except Exception as e:
                logger.warning(f"Could not delete user_creators: {e}")

            # Delete RAG documents (FK constraint)
            try:
                from api.models import RAGDocument

                rag_count = session.query(RAGDocument).filter_by(creator_id=creator_uuid).delete()
                results["deleted"]["rag_documents"] = rag_count
            except Exception as e:
                logger.warning(f"Could not delete rag_documents: {e}")

            # Delete sync queue and state (FK constraint)
            try:
                from api.models import SyncQueue, SyncState

                session.query(SyncQueue).filter_by(creator_id=creator_uuid).delete()
                session.query(SyncState).filter_by(creator_id=creator_uuid).delete()
                results["deleted"]["sync_data"] = True
            except Exception as e:
                logger.warning(f"Could not delete sync data: {e}")

            # Delete the creator itself
            session.delete(creator)
            results["deleted"]["creator"] = True

            session.commit()
            logger.info(f"Creator '{creator_name}' deleted completely")

        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Delete creator failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Clean up tone profile and RAG
    try:
        from core.tone_service import clear_cache, delete_tone_profile

        delete_tone_profile(creator_name)
        clear_cache(creator_name)
    except Exception as e:
        logger.warning("Failed to clean tone profile: %s", e)

    try:
        from core.rag import get_hybrid_rag

        rag = get_hybrid_rag()
        rag.delete_by_creator(creator_name)
    except Exception as e:
        logger.warning("Failed to clean RAG: %s", e)

    return {"status": "success", **results}


@router.delete("/force-delete-creator/{creator_name}")
async def force_delete_creator(creator_name: str, admin: str = Depends(require_admin)):
    """
    Force delete a creator using raw SQL with proper transaction handling.
    Use this when normal delete fails due to transaction issues.

    Requires admin API key (X-API-Key header).
    """
    if not DEMO_RESET_ENABLED:
        raise HTTPException(status_code=403, detail="Demo reset is disabled")

    try:
        from api.database import SessionLocal

        session = SessionLocal()
        try:
            # Clear any failed transaction state from connection pool
            session.rollback()

            # Get creator ID first
            result = session.execute(
                text("SELECT id FROM creators WHERE name = :name"), {"name": creator_name}
            )
            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Creator '{creator_name}' not found")

            creator_id = str(row[0])

            # Delete in order of FK dependencies
            # Format: (table_name, fk_column, needs_lead_subquery)
            tables_to_clean = [
                ("messages", "lead_id", True),
                ("lead_activities", "lead_id", True),
                ("lead_tasks", "lead_id", True),
                ("leads", "creator_id", False),
                ("products", "creator_id", False),
                ("nurturing_sequences", "creator_id", False),
                ("knowledge_base", "creator_id", False),
                ("email_ask_tracking", "creator_id", False),
                ("platform_identities", "creator_id", False),
                ("user_creators", "creator_id", False),
                ("rag_documents", "creator_id", False),
                ("sync_queue", "creator_id", False),
                ("sync_state", "creator_id", False),
            ]

            deleted = {}
            for table, fk_col, needs_lead_subquery in tables_to_clean:
                try:
                    # Validate table and column names against whitelist (SQL injection prevention)
                    validate_table_name(table)
                    validate_fk_column(fk_col)

                    if needs_lead_subquery:
                        # Delete where FK is in leads for this creator (parameterized)
                        # Table/column names validated against whitelist; quoted as defense in depth
                        sql = text(
                            f'DELETE FROM "{table}" WHERE "{fk_col}" IN '
                            "(SELECT id FROM leads WHERE creator_id = :creator_id)"
                        )
                    else:
                        # Delete directly by creator_id (parameterized)
                        # Table/column names validated against whitelist; quoted as defense in depth
                        sql = text(f'DELETE FROM "{table}" WHERE "{fk_col}" = :creator_id')

                    result = session.execute(sql, {"creator_id": creator_id})
                    deleted[table] = result.rowcount
                except Exception as e:
                    logger.warning(f"Could not delete from {table}: {e}")
                    deleted[table] = f"error: {str(e)[:50]}"

            # Delete creator (parameterized query)
            validate_table_name("creators")
            session.execute(
                text("DELETE FROM creators WHERE id = :creator_id"), {"creator_id": creator_id}
            )
            deleted["creators"] = 1

            session.commit()
            return {"status": "success", "creator": creator_name, "deleted": deleted}

        except HTTPException:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
