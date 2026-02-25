"""
Dangerous/destructive admin endpoints — System resets.

Endpoints:
- reset_all_data
- nuclear_reset
- sync_reset
- clear_messages
- reset_demo_data
"""

import json
import logging
import shutil
from pathlib import Path

from api.auth import require_admin
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from .shared import DEMO_RESET_ENABLED, validate_table_name

logger = logging.getLogger(__name__)
router = APIRouter()


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


@router.post("/reset-demo-data/{creator_id}")
async def reset_demo_data(creator_id: str, admin: str = Depends(require_admin)):
    """
    Legacy endpoint - redirects to reset-creator.

    Requires admin API key (X-API-Key header).
    """
    from .dangerous_user_ops import reset_creator

    return await reset_creator(creator_id, admin)
