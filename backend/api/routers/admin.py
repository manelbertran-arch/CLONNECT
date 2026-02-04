"""
Admin endpoints for demo/testing purposes
"""

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

logger = logging.getLogger(__name__)

# URL patterns for link preview detection
INSTAGRAM_URL_REGEX = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)"
)
YOUTUBE_URL_REGEX = re.compile(
    r"https?://(?:www\.|m\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]+)"
)


async def generate_link_preview(url: str, msg_metadata: Dict) -> Dict:
    """
    Generate preview for a URL and add to metadata.
    For YouTube: uses official thumbnail API (instant)
    For Instagram: uses Microlink API for thumbnail
    """
    try:
        # YouTube - use official thumbnail (instant, no browser needed)
        youtube_match = YOUTUBE_URL_REGEX.search(url)
        if youtube_match:
            video_id = youtube_match.group(1)
            return {
                **msg_metadata,
                "type": "shared_video",
                "platform": "youtube",
                "url": url,
                "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                "video_id": video_id,
            }

        # Instagram - use Microlink API for thumbnail
        instagram_match = INSTAGRAM_URL_REGEX.search(url)
        if instagram_match:
            try:
                from api.services.screenshot_service import get_microlink_preview

                microlink_result = await get_microlink_preview(url)
                if microlink_result and microlink_result.get("thumbnail_url"):
                    return {
                        **msg_metadata,
                        "type": "shared_post",
                        "platform": "instagram",
                        "url": url,
                        "thumbnail_url": microlink_result["thumbnail_url"],
                        "title": microlink_result.get("title"),
                        "author": microlink_result.get("author"),
                    }
            except Exception as e:
                logger.warning(f"Microlink error for {url}: {e}")

            # Fallback: mark for later processing if Microlink fails
            return {
                **msg_metadata,
                "type": "shared_post",
                "platform": "instagram",
                "url": url,
                "needs_thumbnail": True,
            }
    except Exception as e:
        logger.warning(f"Error generating link preview for {url}: {e}")

    return msg_metadata


def detect_url_in_metadata(msg_metadata: Dict) -> Optional[str]:
    """Extract URL from message metadata if present"""
    url = msg_metadata.get("url", "")
    if url and url.startswith("http"):
        return url
    return None


router = APIRouter(prefix="/admin", tags=["admin"])

# Only enable if ENABLE_DEMO_RESET is set (default true for testing)
DEMO_RESET_ENABLED = os.getenv("ENABLE_DEMO_RESET", "true").lower() == "true"


@router.post("/reset-db")
async def reset_all_data():
    """
    Reset ALL data in the database and JSON files.
    Returns the creator to a fresh state with:
    - No leads, messages, products, sequences
    - Bot set to Paused
    - Onboarding at 0%
    """
    if not DEMO_RESET_ENABLED:
        raise HTTPException(
            status_code=403, detail="Demo reset is disabled. Set ENABLE_DEMO_RESET=true to enable."
        )

    results = {"database": {}, "json_files": {}, "status": "success"}

    # 1. Reset PostgreSQL database using SQLAlchemy
    try:
        from api.database import DATABASE_URL, SessionLocal, engine

        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                # Import models
                from api.models import (
                    Creator,
                    KnowledgeBase,
                    Lead,
                    Message,
                    NurturingSequence,
                    Product,
                )

                # Delete in correct order (foreign key constraints)
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

                # Reset all creators to bot_active=False
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
                    # Reset file to empty state based on filename
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
                        # Followups files are plain arrays
                        json_file.write_text("[]")
                    elif "nurturing" in json_file.name or "sequences" in json_file.name:
                        json_file.write_text('{"sequences": [], "enrolled": []}')
                    elif "payments" in json_file.name or "purchases" in json_file.name:
                        json_file.write_text('{"purchases": [], "revenue": 0}')
                    elif "config" in json_file.name:
                        # Reset config but keep basic info, set bot to inactive
                        try:
                            with open(json_file) as f:
                                config = json.load(f)
                            config["clone_active"] = False
                            config["is_active"] = False
                            config.pop("products", None)
                            json_file.write_text(json.dumps(config, indent=2))
                        except (json.JSONDecodeError, IOError):
                            pass
                    else:
                        # Generic reset - empty object or array
                        json_file.write_text("{}")
                    json_deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to reset {json_file}: {e}")

    # Also clean follower subdirectories
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
async def delete_user_by_email(email: str):
    """Delete a user AND associated creator by email (for testing/reset purposes)"""
    if not DEMO_RESET_ENABLED:
        raise HTTPException(status_code=403, detail="Demo reset is disabled")

    try:
        from api.database import SessionLocal
        from api.models import Creator, KnowledgeBase, Lead, Message, Product, User, UserCreator

        session = SessionLocal()
        try:
            deleted = {"user": None, "creator": None}

            # Find and delete user
            user = session.query(User).filter(User.email == email).first()
            if user:
                # Get associated creator IDs before deleting associations
                user_creators = (
                    session.query(UserCreator).filter(UserCreator.user_id == user.id).all()
                )
                creator_ids = [uc.creator_id for uc in user_creators]

                # Delete user-creator associations
                session.query(UserCreator).filter(UserCreator.user_id == user.id).delete()

                # Delete user
                session.delete(user)
                deleted["user"] = email

                # Delete associated creators and their data
                for creator_id in creator_ids:
                    # Delete messages via leads (Message has lead_id, not creator_id)
                    leads = session.query(Lead).filter(Lead.creator_id == creator_id).all()
                    for lead in leads:
                        session.query(Message).filter(Message.lead_id == lead.id).delete()
                    session.query(Lead).filter(Lead.creator_id == creator_id).delete()
                    session.query(Product).filter(Product.creator_id == creator_id).delete()
                    session.query(KnowledgeBase).filter(
                        KnowledgeBase.creator_id == creator_id
                    ).delete()
                    session.query(Creator).filter(Creator.id == creator_id).delete()
                    deleted["creator"] = str(creator_id)

            # Also delete any creator with this email (in case orphaned)
            orphan_creator = session.query(Creator).filter(Creator.email == email).first()
            if orphan_creator:
                # Delete messages via leads
                leads = session.query(Lead).filter(Lead.creator_id == orphan_creator.id).all()
                for lead in leads:
                    session.query(Message).filter(Message.lead_id == lead.id).delete()
                session.query(Lead).filter(Lead.creator_id == orphan_creator.id).delete()
                session.query(Product).filter(Product.creator_id == orphan_creator.id).delete()
                session.query(KnowledgeBase).filter(
                    KnowledgeBase.creator_id == orphan_creator.id
                ).delete()
                session.delete(orphan_creator)
                deleted["orphan_creator"] = str(orphan_creator.id)

            session.commit()

            if not deleted["user"] and not deleted.get("orphan_creator"):
                raise HTTPException(status_code=404, detail=f"User/Creator {email} not found")

            return {"status": "ok", "deleted": deleted}
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-creator/{creator_id}")
async def reset_creator(creator_id: str):
    """
    Full reset for a creator - empties everything for demo.

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
                    except ValueError:
                        pass

                if creator:
                    creator_uuid = creator.id

                    # Delete messages for this creator's leads
                    leads = session.query(Lead).filter_by(creator_id=creator_uuid).all()
                    lead_ids = [l.id for l in leads]

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
async def reset_demo_data(creator_id: str):
    """
    Legacy endpoint - redirects to reset-creator.
    """
    return await reset_creator(creator_id)


@router.delete("/creators/{creator_name}")
async def delete_creator(creator_name: str):
    """
    Completely delete a creator and all associated data.
    Use with caution - this is irreversible!
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
            lead_ids = [l.id for l in leads]

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
async def force_delete_creator(creator_name: str):
    """
    Force delete a creator using raw SQL with proper transaction handling.
    Use this when normal delete fails due to transaction issues.
    """
    if not DEMO_RESET_ENABLED:
        raise HTTPException(status_code=403, detail="Demo reset is disabled")

    try:
        from api.database import SessionLocal
        from sqlalchemy import text

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
            tables_to_clean = [
                (
                    "messages",
                    "lead_id",
                    f"SELECT id FROM leads WHERE creator_id = '{creator_id}'::uuid",
                ),
                (
                    "lead_activities",
                    "lead_id",
                    f"SELECT id FROM leads WHERE creator_id = '{creator_id}'::uuid",
                ),
                (
                    "lead_tasks",
                    "lead_id",
                    f"SELECT id FROM leads WHERE creator_id = '{creator_id}'::uuid",
                ),
                ("leads", "creator_id", None),
                ("products", "creator_id", None),
                ("nurturing_sequences", "creator_id", None),
                ("knowledge_base", "creator_id", None),
                ("email_ask_tracking", "creator_id", None),
                ("platform_identities", "creator_id", None),
                ("user_creators", "creator_id", None),
                ("rag_documents", "creator_id", None),
                ("sync_queue", "creator_id", None),
                ("sync_state", "creator_id", None),
            ]

            deleted = {}
            for table, fk_col, subquery in tables_to_clean:
                try:
                    if subquery:
                        sql = text(f"DELETE FROM {table} WHERE {fk_col} IN ({subquery})")
                    else:
                        sql = text(f"DELETE FROM {table} WHERE {fk_col} = '{creator_id}'::uuid")
                    result = session.execute(sql)
                    deleted[table] = result.rowcount
                except Exception as e:
                    logger.warning(f"Could not delete from {table}: {e}")
                    deleted[table] = f"error: {str(e)[:50]}"

            # Delete creator
            session.execute(text(f"DELETE FROM creators WHERE id = '{creator_id}'::uuid"))
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


