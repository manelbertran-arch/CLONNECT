"""Wizard onboarding and clone creation endpoints."""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# =============================================================================
# WIZARD ONBOARDING ENDPOINTS (New multi-step flow)
# =============================================================================


class WizardProfileData(BaseModel):
    """Profile data from wizard onboarding."""

    business_name: str
    description: str
    tone: str  # 'formal', 'casual', 'friendly'


class WizardProductData(BaseModel):
    """Product data from wizard onboarding."""

    name: str
    description: str
    price: Optional[float] = None


class WizardCompleteRequest(BaseModel):
    """Request for completing wizard onboarding."""

    creator_id: str
    profile: WizardProfileData
    products: List[WizardProductData] = []
    bot_active: bool = True


@router.post("/complete")
async def complete_wizard_onboarding(request: WizardCompleteRequest):
    """
    Complete the wizard onboarding process.
    Saves profile, products, and activates the bot.

    This is called from the new multi-step onboarding wizard.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Product

        session = SessionLocal()
        try:
            # Find or create creator
            creator = session.query(Creator).filter_by(name=request.creator_id).first()

            if not creator:
                import uuid

                logger.warning(f"Creator {request.creator_id} not found, creating...")
                creator = Creator(
                    id=uuid.uuid4(),
                    name=request.creator_id,
                    email=f"{request.creator_id}@clonnect.com",
                )
                session.add(creator)
                session.flush()

            # Update profile - use existing fields
            creator.clone_name = request.profile.business_name
            creator.clone_tone = request.profile.tone
            # Store description in knowledge_about JSON
            if not creator.knowledge_about:
                creator.knowledge_about = {}
            creator.knowledge_about["business_description"] = request.profile.description
            creator.knowledge_about["business_name"] = request.profile.business_name

            # Update bot status
            creator.bot_active = request.bot_active
            creator.onboarding_completed = True
            creator.copilot_mode = True  # Enable copilot mode by default

            # Add products
            for prod in request.products:
                product = Product(
                    creator_id=creator.id,
                    name=prod.name,
                    description=prod.description,
                    price=prod.price,
                    active=True,
                )
                session.add(product)

            session.commit()

            logger.info(
                f"Wizard onboarding completed for {request.creator_id}: "
                f"profile={request.profile.business_name}, "
                f"products={len(request.products)}, "
                f"bot_active={request.bot_active}"
            )

            return {
                "status": "success",
                "creator_id": request.creator_id,
                "profile_saved": True,
                "products_added": len(request.products),
                "bot_active": request.bot_active,
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error completing wizard onboarding: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# CLONE CREATION ENDPOINTS (New Flow)
# =============================================================================


class StartCloneRequest(BaseModel):
    """Request to start clone creation process."""

    creator_id: str
    website_url: Optional[str] = None


# Helper function to update clone progress in database (persistent across workers)
def _update_clone_progress(
    creator_id: str,
    status: str = None,
    step: str = None,
    step_status: str = None,
    percent: int = None,
    error: str = None,
    extra: dict = None,
):
    """
    Update clone progress in database. This persists across workers/restarts.

    Args:
        creator_id: Creator's name/ID
        status: Overall status (in_progress, complete, error)
        step: Current step name (instagram, website, training, activating)
        step_status: Step status (pending, active, completed)
        percent: Progress percentage (0-100)
        error: Error message if status is "error"
        extra: Extra data to merge into progress JSON
    """
    from datetime import datetime, timezone

    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            logger.warning(f"[Progress] Creator {creator_id} not found")
            return

        # Initialize progress dict if empty
        if not creator.clone_progress:
            creator.clone_progress = {
                "steps": {
                    "instagram": "pending",
                    "website": "pending",
                    "training": "pending",
                    "activating": "pending",
                },
                "percent": 0,
                "messages_synced": 0,
                "leads_created": 0,
            }

        # Update status
        if status:
            creator.clone_status = status
            if status == "in_progress" and not creator.clone_started_at:
                creator.clone_started_at = datetime.now(timezone.utc)
            elif status == "complete":
                creator.clone_completed_at = datetime.now(timezone.utc)

        # Update step status
        if step and step_status:
            progress = dict(creator.clone_progress)  # Make mutable copy
            if "steps" not in progress:
                progress["steps"] = {}
            progress["steps"][step] = step_status
            creator.clone_progress = progress

        # Update percent
        if percent is not None:
            progress = dict(creator.clone_progress)
            progress["percent"] = percent
            creator.clone_progress = progress

        # Update error
        if error:
            creator.clone_error = error

        # Merge extra data
        if extra:
            progress = dict(creator.clone_progress)
            progress.update(extra)
            creator.clone_progress = progress

        session.commit()
        logger.debug(
            f"[Progress] Updated {creator_id}: status={status}, step={step}={step_status}, percent={percent}"
        )

    except Exception as e:
        logger.error(f"[Progress] Error updating progress: {e}")
        session.rollback()
    finally:
        session.close()


@router.post("/start-clone")
async def start_clone_creation(request: StartCloneRequest, background_tasks: BackgroundTasks):
    """
    Start the clone creation process.
    This triggers background tasks to:
    1. Scrape Instagram posts
    2. Scrape website (if provided)
    3. Generate tone profile (Magic Slice)
    4. Index content in RAG
    5. Activate the bot

    Progress is persisted in database (not in-memory) for reliability.
    """
    from datetime import datetime, timezone

    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=request.creator_id).first()

            if not creator:
                raise HTTPException(
                    status_code=404, detail=f"Creator {request.creator_id} not found"
                )

            if not creator.instagram_token:
                raise HTTPException(status_code=400, detail="Instagram not connected")

            # Initialize progress tracking IN DATABASE (persists across workers)
            creator.clone_status = "in_progress"
            creator.clone_started_at = datetime.now(timezone.utc)
            creator.clone_completed_at = None
            creator.clone_error = None
            creator.clone_progress = {
                "steps": {
                    "instagram": "active",
                    "website": "pending",
                    "training": "pending",
                    "activating": "pending",
                },
                "percent": 0,
                "messages_synced": 0,
                "leads_created": 0,
            }

            # Store website URL if provided
            if request.website_url:
                if not creator.knowledge_about:
                    creator.knowledge_about = {}
                creator.knowledge_about["website_url"] = request.website_url
                # CRITICAL: flag_modified required for SQLAlchemy to detect JSON field changes
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(creator, "knowledge_about")
                logger.info(f"[CloneCreation] Saved website_url: {request.website_url}")

            session.commit()
            logger.info(f"[CloneCreation] Started for {request.creator_id}, progress saved to DB")

            # Start background clone creation
            background_tasks.add_task(
                _run_clone_creation,
                creator_id=request.creator_id,
                website_url=request.website_url,
            )

            return {
                "status": "started",
                "creator_id": request.creator_id,
                "message": "Clone creation started in background",
            }

        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting clone creation: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/progress/{creator_id}")
async def get_clone_progress(creator_id: str):
    """
    Get the progress of clone creation.
    Returns current step status for polling from frontend.

    Progress is read from database (persistent, works across workers).
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            # Read progress from database (persistent across workers)
            clone_status = creator.clone_status or "pending"
            clone_progress_data = creator.clone_progress or {}

            # Build response from DB fields
            steps = clone_progress_data.get(
                "steps",
                {
                    "instagram": "pending",
                    "website": "pending",
                    "training": "pending",
                    "activating": "pending",
                },
            )

            response = {
                "status": clone_status,
                "steps": steps,
                "percent": clone_progress_data.get("percent", 0),
                "messages_synced": clone_progress_data.get("messages_synced", 0),
                "leads_created": clone_progress_data.get("leads_created", 0),
            }

            # Include error if present
            if creator.clone_error:
                response["error"] = creator.clone_error

            # If onboarding is completed but status wasn't updated, fix it
            if creator.onboarding_completed and clone_status != "complete":
                response["status"] = "complete"
                response["steps"] = {
                    "instagram": "completed",
                    "website": "completed",
                    "training": "completed",
                    "activating": "completed",
                }

            logger.debug(f"[Progress] {creator_id}: status={response['status']}, steps={steps}")
            return response

        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting clone progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _run_clone_creation(creator_id: str, website_url: str = None):
    """
    Background task to run the full clone creation pipeline.
    Updates progress IN DATABASE as each step completes (persistent across workers).
    """
    logger.info("[CloneCreation] STARTING _run_clone_creation for %s", creator_id)
    try:
        from api.database import SessionLocal
        from api.models import Creator

        logger.debug("[CloneCreation] Opening database session...")
        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator or not creator.instagram_token:
                logger.error(
                    "[CloneCreation] Creator %s not found or no Instagram token", creator_id
                )
                _update_clone_progress(
                    creator_id, status="error", error="Creator not found or no Instagram token"
                )
                return

            access_token = creator.instagram_token
            instagram_user_id = creator.instagram_user_id or ""
            page_id = creator.instagram_page_id or ""

            # FALLBACK: Get website_url from knowledge_about if not provided as parameter
            if not website_url and creator.knowledge_about:
                website_url = creator.knowledge_about.get("website_url")
                if website_url:
                    logger.info(
                        "[CloneCreation] FALLBACK: Using website_url from knowledge_about: %s",
                        website_url,
                    )

            # Step 1: Scrape Instagram posts
            logger.info(f"[CloneCreation] Step 1: Scraping Instagram for {creator_id}")
            _update_clone_progress(creator_id, step="instagram", step_status="active", percent=10)

            try:
                from ingestion import MetaGraphAPIScraper

                scraper = MetaGraphAPIScraper(
                    access_token=access_token, instagram_business_id=instagram_user_id
                )
                posts = await scraper.get_posts(limit=50)
                logger.info(f"[CloneCreation] Scraped {len(posts)} posts")
            except Exception as e:
                logger.warning(f"[CloneCreation] Instagram scraping failed: {e}")
                posts = []

            _update_clone_progress(
                creator_id, step="instagram", step_status="completed", percent=25
            )

            # Step 2: Website ingestion (RAG + Products) - Using ONLY IngestionV2Pipeline
            _update_clone_progress(creator_id, step="website", step_status="active", percent=30)

            if website_url:
                logger.info(
                    f"[CloneCreation] Step 2: Website ingestion (RAG + Products) from {website_url}"
                )
                try:
                    from ingestion.v2.pipeline import IngestionV2Pipeline

                    # Use existing db session - guaranteed valid at this point
                    logger.info(
                        f"[CloneCreation] Using db_session={session} for IngestionV2Pipeline"
                    )
                    pipeline = IngestionV2Pipeline(db_session=session, max_pages=100)
                    result = await pipeline.run(
                        creator_id=creator_id,
                        website_url=website_url,
                        clean_before=True,  # Clean old data before ingesting
                        re_verify=True,
                    )

                    # Log results
                    logger.info(
                        f"[CloneCreation] Website ingestion complete: "
                        f"pages={result.pages_scraped}, "
                        f"products_detected={result.products_detected}, "
                        f"products_saved={result.products_saved}, "
                        f"rag_docs={result.rag_docs_saved}"
                    )
                    logger.info(
                        "[CloneCreation] Results: products=%d, rag_docs=%d",
                        result.products_saved,
                        result.rag_docs_saved,
                    )

                    if result.products_saved == 0 and result.products_detected > 0:
                        logger.warning(
                            f"[CloneCreation] WARNING: {result.products_detected} products detected but 0 saved!"
                        )
                except Exception as e:
                    logger.error("[CloneCreation] Website ingestion failed: %s", e, exc_info=True)
            else:
                logger.info(f"[CloneCreation] Step 2: No website provided, skipping")

            _update_clone_progress(creator_id, step="website", step_status="completed", percent=45)

            # Step 3: Generate tone profile (Magic Slice)
            _update_clone_progress(creator_id, step="training", step_status="active", percent=50)
            logger.info("[CloneCreation] Step 3: Training clone with %d posts", len(posts))

            if posts:
                try:
                    logger.debug("[CloneCreation] Importing onboarding service...")
                    from core.onboarding_service import OnboardingRequest, get_onboarding_service

                    posts_data = []
                    for p in posts:
                        if p.caption and len(p.caption.strip()) > 10:
                            posts_data.append(
                                {
                                    "post_id": p.post_id,
                                    "caption": p.caption,
                                    "post_type": p.post_type,
                                }
                            )

                    logger.debug("[CloneCreation] Created %d posts for training", len(posts_data))
                    logger.debug("[CloneCreation] Getting onboarding service...")
                    service = get_onboarding_service()
                    logger.debug("[CloneCreation] Got service: %s", type(service))
                    request = OnboardingRequest(
                        creator_id=creator_id, manual_posts=posts_data, scraping_method="manual"
                    )
                    logger.debug("[CloneCreation] Created request with %d posts", len(posts_data))
                    logger.debug("[CloneCreation] About to call service.onboard_creator()...")
                    result = await service.onboard_creator(request)
                    logger.info("[CloneCreation] Training complete: %s", result)
                except Exception as e:
                    logger.warning("[CloneCreation] Training failed: %s", e, exc_info=True)
            else:
                logger.info("[CloneCreation] No posts to train with, skipping")

            _update_clone_progress(creator_id, step="training", step_status="completed", percent=70)
            logger.debug("[CloneCreation] Training step completed, moving to DM sync")

            # Step 4: Sync DM history (with pagination)
            _update_clone_progress(creator_id, step="activating", step_status="active", percent=75)
            logger.info("[CloneCreation] Step 4: Syncing DM history")

            try:
                logger.debug("[CloneCreation] Importing _simple_dm_sync_internal...")
                from api.routers.oauth import _simple_dm_sync_internal

                logger.debug("[CloneCreation] Calling _simple_dm_sync_internal with max_convs=10")
                # Rate-limited: 10 conversations with 2s delay between each
                dm_stats = await _simple_dm_sync_internal(
                    creator_id=creator_id,
                    access_token=access_token,
                    ig_user_id=instagram_user_id,
                    ig_page_id=page_id,
                    max_convs=10,
                )
                logger.info("[CloneCreation] DM sync complete: %s", dm_stats)
                _update_clone_progress(
                    creator_id,
                    extra={
                        "messages_synced": dm_stats.get("messages_saved", 0),
                        "leads_created": dm_stats.get("leads_created", 0),
                    },
                )
            except Exception as e:
                logger.warning("[CloneCreation] DM sync failed: %s", e, exc_info=True)

            _update_clone_progress(creator_id, percent=90)

            # Step 5: Activate bot and mark complete
            logger.info(f"[CloneCreation] Step 5: Activating bot")

            # Refresh creator from DB
            session.expire(creator)
            creator = session.query(Creator).filter_by(name=creator_id).first()

            creator.bot_active = True
            creator.onboarding_completed = True
            creator.copilot_mode = True
            creator.clone_status = "complete"
            session.commit()

            _update_clone_progress(
                creator_id,
                status="complete",
                step="activating",
                step_status="completed",
                percent=100,
            )

            logger.info(f"[CloneCreation] Clone creation complete for {creator_id}")

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[CloneCreation] Error: {e}")
        import traceback

        logger.error(traceback.format_exc())
        _update_clone_progress(creator_id, status="error", error=str(e))
