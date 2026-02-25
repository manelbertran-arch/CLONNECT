"""
Dangerous/destructive admin endpoints — Creator/user operations.

Endpoints:
- reset_creator
- delete_creator
- force_delete_creator
- delete_user_by_email
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
router = APIRouter()


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