@router.post("/nuclear-reset")
async def nuclear_reset(confirm: str = ""):
    """
    NUCLEAR OPTION: Delete absolutely everything from the database.
    Requires confirm=DELETE_EVERYTHING to execute.
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
        from sqlalchemy import text

        session = SessionLocal()
        deleted = {}

        try:
            # Order matters due to foreign key constraints
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
                    result = session.execute(text(f"DELETE FROM {table}"))
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


@router.post("/test-full-sync/{creator_id}/{username}")
async def test_full_sync_conversation(creator_id: str, username: str):
    """
    TEST ENDPOINT: Sincronizar TODOS los mensajes de una conversación específica
    usando paginación completa.

    Ejemplo: POST /admin/test-full-sync/manel_bertran_luque/stefanobonanno
    """
    from datetime import datetime, timedelta

    import httpx
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

        access_token = creator.instagram_token
        ig_user_id = creator.instagram_user_id
        ig_page_id = creator.instagram_page_id

        if not access_token:
            raise HTTPException(status_code=400, detail="Creator has no Instagram token")

        # Dual API strategy
        if ig_page_id:
            api_base = "https://graph.facebook.com/v21.0"
            conv_id_for_api = ig_page_id
            conv_extra_params = {"platform": "instagram"}
        else:
            api_base = "https://graph.instagram.com/v21.0"
            conv_id_for_api = ig_user_id
            conv_extra_params = {}

        creator_ids = {ig_user_id, ig_page_id} - {None}

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Step 1: Get all conversations to find the one with the target username
            conv_resp = await client.get(
                f"{api_base}/{conv_id_for_api}/conversations",
                params={
                    **conv_extra_params,
                    "access_token": access_token,
                    "limit": 50,
                    "fields": "id,updated_time",
                },
            )

            if conv_resp.status_code != 200:
                raise HTTPException(
                    status_code=500, detail=f"Conversations API error: {conv_resp.status_code}"
                )

            conversations = conv_resp.json().get("data", [])

            # Find the conversation with the target username
            target_conv_id = None
            target_follower_id = None

            for conv in conversations:
                conv_id = conv.get("id")
                if not conv_id:
                    continue

                # Fetch messages to identify participant
                msg_resp = await client.get(
                    f"{api_base}/{conv_id}/messages",
                    params={
                        "fields": "id,message,from,to,created_time",
                        "access_token": access_token,
                        "limit": 5,
                    },
                )

                if msg_resp.status_code != 200:
                    continue

                messages = msg_resp.json().get("data", [])
                for msg in messages:
                    from_data = msg.get("from", {})
                    if from_data.get("username") == username:
                        target_conv_id = conv_id
                        target_follower_id = from_data.get("id")
                        break

                    to_data = msg.get("to", {}).get("data", [])
                    for recipient in to_data:
                        if recipient.get("username") == username:
                            target_conv_id = conv_id
                            target_follower_id = recipient.get("id")
                            break

                    if target_conv_id:
                        break

                if target_conv_id:
                    break

            if not target_conv_id:
                raise HTTPException(
                    status_code=404, detail=f"Conversation with {username} not found"
                )

            # Step 2: Fetch ALL messages with pagination
            # Request extended fields to capture media, stories, reactions, etc.
            all_messages = []
            msg_url = f"{api_base}/{target_conv_id}/messages"
            msg_params = {
                "fields": "id,message,from,to,created_time,attachments,story,shares,reactions,sticker",
                "access_token": access_token,
                "limit": 50,
            }

            pages_fetched = 0
            max_pages = 20  # Safety limit: 50 * 20 = 1000 messages max

            while msg_url and pages_fetched < max_pages:
                msg_resp = await client.get(msg_url, params=msg_params)

                if msg_resp.status_code != 200:
                    logger.warning(
                        f"Messages API error {msg_resp.status_code} on page {pages_fetched}"
                    )
                    break

                msg_data = msg_resp.json()
                page_messages = msg_data.get("data", [])
                all_messages.extend(page_messages)

                # Check for next page
                paging = msg_data.get("paging", {})
                next_url = paging.get("next")

                if next_url:
                    msg_url = next_url
                    msg_params = {}  # Next URL includes params
                    pages_fetched += 1
                    logger.info(
                        f"[FullSync] Fetched page {pages_fetched}, total messages: {len(all_messages)}"
                    )
                else:
                    break

            logger.info(
                f"[FullSync] Total pages: {pages_fetched + 1}, total messages: {len(all_messages)}"
            )

            # Step 3: Get or create lead
            days_limit_ago = datetime.now().astimezone() - timedelta(days=180)

            lead = (
                session.query(Lead)
                .filter_by(
                    creator_id=creator.id, platform="instagram", platform_user_id=target_follower_id
                )
                .first()
            )

            if not lead:
                lead = Lead(
                    creator_id=creator.id,
                    platform="instagram",
                    platform_user_id=target_follower_id,
                    username=username,
                    status="new",
                )
                session.add(lead)
                session.commit()

            # Step 4: Save all messages (including media, reactions, stories)
            saved_count = 0
            skipped_duplicate = 0
            updated_unknown = 0  # Messages updated from unknown to proper type
            skipped_old = 0
            skipped_no_id = 0
            content_types = {
                "text": 0,
                "attachment": 0,
                "story": 0,
                "share": 0,
                "reaction": 0,
                "sticker": 0,
                "unknown": 0,
            }

            for msg in all_messages:
                msg_id = msg.get("id")
                if not msg_id:
                    skipped_no_id += 1
                    continue

                # Detect content type and build message text
                msg_text = msg.get("message", "")
                metadata = {}

                if msg_text:
                    content_types["text"] += 1
                elif msg.get("share"):
                    # Shared content (singular - shared post/reel)
                    share_data = msg.get("share", {})
                    share_link = share_data.get("link", "")
                    msg_text = "[Post compartido]" if share_link else "[Contenido compartido]"
                    metadata["type"] = "share"
                    metadata["url"] = share_link
                    metadata["thumbnail_url"] = share_data.get("image_url", "")
                    metadata["name"] = share_data.get("name", "")
                    content_types["share"] += 1
                elif msg.get("attachments"):
                    # Media attachment (image, video, file)
                    # FIX 2026-02-02: Support both Meta formats:
                    # - Dict format: {"data": [{...}]}
                    # - List format: [{...}]
                    raw_attachments = msg.get("attachments", {})
                    if isinstance(raw_attachments, dict):
                        attachments = raw_attachments.get("data", [])
                    elif isinstance(raw_attachments, list):
                        attachments = raw_attachments
                    else:
                        attachments = []
                    if attachments:
                        att = attachments[0]
                        att_type_raw = (att.get("type") or "").lower()

                        # Structure-based detection (Instagram often omits explicit type)
                        has_video = att.get("video_data") is not None
                        has_image = att.get("image_data") is not None
                        has_audio = att.get("audio_data") is not None
                        is_sticker = att.get("render_as_sticker", False)
                        is_animated = att.get("animated_gif_url") is not None

                        # Try new payload format first, then legacy formats
                        payload = att.get("payload", {})
                        payload_url = payload.get("url") if isinstance(payload, dict) else None
                        legacy_url = (
                            att.get("video_data", {}).get("url")
                            or att.get("image_data", {}).get("url")
                            or att.get("audio_data", {}).get("url")
                            or att.get("url")
                        )
                        att_url = payload_url or legacy_url or ""

                        # Determine type: prefer structure-based, fallback to explicit type
                        if "video" in att_type_raw or has_video:
                            msg_text = "[Video]"
                            metadata["type"] = "video"
                        elif "audio" in att_type_raw or has_audio:
                            msg_text = "[Audio]"
                            metadata["type"] = "audio"
                        elif is_sticker:
                            msg_text = "[Sticker]"
                            metadata["type"] = "sticker"
                        elif is_animated or "gif" in att_type_raw:
                            msg_text = "[GIF]"
                            metadata["type"] = "gif"
                            att_url = att.get("animated_gif_url") or att_url
                        elif "image" in att_type_raw or "photo" in att_type_raw or has_image:
                            msg_text = "[Imagen]"
                            metadata["type"] = "image"
                        elif "share" in att_type_raw or "post" in att_type_raw:
                            msg_text = "[Post compartido]"
                            metadata["type"] = "shared_post"
                        elif att_type_raw:
                            msg_text = f"[{att_type_raw.title()}]"
                            metadata["type"] = att_type_raw
                        else:
                            msg_text = "[Archivo]"
                            metadata["type"] = "file"
                        metadata["url"] = att_url
                        metadata["captured_at"] = datetime.utcnow().isoformat() + "Z"
                    else:
                        msg_text = "[Adjunto]"
                        metadata["type"] = "attachment"
                    content_types["attachment"] += 1
                elif msg.get("story"):
                    # Story mention or reply
                    story = msg.get("story", {})
                    if story.get("mention"):
                        msg_text = "[Te mencionó en su story]"
                        metadata["type"] = "story_mention"
                    else:
                        msg_text = "[Respuesta a story]"
                        metadata["type"] = "story_reply"
                    metadata["story_id"] = story.get("id", "")
                    content_types["story"] += 1
                elif msg.get("shares"):
                    # Shared content (post, reel, profile)
                    shares = msg.get("shares", {}).get("data", [])
                    if shares:
                        share = shares[0]
                        share_link = share.get("link", "")
                        msg_text = (
                            f"[Compartido: {share_link}]"
                            if share_link
                            else "[Contenido compartido]"
                        )
                        metadata["type"] = "share"
                        metadata["url"] = share_link
                    else:
                        msg_text = "[Contenido compartido]"
                        metadata["type"] = "share"
                    content_types["share"] += 1
                elif msg.get("reactions"):
                    # Reaction to a message
                    reactions = msg.get("reactions", {}).get("data", [])
                    if reactions:
                        emoji = reactions[0].get("reaction", "❤️")
                        # Ensure heart emoji has variation selector (U+FE0F) for red rendering
                        if emoji == "❤" or emoji == "\u2764":
                            emoji = "❤️"
                        msg_text = f"[Reacción: {emoji}]"
                        metadata["emoji"] = emoji
                    else:
                        msg_text = "[Reacción]"
                    metadata["type"] = "reaction"
                    content_types["reaction"] += 1
                elif msg.get("sticker"):
                    # Sticker
                    msg_text = "[Sticker]"
                    metadata["type"] = "sticker"
                    metadata["sticker_id"] = msg.get("sticker", "")
                    content_types["sticker"] += 1
                else:
                    # Check if this is an empty/deleted message (no content at all)
                    has_any_content = (
                        msg.get("message") or
                        msg.get("attachments") or
                        msg.get("share") or
                        msg.get("shares") or
                        msg.get("story") or
                        msg.get("sticker") or
                        msg.get("reactions")
                    )
                    if not has_any_content:
                        # Empty message - likely deleted or expired media
                        msg_text = "[Mensaje eliminado]"
                        metadata["type"] = "deleted"
                        content_types["deleted"] = content_types.get("deleted", 0) + 1
                    else:
                        # Truly unknown type - save with debug info
                        msg_text = "[Media]"
                        metadata["type"] = "unknown"
                        metadata["raw_keys"] = list(msg.keys())
                        content_types["unknown"] += 1

                # Check timestamp
                msg_time = None
                if msg.get("created_time"):
                    try:
                        msg_time = datetime.fromisoformat(
                            msg["created_time"].replace("+0000", "+00:00")
                        )
                        if msg_time < days_limit_ago:
                            skipped_old += 1
                            continue
                    except ValueError:
                        pass

                # Check for duplicate - but UPDATE if existing has type="unknown"
                existing = session.query(Message).filter_by(platform_message_id=msg_id).first()
                if existing:
                    # If existing message has unknown type and new extraction has better type, update it
                    existing_type = (existing.msg_metadata or {}).get("type", "")
                    new_type = metadata.get("type", "unknown")
                    if existing_type == "unknown" and new_type != "unknown":
                        # Update the existing message with new metadata
                        existing.content = msg_text
                        existing.msg_metadata = metadata
                        updated_unknown += 1
                    else:
                        skipped_duplicate += 1
                    continue

                # Determine role
                from_id = msg.get("from", {}).get("id")
                role = "assistant" if from_id in creator_ids else "user"

                new_msg = Message(
                    lead_id=lead.id,
                    role=role,
                    content=msg_text,
                    platform_message_id=msg_id,
                    msg_metadata=metadata if metadata else {},
                )
                if msg_time:
                    new_msg.created_at = msg_time
                session.add(new_msg)
                saved_count += 1

            session.commit()

            # Update lead timestamps
            lead_messages = (
                session.query(Message).filter_by(lead_id=lead.id).order_by(Message.created_at).all()
            )
            if lead_messages:
                lead.first_contact_at = lead_messages[0].created_at
                lead.last_contact_at = lead_messages[-1].created_at
                session.commit()

            return {
                "status": "success",
                "username": username,
                "conversation_id": target_conv_id,
                "follower_id": target_follower_id,
                "pages_fetched": pages_fetched + 1,
                "total_api_messages": len(all_messages),
                "messages_saved": saved_count,
                "updated_unknown": updated_unknown,
                "skipped_duplicate": skipped_duplicate,
                "skipped_old": skipped_old,
                "skipped_no_id": skipped_no_id,
                "content_types": content_types,
                "lead_id": str(lead.id),
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FullSync] Error: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.get("/debug-raw-messages/{creator_id}/{username}")
async def debug_raw_messages(creator_id: str, username: str):
    """
    DEBUG: Get raw Instagram API response for messages to see what fields are actually returned.
    This helps debug why media rendering isn't working.
    """
    import httpx
    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

        access_token = creator.instagram_token
        ig_user_id = creator.instagram_user_id
        ig_page_id = creator.instagram_page_id

        if not access_token:
            raise HTTPException(status_code=400, detail="Creator has no Instagram token")

        # Dual API strategy
        if ig_page_id:
            api_base = "https://graph.facebook.com/v21.0"
            conv_id_for_api = ig_page_id
            conv_extra_params = {"platform": "instagram"}
        else:
            api_base = "https://graph.instagram.com/v21.0"
            conv_id_for_api = ig_user_id
            conv_extra_params = {}

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Get conversations
            conv_resp = await client.get(
                f"{api_base}/{conv_id_for_api}/conversations",
                params={
                    **conv_extra_params,
                    "access_token": access_token,
                    "limit": 20,
                    "fields": "id,updated_time",
                },
            )

            if conv_resp.status_code != 200:
                return {
                    "error": f"Conversations API error: {conv_resp.status_code}",
                    "response": conv_resp.text,
                }

            conversations = conv_resp.json().get("data", [])

            # Find conversation with target username
            target_conv_id = None
            for conv in conversations:
                conv_id = conv.get("id")
                if not conv_id:
                    continue

                msg_resp = await client.get(
                    f"{api_base}/{conv_id}/messages",
                    params={
                        "fields": "id,message,from,to,created_time",
                        "access_token": access_token,
                        "limit": 3,
                    },
                )
                if msg_resp.status_code == 200:
                    for msg in msg_resp.json().get("data", []):
                        if msg.get("from", {}).get("username") == username:
                            target_conv_id = conv_id
                            break
                        for recipient in msg.get("to", {}).get("data", []):
                            if recipient.get("username") == username:
                                target_conv_id = conv_id
                                break
                if target_conv_id:
                    break

            if not target_conv_id:
                return {"error": f"Conversation with {username} not found"}

            # Get messages with ALL possible fields
            msg_resp = await client.get(
                f"{api_base}/{target_conv_id}/messages",
                params={
                    "fields": "id,message,from,to,created_time,attachments,story,shares,reactions,sticker,is_unsupported",
                    "access_token": access_token,
                    "limit": 20,
                },
            )

            raw_messages = (
                msg_resp.json() if msg_resp.status_code == 200 else {"error": msg_resp.text}
            )

            # Analyze what fields are present in each message
            field_analysis = []
            for msg in raw_messages.get("data", []):
                analysis = {
                    "id": msg.get("id", "")[:20] + "...",
                    "has_message_text": bool(msg.get("message")),
                    "message_preview": (
                        (msg.get("message", "")[:50] + "...") if msg.get("message") else None
                    ),
                    "has_attachments": bool(msg.get("attachments")),
                    "has_story": bool(msg.get("story")),
                    "has_shares": bool(msg.get("shares")),
                    "has_reactions": bool(msg.get("reactions")),
                    "has_sticker": bool(msg.get("sticker")),
                    "is_unsupported": msg.get("is_unsupported"),
                    "all_keys": list(msg.keys()),
                }
                if msg.get("attachments"):
                    analysis["attachments_data"] = msg.get("attachments")
                if msg.get("story"):
                    analysis["story_data"] = msg.get("story")
                if msg.get("shares"):
                    analysis["shares_data"] = msg.get("shares")
                field_analysis.append(analysis)

            return {
                "conversation_id": target_conv_id,
                "username": username,
                "total_messages": len(raw_messages.get("data", [])),
                "field_analysis": field_analysis,
                "raw_messages": raw_messages.get("data", [])[:5],  # First 5 raw messages
            }

    finally:
        session.close()


@router.post("/run-migration/email-capture")
async def run_email_capture_migration():
    """
    Run migration to add email capture tables and columns.
    Safe to run multiple times (uses IF NOT EXISTS).
    """
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            # Add email_capture_config column
            session.execute(
                text(
                    """
                ALTER TABLE creators
                ADD COLUMN IF NOT EXISTS email_capture_config JSONB DEFAULT NULL
            """
                )
            )

            # Create unified_profiles table
            session.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS unified_profiles (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255),
                    phone VARCHAR(50),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """
                )
            )

            # Create platform_identities table
            session.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS platform_identities (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    unified_profile_id UUID REFERENCES unified_profiles(id),
                    creator_id UUID REFERENCES creators(id),
                    platform VARCHAR(50) NOT NULL,
                    platform_user_id VARCHAR(255) NOT NULL,
                    username VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """
                )
            )

            # Create unique index
            session.execute(
                text(
                    """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_platform_identity_unique
                ON platform_identities(platform, platform_user_id)
            """
                )
            )

            # Create email_ask_tracking table
            session.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS email_ask_tracking (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    creator_id UUID REFERENCES creators(id),
                    platform VARCHAR(50) NOT NULL,
                    platform_user_id VARCHAR(255) NOT NULL,
                    ask_level INTEGER DEFAULT 0,
                    last_asked_at TIMESTAMP WITH TIME ZONE,
                    declined_count INTEGER DEFAULT 0,
                    captured_email VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """
                )
            )

            # Create index for fast lookups
            session.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_email_ask_tracking_lookup
                ON email_ask_tracking(platform, platform_user_id)
            """
                )
            )

            session.commit()
            logger.info("Email capture migration completed successfully")

            return {
                "status": "success",
                "message": "Migration completed",
                "tables_created": ["unified_profiles", "platform_identities", "email_ask_tracking"],
                "columns_added": ["creators.email_capture_config"],
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/refresh-all-tokens")
async def refresh_all_instagram_tokens():
    """
    Cron job: Revisar todos los tokens de Instagram y refrescar los que expiran pronto.

    Diseñado para ser llamado diariamente por un cron job.

    Refresca tokens que expiran en menos de 7 días.
    Los tokens long-lived duran 60 días y se pueden refrescar indefinidamente.
    """
    try:
        from api.database import SessionLocal
        from core.token_refresh_service import refresh_all_creator_tokens

        session = SessionLocal()
        try:
            result = await refresh_all_creator_tokens(session)
            return {"status": "success", **result}
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/refresh-token/{creator_id}")
async def refresh_creator_token(creator_id: str):
    """
    Refrescar el token de Instagram de un creator específico.

    Args:
        creator_id: Nombre o UUID del creator

    Returns:
        Estado del refresh (success/skip/error)
    """
    try:
        from api.database import SessionLocal
        from core.token_refresh_service import check_and_refresh_if_needed

        session = SessionLocal()
        try:
            result = await check_and_refresh_if_needed(creator_id, session)
            return {"status": "success" if result.get("success") else "error", **result}
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Token refresh failed for {creator_id}: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/exchange-token/{creator_id}")
async def exchange_short_lived_token(creator_id: str, short_lived_token: str):
    """
    Convertir un token short-lived (1-2h) a long-lived (60 días).

    Usar después del OAuth flow para obtener un token duradero.

    Args:
        creator_id: Nombre o UUID del creator
        short_lived_token: Token de corta duración del OAuth

    Returns:
        Nuevo token long-lived y fecha de expiración
    """
    try:
        from api.database import SessionLocal
        from core.token_refresh_service import exchange_for_long_lived_token
        from sqlalchemy import text

        # Exchange token
        new_token_data = await exchange_for_long_lived_token(short_lived_token)

        if not new_token_data:
            return {
                "status": "error",
                "error": "Failed to exchange token. Check META_APP_SECRET is configured.",
            }

        # Save to database
        session = SessionLocal()
        try:
            session.execute(
                text(
                    """
                    UPDATE creators
                    SET instagram_token = :token,
                        instagram_token_expires_at = :expires_at
                    WHERE id::text = :cid OR name = :cid
                """
                ),
                {
                    "token": new_token_data["token"],
                    "expires_at": new_token_data["expires_at"],
                    "cid": creator_id,
                },
            )
            session.commit()

            return {
                "status": "success",
                "token_prefix": new_token_data["token"][:20] + "...",
                "expires_at": new_token_data["expires_at"].isoformat(),
                "expires_in_days": new_token_data["expires_in"] // 86400,
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Token exchange failed for {creator_id}: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/set-token/{creator_id}")
async def set_creator_token(creator_id: str, token: str, instagram_user_id: str = None):
    """
    Set Instagram token directly for a creator.

    Use this when you already have a valid long-lived token
    (e.g., from Meta Developer Portal or manual OAuth).

    Args:
        creator_id: Nombre del creator
        token: Token de Instagram válido
        instagram_user_id: ID de usuario de Instagram (opcional)
    """
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            # Build update query
            if instagram_user_id:
                session.execute(
                    text(
                        """
                        UPDATE creators
                        SET instagram_token = :token,
                            instagram_user_id = :ig_user_id
                        WHERE name = :cid
                    """
                    ),
                    {"token": token, "ig_user_id": instagram_user_id, "cid": creator_id},
                )
            else:
                session.execute(
                    text(
                        """
                        UPDATE creators
                        SET instagram_token = :token
                        WHERE name = :cid
                    """
                    ),
                    {"token": token, "cid": creator_id},
                )
            session.commit()

            return {
                "status": "success",
                "creator_id": creator_id,
                "token_prefix": token[:20] + "...",
                "instagram_user_id": instagram_user_id,
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Set token failed for {creator_id}: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/set-page-token/{creator_id}")
async def set_page_access_token(creator_id: str, token: str):
    """
    Manually set a Page Access Token for Instagram Messaging.

    Use this when the OAuth flow doesn't return a proper Page token.
    Get the token from Graph API Explorer:
    1. Go to https://developers.facebook.com/tools/explorer/
    2. Select your App
    3. Select "Page" (not User) for the token type
    4. Add permissions: pages_messaging, instagram_manage_messages
    5. Generate and copy the token

    Args:
        creator_id: Creator name or UUID
        token: Page Access Token (should start with 'EAA')
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator

        # Validate token format
        if not token.startswith("EAA"):
            logger.warning(f"Token doesn't start with EAA - may not be a Page token")

        session = SessionLocal()
        try:
            creator = (
                session.query(Creator)
                .filter((Creator.name == creator_id) | (Creator.id == creator_id))
                .first()
            )

            if not creator:
                return {"status": "error", "error": f"Creator {creator_id} not found"}

            old_prefix = creator.instagram_token[:15] if creator.instagram_token else "NONE"
            creator.instagram_token = token
            session.commit()

            logger.info(f"Set Page token for {creator_id}: {old_prefix}... -> {token[:15]}...")

            return {
                "status": "success",
                "creator_id": creator_id,
                "old_token_prefix": old_prefix,
                "new_token_prefix": token[:15] + "...",
                "token_type": (
                    "PAGE (EAA)"
                    if token.startswith("EAA")
                    else "INSTAGRAM (IGAAT)" if token.startswith("IGAAT") else "UNKNOWN"
                ),
                "valid_for_messaging": token.startswith("EAA"),
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error setting page token: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/demo-status")
async def get_demo_status():
    """Check if demo reset is enabled and get current data counts"""
    counts = {}

    try:
        from api.database import DATABASE_URL, SessionLocal

        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator, Lead, Message, NurturingSequence, Product

                counts["creators"] = session.query(Creator).count()
                counts["leads"] = session.query(Lead).count()
                counts["messages"] = session.query(Message).count()
                counts["products"] = session.query(Product).count()
                counts["sequences"] = session.query(NurturingSequence).count()

                # Get bot status and onboarding status
                creators = session.query(Creator).all()
                counts["creator_statuses"] = {
                    c.name: {
                        "bot_active": c.bot_active,
                        "onboarding_completed": c.onboarding_completed,
                        "copilot_mode": c.copilot_mode,
                        "has_instagram": bool(c.instagram_token),
                    }
                    for c in creators
                }

            finally:
                session.close()
    except Exception as e:
        counts["db_error"] = str(e)

    # Check tone profiles
    try:
        from core.tone_service import list_profiles

        counts["tone_profiles"] = list_profiles()
    except Exception as e:
        counts["tone_profiles_error"] = str(e)

    # Check RAG documents
    try:
        from core.rag import get_hybrid_rag

        rag = get_hybrid_rag()
        counts["rag_documents"] = rag.count()
    except Exception as e:
        counts["rag_error"] = str(e)

    return {
        "demo_reset_enabled": DEMO_RESET_ENABLED,
        "counts": counts,
        "endpoints": {
            "reset_all": "POST /admin/reset-db",
            "reset_creator": "POST /admin/reset-creator/{creator_id}",
            "demo_status": "GET /admin/demo-status",
        },
    }


@router.post("/rescore-leads/{creator_id}")
async def rescore_leads(creator_id: str):
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
            CATEGORIAS_CONFIG,
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
                    "interesado": 0,
                    "caliente": 0,
                    "cliente": 0,
                    "fantasma": 0,
                },
                "details": [],
            }

            for lead in leads:
                messages = (
                    session.query(Message)
                    .filter_by(lead_id=lead.id)
                    .order_by(Message.created_at)
                    .all()
                )

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
                lead.purchase_intent = resultado.intent_score

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
async def get_lead_categories():
    """
    Obtener configuración de categorías de leads para el frontend.

    Retorna colores, iconos, labels y descripciones de cada categoría.
    """
    from core.lead_categorization import CATEGORIAS_CONFIG

    return {"status": "success", "categories": CATEGORIAS_CONFIG}


