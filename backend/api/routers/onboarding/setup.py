"""Manual setup, quick setup, and full reset endpoints."""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class ManualSetupRequest(BaseModel):
    """Request para setup manual sin OAuth."""

    creator_id: str
    instagram_username: str
    website_url: Optional[str] = None
    max_posts: int = 20  # Reduced from 50 to avoid rate limits


class ManualSetupResponse(BaseModel):
    """Response del setup manual."""

    success: bool
    creator_id: str
    steps_completed: Dict[str, bool]
    details: Dict
    errors: List[str] = []


@router.post("/quick-setup")
async def quick_setup(request: ManualSetupRequest):
    """
    Setup rapido sin scraping - para testing y demos.

    Solo crea/actualiza el creator y marca onboarding como completado.
    No hace scraping de Instagram ni website.
    """
    try:
        import uuid as uuid_module

        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator

        if not DATABASE_URL or not SessionLocal:
            return {
                "success": True,
                "creator_id": request.creator_id,
                "steps_completed": {"onboarding_completed": True, "bot_activated": True},
                "details": {"mode": "no_database"},
                "errors": [],
            }

        session = SessionLocal()
        try:
            # Get or create creator
            creator = session.query(Creator).filter_by(name=request.creator_id).first()
            if not creator:
                creator = Creator(
                    id=uuid_module.uuid4(),
                    name=request.creator_id,
                    email=f"{request.creator_id}@clonnect.io",
                    bot_active=True,
                    onboarding_completed=True,
                    copilot_mode=True,
                )
                session.add(creator)
                logger.info(f"[QuickSetup] Created new creator: {request.creator_id}")
            else:
                creator.bot_active = True
                creator.onboarding_completed = True
                logger.info(f"[QuickSetup] Updated existing creator: {request.creator_id}")

            session.commit()

            return {
                "success": True,
                "creator_id": request.creator_id,
                "steps_completed": {
                    "posts_scraped": False,
                    "tone_profile_generated": False,
                    "rag_indexed": False,
                    "website_scraped": False,
                    "onboarding_completed": True,
                    "bot_activated": True,
                },
                "details": {
                    "posts_count": 0,
                    "mode": "quick_setup",
                    "instagram_username": request.instagram_username,
                },
                "errors": [],
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"[QuickSetup] Error: {e}")
        return {
            "success": False,
            "creator_id": request.creator_id,
            "steps_completed": {},
            "details": {},
            "errors": [str(e)],
        }


