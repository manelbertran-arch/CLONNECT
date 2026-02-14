"""Full auto-setup V2 endpoints with background processing."""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from .helpers import _get_clone_status_db, _update_clone_status_db, setup_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# =============================================================================
# FULL AUTO-SETUP V2 - Uses all V2 technologies for zero-hallucination
# =============================================================================


class FullAutoSetupRequest(BaseModel):
    """Request para auto-configuracion completa."""

    creator_id: str
    instagram_username: str
    website_url: Optional[str] = None
    max_posts: int = 50
    transcribe_videos: bool = False  # Disabled by default (slow)


@router.post("/full-auto-setup")
async def full_auto_setup(request: FullAutoSetupRequest, background_tasks: BackgroundTasks):
    """
    Auto-configuracion completa V2 del clon.

    Este endpoint ejecuta TODO el pipeline de creacion de clon:
    1. Scrapea 50 posts de Instagram con sanity checks V2
    2. Transcribe videos/reels con Whisper (opcional)
    3. Scrapea website y detecta productos con V2 signals
    4. Genera ToneProfile desde el contenido
    5. Indexa todo para RAG con citations
    6. Actualiza el Creator y activa el bot

    El proceso puede tardar 3-5 minutos si transcribe videos.
    Para una UX rapida, usar quick-setup primero y este en background.

    Body:
    ```json
    {
        "creator_id": "stefano_bonanno",
        "instagram_username": "stefanobonanno",
        "website_url": "https://stefanobonanno.com",
        "max_posts": 50,
        "transcribe_videos": false
    }
    ```

    Returns:
        AutoConfigResult con estadisticas completas del proceso
    """
    try:
        from core.auto_configurator import auto_configure_clone

        logger.info(f"[FullAutoSetup] Starting for {request.creator_id}")

        result = await auto_configure_clone(
            creator_id=request.creator_id,
            instagram_username=request.instagram_username,
            website_url=request.website_url,
            max_posts=request.max_posts,
            transcribe_videos=request.transcribe_videos,
        )

        if not result.success and not result.steps_completed:
            raise HTTPException(
                status_code=400, detail=f"Auto-configuration failed: {result.errors}"
            )

        logger.info(
            f"[FullAutoSetup] Completed for {request.creator_id}: "
            f"status={result.status}, steps={result.steps_completed}"
        )

        return result.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FullAutoSetup] Error for {request.creator_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/full-auto-setup-background")
async def full_auto_setup_background(
    request: FullAutoSetupRequest, background_tasks: BackgroundTasks
):
    """
    Version en background de full-auto-setup.

    Inicia el proceso y retorna inmediatamente.
    Usar /full-auto-setup/{creator_id}/status para ver progreso.
    """
    # Initialize status (memory + DB for persistence)
    initial_status = {
        "status": "in_progress",
        "progress": 0,
        "current_step": "starting",
        "steps_completed": [],
        "errors": [],
        "warnings": [],
        "result": {},
    }
    setup_status[request.creator_id] = initial_status
    _update_clone_status_db(request.creator_id, initial_status)

    # Run in background
    background_tasks.add_task(
        _run_full_auto_setup_background,
        request.creator_id,
        request.instagram_username,
        request.website_url,
        request.max_posts,
        request.transcribe_videos,
    )

    return {
        "status": "started",
        "message": "Auto-configuration started in background",
        "creator_id": request.creator_id,
        "check_status_at": f"/onboarding/full-auto-setup/{request.creator_id}/status",
    }


@router.get("/full-auto-setup/{creator_id}/status")
async def get_full_auto_setup_status(creator_id: str):
    """
    Obtiene el estado de la auto-configuracion en background.
    Now reads from DB to survive deploys (with memory cache for speed).
    """
    # First check memory cache (fast, but lost on deploy)
    if creator_id in setup_status:
        return setup_status[creator_id]

    # Fallback to DB (survives deploys)
    db_status = _get_clone_status_db(creator_id)
    if db_status:
        # Cache it in memory for next poll
        setup_status[creator_id] = db_status
        return db_status

    # No status found - return pending instead of not_found
    return {
        "status": "pending",
        "progress": 0,
        "creator_id": creator_id,
        "current_step": "waiting",
        "steps_completed": [],
        "errors": [],
        "warnings": [],
        "result": {},
        "message": "Setup not started yet",
    }


async def _run_full_auto_setup_background(
    creator_id: str,
    instagram_username: str,
    website_url: Optional[str],
    max_posts: int,
    transcribe_videos: bool,
):
    """Ejecuta auto-setup en background actualizando status en tiempo real."""
    status = setup_status[creator_id]

    def save_progress():
        """Helper to save progress to both memory and DB."""
        _update_clone_status_db(creator_id, status)

    db_session = None
    try:
        from api.database import SessionLocal
        from core.auto_configurator import AutoConfigurator

        # CRITICAL: Pass db_session so products get saved to database
        db_session = SessionLocal()
        configurator = AutoConfigurator(db_session=db_session)

        # Step 1: Instagram scraping
        status["current_step"] = "instagram_scraping"
        status["progress"] = 10
        save_progress()
        logger.info(f"[FullAutoSetup-BG] Step 1: Instagram scraping for {creator_id}")

        try:
            ig_result = await configurator._scrape_instagram(
                creator_id=creator_id, instagram_username=instagram_username, max_posts=max_posts
            )
            posts_scraped = ig_result.get("posts_scraped", 0)
            posts_passed = ig_result.get("posts_passed_sanity", posts_scraped)
            status["steps_completed"].append("instagram_scraping")
            status["progress"] = 30
            status["result"] = {
                "instagram": {"posts_scraped": posts_scraped, "sanity_passed": posts_passed}
            }
            save_progress()
            logger.info(f"[FullAutoSetup-BG] Instagram: {posts_scraped} posts scraped")
        except Exception as e:
            logger.warning(f"[FullAutoSetup-BG] Instagram error: {e}")
            status["errors"].append(f"Instagram: {str(e)}")
            save_progress()

        # Step 2: Website scraping + Product detection
        if website_url:
            status["current_step"] = "website_scraping"
            status["progress"] = 40
            save_progress()
            logger.info(f"[FullAutoSetup-BG] Step 2: Website scraping for {creator_id}")

            try:
                web_result = await configurator._scrape_website(
                    creator_id=creator_id, website_url=website_url
                )
                products_detected = web_result.get("products_detected", 0)
                status["steps_completed"].append("website_scraping")
                status["steps_completed"].append("product_detection")
                status["progress"] = 55
                if "result" not in status:
                    status["result"] = {}
                status["result"]["website"] = {"products_detected": products_detected}
                save_progress()
                logger.info(f"[FullAutoSetup-BG] Website: {products_detected} products detected")
            except Exception as e:
                logger.warning(f"[FullAutoSetup-BG] Website error: {e}")
                status["errors"].append(f"Website: {str(e)}")
                save_progress()
        else:
            status["steps_completed"].append("website_scraping")
            status["steps_completed"].append("product_detection")
            status["progress"] = 55
            save_progress()

        # Step 3: ToneProfile generation
        status["current_step"] = "tone_profile"
        status["progress"] = 65
        save_progress()
        logger.info(f"[FullAutoSetup-BG] Step 3: ToneProfile for {creator_id}")

        try:
            tone_result = await configurator._generate_tone_profile(creator_id)
            tone_generated = tone_result.get("success", False)
            tone_confidence = tone_result.get("confidence", 0.0)
            status["steps_completed"].append("tone_profile")
            status["progress"] = 80
            if "result" not in status:
                status["result"] = {}
            status["result"]["tone_profile"] = {
                "generated": tone_generated,
                "confidence": tone_confidence,
            }
            logger.info(f"[FullAutoSetup-BG] ToneProfile generated: {tone_generated}")
        except Exception as e:
            logger.warning(f"[FullAutoSetup-BG] ToneProfile error: {e}")
            status["errors"].append(f"ToneProfile: {str(e)}")

        # Step 4: Load DM History (includes lead scoring)
        status["current_step"] = "dm_history"
        status["progress"] = 70
        logger.info(f"[FullAutoSetup-BG] Step 4: Loading DM history for {creator_id}")

        try:
            dm_result = await configurator._load_dm_history(creator_id)
            if dm_result.get("success"):
                status["steps_completed"].append("dm_history")
                if "result" not in status:
                    status["result"] = {}
                status["result"]["dms"] = {
                    "conversations": dm_result.get("conversations_found", 0),
                    "messages": dm_result.get("messages_imported", 0),
                    "leads_created": dm_result.get("leads_created", 0),
                }
                logger.info(
                    f"[FullAutoSetup-BG] DM history loaded: {dm_result.get('messages_imported', 0)} messages"
                )
            else:
                reason = dm_result.get("reason", "Unknown")
                status["warnings"].append(f"DM history: {reason}")
                logger.info(f"[FullAutoSetup-BG] DM history skipped: {reason}")
        except Exception as e:
            logger.warning(f"[FullAutoSetup-BG] DM history error: {e}")
            status["warnings"].append(f"DM history: {str(e)}")

        # Step 5: Extract Bio
        status["current_step"] = "bio_extracted"
        status["progress"] = 78
        logger.info(f"[FullAutoSetup-BG] Step 5: Extracting bio for {creator_id}")

        try:
            bio_result = await configurator._extract_bio(creator_id, instagram_username)
            if bio_result.get("success"):
                status["steps_completed"].append("bio_extracted")
                if "result" not in status:
                    status["result"] = {}
                status["result"]["bio"] = {"loaded": True}
                logger.info(f"[FullAutoSetup-BG] Bio extracted successfully")
            else:
                logger.info(f"[FullAutoSetup-BG] Bio extraction skipped")
        except Exception as e:
            logger.warning(f"[FullAutoSetup-BG] Bio extraction error: {e}")
            status["warnings"].append(f"Bio extraction: {str(e)}")

        # Step 6: Generate FAQs
        status["current_step"] = "faqs_generated"
        status["progress"] = 85
        logger.info(f"[FullAutoSetup-BG] Step 6: Generating FAQs for {creator_id}")

        try:
            faq_result = await configurator._generate_faqs(creator_id)
            faqs_created = faq_result.get("faqs_created", 0)
            if faqs_created > 0:
                status["steps_completed"].append("faqs_generated")
                if "result" not in status:
                    status["result"] = {}
                status["result"]["faqs"] = {"generated": faqs_created}
                logger.info(f"[FullAutoSetup-BG] Generated {faqs_created} FAQs")
            else:
                logger.info(f"[FullAutoSetup-BG] No new FAQs generated")
        except Exception as e:
            logger.warning(f"[FullAutoSetup-BG] FAQ generation error: {e}")
            status["warnings"].append(f"FAQ generation: {str(e)}")

        # Step 7: Update Creator (includes RAG indexing)
        status["current_step"] = "creator_updated"
        status["progress"] = 92
        logger.info(f"[FullAutoSetup-BG] Step 7: Updating creator {creator_id}")

        try:
            await configurator._update_creator(
                creator_id=creator_id,
                instagram_username=instagram_username,
                website_url=website_url,
                tone_confidence=status.get("result", {})
                .get("tone_profile", {})
                .get("confidence", 0.0),
            )
            status["steps_completed"].append("creator_updated")
            logger.info(f"[FullAutoSetup-BG] Creator updated")
        except Exception as e:
            logger.warning(f"[FullAutoSetup-BG] Creator update error: {e}")
            status["warnings"].append(f"Creator update: {str(e)}")

        # Final status
        status["status"] = "completed"
        status["progress"] = 100
        status["current_step"] = "completed"
        save_progress()

        logger.info(
            f"[FullAutoSetup-BG] Completed for {creator_id}: steps={status['steps_completed']}"
        )

    except Exception as e:
        logger.error(f"[FullAutoSetup-BG] Error for {creator_id}: {e}")
        import traceback

        traceback.print_exc()
        status["status"] = "failed"
        status["errors"].append(str(e))
        save_progress()
    finally:
        # Always close db session to prevent connection leaks
        if db_session:
            db_session.close()