@router.delete("/cleanup-test-leads/{creator_id}")
async def cleanup_test_leads(creator_id: str):
    """
    Eliminar leads de test y leads sin username.

    Elimina:
    - Leads sin username (NULL o vacío)
    - Leads con username que empieza con 'test'
    - Leads con platform_user_id que empieza con 'test'
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message
        from sqlalchemy import or_, text

        session = SessionLocal()
        try:
            # Get creator
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"status": "error", "error": f"Creator not found: {creator_id}"}

            # Find test leads
            test_leads = (
                session.query(Lead)
                .filter(
                    Lead.creator_id == creator.id,
                    or_(
                        Lead.username == None,
                        Lead.username == "",
                        Lead.username.like("test%"),
                        Lead.platform_user_id.like("test%"),
                    ),
                )
                .all()
            )

            lead_ids = [l.id for l in test_leads]

            if not lead_ids:
                return {
                    "status": "success",
                    "message": "No test leads found",
                    "deleted_leads": 0,
                    "deleted_messages": 0,
                }

            # Delete messages first (foreign key)
            deleted_messages = (
                session.query(Message)
                .filter(Message.lead_id.in_(lead_ids))
                .delete(synchronize_session=False)
            )

            # Delete leads
            deleted_leads = (
                session.query(Lead).filter(Lead.id.in_(lead_ids)).delete(synchronize_session=False)
            )

            session.commit()

            logger.info(
                f"[Cleanup] Deleted {deleted_leads} test leads and {deleted_messages} messages for {creator_id}"
            )

            return {
                "status": "success",
                "creator_id": creator_id,
                "deleted_leads": deleted_leads,
                "deleted_messages": deleted_messages,
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Cleanup failed for {creator_id}: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/debug-instagram-api/{creator_id}")
async def debug_instagram_api(creator_id: str):
    """
    Debug: Ver qué retorna la API de Instagram para conversaciones y mensajes.
    Uses centralized get_instagram_credentials() for consistent token lookup.
    """
    import httpx
    from api.services import db_service

    try:
        # Use centralized function for Instagram credentials
        creds = db_service.get_instagram_credentials(creator_id)
        if not creds["success"]:
            return {"error": creds["error"]}

        ig_user_id = creds["user_id"] or creds["page_id"]
        page_id = creds["page_id"]
        access_token = creds["token"]

        # Estrategia dual: usar Facebook API con page_id si existe, sino Instagram API
        if page_id:
            api_base = "https://graph.facebook.com/v21.0"
            conv_id_for_api = page_id
            conv_extra_params = {"platform": "instagram"}
        else:
            api_base = "https://graph.instagram.com/v21.0"
            conv_id_for_api = ig_user_id
            conv_extra_params = {}

        results = {
            "ig_user_id": ig_user_id,
            "page_id": page_id,
            "api_used": "Facebook" if page_id else "Instagram",
            "conversations": [],
            "sample_messages": [],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get conversations
            conv_url = f"{api_base}/{conv_id_for_api}/conversations"
            conv_resp = await client.get(
                conv_url, params={**conv_extra_params, "access_token": access_token, "limit": 5}
            )

            if conv_resp.status_code != 200:
                results["conversations_error"] = conv_resp.json()
                return results

            conv_data = conv_resp.json()
            conversations = conv_data.get("data", [])
            results["conversations_count"] = len(conversations)

            # Try to get messages for first 3 conversations
            for i, conv in enumerate(conversations[:3]):
                conv_id = conv.get("id")
                conv_info = {"conv_id": conv_id, "conv_data": conv}

                # Get messages
                msg_url = f"{api_base}/{conv_id}/messages"
                msg_resp = await client.get(
                    msg_url,
                    params={
                        "fields": "id,message,from,to,created_time",
                        "access_token": access_token,
                        "limit": 3,
                    },
                )

                if msg_resp.status_code != 200:
                    conv_info["messages_error"] = msg_resp.json()
                else:
                    msg_data = msg_resp.json()
                    conv_info["messages"] = msg_data.get("data", [])
                    conv_info["messages_count"] = len(conv_info["messages"])

                results["sample_messages"].append(conv_info)

        return results

    except Exception as e:
        return {"error": str(e)}


@router.get("/debug-sync-logic/{creator_id}")
async def debug_sync_logic(creator_id: str):
    """
    Debug: Simular exactamente lo que hace sync_worker para identificar
    por qué los mensajes no se guardan.
    """
    import httpx
    from api.services import db_service

    try:
        creds = db_service.get_instagram_credentials(creator_id)
        if not creds["success"]:
            return {"error": creds["error"]}

        ig_user_id = creds["user_id"] or creds["page_id"]
        ig_page_id = creds["page_id"]
        creator_ids = {ig_user_id, ig_page_id} - {None}
        access_token = creds["token"]

        # Usar la misma lógica que sync_worker
        if ig_page_id:
            api_base = "https://graph.facebook.com/v21.0"
            conv_id_for_api = ig_page_id
            conv_extra_params = {"platform": "instagram"}
        else:
            api_base = "https://graph.instagram.com/v21.0"
            conv_id_for_api = ig_user_id
            conv_extra_params = {}

        results = {
            "creator_ids": list(creator_ids),
            "api_base": api_base,
            "conversations_analysis": [],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get conversations
            conv_resp = await client.get(
                f"{api_base}/{conv_id_for_api}/conversations",
                params={**conv_extra_params, "access_token": access_token, "limit": 3},
            )

            if conv_resp.status_code != 200:
                return {"error": f"Conversations API error: {conv_resp.json()}"}

            conversations = conv_resp.json().get("data", [])

            for conv in conversations[:3]:
                conv_id = conv.get("id")
                conv_analysis = {
                    "conv_id": conv_id,
                    "messages_raw": [],
                    "follower_detection": {},
                    "messages_would_save": [],
                }

                # Get messages
                msg_resp = await client.get(
                    f"{api_base}/{conv_id}/messages",
                    params={
                        "fields": "id,message,from,to,created_time",
                        "access_token": access_token,
                        "limit": 10,
                    },
                )

                if msg_resp.status_code != 200:
                    conv_analysis["messages_error"] = msg_resp.json()
                    results["conversations_analysis"].append(conv_analysis)
                    continue

                messages = msg_resp.json().get("data", [])
                conv_analysis["total_messages"] = len(messages)

                # Simular lógica de identificación de follower
                follower_id = None
                follower_username = None

                for msg in messages:
                    from_data = msg.get("from", {})
                    from_id = from_data.get("id")
                    from_username = from_data.get("username", "unknown")
                    msg_text = msg.get("message", "")

                    conv_analysis["messages_raw"].append(
                        {
                            "id": msg.get("id"),
                            "from_id": from_id,
                            "from_username": from_username,
                            "is_creator": from_id in creator_ids if from_id else "no_from_id",
                            "has_text": bool(msg_text),
                            "text_preview": msg_text[:50] if msg_text else "(empty)",
                        }
                    )

                    # Lógica de sync_worker para encontrar follower
                    if from_id and from_id not in creator_ids and not follower_id:
                        follower_id = from_id
                        follower_username = from_username

                conv_analysis["follower_detection"] = {
                    "found": bool(follower_id),
                    "follower_id": follower_id,
                    "follower_username": follower_username,
                    "reason": (
                        "Found non-creator sender"
                        if follower_id
                        else "All senders are in creator_ids or no from.id"
                    ),
                }

                # Simular qué mensajes se guardarían
                for msg in messages:
                    msg_id = msg.get("id")
                    msg_text = msg.get("message", "")
                    from_id = msg.get("from", {}).get("id")

                    would_save = bool(msg_text) and bool(msg_id)
                    role = "assistant" if from_id in creator_ids else "user"

                    conv_analysis["messages_would_save"].append(
                        {
                            "id": msg_id,
                            "would_save": would_save,
                            "skip_reason": (
                                None if would_save else ("no_text" if not msg_text else "no_id")
                            ),
                            "role": role,
                        }
                    )

                results["conversations_analysis"].append(conv_analysis)

        return results

    except Exception as e:
        import traceback

        return {"error": str(e), "traceback": traceback.format_exc()}


@router.get("/debug-orphaned-messages/{creator_id}")
async def debug_orphaned_messages(creator_id: str):
    """
    Diagnóstico: Buscar mensajes huérfanos o duplicados que impiden el sync.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message
        from sqlalchemy import text

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"error": f"Creator '{creator_id}' not found"}

            # 1. Contar mensajes totales en la BD
            total_messages = session.query(Message).count()

            # 2. Leads actuales del creator
            leads = session.query(Lead).filter_by(creator_id=creator.id).all()
            lead_ids = [str(l.id) for l in leads]
            lead_count = len(leads)

            # 3. Mensajes vinculados a leads de este creator
            if lead_ids:
                creator_messages = (
                    session.query(Message)
                    .filter(Message.lead_id.in_([l.id for l in leads]))
                    .count()
                )
            else:
                creator_messages = 0

            # 4. Mensajes con platform_message_id de Instagram (posibles duplicados)
            ig_messages = (
                session.query(Message)
                .filter(
                    Message.platform_message_id.like(
                        "aWdf%"
                    )  # Instagram message IDs start with aWdf
                )
                .all()
            )

            # Analizar a qué leads pertenecen
            orphaned = []
            for msg in ig_messages[:20]:  # Limitar para no sobrecargar
                lead = session.query(Lead).filter_by(id=msg.lead_id).first()
                orphaned.append(
                    {
                        "msg_id": str(msg.id)[:8],
                        "platform_msg_id": msg.platform_message_id[:30] + "...",
                        "lead_id": str(msg.lead_id)[:8] if msg.lead_id else None,
                        "lead_exists": lead is not None,
                        "lead_creator": lead.creator_id == creator.id if lead else False,
                        "content_preview": msg.content[:30] if msg.content else "(empty)",
                    }
                )

            return {
                "creator_id": creator_id,
                "creator_uuid": str(creator.id),
                "total_messages_in_db": total_messages,
                "leads_for_creator": lead_count,
                "messages_for_creator": creator_messages,
                "instagram_messages_sample": orphaned,
                "diagnosis": (
                    "Messages exist but not linked to current creator's leads"
                    if len(ig_messages) > 0 and creator_messages == 0
                    else "OK" if creator_messages > 0 else "No messages found"
                ),
            }

        finally:
            session.close()

    except Exception as e:
        import traceback

        return {"error": str(e), "traceback": traceback.format_exc()}