@router.post("/manual-setup", response_model=ManualSetupResponse)
async def manual_setup(request: ManualSetupRequest):
    """
    Setup manual completo sin OAuth.

    Ideal para demos o cuando no se tiene acceso a Instagram OAuth.

    Este endpoint:
    1. Scrapea 50 posts publicos del Instagram username
    2. Genera ToneProfile con Magic Slice
    3. Indexa contenido en RAG (PostgreSQL + archivos)
    4. Scrapea website y anade al RAG
    5. Marca onboarding como completado
    6. Activa el bot

    Body:
    ```json
    {
        "creator_id": "stefano_auto",
        "instagram_username": "stefanobonanno",
        "website_url": "https://stefanobonanno.com"
    }
    ```
    """
    errors = []
    steps_completed = {
        "posts_scraped": False,
        "tone_profile_generated": False,
        "rag_indexed": False,
        "website_scraped": False,
        "onboarding_completed": False,
        "bot_activated": False,
    }
    details = {"posts_count": 0, "tone_summary": None, "rag_documents": 0, "website_pages": 0}

    logger.info(
        f"[ManualSetup] Starting for {request.creator_id} from @{request.instagram_username}"
    )

    # ==========================================================================
    # STEP 1: Scrape Instagram posts (public, no OAuth)
    # Uses delay_between_posts=3.0 to avoid rate limiting
    # ==========================================================================
    posts = []
    try:
        from ingestion.instagram_scraper import InstagramScraperError, InstaloaderScraper

        scraper = InstaloaderScraper()
        posts = scraper.get_posts(
            target_username=request.instagram_username,
            limit=request.max_posts,
            delay_between_posts=3.0,  # 3 seconds between each post to avoid rate limits
        )

        if posts:
            steps_completed["posts_scraped"] = True
            details["posts_count"] = len(posts)
            logger.info(
                f"[ManualSetup] Scraped {len(posts)} posts from @{request.instagram_username}"
            )
        else:
            errors.append("No posts found or profile is private")

    except Exception as e:
        errors.append(f"Instagram scraping failed: {str(e)}")
        logger.error(f"[ManualSetup] Scraping error: {e}")

    # ==========================================================================
    # STEP 2: Generate ToneProfile with Magic Slice
    # ==========================================================================
    if posts:
        try:
            from core.tone_service import save_tone_profile
            from ingestion.tone_analyzer import ToneAnalyzer

            # Convert posts to dict format
            posts_data = [
                {
                    "caption": post.caption,
                    "post_id": post.post_id,
                    "post_type": post.post_type,
                    "permalink": post.permalink,
                    "timestamp": post.timestamp.isoformat() if post.timestamp else None,
                    "likes_count": post.likes_count,
                    "comments_count": post.comments_count,
                }
                for post in posts
                if post.caption
            ]

            if posts_data:
                analyzer = ToneAnalyzer()
                tone_profile = await analyzer.analyze(request.creator_id, posts_data)
                await save_tone_profile(tone_profile)

                steps_completed["tone_profile_generated"] = True
                details["tone_summary"] = {
                    "formality": tone_profile.formality,
                    "energy": tone_profile.energy,
                    "warmth": tone_profile.warmth,
                    "uses_emojis": tone_profile.uses_emojis,
                    "primary_language": tone_profile.primary_language,
                    "signature_phrases": tone_profile.signature_phrases[:5],
                }
                logger.info(
                    f"[ManualSetup] ToneProfile generated: {tone_profile.formality}, {tone_profile.energy}"
                )

        except Exception as e:
            errors.append(f"ToneProfile generation failed: {str(e)}")
            logger.error(f"[ManualSetup] Tone error: {e}")

    # ==========================================================================
    # STEP 3: Index content in RAG
    # ==========================================================================
    if posts:
        try:
            from core.rag import get_hybrid_rag

            rag = get_hybrid_rag()
            indexed_count = 0

            for post in posts:
                if not post.caption or len(post.caption.strip()) < 20:
                    continue

                doc_id = f"ig_post_{post.post_id}"
                metadata = {
                    "creator_id": request.creator_id,
                    "source_type": "instagram_post",
                    "post_type": post.post_type,
                    "url": post.permalink,
                    "hashtags": post.hashtags[:10] if post.hashtags else [],
                    "likes": post.likes_count,
                    "comments": post.comments_count,
                }

                rag.add_document(doc_id=doc_id, text=post.caption, metadata=metadata)
                indexed_count += 1

            if indexed_count > 0:
                steps_completed["rag_indexed"] = True
                details["rag_documents"] = indexed_count
                logger.info(f"[ManualSetup] Indexed {indexed_count} posts in RAG")

        except Exception as e:
            errors.append(f"RAG indexing failed: {str(e)}")
            logger.error(f"[ManualSetup] RAG error: {e}")

    # ==========================================================================
    # STEP 4: Scrape website and add to RAG
    # ==========================================================================
    if request.website_url:
        try:
            from core.website_scraper import scrape_and_index_website

            result = await scrape_and_index_website(
                creator_id=request.creator_id, url=request.website_url
            )

            if result.get("success"):
                steps_completed["website_scraped"] = True
                details["website_pages"] = result.get("pages_indexed", 0)
                logger.info(
                    f"[ManualSetup] Website scraped: {result.get('pages_indexed', 0)} pages"
                )
            else:
                errors.append(f"Website scraping: {result.get('error', 'Unknown error')}")

        except Exception as e:
            errors.append(f"Website scraping failed: {str(e)}")
            logger.error(f"[ManualSetup] Website error: {e}")
    else:
        # No website provided - mark as completed (optional step)
        steps_completed["website_scraped"] = True
        details["website_pages"] = 0

    # ==========================================================================
    # STEP 5: Create demo leads and products if posts were scraped
    # ==========================================================================
    if steps_completed["posts_scraped"] or steps_completed["tone_profile_generated"]:
        try:
            import random
            import uuid as uuid_module
            from datetime import datetime, timedelta

            from api.database import DATABASE_URL, SessionLocal
            from api.models import Creator, Lead, Product

            if DATABASE_URL and SessionLocal:
                session = SessionLocal()
                try:
                    # Get or create creator
                    creator = session.query(Creator).filter_by(name=request.creator_id).first()
                    if not creator:
                        creator = Creator(
                            id=uuid_module.uuid4(),
                            name=request.creator_id,
                            email=f"{request.creator_id}@clonnect.io",
                            bot_active=False,
                            onboarding_completed=False,
                            copilot_mode=True,
                        )
                        session.add(creator)
                        session.commit()
                        logger.info(f"[ManualSetup] Created new creator: {request.creator_id}")

                    creator_uuid = creator.id

                    # Create demo products
                    demo_products = [
                        {
                            "name": "Consultoría 1:1",
                            "price": 150.0,
                            "description": "Sesión de consultoría personalizada de 1 hora",
                        },
                        {
                            "name": "Curso Online",
                            "price": 97.0,
                            "description": "Acceso completo al curso con materiales",
                        },
                        {
                            "name": "Mentoría Grupal",
                            "price": 49.0,
                            "description": "Sesión grupal mensual con Q&A",
                        },
                    ]

                    products_created = 0
                    for prod in demo_products:
                        existing = (
                            session.query(Product)
                            .filter_by(creator_id=creator_uuid, name=prod["name"])
                            .first()
                        )
                        if not existing:
                            new_product = Product(
                                id=uuid_module.uuid4(),
                                creator_id=creator_uuid,
                                name=prod["name"],
                                price=prod["price"],
                                description=prod["description"],
                                is_active=True,
                            )
                            session.add(new_product)
                            products_created += 1

                    # NOTE: Demo leads creation DISABLED - we only show real DMs from Instagram
                    leads_created = 0

                    session.commit()
                    details["demo_leads_created"] = leads_created
                    details["demo_products_created"] = products_created
                    logger.info(
                        f"[ManualSetup] Created {leads_created} demo leads and {products_created} demo products"
                    )

                finally:
                    session.close()

        except Exception as e:
            errors.append(f"Demo data creation failed: {str(e)}")
            logger.error(f"[ManualSetup] Demo data error: {e}")

    # ==========================================================================
    # STEP 6: Mark onboarding completed and activate bot (ONLY if setup succeeded)
    # ==========================================================================
    # Only mark as completed if we have meaningful data
    should_complete = steps_completed["posts_scraped"] or steps_completed["tone_profile_generated"]

    try:
        from api.database import DATABASE_URL, SessionLocal

        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                import uuid as uuid_module

                from api.models import Creator

                creator = session.query(Creator).filter_by(name=request.creator_id).first()

                if not creator:
                    # Create creator if doesn't exist
                    creator = Creator(
                        id=uuid_module.uuid4(),
                        name=request.creator_id,
                        email=f"{request.creator_id}@clonnect.io",
                        bot_active=should_complete,
                        onboarding_completed=should_complete,
                        copilot_mode=True,
                    )
                    session.add(creator)
                    logger.info(f"[ManualSetup] Created new creator: {request.creator_id}")
                else:
                    # Update existing creator - only complete if setup succeeded
                    if should_complete:
                        creator.bot_active = True
                        creator.onboarding_completed = True
                        logger.info(
                            f"[ManualSetup] Updated creator (completed): {request.creator_id}"
                        )
                    else:
                        # Keep onboarding_completed=false so user can retry
                        logger.info(
                            f"[ManualSetup] Setup failed, keeping onboarding incomplete: {request.creator_id}"
                        )

                session.commit()
                steps_completed["onboarding_completed"] = should_complete
                steps_completed["bot_activated"] = should_complete

            finally:
                session.close()

    except Exception as e:
        errors.append(f"Database update failed: {str(e)}")
        logger.error(f"[ManualSetup] DB error: {e}")

    # ==========================================================================
    # RESULT
    # ==========================================================================
    success = (
        steps_completed["posts_scraped"]
        and steps_completed["tone_profile_generated"]
        and steps_completed["bot_activated"]
    )

    logger.info(
        f"[ManualSetup] Completed for {request.creator_id}: success={success}, steps={steps_completed}"
    )

    return ManualSetupResponse(
        success=success,
        creator_id=request.creator_id,
        steps_completed=steps_completed,
        details=details,
        errors=errors,
    )


