"""
Admin endpoints for demo/testing purposes
"""
import os
import re
import json
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, BackgroundTasks

logger = logging.getLogger(__name__)

# URL patterns for link preview detection
INSTAGRAM_URL_REGEX = re.compile(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)')
YOUTUBE_URL_REGEX = re.compile(r'https?://(?:www\.|m\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]+)')


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
                "video_id": video_id
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
                        "author": microlink_result.get("author")
                    }
            except Exception as e:
                logger.warning(f"Microlink error for {url}: {e}")

            # Fallback: mark for later processing if Microlink fails
            return {
                **msg_metadata,
                "type": "shared_post",
                "platform": "instagram",
                "url": url,
                "needs_thumbnail": True
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
            status_code=403,
            detail="Demo reset is disabled. Set ENABLE_DEMO_RESET=true to enable."
        )

    results = {
        "database": {},
        "json_files": {},
        "status": "success"
    }

    # 1. Reset PostgreSQL database using SQLAlchemy
    try:
        from api.database import DATABASE_URL, engine, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                # Import models
                from api.models import Creator, Lead, Message, Product, NurturingSequence, KnowledgeBase

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
                        json_file.write_text('{"messages_today": 0, "leads_today": 0, "hot_leads_count": 0, "total_messages": 0, "total_leads": 0}')
                    elif "followups" in json_file.name:
                        # Followups files are plain arrays
                        json_file.write_text('[]')
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
                        except:
                            pass
                    else:
                        # Generic reset - empty object or array
                        json_file.write_text('{}')
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
            status_code=403,
            detail="Demo reset is disabled. Set ENABLE_DEMO_RESET=true to enable."
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
            "onboarding_reset": False
        }
    }

    # 1. Database reset using SQLAlchemy
    try:
        from api.database import DATABASE_URL, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator, Lead, Message, Product, NurturingSequence, KnowledgeBase

                # Find creator by name
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    # Try by ID if it's a UUID
                    try:
                        from uuid import UUID
                        creator = session.query(Creator).filter_by(id=UUID(creator_id)).first()
                    except:
                        pass

                if creator:
                    creator_uuid = creator.id

                    # Delete messages for this creator's leads
                    leads = session.query(Lead).filter_by(creator_id=creator_uuid).all()
                    lead_ids = [l.id for l in leads]

                    if lead_ids:
                        msg_count = session.query(Message).filter(
                            Message.lead_id.in_(lead_ids)
                        ).delete(synchronize_session='fetch')
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

                    # Delete email tracking for this creator
                    try:
                        from api.models import EmailAskTracking, PlatformIdentity
                        email_tracking_count = session.query(EmailAskTracking).filter_by(creator_id=creator_uuid).delete()
                        results["deleted"]["email_tracking"] = email_tracking_count

                        # Delete platform identities (but keep unified profiles - they're cross-creator)
                        identity_count = session.query(PlatformIdentity).filter_by(creator_id=creator_uuid).delete()
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
        from core.tone_service import delete_tone_profile, clear_cache
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
                        filepath.write_text('[]')
                    elif "config" in pattern:
                        try:
                            with open(filepath) as f:
                                config = json.load(f)
                            config["clone_active"] = False
                            config["is_active"] = False
                            filepath.write_text(json.dumps(config, indent=2))
                        except:
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
        except:
            pass

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
            status_code=403,
            detail="Demo reset is disabled. Set ENABLE_DEMO_RESET=true to enable."
        )

    results = {
        "creator_name": creator_name,
        "deleted": {
            "leads": 0,
            "messages": 0,
            "products": 0,
            "sequences": 0,
            "knowledge_base": 0,
            "creator": False
        }
    }

    try:
        from api.database import SessionLocal
        session = SessionLocal()
        try:
            from api.models import Creator, Lead, Message, Product, NurturingSequence, KnowledgeBase

            # Find creator by name
            creator = session.query(Creator).filter_by(name=creator_name).first()
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator '{creator_name}' not found")

            creator_uuid = creator.id

            # Delete messages for this creator's leads
            leads = session.query(Lead).filter_by(creator_id=creator_uuid).all()
            lead_ids = [l.id for l in leads]

            if lead_ids:
                msg_count = session.query(Message).filter(
                    Message.lead_id.in_(lead_ids)
                ).delete(synchronize_session='fetch')
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
        from core.tone_service import delete_tone_profile, clear_cache
        delete_tone_profile(creator_name)
        clear_cache(creator_name)
    except:
        pass

    try:
        from core.rag import get_hybrid_rag
        rag = get_hybrid_rag()
        rag.delete_by_creator(creator_name)
    except:
        pass

    return {"status": "success", **results}


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
            session.execute(text("""
                ALTER TABLE creators
                ADD COLUMN IF NOT EXISTS email_capture_config JSONB DEFAULT NULL
            """))

            # Create unified_profiles table
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS unified_profiles (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255),
                    phone VARCHAR(50),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))

            # Create platform_identities table
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS platform_identities (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    unified_profile_id UUID REFERENCES unified_profiles(id),
                    creator_id UUID REFERENCES creators(id),
                    platform VARCHAR(50) NOT NULL,
                    platform_user_id VARCHAR(255) NOT NULL,
                    username VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))

            # Create unique index
            session.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_platform_identity_unique
                ON platform_identities(platform, platform_user_id)
            """))

            # Create email_ask_tracking table
            session.execute(text("""
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
            """))

            # Create index for fast lookups
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_email_ask_tracking_lookup
                ON email_ask_tracking(platform, platform_user_id)
            """))

            session.commit()
            logger.info("Email capture migration completed successfully")

            return {
                "status": "success",
                "message": "Migration completed",
                "tables_created": [
                    "unified_profiles",
                    "platform_identities",
                    "email_ask_tracking"
                ],
                "columns_added": [
                    "creators.email_capture_config"
                ]
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.post("/refresh-all-tokens")
async def refresh_all_instagram_tokens():
    """
    Cron job: Revisar todos los tokens de Instagram y refrescar los que expiran pronto.

    Diseñado para ser llamado diariamente por un cron job.

    Refresca tokens que expiran en menos de 7 días.
    Los tokens long-lived duran 60 días y se pueden refrescar indefinidamente.
    """
    try:
        from core.token_refresh_service import refresh_all_creator_tokens
        from api.database import SessionLocal

        session = SessionLocal()
        try:
            result = await refresh_all_creator_tokens(session)
            return {
                "status": "success",
                **result
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


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
        from core.token_refresh_service import check_and_refresh_if_needed
        from api.database import SessionLocal

        session = SessionLocal()
        try:
            result = await check_and_refresh_if_needed(creator_id, session)
            return {
                "status": "success" if result.get("success") else "error",
                **result
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Token refresh failed for {creator_id}: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


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
        from core.token_refresh_service import exchange_for_long_lived_token
        from api.database import SessionLocal
        from sqlalchemy import text

        # Exchange token
        new_token_data = await exchange_for_long_lived_token(short_lived_token)

        if not new_token_data:
            return {
                "status": "error",
                "error": "Failed to exchange token. Check META_APP_SECRET is configured."
            }

        # Save to database
        session = SessionLocal()
        try:
            session.execute(
                text("""
                    UPDATE creators
                    SET instagram_token = :token,
                        instagram_token_expires_at = :expires_at
                    WHERE id::text = :cid OR name = :cid
                """),
                {
                    "token": new_token_data["token"],
                    "expires_at": new_token_data["expires_at"],
                    "cid": creator_id
                }
            )
            session.commit()

            return {
                "status": "success",
                "token_prefix": new_token_data["token"][:20] + "...",
                "expires_at": new_token_data["expires_at"].isoformat(),
                "expires_in_days": new_token_data["expires_in"] // 86400
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Token exchange failed for {creator_id}: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


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
            creator = session.query(Creator).filter(
                (Creator.name == creator_id) | (Creator.id == creator_id)
            ).first()

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
                "token_type": "PAGE (EAA)" if token.startswith("EAA") else "INSTAGRAM (IGAAT)" if token.startswith("IGAAT") else "UNKNOWN",
                "valid_for_messaging": token.startswith("EAA")
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
                from api.models import Creator, Lead, Message, Product, NurturingSequence

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
            "demo_status": "GET /admin/demo-status"
        }
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
        from sqlalchemy import text
        from core.lead_categorization import (
            calcular_categoria,
            categoria_a_status_legacy,
            CATEGORIAS_CONFIG
        )

        session = SessionLocal()
        try:
            # Get creator
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                creator = session.query(Creator).filter(
                    text("id::text = :cid")
                ).params(cid=creator_id).first()

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
                    "fantasma": 0
                },
                "details": []
            }

            for lead in leads:
                messages = session.query(Message).filter_by(lead_id=lead.id).order_by(Message.created_at).all()

                # Convertir a formato esperado por calcular_categoria
                mensajes_dict = [
                    {"role": m.role, "content": m.content or ""}
                    for m in messages
                ]

                # Obtener último mensaje del lead para detectar fantasma
                mensajes_usuario = [m for m in messages if m.role == "user"]
                ultimo_msg_lead = mensajes_usuario[-1].created_at if mensajes_usuario else None

                # Obtener última interacción (cualquier mensaje)
                ultima_interaccion = messages[-1].created_at if messages else None

                # Verificar si es cliente (por ahora manual, luego webhook)
                es_cliente = getattr(lead, 'has_purchased', False) if hasattr(lead, 'has_purchased') else False

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
                    ultima_interaccion=ultima_interaccion
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

                stats["details"].append({
                    "username": lead.username,
                    "categoria": resultado.categoria,
                    "status_legacy": new_status,
                    "old_status": old_status,
                    "intent_score": resultado.intent_score,
                    "old_intent": old_intent,
                    "razones": resultado.razones,
                    "keywords": resultado.keywords_detectados[:5],
                    "messages_count": len(messages),
                    "first_contact": str(lead.first_contact_at) if lead.first_contact_at else None,
                    "last_contact": str(lead.last_contact_at) if lead.last_contact_at else None
                })

            session.commit()
            logger.info(f"[Rescore] Updated {stats['leads_updated']} leads for {creator_id}")

            return {
                "status": "success",
                "creator_id": creator_id,
                **stats
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Rescore failed for {creator_id}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/lead-categories")
async def get_lead_categories():
    """
    Obtener configuración de categorías de leads para el frontend.

    Retorna colores, iconos, labels y descripciones de cada categoría.
    """
    from core.lead_categorization import CATEGORIAS_CONFIG
    return {
        "status": "success",
        "categories": CATEGORIAS_CONFIG
    }


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
            test_leads = session.query(Lead).filter(
                Lead.creator_id == creator.id,
                or_(
                    Lead.username == None,
                    Lead.username == "",
                    Lead.username.like("test%"),
                    Lead.platform_user_id.like("test%")
                )
            ).all()

            lead_ids = [l.id for l in test_leads]

            if not lead_ids:
                return {
                    "status": "success",
                    "message": "No test leads found",
                    "deleted_leads": 0,
                    "deleted_messages": 0
                }

            # Delete messages first (foreign key)
            deleted_messages = session.query(Message).filter(
                Message.lead_id.in_(lead_ids)
            ).delete(synchronize_session=False)

            # Delete leads
            deleted_leads = session.query(Lead).filter(
                Lead.id.in_(lead_ids)
            ).delete(synchronize_session=False)

            session.commit()

            logger.info(f"[Cleanup] Deleted {deleted_leads} test leads and {deleted_messages} messages for {creator_id}")

            return {
                "status": "success",
                "creator_id": creator_id,
                "deleted_leads": deleted_leads,
                "deleted_messages": deleted_messages
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Cleanup failed for {creator_id}: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


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
        access_token = creds["token"]
        api_base = "https://graph.instagram.com/v21.0"

        results = {
            "ig_user_id": ig_user_id,
            "conversations": [],
            "sample_messages": []
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get conversations
            conv_url = f"{api_base}/{ig_user_id}/conversations"
            conv_resp = await client.get(conv_url, params={
                "access_token": access_token,
                "limit": 5
            })

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
                msg_resp = await client.get(msg_url, params={
                    "fields": "id,message,from,to,created_time",
                    "access_token": access_token,
                    "limit": 3
                })

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


@router.post("/simple-dm-sync/{creator_id}")
async def simple_dm_sync(creator_id: str, max_convs: int = 20):
    """
    Simple DM sync without complex rate limiting.
    Fetches messages and saves them directly.
    Uses centralized get_instagram_credentials() for consistent token lookup.
    """
    import httpx
    from datetime import datetime
    from api.services import db_service

    results = {
        "conversations_processed": 0,
        "messages_saved": 0,
        "messages_empty": 0,
        "messages_duplicate": 0,
        "messages_filtered_180days": 0,
        "messages_with_attachments": 0,
        "leads_created": 0,
        "errors": []
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
            api_base = "https://graph.instagram.com/v21.0"

            async with httpx.AsyncClient(timeout=60.0) as client:
                # Get conversations with updated_time
                conv_resp = await client.get(
                    f"{api_base}/{ig_user_id}/conversations",
                    params={"access_token": access_token, "limit": max_convs, "fields": "id,updated_time"}
                )

                if conv_resp.status_code != 200:
                    return {"error": f"Conversations API error: {conv_resp.json()}"}

                conversations = conv_resp.json().get("data", [])

                # REGLA 1: Ordenar por updated_time (más reciente primero)
                conversations.sort(
                    key=lambda c: c.get("updated_time", ""),
                    reverse=True
                )

                for conv in conversations:
                    conv_id = conv.get("id")
                    if not conv_id:
                        continue

                    try:
                        # Get messages for this conversation (REGLA 3+4: attachments, stories, reactions)
                        msg_resp = await client.get(
                            f"{api_base}/{conv_id}/messages",
                            params={
                                "fields": "id,message,from,to,created_time,attachments,story,reactions",
                                "access_token": access_token,
                                "limit": 50
                            }
                        )

                        if msg_resp.status_code != 200:
                            error_data = msg_resp.json().get("error", {})
                            # Check for rate limit
                            if error_data.get("code") in [4, 17]:
                                results["errors"].append(f"Rate limit hit at conv {results['conversations_processed']}")
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
                                    "access_token": access_token
                                }
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
                        lead = session.query(Lead).filter_by(
                            creator_id=creator.id,
                            platform="instagram",
                            platform_user_id=follower_id
                        ).first()

                        # Parse conversation updated_time as fallback
                        conv_updated_time = None
                        if conv.get("updated_time"):
                            try:
                                conv_updated_time = datetime.fromisoformat(
                                    conv["updated_time"].replace("+0000", "+00:00")
                                )
                            except:
                                pass

                        # Parse message timestamps for first/last contact
                        all_msg_timestamps = []
                        user_msg_timestamps = []

                        for msg in messages:
                            if msg.get("created_time"):
                                try:
                                    ts = datetime.fromisoformat(msg["created_time"].replace("+0000", "+00:00"))
                                    all_msg_timestamps.append(ts)

                                    # Solo contar mensajes del follower para last_contact
                                    from_id = msg.get("from", {}).get("id")
                                    if from_id and from_id != ig_user_id:
                                        user_msg_timestamps.append(ts)
                                except:
                                    pass

                        first_msg_time = min(all_msg_timestamps) if all_msg_timestamps else conv_updated_time
                        # IMPORTANTE: usar último mensaje del USUARIO para fantasma
                        last_user_msg_time = max(user_msg_timestamps) if user_msg_timestamps else first_msg_time

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
                                last_contact_at=last_user_msg_time or first_msg_time
                            )
                            session.add(lead)
                            session.commit()
                            results["leads_created"] += 1
                        else:
                            # Update timestamps if we have older/newer messages
                            if first_msg_time and (not lead.first_contact_at or first_msg_time < lead.first_contact_at):
                                lead.first_contact_at = first_msg_time
                            # IMPORTANTE: solo actualizar si hay mensaje del USUARIO más reciente
                            if last_user_msg_time and (not lead.last_contact_at or last_user_msg_time > lead.last_contact_at):
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
                                    reaction_emoji = reactions_data[0].get("emoji", "❤")

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
                                    msg_metadata = {"type": "story_reaction", "url": story_link, "emoji": reaction_emoji}
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
                                        print(f"[SYNC DEBUG] Share field found: {share_data}")
                                        msg_text = "Post compartido"
                                        msg_metadata = {
                                            "type": "shared_post",
                                            "url": share_data.get("link", ""),
                                            "thumbnail_url": share_data.get("image_url", ""),
                                            "name": share_data.get("name", ""),
                                            "description": share_data.get("description", "")
                                        }
                                    else:
                                        attachments = msg.get("attachments", {}).get("data", [])
                                        if attachments:
                                            for att in attachments:
                                                # DEBUG: Log attachment structure
                                                print(f"[SYNC DEBUG] Attachment: {att}")

                                                att_type = (att.get("type") or "").lower()

                                                # Instagram sends structure-based types (no explicit type field)
                                                has_video = att.get("video_data") is not None
                                                has_image = att.get("image_data") is not None
                                                has_audio = att.get("audio_data") is not None
                                                is_sticker = att.get("render_as_sticker", False)
                                                is_animated = att.get("animated_gif_url") is not None

                                                # Get URL based on structure
                                                if has_video:
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
                                                elif "share" in att_type or "post" in att_type or "media_share" in att_type:
                                                    # Shared post (explicit type)
                                                    post_url = att.get("target", {}).get("url") or att_url
                                                    thumbnail_url = att.get("image_data", {}).get("url") if att.get("image_data") else att.get("preview_url")
                                                    msg_text = "Post compartido"
                                                    msg_metadata = {
                                                        "type": "shared_post",
                                                        "url": post_url,
                                                        "thumbnail_url": thumbnail_url
                                                    }
                                                elif "image" in att_type or "photo" in att_type or has_image:
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
                                    msg_timestamp = datetime.fromisoformat(msg_time_str.replace("+0000", "+00:00"))
                                    if msg_timestamp < days_limit_ago:
                                        results["messages_filtered_180days"] += 1
                                        continue  # Skip messages older than 180 days
                                except:
                                    pass

                            # Track attachment processing
                            if msg_text.startswith("[") and msg_text.endswith("]"):
                                results["messages_with_attachments"] += 1

                            # Check if already exists
                            existing = session.query(Message).filter_by(
                                platform_message_id=msg_id
                            ).first()

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
                                msg_metadata = await generate_link_preview(url_to_preview, msg_metadata)

                            new_msg = Message(
                                lead_id=lead.id,
                                role=role,
                                content=msg_text,
                                platform_message_id=msg_id,
                                msg_metadata=msg_metadata if msg_metadata else {}
                            )

                            # Parse timestamp
                            msg_time = msg.get("created_time")
                            if msg_time:
                                try:
                                    new_msg.created_at = datetime.fromisoformat(
                                        msg_time.replace("+0000", "+00:00")
                                    )
                                except:
                                    pass

                            session.add(new_msg)
                            results["messages_saved"] += 1

                        session.commit()
                        results["conversations_processed"] += 1

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
            from api.services.screenshot_service import ScreenshotService, PLAYWRIGHT_AVAILABLE
        except ImportError:
            return {"error": "Screenshot service not available", "playwright_available": False}

        if not PLAYWRIGHT_AVAILABLE:
            return {"error": "Playwright not installed", "playwright_available": False}

        session = SessionLocal()
        results = {
            "thumbnails_generated": 0,
            "thumbnails_failed": 0,
            "messages_processed": 0
        }

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
            messages = session.query(Message).filter(
                Message.lead_id.in_(lead_ids)
            ).all()

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
            deleted_count = session.query(Message).filter(
                Message.lead_id.in_(lead_ids)
            ).delete(synchronize_session=False)

            session.commit()

            return {
                "status": "success",
                "messages_deleted": deleted_count,
                "leads_count": len(lead_ids),
                "creator": creator_id
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
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message
        from datetime import datetime, timezone
        import uuid

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
                "author": preview.get("author") if preview else None
            }

            test_msg = Message(
                lead_id=lead.id,
                role="user",
                content="Mira este post! 👀",
                msg_metadata=msg_metadata,
                created_at=datetime.now(timezone.utc)
            )
            session.add(test_msg)
            session.commit()

            return {
                "status": "success",
                "message_id": str(test_msg.id),
                "metadata": msg_metadata,
                "lead_username": lead.username
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
    from core.sync_worker import start_sync_for_creator, run_sync_worker_iteration
    from api.database import SessionLocal

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
    from core.sync_worker import run_sync_worker_iteration, get_sync_status
    from api.database import SessionLocal

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
        "message": "Sync resumed in background"
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

        return {
            "status": "reset",
            "jobs_deleted": deleted_jobs,
            "state_deleted": deleted_state
        }
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
                creator = session.query(Creator).filter(
                    text("id::text = :cid")
                ).params(cid=creator_id).first()

            if not creator:
                return {"status": "error", "error": f"Creator not found: {creator_id}"}

            leads = session.query(Lead).filter_by(creator_id=creator.id).all()

            stats = {
                "total_leads": len(leads),
                "leads_updated": 0,
                "leads_no_messages": 0,
                "leads_no_user_messages": 0,
                "details": []
            }

            for lead in leads:
                messages = session.query(Message).filter_by(lead_id=lead.id).order_by(Message.created_at).all()
                old_first = lead.first_contact_at
                old_last = lead.last_contact_at

                if not messages:
                    # Para leads SIN mensajes: last_contact = first_contact
                    # Esto permite detectarlos correctamente como fantasma
                    if lead.first_contact_at and lead.last_contact_at != lead.first_contact_at:
                        lead.last_contact_at = lead.first_contact_at
                        stats["leads_no_messages"] += 1
                        stats["leads_updated"] += 1
                        stats["details"].append({
                            "username": lead.username,
                            "old_first": str(old_first) if old_first else None,
                            "new_first": str(lead.first_contact_at) if lead.first_contact_at else None,
                            "old_last": str(old_last) if old_last else None,
                            "new_last": str(lead.last_contact_at) if lead.last_contact_at else None,
                            "total_messages": 0,
                            "user_messages": 0,
                            "fix_type": "no_messages_use_first_contact"
                        })
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

                    stats["details"].append({
                        "username": lead.username,
                        "old_first": str(old_first) if old_first else None,
                        "new_first": str(lead.first_contact_at) if lead.first_contact_at else None,
                        "old_last": str(old_last) if old_last else None,
                        "new_last": str(lead.last_contact_at) if lead.last_contact_at else None,
                        "total_messages": len(messages),
                        "user_messages": len(user_messages)
                    })
                else:
                    # Mensajes pero ninguno del usuario: usar first_contact
                    if lead.first_contact_at:
                        lead.last_contact_at = lead.first_contact_at
                        stats["leads_updated"] += 1
                    stats["leads_no_user_messages"] += 1

            session.commit()
            logger.info(f"[FixTimestamps] Updated {stats['leads_updated']} leads for {creator_id}")

            return {
                "status": "success",
                "creator_id": creator_id,
                **stats
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Fix timestamps failed for {creator_id}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e)
        }


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
    max_per_cycle: int = None
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
            max_per_cycle=max_per_cycle
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
            creator = session.query(Creator).filter(
                text("id::text = :cid")
            ).params(cid=creator_id).first()

        if not creator:
            return {"status": "error", "error": f"Creator not found: {creator_id}"}

        # Check Instagram connection
        if not creator.instagram_page_id or not creator.instagram_token:
            return {"status": "error", "error": "Instagram not connected for this creator"}

        access_token = creator.instagram_token
        api_base = "https://graph.instagram.com/v21.0"

        # Get leads without profile pic
        leads_without_pic = session.query(Lead).filter(
            Lead.creator_id == creator.id,
            Lead.platform == "instagram",
            Lead.platform_user_id.isnot(None),
            Lead.profile_pic_url.is_(None)
        ).limit(limit).all()

        # Count total remaining
        total_remaining = session.query(Lead).filter(
            Lead.creator_id == creator.id,
            Lead.platform == "instagram",
            Lead.platform_user_id.isnot(None),
            Lead.profile_pic_url.is_(None)
        ).count()

        results = {
            "updated": 0,
            "failed": 0,
            "total": len(leads_without_pic),
            "remaining": total_remaining - len(leads_without_pic),
            "details": []
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
                            "access_token": access_token
                        }
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
                            results["details"].append({
                                "username": lead.username,
                                "status": "updated"
                            })
                        else:
                            results["failed"] += 1
                            results["details"].append({
                                "username": lead.username,
                                "status": "no_pic_in_response"
                            })
                    else:
                        results["failed"] += 1
                        results["details"].append({
                            "username": lead.username,
                            "status": f"api_error_{resp.status_code}"
                        })

                    # Rate limiting: 500ms between requests
                    await asyncio.sleep(0.5)

                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({
                        "username": lead.username,
                        "status": f"error: {str(e)[:50]}"
                    })

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
    from core.link_preview import extract_urls, extract_link_preview

    session = SessionLocal()
    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            from sqlalchemy import text
            creator = session.query(Creator).filter(
                text("id::text = :cid")
            ).params(cid=creator_id).first()

        if not creator:
            return {"status": "error", "error": f"Creator not found: {creator_id}"}

        # Find messages with URLs using JOIN (avoids N+1)
        # Single query: messages -> leads -> creator
        messages = session.query(Message).join(
            Lead, Message.lead_id == Lead.id
        ).filter(
            Lead.creator_id == creator.id,
            Message.content.ilike('%http%')
        ).order_by(Message.created_at.desc()).limit(limit).all()

        if not messages:
            return {"status": "ok", "message": "No messages with URLs found", "updated": 0, "total": 0}

        results = {
            "updated": 0,
            "failed": 0,
            "no_urls": 0,
            "already_has_preview": 0,
            "total": len(messages),
            "details": []
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
                    results["details"].append({
                        "url": urls[0][:50],
                        "title": preview.get("title", "")[:30] if preview.get("title") else None,
                        "status": "updated"
                    })

                    # Batch commit every 10 updates for efficiency
                    if results["updated"] % 10 == 0:
                        session.commit()
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "url": urls[0][:50],
                        "status": "no_preview_data"
                    })

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
    creator_id: str,
    recategorize: bool = False,
    limit: int = 100
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
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message
    from core.lead_categorization import calcular_categoria, categoria_a_status_legacy
    from sqlalchemy import func, text
    from datetime import timezone

    session = SessionLocal()
    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            creator = session.query(Creator).filter(
                text("id::text = :cid")
            ).params(cid=creator_id).first()

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
                "updated": 0
            }

        # Get all messages for these leads in single query (avoid N+1)
        lead_ids = [lead.id for lead in leads]
        messages_query = session.query(Message).filter(
            Message.lead_id.in_(lead_ids)
        ).order_by(Message.lead_id, Message.created_at).all()

        # Group messages by lead_id
        messages_by_lead = {}
        for msg in messages_query:
            if msg.lead_id not in messages_by_lead:
                messages_by_lead[msg.lead_id] = []
            messages_by_lead[msg.lead_id].append({
                "role": msg.role,
                "content": msg.content or "",
                "created_at": msg.created_at
            })

        results = {
            "total_leads": len(leads),
            "updated": 0,
            "skipped": 0,
            "categorized": {
                "nuevo": 0,
                "interesado": 0,
                "caliente": 0,
                "cliente": 0,
                "fantasma": 0
            },
            "details": []
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
                    lead_created_at=lead.first_contact_at
                )

                # Map category to legacy status for compatibility
                new_status = categoria_a_status_legacy(result.categoria)

                # Check if update needed
                if lead.status == new_status and abs((lead.purchase_intent or 0) - result.intent_score) < 0.01:
                    results["skipped"] += 1
                    continue

                # Update lead
                old_status = lead.status
                lead.status = new_status
                lead.purchase_intent = result.intent_score

                results["updated"] += 1
                results["categorized"][result.categoria] += 1
                results["details"].append({
                    "lead_id": str(lead.id),
                    "username": lead.username,
                    "old_status": old_status,
                    "new_status": new_status,
                    "categoria": result.categoria,
                    "intent_score": round(result.intent_score, 2),
                    "razones": result.razones[:2],
                    "total_messages": len(msgs)
                })

                # Batch commit every 20 updates
                if results["updated"] % 20 == 0:
                    session.commit()

            except Exception as e:
                logger.warning(f"Error categorizing lead {lead.id}: {e}")
                results["skipped"] += 1

        # Final commit
        session.commit()

        logger.info(f"Sync leads for {creator_id}: {results['updated']} updated, {results['skipped']} skipped")
        return {"status": "ok", **results}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"sync_leads error: {e}")
        session.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        session.close()