@router.post("/clean-and-sync/{creator_id}")
async def clean_and_sync(creator_id: str, max_convs: int = 10):
    """
    Limpia mensajes huérfanos y hace sync limpio.

    1. Elimina TODOS los mensajes con platform_message_id de Instagram
    2. Ejecuta un sync fresco
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        session = SessionLocal()
        results = {"cleaned": {"orphaned_messages": 0}, "sync": {}}

        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"error": f"Creator '{creator_id}' not found"}

            # 1. Eliminar TODOS los mensajes de Instagram (empezar fresco)
            deleted = (
                session.query(Message)
                .filter(Message.platform_message_id.like("aWdf%"))
                .delete(synchronize_session="fetch")
            )
            results["cleaned"]["orphaned_messages"] = deleted
            session.commit()
            logger.info(f"Deleted {deleted} Instagram messages for clean sync")

        finally:
            session.close()

        # 2. Ejecutar sync
        sync_result = await simple_dm_sync(creator_id, max_convs)
        results["sync"] = sync_result

        return results

    except Exception as e:
        import traceback

        return {"error": str(e), "traceback": traceback.format_exc()}


@router.post("/simple-dm-sync/{creator_id}")
async def simple_dm_sync(creator_id: str, max_convs: int = 10):
    """
    [DEPRECATED] Use /onboarding/sync-instagram-dms-background instead.

    Simple DM sync with rate limiting (2s delay between conversations).
    """
    import asyncio
    import logging
    from datetime import datetime

    import httpx
    from api.services import db_service

    _logger = logging.getLogger(__name__)
    _logger.warning(f"[DEPRECATED] /admin/simple-dm-sync called for {creator_id}")

    DELAY_BETWEEN_CONVS = 2.0

    results = {
        "conversations_processed": 0,
        "messages_saved": 0,
        "messages_empty": 0,
        "messages_duplicate": 0,
        "messages_filtered_180days": 0,
        "messages_with_attachments": 0,
        "leads_created": 0,
        "errors": [],
        "rate_limited": False,
    }

    # First check Instagram credentials using centralized function
    creds = db_service.get_instagram_credentials(creator_id)
    if not creds["success"]:
        return {"error": creds["error"]}

    # IMPORTANT: Instagram has TWO IDs for the same account:
    # - page_id: appears in message from.id (e.g., 17841407135263418)
    # - user_id: used for API calls (e.g., 26196963493255185)
    # We need to check BOTH when identifying if a message is from the creator
    ig_user_id = creds["user_id"] or creds["page_id"]
    ig_page_id = creds["page_id"]
    creator_ids = {ig_user_id, ig_page_id} - {None}  # Set of all creator IDs
    access_token = creds["token"]

    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message

        if not DATABASE_URL or not SessionLocal:
            return {"error": "Database not configured"}

        session = SessionLocal()
        try:
            # Get creator for UUID (needed for FK relationships)
            creator = session.query(Creator).filter_by(name=creator_id).first()

            # Estrategia dual: usar Facebook API con page_id si existe, sino Instagram API
            if ig_page_id:
                api_base = "https://graph.facebook.com/v21.0"
                conv_id_for_api = ig_page_id
                conv_extra_params = {"platform": "instagram"}
            else:
                api_base = "https://graph.instagram.com/v21.0"
                conv_id_for_api = ig_user_id
                conv_extra_params = {}

            async with httpx.AsyncClient(timeout=60.0) as client:
                # Get conversations with updated_time
                conv_resp = await client.get(
                    f"{api_base}/{conv_id_for_api}/conversations",
                    params={
                        **conv_extra_params,
                        "access_token": access_token,
                        "limit": max_convs,
                        "fields": "id,updated_time",
                    },
                )

                if conv_resp.status_code != 200:
                    return {"error": f"Conversations API error: {conv_resp.json()}"}

                conversations = conv_resp.json().get("data", [])

                # REGLA 1: Ordenar por updated_time (más reciente primero)
                conversations.sort(key=lambda c: c.get("updated_time", ""), reverse=True)

                for conv_idx, conv in enumerate(conversations):
                    conv_id = conv.get("id")
                    if not conv_id:
                        continue

                    # Rate limiting: delay between conversations
                    if conv_idx > 0:
                        _logger.info(
                            f"[DMSync] Rate limit delay: {DELAY_BETWEEN_CONVS}s before conv {conv_idx + 1}/{len(conversations)}"
                        )
                        await asyncio.sleep(DELAY_BETWEEN_CONVS)

                    try:
                        # Get messages for this conversation (REGLA 3+4: attachments, stories, reactions)
                        msg_resp = await client.get(
                            f"{api_base}/{conv_id}/messages",
                            params={
                                "fields": "id,message,from,to,created_time,attachments,story,reactions",
                                "access_token": access_token,
                                "limit": 50,
                            },
                        )

                        if msg_resp.status_code != 200:
                            error_data = msg_resp.json().get("error", {})
                            # Check for rate limit
                            if error_data.get("code") in [4, 17]:
                                results["errors"].append(
                                    f"Rate limit hit at conv {results['conversations_processed']}"
                                )
                                break
                            continue

                        messages = msg_resp.json().get("data", [])
                        if not messages:
                            continue

                        # Find the follower (non-creator participant)
                        # Check BOTH creator IDs (user_id and page_id)
                        follower_id = None
                        follower_username = None

                        for msg in messages:
                            from_data = msg.get("from", {})
                            from_id = from_data.get("id")
                            # Follower is someone whose ID is NOT in creator_ids
                            if from_id and from_id not in creator_ids:
                                follower_id = from_id
                                follower_username = from_data.get("username", "unknown")
                                break

                        if not follower_id:
                            # Check "to" field
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
                            continue

                        # Fetch profile picture from Instagram API
                        follower_profile_pic = None
                        try:
                            profile_resp = await client.get(
                                f"{api_base}/{follower_id}",
                                params={
                                    "fields": "id,username,name,profile_pic",
                                    "access_token": access_token,
                                },
                            )
                            if profile_resp.status_code == 200:
                                profile_data = profile_resp.json()
                                follower_profile_pic = profile_data.get("profile_pic")
                                # Also update username/name if we got better data
                                if profile_data.get("username"):
                                    follower_username = profile_data.get("username")
                        except Exception as e:
                            logger.warning(f"Could not fetch profile for {follower_id}: {e}")

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

                        # Parse conversation updated_time as fallback
                        conv_updated_time = None
                        if conv.get("updated_time"):
                            try:
                                conv_updated_time = datetime.fromisoformat(
                                    conv["updated_time"].replace("+0000", "+00:00")
                                )
                            except ValueError:
                                pass

                        # Parse message timestamps for first/last contact
                        all_msg_timestamps = []
                        user_msg_timestamps = []

                        for msg in messages:
                            if msg.get("created_time"):
                                try:
                                    ts = datetime.fromisoformat(
                                        msg["created_time"].replace("+0000", "+00:00")
                                    )
                                    all_msg_timestamps.append(ts)

                                    # Solo contar mensajes del follower para last_contact
                                    from_id = msg.get("from", {}).get("id")
                                    if from_id and from_id != ig_user_id:
                                        user_msg_timestamps.append(ts)
                                except ValueError:
                                    pass

                        first_msg_time = (
                            min(all_msg_timestamps) if all_msg_timestamps else conv_updated_time
                        )
                        # IMPORTANTE: usar último mensaje del USUARIO para fantasma
                        last_user_msg_time = (
                            max(user_msg_timestamps) if user_msg_timestamps else first_msg_time
                        )

                        if not lead:
                            lead = Lead(
                                creator_id=creator.id,
                                platform="instagram",
                                platform_user_id=follower_id,
                                username=follower_username,
                                profile_pic_url=follower_profile_pic,
                                status="new",
                                first_contact_at=first_msg_time,
                                # IMPORTANTE: usar último mensaje del USUARIO para fantasma
                                last_contact_at=last_user_msg_time or first_msg_time,
                            )
                            session.add(lead)
                            session.commit()
                            results["leads_created"] += 1
                        else:
                            # Update timestamps if we have older/newer messages
                            if first_msg_time and (
                                not lead.first_contact_at or first_msg_time < lead.first_contact_at
                            ):
                                lead.first_contact_at = first_msg_time
                            # IMPORTANTE: solo actualizar si hay mensaje del USUARIO más reciente
                            if last_user_msg_time and (
                                not lead.last_contact_at
                                or last_user_msg_time > lead.last_contact_at
                            ):
                                lead.last_contact_at = last_user_msg_time
                            # Update profile pic if we got one and lead doesn't have it
                            if follower_profile_pic and not lead.profile_pic_url:
                                lead.profile_pic_url = follower_profile_pic
                            session.commit()

                        # REGLA 2: Calcular límite de 90 días
                        from datetime import timedelta

                        # 180 days for initial import (captures more valuable conversations)
                        days_limit_ago = datetime.now().astimezone() - timedelta(days=180)

                        # Save messages
                        messages_saved_this_conv = 0
                        for msg in messages:
                            msg_id = msg.get("id")
                            msg_text = msg.get("message", "")
                            msg_metadata = {}  # Initialize for all messages

                            # REGLA 3+4: Si no hay texto, procesar attachments, stories y reacciones
                            if not msg_text:
                                # REGLA 4: Primero verificar stories y reacciones
                                story_data = msg.get("story", {})
                                reactions_data = msg.get("reactions", {}).get("data", [])

                                # Obtener emoji de reacción si existe
                                reaction_emoji = None
                                if reactions_data:
                                    reaction_emoji = reactions_data[0].get("emoji", "❤️")
                                    # Ensure heart emoji has variation selector (U+FE0F) for red rendering
                                    if reaction_emoji == "❤" or reaction_emoji == "\u2764":
                                        reaction_emoji = "❤️"

                                # Obtener link de story si existe
                                story_link = None
                                story_type = None
                                if story_data.get("reply_to"):
                                    story_link = story_data["reply_to"].get("link", "")
                                    story_type = "reply_to"
                                elif story_data.get("mention"):
                                    story_link = story_data["mention"].get("link", "")
                                    story_type = "mention"

                                # Build message with metadata for frontend rendering
                                # (msg_metadata already initialized at loop start)

                                # Construir mensaje según combinación
                                if story_type and reaction_emoji:
                                    msg_text = f"Reacción {reaction_emoji} a story"
                                    msg_metadata = {
                                        "type": "story_reaction",
                                        "url": story_link,
                                        "emoji": reaction_emoji,
                                    }
                                elif story_type == "reply_to":
                                    msg_text = "Respuesta a story"
                                    msg_metadata = {"type": "story_reply", "url": story_link}
                                elif story_type == "mention":
                                    msg_text = "Mención en story"
                                    msg_metadata = {"type": "story_mention", "url": story_link}
                                elif reaction_emoji:
                                    msg_text = f"Reacción {reaction_emoji}"
                                    msg_metadata = {"type": "reaction", "emoji": reaction_emoji}

                                # REGLA 3: Si aún no hay texto, procesar attachments
                                if not msg_text:
                                    # Check for share field at message level (shared posts/reels)
                                    share_data = msg.get("share")
                                    if share_data:
                                        logger.debug("Share field found: %s", share_data)
                                        msg_text = "Post compartido"
                                        msg_metadata = {
                                            "type": "shared_post",
                                            "url": share_data.get("link", ""),
                                            "thumbnail_url": share_data.get("image_url", ""),
                                            "name": share_data.get("name", ""),
                                            "description": share_data.get("description", ""),
                                        }
                                    else:
                                        attachments = msg.get("attachments", {}).get("data", [])
                                        if attachments:
                                            for att in attachments:
                                                # DEBUG: Log attachment structure
                                                logger.debug("Attachment: %s", att)

                                                att_type = (att.get("type") or "").lower()

                                                # Instagram sends structure-based types (no explicit type field)
                                                has_video = att.get("video_data") is not None
                                                has_image = att.get("image_data") is not None
                                                has_audio = att.get("audio_data") is not None
                                                is_sticker = att.get("render_as_sticker", False)
                                                is_animated = (
                                                    att.get("animated_gif_url") is not None
                                                )

                                                # Get URL based on structure
                                                # FIX 2026-02-02: Try payload.url first (new format)
                                                payload = att.get("payload", {})
                                                payload_url = (
                                                    payload.get("url")
                                                    if isinstance(payload, dict)
                                                    else None
                                                )

                                                if payload_url:
                                                    att_url = payload_url
                                                elif has_video:
                                                    att_url = att["video_data"].get("url")
                                                elif has_image:
                                                    att_url = att["image_data"].get("url")
                                                elif has_audio:
                                                    att_url = att["audio_data"].get("url")
                                                else:
                                                    att_url = att.get("url")

                                                # Detect type by structure or explicit type
                                                if "video" in att_type or has_video:
                                                    msg_text = "Video"
                                                    msg_metadata = {"type": "video", "url": att_url}
                                                elif "audio" in att_type or has_audio:
                                                    msg_text = "Audio"
                                                    msg_metadata = {"type": "audio", "url": att_url}
                                                elif is_sticker or is_animated:
                                                    # GIFs/Stickers
                                                    gif_url = att.get("animated_gif_url") or att_url
                                                    msg_text = "GIF"
                                                    msg_metadata = {"type": "gif", "url": gif_url}
                                                elif (
                                                    "share" in att_type
                                                    or "post" in att_type
                                                    or "media_share" in att_type
                                                ):
                                                    # Shared post (explicit type)
                                                    post_url = (
                                                        att.get("target", {}).get("url") or att_url
                                                    )
                                                    thumbnail_url = (
                                                        att.get("image_data", {}).get("url")
                                                        if att.get("image_data")
                                                        else att.get("preview_url")
                                                    )
                                                    msg_text = "Post compartido"
                                                    msg_metadata = {
                                                        "type": "shared_post",
                                                        "url": post_url,
                                                        "thumbnail_url": thumbnail_url,
                                                    }
                                                elif (
                                                    "image" in att_type
                                                    or "photo" in att_type
                                                    or has_image
                                                ):
                                                    msg_text = "Imagen"
                                                    msg_metadata = {"type": "image", "url": att_url}
                                                elif "link" in att_type:
                                                    msg_text = "Link"
                                                    msg_metadata = {"type": "link", "url": att_url}
                                                else:
                                                    # Unknown type - still save it
                                                    msg_text = "Archivo"
                                                    msg_metadata = {"type": "file", "url": att_url}
                                                break  # Solo usar el primer attachment

                            if not msg_text or not msg_id:
                                results["messages_empty"] += 1
                                continue

                            # REGLA 2: Filtrar por 90 días
                            msg_time_str = msg.get("created_time")
                            if msg_time_str:
                                try:
                                    msg_timestamp = datetime.fromisoformat(
                                        msg_time_str.replace("+0000", "+00:00")
                                    )
                                    if msg_timestamp < days_limit_ago:
                                        results["messages_filtered_180days"] += 1
                                        continue  # Skip messages older than 180 days
                                except ValueError:
                                    pass

                            # Track attachment processing
                            if msg_text.startswith("[") and msg_text.endswith("]"):
                                results["messages_with_attachments"] += 1

                            # Check if already exists
                            existing = (
                                session.query(Message).filter_by(platform_message_id=msg_id).first()
                            )

                            if existing:
                                results["messages_duplicate"] += 1
                                continue

                            from_data = msg.get("from", {})
                            # Check if sender is the creator (could be user_id OR page_id)
                            is_from_creator = from_data.get("id") in creator_ids
                            role = "assistant" if is_from_creator else "user"

                            # LINK PREVIEW: Enhance metadata with thumbnails for shared content
                            url_to_preview = detect_url_in_metadata(msg_metadata)
                            if url_to_preview:
                                msg_metadata = await generate_link_preview(
                                    url_to_preview, msg_metadata
                                )

                            new_msg = Message(
                                lead_id=lead.id,
                                role=role,
                                content=msg_text,
                                platform_message_id=msg_id,
                                msg_metadata=msg_metadata if msg_metadata else {},
                            )

                            # Parse timestamp
                            msg_time = msg.get("created_time")
                            if msg_time:
                                try:
                                    new_msg.created_at = datetime.fromisoformat(
                                        msg_time.replace("+0000", "+00:00")
                                    )
                                except ValueError:
                                    pass

                            session.add(new_msg)
                            results["messages_saved"] += 1
                            messages_saved_this_conv += 1

                        session.commit()
                        results["conversations_processed"] += 1

                        # Auto-categorizar lead después de guardar mensajes
                        if messages_saved_this_conv > 0:
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
                                    {"role": m.role, "content": m.content or ""}
                                    for m in lead_messages
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
                                if (
                                    lead.status != new_status
                                    or lead.purchase_intent != cat_result.intent_score
                                ):
                                    lead.status = new_status
                                    lead.purchase_intent = cat_result.intent_score
                                    session.commit()
                                    logger.info(
                                        f"Lead {lead.username} auto-categorizado: {cat_result.categoria} (intent: {cat_result.intent_score:.2f})"
                                    )

                            except Exception as cat_error:
                                logger.warning(f"Error en auto-categorización: {cat_error}")

                    except Exception as e:
                        results["errors"].append(f"Conv error: {str(e)}")
                        continue

            return {"status": "success", **results}

        finally:
            session.close()

    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"error": str(e), **results}


@router.post("/generate-thumbnails/{creator_id}")
async def generate_thumbnails(creator_id: str, limit: int = 10):
    """
    Generate thumbnails for messages with needs_thumbnail=true.
    Processes Instagram posts/reels using Playwright screenshots.

    Args:
        creator_id: Creator name
        limit: Max number of thumbnails to generate (default 10)

    Returns:
        Count of thumbnails generated
    """
    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message
        from sqlalchemy import and_

        if not DATABASE_URL or not SessionLocal:
            return {"error": "Database not configured"}

        # Try to import screenshot service
        try:
            from api.services.screenshot_service import PLAYWRIGHT_AVAILABLE, ScreenshotService
        except ImportError:
            return {"error": "Screenshot service not available", "playwright_available": False}

        if not PLAYWRIGHT_AVAILABLE:
            return {"error": "Playwright not installed", "playwright_available": False}

        session = SessionLocal()
        results = {"thumbnails_generated": 0, "thumbnails_failed": 0, "messages_processed": 0}

        try:
            # Get creator
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"error": f"Creator {creator_id} not found"}

            # Find messages with needs_thumbnail flag
            leads = session.query(Lead).filter_by(creator_id=creator.id).all()
            lead_ids = [l.id for l in leads]

            if not lead_ids:
                return {"error": "No leads found for creator"}

            # Query messages that need thumbnails
            messages = session.query(Message).filter(Message.lead_id.in_(lead_ids)).all()

            processed = 0
            for msg in messages:
                if processed >= limit:
                    break

                metadata = msg.msg_metadata or {}

                # Check if needs thumbnail
                if not metadata.get("needs_thumbnail"):
                    continue

                url = metadata.get("url")
                if not url:
                    continue

                results["messages_processed"] += 1
                processed += 1

                try:
                    # Generate screenshot
                    preview = await ScreenshotService.capture_instagram_post(url)

                    if preview and preview.get("thumbnail_base64"):
                        # Update metadata with thumbnail
                        metadata["thumbnail_base64"] = preview["thumbnail_base64"]
                        metadata["needs_thumbnail"] = False  # Mark as processed
                        msg.msg_metadata = metadata
                        results["thumbnails_generated"] += 1
                    else:
                        results["thumbnails_failed"] += 1

                except Exception as e:
                    logger.warning(f"Failed to generate thumbnail for {url}: {e}")
                    results["thumbnails_failed"] += 1

            session.commit()
            return {"status": "success", **results}

        finally:
            session.close()

    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"error": str(e)}


@router.delete("/clear-messages/{creator_id}")
async def clear_messages(creator_id: str):
    """
    Delete all messages for a creator to allow re-import with new features.

    WARNING: This permanently deletes all messages. Use with caution.

    Args:
        creator_id: Creator name (e.g., 'fitpack_global')

    Returns:
        Count of deleted messages
    """
    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message

        if not DATABASE_URL or not SessionLocal:
            return {"error": "Database not configured"}

        session = SessionLocal()
        try:
            # Get creator
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"error": f"Creator {creator_id} not found"}

            # Get all leads for this creator
            leads = session.query(Lead).filter_by(creator_id=creator.id).all()
            lead_ids = [l.id for l in leads]

            if not lead_ids:
                return {"status": "ok", "messages_deleted": 0, "message": "No leads found"}

            # Delete all messages for these leads
            deleted_count = (
                session.query(Message)
                .filter(Message.lead_id.in_(lead_ids))
                .delete(synchronize_session=False)
            )

            session.commit()

            return {
                "status": "success",
                "messages_deleted": deleted_count,
                "leads_count": len(lead_ids),
                "creator": creator_id,
            }

        finally:
            session.close()

    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"error": str(e)}


@router.post("/test-shared-post/{creator_id}/{lead_id}")
async def insert_test_shared_post(creator_id: str, lead_id: str):
    """
    Insert a test shared_post message with thumbnail for frontend testing.
    """
    try:
        import uuid
        from datetime import datetime, timezone

        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message

        if not DATABASE_URL or not SessionLocal:
            return {"error": "Database not configured"}

        # Get a real Instagram preview
        from api.services.screenshot_service import get_microlink_preview

        test_url = "https://www.instagram.com/p/C3xK7ZmOQVz/"
        preview = await get_microlink_preview(test_url)

        session = SessionLocal()
        try:
            # Verify creator and lead exist
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"error": f"Creator {creator_id} not found"}

            lead = session.query(Lead).filter_by(id=uuid.UUID(lead_id)).first()
            if not lead:
                return {"error": f"Lead {lead_id} not found"}

            # Create test message with shared_post
            msg_metadata = {
                "type": "shared_post",
                "platform": "instagram",
                "url": test_url,
                "thumbnail_url": preview.get("thumbnail_url") if preview else None,
                "title": preview.get("title") if preview else "Instagram Post",
                "author": preview.get("author") if preview else None,
            }

            test_msg = Message(
                lead_id=lead.id,
                role="user",
                content="Mira este post! 👀",
                msg_metadata=msg_metadata,
                created_at=datetime.now(timezone.utc),
            )
            session.add(test_msg)
            session.commit()

            return {
                "status": "success",
                "message_id": str(test_msg.id),
                "metadata": msg_metadata,
                "lead_username": lead.username,
            }

        finally:
            session.close()

    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"error": str(e)}


# =============================================================================
# SYNC QUEUE SYSTEM - Sincronización inteligente con rate limiting
# =============================================================================


@router.post("/start-sync/{creator_id}")
async def start_sync(creator_id: str, background_tasks: BackgroundTasks):
    """
    Inicia sincronización de DMs en background.

    Características:
    - Retorna inmediatamente (no-bloqueante)
    - Procesa 1 conversación cada 3 segundos
    - Pausa automática si hay rate limit
    - Guarda progreso después de cada job

    Uso:
    1. POST /admin/start-sync/fitpack_global → inicia sync
    2. GET /admin/sync-status/fitpack_global → ver progreso
    """
    from api.database import SessionLocal
    from core.sync_worker import run_sync_worker_iteration, start_sync_for_creator

    # Start the sync (queues conversations)
    result = await start_sync_for_creator(creator_id)

    if result["status"] == "started":
        # Run worker in background
        async def run_worker():
            session = SessionLocal()
            try:
                await run_sync_worker_iteration(session, creator_id)
            finally:
                session.close()

        background_tasks.add_task(run_worker)

    return result


@router.get("/sync-status/{creator_id}")
async def sync_status(creator_id: str):
    """
    Obtiene el estado actual del sync.

    Respuestas posibles:
    - status: "not_started" → No hay sync activo
    - status: "running" → Procesando conversaciones
    - status: "rate_limited" → Pausado por rate limit (auto-resume)
    - status: "completed" → Terminado
    """
    from core.sync_worker import get_sync_status

    return get_sync_status(creator_id)


@router.post("/sync-continue/{creator_id}")
async def sync_continue(creator_id: str, background_tasks: BackgroundTasks):
    """
    Continúa el sync si hay jobs pendientes.
    Útil para reanudar después de rate limit.
    """
    from api.database import SessionLocal
    from core.sync_worker import get_sync_status, run_sync_worker_iteration

    status = get_sync_status(creator_id)

    if status["status"] == "not_started":
        return {"error": "No sync started. Use /start-sync first."}

    if status["pending_jobs"] == 0:
        return {"message": "No pending jobs. Sync complete."}

    # Run worker in background
    async def run_worker():
        session = SessionLocal()
        try:
            await run_sync_worker_iteration(session, creator_id)
        finally:
            session.close()

    background_tasks.add_task(run_worker)

    return {
        "status": "continuing",
        "pending_jobs": status["pending_jobs"],
        "message": "Sync resumed in background",
    }


@router.delete("/sync-reset/{creator_id}")
async def sync_reset(creator_id: str):
    """
    Resetea el estado del sync para un creator.
    Limpia la cola y el estado.
    """
    from api.database import SessionLocal
    from api.models import SyncQueue, SyncState

    session = SessionLocal()
    try:
        # Delete queue jobs
        deleted_jobs = session.query(SyncQueue).filter_by(creator_id=creator_id).delete()

        # Delete state
        deleted_state = session.query(SyncState).filter_by(creator_id=creator_id).delete()

        session.commit()

        return {"status": "reset", "jobs_deleted": deleted_jobs, "state_deleted": deleted_state}
    finally:
        session.close()


@router.post("/fix-lead-timestamps/{creator_id}")
async def fix_lead_timestamps(creator_id: str):
    """
    Corrige las fechas de last_contact_at basándose en los mensajes guardados.

    El problema: last_contact_at se estaba guardando con el timestamp del último
    mensaje de la conversación (incluyendo mensajes del bot), pero para FANTASMA
    necesitamos el último mensaje del USUARIO.

    Esta función:
    1. Lee todos los mensajes de cada lead
    2. Calcula first_contact y last_contact correctamente
    3. last_contact = último mensaje role=user
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
                "leads_no_messages": 0,
                "leads_no_user_messages": 0,
                "details": [],
            }

            for lead in leads:
                messages = (
                    session.query(Message)
                    .filter_by(lead_id=lead.id)
                    .order_by(Message.created_at)
                    .all()
                )
                old_first = lead.first_contact_at
                old_last = lead.last_contact_at

                if not messages:
                    # Para leads SIN mensajes: last_contact = first_contact
                    # Esto permite detectarlos correctamente como fantasma
                    if lead.first_contact_at and lead.last_contact_at != lead.first_contact_at:
                        lead.last_contact_at = lead.first_contact_at
                        stats["leads_no_messages"] += 1
                        stats["leads_updated"] += 1
                        stats["details"].append(
                            {
                                "username": lead.username,
                                "old_first": str(old_first) if old_first else None,
                                "new_first": (
                                    str(lead.first_contact_at) if lead.first_contact_at else None
                                ),
                                "old_last": str(old_last) if old_last else None,
                                "new_last": (
                                    str(lead.last_contact_at) if lead.last_contact_at else None
                                ),
                                "total_messages": 0,
                                "user_messages": 0,
                                "fix_type": "no_messages_use_first_contact",
                            }
                        )
                    else:
                        stats["leads_no_messages"] += 1
                    continue

                # Separar mensajes de usuario vs bot
                user_messages = [m for m in messages if m.role == "user"]
                all_timestamps = [m.created_at for m in messages if m.created_at]
                user_timestamps = [m.created_at for m in user_messages if m.created_at]

                # first_contact = primer mensaje de cualquiera
                if all_timestamps:
                    lead.first_contact_at = min(all_timestamps)

                # last_contact = último mensaje del USUARIO
                if user_timestamps:
                    lead.last_contact_at = max(user_timestamps)
                    stats["leads_updated"] += 1

                    stats["details"].append(
                        {
                            "username": lead.username,
                            "old_first": str(old_first) if old_first else None,
                            "new_first": (
                                str(lead.first_contact_at) if lead.first_contact_at else None
                            ),
                            "old_last": str(old_last) if old_last else None,
                            "new_last": str(lead.last_contact_at) if lead.last_contact_at else None,
                            "total_messages": len(messages),
                            "user_messages": len(user_messages),
                        }
                    )
                else:
                    # Mensajes pero ninguno del usuario: usar first_contact
                    if lead.first_contact_at:
                        lead.last_contact_at = lead.first_contact_at
                        stats["leads_updated"] += 1
                    stats["leads_no_user_messages"] += 1

            session.commit()
            logger.info(f"[FixTimestamps] Updated {stats['leads_updated']} leads for {creator_id}")

            return {"status": "success", "creator_id": creator_id, **stats}

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Fix timestamps failed for {creator_id}: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# =============================================================================
# GHOST REACTIVATION - Reactivación automática de leads fantasma
# =============================================================================