# =============================================================================
# FULL RESET - Delete ALL data for a creator (for testing)
# =============================================================================


@router.delete("/full-reset/{creator_id}")
async def full_reset_creator(
    creator_id: str,
    email: Optional[str] = None,
    confirm: str = None,
    admin: str = Depends(require_admin),
):
    """
    Delete ALL data for a creator. Use for testing/starting fresh.

    Requires admin API key (X-API-Key header).
    DANGER: Requires confirmation parameter.

    Deletes:
    - Creator record from DB
    - User record (if email provided)
    - All leads and messages
    - All products
    - Instagram posts
    - Content chunks (RAG)
    - ToneProfile
    - ContentIndex files

    WARNING: This is destructive and cannot be undone!

    Usage:
        DELETE /onboarding/full-reset/stefano_bonanno?confirm=DELETE_EVERYTHING&email=stefano@fitpackglobal.com
    """
    # SAFETY: Require explicit confirmation
    if confirm != "DELETE_EVERYTHING":
        return {
            "error": "Safety check failed",
            "usage": f"DELETE /onboarding/full-reset/{creator_id}?confirm=DELETE_EVERYTHING",
            "warning": "This will PERMANENTLY delete ALL data for this creator. Cannot be undone.",
        }

    logger.warning(f"[DANGER] full_reset_creator called for {creator_id} (email={email})")

    deleted = {
        "creator": False,
        "user": False,
        "leads": 0,
        "messages": 0,
        "products": 0,
        "instagram_posts": 0,
        "content_chunks": 0,
        "tone_profile": False,
        "content_index": False,
    }
    errors = []

    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message, Product, UserCreator

        if not DATABASE_URL or not SessionLocal:
            return {"success": False, "error": "Database not configured"}

        session = SessionLocal()
        try:
            # Find creator by name
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if creator:
                creator_uuid = creator.id

                # Delete messages for all leads
                leads = session.query(Lead).filter_by(creator_id=creator_uuid).all()
                for lead in leads:
                    msg_count = session.query(Message).filter_by(lead_id=lead.id).delete()
                    deleted["messages"] += msg_count

                # Delete leads
                deleted["leads"] = session.query(Lead).filter_by(creator_id=creator_uuid).delete()

                # Delete products
                deleted["products"] = (
                    session.query(Product).filter_by(creator_id=creator_uuid).delete()
                )

                # Delete user_creators relationships (MUST be before creator delete)
                user_creators_deleted = (
                    session.query(UserCreator).filter_by(creator_id=creator_uuid).delete()
                )
                logger.info(
                    f"[FullReset] Deleted {user_creators_deleted} user_creators relationships"
                )

                # Delete creator
                session.delete(creator)
                deleted["creator"] = True

                logger.info(f"[FullReset] Deleted creator {creator_id} and related data")

            # Delete user by email if provided
            if email:
                try:
                    from api.models import User

                    user = session.query(User).filter_by(email=email).first()
                    if user:
                        session.delete(user)
                        deleted["user"] = True
                        logger.info(f"[FullReset] Deleted user {email}")
                except Exception as e:
                    errors.append(f"User deletion failed: {str(e)}")

            session.commit()

        finally:
            session.close()

        # Delete Instagram posts from DB
        try:
            from core.tone_profile_db import delete_content_chunks_db, delete_instagram_posts_db

            posts_deleted = await delete_instagram_posts_db(creator_id)
            deleted["instagram_posts"] = posts_deleted or 0

            chunks_deleted = await delete_content_chunks_db(creator_id)
            deleted["content_chunks"] = chunks_deleted or 0

        except Exception as e:
            errors.append(f"Instagram/chunks deletion failed: {str(e)}")

        # Delete ToneProfile
        try:
            from core.tone_service import delete_tone_profile

            deleted["tone_profile"] = delete_tone_profile(creator_id)
        except Exception as e:
            errors.append(f"ToneProfile deletion failed: {str(e)}")

        # Delete ContentIndex files
        try:
            from core.citation_service import delete_content_index

            deleted["content_index"] = delete_content_index(creator_id)
        except Exception as e:
            errors.append(f"ContentIndex deletion failed: {str(e)}")

        # Delete local data files
        try:
            import shutil
            from pathlib import Path

            paths_to_delete = [
                Path(f"data/content_index/{creator_id}"),
                Path(f"data/tone_profiles/{creator_id}.json"),
                Path(f"data/creators/{creator_id}_config.json"),
                Path(f"data/products/{creator_id}_products.json"),
                Path(f"data/followers/{creator_id}"),
            ]

            for path in paths_to_delete:
                if path.exists():
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    logger.info(f"[FullReset] Deleted {path}")

        except Exception as e:
            errors.append(f"File deletion failed: {str(e)}")

        return {
            "success": True,
            "creator_id": creator_id,
            "email": email,
            "deleted": deleted,
            "errors": errors if errors else None,
        }

    except Exception as e:
        logger.error(f"[FullReset] Error: {e}")
        import traceback

        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}