@router.get("/ghost-stats/{creator_id}")
async def get_ghost_stats(creator_id: str):
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
async def reactivate_ghosts(creator_id: str, dry_run: bool = False):
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
async def get_ghost_config():
    """Obtiene la configuración actual de reactivación."""
    try:
        from core.ghost_reactivation import REACTIVATION_CONFIG

        return {"status": "success", "config": REACTIVATION_CONFIG}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/update-profile-pics/{creator_id}")
async def update_profile_pics(creator_id: str, limit: int = 20):
    """
    Endpoint ligero para actualizar SOLO fotos de perfil de Instagram.

    No hace sync de mensajes, solo obtiene profile_pic para leads existentes.
    Procesa en batches pequeños para evitar timeout.

    Args:
        creator_id: ID del creator
        limit: Máximo leads a procesar (default: 20)

    Returns:
        {"updated": 15, "failed": 2, "total": 17, "remaining": 5}
    """
    import asyncio

    import httpx
    from api.database import SessionLocal
    from api.models import Creator, Lead

    session = SessionLocal()
    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            from sqlalchemy import text

            creator = (
                session.query(Creator)
                .filter(text("id::text = :cid"))
                .params(cid=creator_id)
                .first()
            )

        if not creator:
            return {"status": "error", "error": f"Creator not found: {creator_id}"}

        # Check Instagram connection - support both page_id and user_id (IGAAT tokens)
        if not creator.instagram_token:
            return {"status": "error", "error": "Instagram not connected for this creator"}

        if not creator.instagram_page_id and not creator.instagram_user_id:
            return {"status": "error", "error": "Instagram page_id or user_id required"}

        access_token = creator.instagram_token
        # Use correct API based on token type
        # IGAAT tokens (start with IGAAT) use graph.instagram.com
        # EAA tokens (Page tokens) use graph.facebook.com
        if access_token.startswith("IGAAT"):
            api_base = "https://graph.instagram.com/v21.0"
        else:
            api_base = "https://graph.facebook.com/v21.0"

        # Get leads without profile pic
        leads_without_pic = (
            session.query(Lead)
            .filter(
                Lead.creator_id == creator.id,
                Lead.platform == "instagram",
                Lead.platform_user_id.isnot(None),
                Lead.profile_pic_url.is_(None),
            )
            .limit(limit)
            .all()
        )

        # Count total remaining
        total_remaining = (
            session.query(Lead)
            .filter(
                Lead.creator_id == creator.id,
                Lead.platform == "instagram",
                Lead.platform_user_id.isnot(None),
                Lead.profile_pic_url.is_(None),
            )
            .count()
        )

        results = {
            "updated": 0,
            "failed": 0,
            "total": len(leads_without_pic),
            "remaining": total_remaining - len(leads_without_pic),
            "details": [],
        }

        if not leads_without_pic:
            return {"status": "ok", "message": "All leads already have profile pics", **results}

        async with httpx.AsyncClient(timeout=10.0) as client:
            for lead in leads_without_pic:
                try:
                    # Fetch profile from Instagram API
                    resp = await client.get(
                        f"{api_base}/{lead.platform_user_id}",
                        params={
                            "fields": "id,username,name,profile_pic",
                            "access_token": access_token,
                        },
                    )

                    if resp.status_code == 200:
                        data = resp.json()
                        profile_pic = data.get("profile_pic")

                        if profile_pic:
                            lead.profile_pic_url = profile_pic
                            # Also update username if we got better data
                            if data.get("username") and not lead.username:
                                lead.username = data.get("username")
                            if data.get("name") and not lead.full_name:
                                lead.full_name = data.get("name")
                            session.commit()
                            results["updated"] += 1
                            results["details"].append(
                                {"username": lead.username, "status": "updated"}
                            )
                        else:
                            results["failed"] += 1
                            results["details"].append(
                                {"username": lead.username, "status": "no_pic_in_response"}
                            )
                    else:
                        results["failed"] += 1
                        results["details"].append(
                            {"username": lead.username, "status": f"api_error_{resp.status_code}"}
                        )

                    # Rate limiting: 500ms between requests
                    await asyncio.sleep(0.5)

                except Exception as e:
                    results["failed"] += 1
                    results["details"].append(
                        {"username": lead.username, "status": f"error: {str(e)[:50]}"}
                    )

        return {"status": "ok", **results}

    except Exception as e:
        logger.error(f"update_profile_pics error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        session.close()


@router.post("/generate-link-previews/{creator_id}")
async def generate_link_previews(creator_id: str, limit: int = 50):
    """
    Generate link previews for existing messages that have URLs but no preview.

    Finds messages containing URLs, extracts Open Graph metadata, and updates
    the msg_metadata field with link_preview data.

    Args:
        creator_id: ID del creator
        limit: Max messages to process (default: 50)

    Returns:
        {"updated": 10, "failed": 2, "no_urls": 38, "total": 50}
    """
    import asyncio
    import re

    from api.database import SessionLocal
    from api.models import Creator, Lead, Message
    from core.link_preview import extract_link_preview, extract_urls

    session = SessionLocal()
    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            from sqlalchemy import text

            creator = (
                session.query(Creator)
                .filter(text("id::text = :cid"))
                .params(cid=creator_id)
                .first()
            )

        if not creator:
            return {"status": "error", "error": f"Creator not found: {creator_id}"}

        # Find messages with URLs using JOIN (avoids N+1)
        # Single query: messages -> leads -> creator
        messages = (
            session.query(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(Lead.creator_id == creator.id, Message.content.ilike("%http%"))
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )

        if not messages:
            return {
                "status": "ok",
                "message": "No messages with URLs found",
                "updated": 0,
                "total": 0,
            }

        results = {
            "updated": 0,
            "failed": 0,
            "no_urls": 0,
            "already_has_preview": 0,
            "total": len(messages),
            "details": [],
        }

        for msg in messages:
            try:
                # Skip if already has link preview
                if msg.msg_metadata and msg.msg_metadata.get("link_preview"):
                    results["already_has_preview"] += 1
                    continue

                # Extract URLs
                urls = extract_urls(msg.content)
                if not urls:
                    results["no_urls"] += 1
                    continue

                # Get preview for first URL
                preview = await extract_link_preview(urls[0])

                if preview:
                    # Update message metadata (commit batched below)
                    current_metadata = msg.msg_metadata or {}
                    current_metadata["link_preview"] = preview
                    msg.msg_metadata = current_metadata

                    results["updated"] += 1
                    results["details"].append(
                        {
                            "url": urls[0][:50],
                            "title": (
                                preview.get("title", "")[:30] if preview.get("title") else None
                            ),
                            "status": "updated",
                        }
                    )

                    # Batch commit every 10 updates for efficiency
                    if results["updated"] % 10 == 0:
                        session.commit()
                else:
                    results["failed"] += 1
                    results["details"].append({"url": urls[0][:50], "status": "no_preview_data"})

                # Rate limiting - don't saturate external services
                await asyncio.sleep(0.3)

            except Exception as e:
                results["failed"] += 1
                logger.debug(f"Link preview error: {e}")

        # Final commit for remaining updates
        if results["updated"] % 10 != 0:
            session.commit()

        return {"status": "ok", **results}

    except Exception as e:
        logger.error(f"generate_link_previews error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        session.close()


# =============================================================================
# LEAD SYNC: Categorize and score leads based on their conversations
# =============================================================================


@router.post("/sync-leads/{creator_id}")
async def sync_leads_from_conversations(
    creator_id: str, recategorize: bool = False, limit: int = 100
):
    """
    Sync and categorize leads from their conversations.

    This endpoint:
    1. Gets all leads for a creator
    2. Analyzes their messages for purchase intent signals
    3. Updates status (nuevo/interesado/caliente/fantasma) and purchase_intent score
    4. Returns statistics about the sync

    Args:
        creator_id: Creator name or UUID
        recategorize: If True, re-categorize all leads. If False, only process leads with status 'new'
        limit: Maximum number of leads to process

    Returns:
        {
            "total_leads": 50,
            "categorized": {"nuevo": 10, "interesado": 25, "caliente": 5, "fantasma": 8, "cliente": 2},
            "updated": 40,
            "skipped": 10,
            "details": [...]
        }
    """
    from datetime import timezone

    from api.database import SessionLocal
    from api.models import Creator, Lead, Message
    from core.lead_categorization import calcular_categoria, categoria_a_status_legacy
    from sqlalchemy import func, text

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
            raise HTTPException(status_code=404, detail=f"Creator not found: {creator_id}")

        # Get leads to process
        query = session.query(Lead).filter(Lead.creator_id == creator.id)

        # If not recategorizing, only process new leads
        if not recategorize:
            query = query.filter(Lead.status == "new")

        leads = query.order_by(Lead.last_contact_at.desc()).limit(limit).all()

        if not leads:
            return {
                "status": "ok",
                "message": "No leads to process",
                "total_leads": 0,
                "updated": 0,
            }

        # Get all messages for these leads in single query (avoid N+1)
        lead_ids = [lead.id for lead in leads]
        messages_query = (
            session.query(Message)
            .filter(Message.lead_id.in_(lead_ids))
            .order_by(Message.lead_id, Message.created_at)
            .all()
        )

        # Group messages by lead_id
        messages_by_lead = {}
        for msg in messages_query:
            if msg.lead_id not in messages_by_lead:
                messages_by_lead[msg.lead_id] = []
            messages_by_lead[msg.lead_id].append(
                {"role": msg.role, "content": msg.content or "", "created_at": msg.created_at}
            )

        results = {
            "total_leads": len(leads),
            "updated": 0,
            "skipped": 0,
            "categorized": {
                "nuevo": 0,
                "interesado": 0,
                "caliente": 0,
                "cliente": 0,
                "fantasma": 0,
            },
            "details": [],
        }

        for lead in leads:
            try:
                msgs = messages_by_lead.get(lead.id, [])

                # Get last message from user for fantasma detection
                user_msgs = [m for m in msgs if m["role"] == "user"]
                last_user_msg_time = user_msgs[-1]["created_at"] if user_msgs else None

                # Check if is_customer from context
                ctx = lead.context or {}
                is_cliente = ctx.get("is_customer", False)

                # Calculate category
                result = calcular_categoria(
                    mensajes=msgs,
                    es_cliente=is_cliente,
                    ultimo_mensaje_lead=last_user_msg_time,
                    dias_fantasma=7,
                    lead_created_at=lead.first_contact_at,
                )

                # Map category to legacy status for compatibility
                new_status = categoria_a_status_legacy(result.categoria)

                # Check if update needed
                if (
                    lead.status == new_status
                    and abs((lead.purchase_intent or 0) - result.intent_score) < 0.01
                ):
                    results["skipped"] += 1
                    continue

                # Update lead
                old_status = lead.status
                lead.status = new_status
                lead.purchase_intent = result.intent_score

                results["updated"] += 1
                results["categorized"][result.categoria] += 1
                results["details"].append(
                    {
                        "lead_id": str(lead.id),
                        "username": lead.username,
                        "old_status": old_status,
                        "new_status": new_status,
                        "categoria": result.categoria,
                        "intent_score": round(result.intent_score, 2),
                        "razones": result.razones[:2],
                        "total_messages": len(msgs),
                    }
                )

                # Batch commit every 20 updates
                if results["updated"] % 20 == 0:
                    session.commit()

            except Exception as e:
                logger.warning(f"Error categorizing lead {lead.id}: {e}")
                results["skipped"] += 1

        # Final commit
        session.commit()

        logger.info(
            f"Sync leads for {creator_id}: {results['updated']} updated, {results['skipped']} skipped"
        )
        return {"status": "ok", **results}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"sync_leads error: {e}")
        session.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        session.close()


@router.post("/test-ingestion-v2/{creator_id}")
async def test_ingestion_v2(creator_id: str, website_url: str):
    """
    Test endpoint to run IngestionV2Pipeline directly.

    Usage: POST /admin/test-ingestion-v2/stefano?website_url=https://stefanobonanno.com
    """
    try:
        from api.database import SessionLocal
        from ingestion.v2.pipeline import IngestionV2Pipeline

        session = SessionLocal()
        try:
            pipeline = IngestionV2Pipeline(db_session=session)
            result = await pipeline.run(
                creator_id=creator_id, website_url=website_url, clean_before=True, re_verify=True
            )

            # Ensure commit is done
            session.commit()

            return {
                "status": result.status,
                "success": result.success,
                "products_saved": result.products_saved,
                "knowledge_saved": result.knowledge_saved,
                "products_count": len(result.products),
                "products": result.products[:5] if result.products else [],
                "bio": result.bio,
                "faqs_count": len(result.faqs) if result.faqs else 0,
                "faqs": result.faqs[:3] if result.faqs else [],
                "tone": result.tone,
                "errors": result.errors,
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"test_ingestion_v2 error: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------
# ADMIN PANEL ENDPOINTS (moved from main.py)
# ---------------------------------------------------------
@router.get("/creators")
async def admin_list_creators():
    """
    [ADMIN] Listar todos los creadores con estadísticas básicas.
    Requiere CLONNECT_ADMIN_KEY.
    """
    from api.auth import require_admin
    from api.routers.dm import get_dm_agent
    from core.creator_config import CreatorConfigManager

    try:
        config_manager = CreatorConfigManager()
        creators = config_manager.list_creators()
        creator_stats = []

        for creator_id in creators:
            config = config_manager.get_config(creator_id)
            if not config:
                continue

            # Obtener métricas básicas
            try:
                agent = get_dm_agent(creator_id)
                metrics = await agent.get_metrics()
                leads = await agent.get_leads()
            except Exception as e:
                metrics = {}
                logger.warning(f"Failed to get metrics for {creator_id}: {e}")
                leads = []

            creator_stats.append(
                {
                    "creator_id": creator_id,
                    "name": config.name,
                    "instagram_handle": config.instagram_handle,
                    "is_active": config.is_active,
                    "pause_reason": config.pause_reason if not config.is_active else None,
                    "total_messages": metrics.get("total_messages", 0),
                    "total_leads": len(leads),
                    "hot_leads": len([l for l in leads if l.get("score", 0) >= 0.7]),
                    "updated_at": config.updated_at,
                }
            )

        return {"status": "ok", "creators": creator_stats, "total": len(creator_stats)}

    except Exception as e:
        logger.error(f"Error listing creators: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def admin_global_stats():
    """
    [ADMIN] Estadísticas globales de la plataforma.
    Requiere CLONNECT_ADMIN_KEY.
    """
    from api.routers.dm import get_dm_agent
    from core.creator_config import CreatorConfigManager

    try:
        config_manager = CreatorConfigManager()
        creators = config_manager.list_creators()

        total_messages = 0
        total_leads = 0
        total_hot_leads = 0
        total_conversations = 0
        active_bots = 0
        paused_bots = 0

        for creator_id in creators:
            config = config_manager.get_config(creator_id)
            if config:
                if config.is_active:
                    active_bots += 1
                else:
                    paused_bots += 1

            try:
                agent = get_dm_agent(creator_id)
                metrics = await agent.get_metrics()
                leads = await agent.get_leads()
                conversations = await agent.get_all_conversations(1000)

                total_messages += metrics.get("total_messages", 0)
                total_leads += len(leads)
                total_hot_leads += len([l for l in leads if l.get("score", 0) >= 0.7])
                total_conversations += len(conversations)
            except Exception as e:
                logger.warning(f"Failed to aggregate stats: {e}")

        return {
            "status": "ok",
            "stats": {
                "total_creators": len(creators),
                "active_bots": active_bots,
                "paused_bots": paused_bots,
                "total_messages": total_messages,
                "total_conversations": total_conversations,
                "total_leads": total_leads,
                "hot_leads": total_hot_leads,
            },
        }

    except Exception as e:
        logger.error(f"Error getting global stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations")
async def admin_all_conversations(creator_id: Optional[str] = None, limit: int = 100):
    """
    [ADMIN] Listar todas las conversaciones de todos los creadores.
    Opcionalmente filtrar por creator_id.
    Requiere CLONNECT_ADMIN_KEY.
    """
    from api.routers.dm import get_dm_agent
    from core.creator_config import CreatorConfigManager

    try:
        config_manager = CreatorConfigManager()
        if creator_id:
            creators = [creator_id]
        else:
            creators = config_manager.list_creators()

        all_conversations = []

        for cid in creators:
            try:
                agent = get_dm_agent(cid)
                conversations = await agent.get_all_conversations(limit)

                for conv in conversations:
                    conv["creator_id"] = cid
                    all_conversations.append(conv)
            except Exception as e:
                logger.warning(f"Failed to get conversations: {e}")

        # Ordenar por última actividad
        all_conversations.sort(key=lambda x: x.get("last_contact", ""), reverse=True)

        return {
            "status": "ok",
            "conversations": all_conversations[:limit],
            "total": len(all_conversations),
        }

    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def admin_recent_alerts(limit: int = 50):
    """
    [ADMIN] Obtener alertas recientes del sistema.
    Requiere CLONNECT_ADMIN_KEY.

    Nota: Las alertas se envían a Telegram, este endpoint
    es para consultar un historial local si está habilitado.
    """
    try:
        # Leer alertas del log si existe
        alerts = []
        log_file = os.path.join(os.getenv("DATA_PATH", "./data"), "alerts.log")

        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                lines = f.readlines()[-limit:]
                for line in lines:
                    try:
                        alert = json.loads(line.strip())
                        alerts.append(alert)
                    except Exception as e:
                        logger.debug(f"Skipping malformed alert line: {e}")

        return {
            "status": "ok",
            "alerts": alerts,
            "total": len(alerts),
            "telegram_enabled": os.getenv("TELEGRAM_ALERTS_ENABLED", "false").lower() == "true",
        }

    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/creators/{creator_id}/pause")
async def admin_pause_creator(creator_id: str, reason: str = "Pausado por admin"):
    """
    [ADMIN] Pausar el bot de cualquier creador.
    Requiere CLONNECT_ADMIN_KEY.
    """
    from core.creator_config import CreatorConfigManager

    try:
        config_manager = CreatorConfigManager()
        success = config_manager.set_active(creator_id, False, reason)

        if not success:
            raise HTTPException(status_code=404, detail="Creator not found")

        logger.warning(f"Admin paused bot for creator {creator_id}: {reason}")

        return {"status": "ok", "creator_id": creator_id, "is_active": False, "reason": reason}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing creator: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/creators/{creator_id}/resume")
async def admin_resume_creator(creator_id: str):
    """
    [ADMIN] Reanudar el bot de cualquier creador.
    Requiere CLONNECT_ADMIN_KEY.
    """
    from core.creator_config import CreatorConfigManager

    try:
        config_manager = CreatorConfigManager()
        success = config_manager.set_active(creator_id, True)

        if not success:
            raise HTTPException(status_code=404, detail="Creator not found")

        logger.info(f"Admin resumed bot for creator {creator_id}")

        return {"status": "ok", "creator_id": creator_id, "is_active": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming creator: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-rate-limiter/{creator_id}")
async def admin_reset_rate_limiter(creator_id: str):
    """Reset Instagram rate limiter backoff for a creator."""
    try:
        from core.instagram_rate_limiter import get_instagram_rate_limiter

        limiter = get_instagram_rate_limiter()
        result = limiter.reset_backoff(creator_id)
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Error resetting rate limiter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rate-limiter-stats")
async def admin_rate_limiter_stats(creator_id: str = None):
    """Get Instagram rate limiter statistics."""
    try:
        from core.instagram_rate_limiter import get_instagram_rate_limiter

        limiter = get_instagram_rate_limiter()
        return limiter.get_stats(creator_id)
    except Exception as e:
        logger.error(f"Error getting rate limiter stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backup")
async def admin_create_backup(creators_only: bool = False):
    """
    [ADMIN] Create a database backup.
    Exports critical data to JSON files.

    Args:
        creators_only: If True, only backup creator config (faster)

    Returns:
        Backup location and stats
    """
    import subprocess
    import sys

    try:
        # Run backup script
        script_path = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "backup_db.py")
        cmd = [sys.executable, script_path]
        if creators_only:
            cmd.append("--creators-only")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.error(f"Backup failed: {result.stderr}")
            raise HTTPException(status_code=500, detail=f"Backup failed: {result.stderr}")

        logger.info(f"Backup completed: {result.stdout}")

        return {
            "status": "ok",
            "message": "Backup created successfully",
            "output": result.stdout,
            "creators_only": creators_only,
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Backup timed out (5 min limit)")
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backups")
async def admin_list_backups():
    """
    [ADMIN] List available backups.
    """
    try:
        backup_dir = os.path.join(os.getenv("DATA_PATH", "./data"), "backups")
        backups = []

        if os.path.exists(backup_dir):
            for item in sorted(os.listdir(backup_dir), reverse=True)[:20]:  # Last 20
                item_path = os.path.join(backup_dir, item)
                if os.path.isdir(item_path):
                    meta_file = os.path.join(item_path, "_backup_meta.json")
                    if os.path.exists(meta_file):
                        with open(meta_file) as f:
                            meta = json.load(f)
                        backups.append(
                            {
                                "name": item,
                                "created_at": meta.get("created_at"),
                                "tables": list(meta.get("stats", {}).get("tables", {}).keys()),
                            }
                        )

        return {"status": "ok", "backups": backups, "total": len(backups)}

    except Exception as e:
        logger.error(f"Error listing backups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.api_route("/fix-reaction-emojis", methods=["GET", "POST"])
async def fix_reaction_emojis():
    """
    Fix reaction emojis missing the variation selector.

    The problem: Hearts stored as "❤" (U+2764) render as white/black text.
    The fix: Add variation selector to make "❤️" (U+2764 U+FE0F) render as red emoji.
    """
    try:
        from api.database import SessionLocal
        from api.models import Message

        session = SessionLocal()
        try:
            # Find messages with reaction type or emoji in metadata
            messages = (
                session.query(Message)
                .filter(Message.msg_metadata.isnot(None))
                .all()
            )

            fixed_count = 0
            for msg in messages:
                if msg.msg_metadata and isinstance(msg.msg_metadata, dict):
                    emoji = msg.msg_metadata.get("emoji")
                    # Check if it's the heart without variation selector
                    if emoji == "❤" or emoji == "\u2764":
                        msg.msg_metadata = {**msg.msg_metadata, "emoji": "❤️"}
                        fixed_count += 1

            session.commit()
            return {
                "status": "ok",
                "messages_checked": len(messages),
                "messages_fixed": fixed_count,
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error fixing reaction emojis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnose-duplicate-leads/{creator_id}")
async def diagnose_duplicate_leads(creator_id: str):
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
            text("""
                SELECT COUNT(*) FROM (
                    SELECT username FROM leads
                    WHERE username IS NOT NULL AND username != ''
                    AND creator_id = :creator_id
                    GROUP BY username
                    HAVING COUNT(*) > 1
                ) as dupes
            """),
            {"creator_id": str(creator.id)},
        )
        dupe_count = result.scalar()

        # 2. Get duplicate details with message counts
        result = session.execute(
            text("""
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
            """),
            {"creator_id": str(creator.id)},
        )
        rows = result.fetchall()

        duplicates = {}
        for row in rows:
            username = row[0]
            if username not in duplicates:
                duplicates[username] = []
            duplicates[username].append({
                "platform_user_id": row[1],
                "lead_id": str(row[2]),
                "message_count": row[3],
                "updated": str(row[4]) if row[4] else None,
            })

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
async def merge_duplicate_leads(creator_id: str):
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
            text("""
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
            """),
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
                text("""
                    SELECT id FROM leads
                    WHERE platform_user_id = :pid AND creator_id = :cid
                """),
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

                details.append({
                    "username": username,
                    "deleted_platform_id": dup_platform_id,
                    "kept_platform_id": original_platform_id,
                    "messages_moved": dup_msg_count,
                })

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

    finally:
        session.close()
