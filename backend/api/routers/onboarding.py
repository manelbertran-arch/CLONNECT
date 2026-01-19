"""Onboarding checklist endpoints + Magic Slice pipeline + Full Auto-Setup"""
import os
import logging
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict

from core.products import ProductManager
from core.creator_config import CreatorConfigManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# =============================================================================
# SETUP STATUS - Now persisted in DB (with memory cache for fast access)
# =============================================================================

setup_status: Dict[str, Dict] = {}  # Memory cache, also persisted to DB


def _update_clone_status_db(creator_id: str, status_data: Dict):
    """Persist clone setup status to database (survives deploys)."""
    try:
        from api.database import SessionLocal
        from api.models import Creator
        from datetime import datetime, timezone

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator:
                creator.clone_status = status_data.get("status", "in_progress")
                creator.clone_progress = status_data
                if status_data.get("status") == "in_progress" and not creator.clone_started_at:
                    creator.clone_started_at = datetime.now(timezone.utc)
                if status_data.get("status") in ["completed", "failed"]:
                    creator.clone_completed_at = datetime.now(timezone.utc)
                session.commit()
                logger.debug(f"[CloneStatus] Saved to DB: {creator_id} -> {status_data.get('status')}")
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"[CloneStatus] Failed to save to DB: {e}")


def _get_clone_status_db(creator_id: str) -> Optional[Dict]:
    """Get clone setup status from database."""
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator and creator.clone_progress:
                return creator.clone_progress
            elif creator:
                return {
                    "status": creator.clone_status or "pending",
                    "progress": 0 if creator.clone_status == "pending" else 100 if creator.clone_status == "completed" else 0,
                    "current_step": "completed" if creator.clone_status == "completed" else "pending",
                    "steps_completed": [],
                    "errors": [],
                    "warnings": [],
                    "result": {}
                }
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"[CloneStatus] Failed to read from DB: {e}")
    return None


# =============================================================================
# PYDANTIC MODELS FOR MAGIC SLICE ONBOARDING
# =============================================================================

class PostInput(BaseModel):
    """Post input for onboarding."""
    caption: str
    post_id: Optional[str] = None
    post_type: Optional[str] = "instagram_post"
    url: Optional[str] = None
    permalink: Optional[str] = None
    timestamp: Optional[str] = None
    likes_count: Optional[int] = None
    comments_count: Optional[int] = None


class QuickOnboardRequest(BaseModel):
    """Request simplificado para onboarding rapido."""
    creator_id: str
    posts: List[PostInput]


class FullOnboardRequest(BaseModel):
    """Request completo para onboarding."""
    creator_id: str
    instagram_username: Optional[str] = None
    instagram_access_token: Optional[str] = None
    manual_posts: Optional[List[Dict]] = None
    scraping_method: str = "manual"
    max_posts: int = 50


# =============================================================================
# EXISTING HELPER FUNCTIONS
# =============================================================================


async def check_instagram_connected(creator_id: str) -> bool:
    """Check if Instagram is connected for this creator"""
    try:
        # Check database first
        from api.database import DATABASE_URL, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if creator and creator.instagram_token:
                    return len(creator.instagram_token) > 10
            finally:
                session.close()
    except Exception as e:
        logger.warning(f"DB check failed for instagram: {e}")
    return False


async def check_telegram_connected(creator_id: str) -> bool:
    """Check if Telegram bot is configured for this creator"""
    try:
        # Check database first
        from api.database import DATABASE_URL, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if creator and creator.telegram_bot_token:
                    return len(creator.telegram_bot_token) > 10
            finally:
                session.close()
    except Exception as e:
        logger.warning(f"DB check failed for telegram: {e}")
    return False


async def check_whatsapp_connected(creator_id: str) -> bool:
    """Check if WhatsApp is configured - checks DB first, then env vars"""
    # First check if creator has WhatsApp configured in DB
    try:
        from api.database import DATABASE_URL, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if creator and creator.whatsapp_token and creator.whatsapp_phone_id:
                    return True
            finally:
                session.close()
    except Exception as e:
        logger.warning(f"DB check failed for whatsapp: {e}")

    # Fallback to env vars (account-level config)
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")  # Consistent with core/whatsapp.py
    return bool(token and phone_id and len(token) > 10)


async def check_has_products(creator_id: str) -> bool:
    """Check if creator has at least 1 product"""
    try:
        product_manager = ProductManager()
        products = product_manager.get_products(creator_id)
        return len(products) > 0
    except Exception as e:
        logger.warning(f"Error checking products: {e}")
        return False


async def check_personality_configured(creator_id: str) -> bool:
    """Check if personality/config is set up"""
    try:
        config_manager = CreatorConfigManager()
        config = config_manager.get_config(creator_id)
        # Check for essential fields
        has_name = bool(config.get("name"))
        has_personality = bool(config.get("personality")) or bool(config.get("tone"))
        return has_name and has_personality
    except Exception:
        return False


async def check_bot_active(creator_id: str) -> bool:
    """Check if bot is activated"""
    try:
        config_manager = CreatorConfigManager()
        return config_manager.is_bot_active(creator_id)
    except Exception:
        return False  # Default to inactive (paused)


@router.get("/{creator_id}/status")
async def get_onboarding_status(creator_id: str):
    """Get onboarding checklist status"""

    # Check each step
    steps = {
        "connect_instagram": await check_instagram_connected(creator_id),
        "connect_telegram": await check_telegram_connected(creator_id),
        "connect_whatsapp": await check_whatsapp_connected(creator_id),
        "add_product": await check_has_products(creator_id),
        "configure_personality": await check_personality_configured(creator_id),
        "activate_bot": await check_bot_active(creator_id)
    }

    # At least one messaging channel connected
    has_channel = steps["connect_instagram"] or steps["connect_telegram"] or steps["connect_whatsapp"]

    # Core steps (required for basic functionality)
    core_steps = {
        "connect_channel": has_channel,
        "add_product": steps["add_product"],
        "configure_personality": steps["configure_personality"],
        "activate_bot": steps["activate_bot"]
    }

    completed = sum(1 for v in core_steps.values() if v)
    total = len(core_steps)

    return {
        "status": "ok",
        "steps": steps,
        "core_steps": core_steps,
        "completed": completed,
        "total": total,
        "percentage": int((completed / total) * 100),
        "is_complete": completed == total,
        "next_step": _get_next_step(core_steps)
    }


def _get_next_step(steps: dict) -> dict:
    """Get the next step to complete"""
    step_info = {
        "connect_channel": {
            "label": "Conectar un canal de mensajes",
            "description": "Conecta Instagram, Telegram o WhatsApp",
            "link": "/settings?tab=connections"
        },
        "add_product": {
            "label": "Añadir un producto",
            "description": "Añade al menos un producto para vender",
            "link": "/settings?tab=products"
        },
        "configure_personality": {
            "label": "Configurar personalidad",
            "description": "Define cómo habla tu clon de IA",
            "link": "/settings?tab=personality"
        },
        "activate_bot": {
            "label": "Activar el bot",
            "description": "Activa las respuestas automáticas",
            "link": "/settings?tab=bot"
        }
    }

    for step_key, is_complete in steps.items():
        if not is_complete:
            return {
                "key": step_key,
                **step_info.get(step_key, {"label": step_key, "link": "/settings"})
            }

    return {"key": None, "label": "Completado", "link": "/dashboard"}


@router.post("/{creator_id}/skip")
async def skip_onboarding(creator_id: str):
    """Mark onboarding as skipped (user will configure later)"""
    # Could store in database/file that user skipped onboarding
    return {"status": "ok", "message": "Onboarding skipped"}


@router.get("/{creator_id}/visual-status")
async def get_visual_onboarding_status(creator_id: str):
    """Check if the visual onboarding tour has been completed"""
    try:
        from api.database import DATABASE_URL, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if creator:
                    return {
                        "status": "ok",
                        "onboarding_completed": creator.onboarding_completed or False
                    }
            finally:
                session.close()
    except Exception as e:
        logger.warning(f"Error checking visual onboarding status: {e}")

    return {"status": "ok", "onboarding_completed": False}


@router.post("/{creator_id}/complete")
async def complete_visual_onboarding(creator_id: str):
    """Mark the visual onboarding tour as completed"""
    try:
        from api.database import DATABASE_URL, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if creator:
                    creator.onboarding_completed = True
                    session.commit()
                    logger.info(f"Visual onboarding completed for creator: {creator_id}")
                    return {"status": "ok", "message": "Onboarding completed"}
                else:
                    # Creator doesn't exist in DB yet - create them
                    import uuid
                    new_creator = Creator(
                        id=uuid.uuid4(),
                        name=creator_id,
                        email=f"{creator_id}@clonnect.io",
                        onboarding_completed=True
                    )
                    session.add(new_creator)
                    session.commit()
                    logger.info(f"Created creator and completed onboarding: {creator_id}")
                    return {"status": "ok", "message": "Onboarding completed"}
            finally:
                session.close()
    except Exception as e:
        logger.error(f"Error completing visual onboarding: {e}")
        return {"status": "error", "message": str(e)}

    return {"status": "ok", "message": "Onboarding completed"}


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
            creator.knowledge_about['business_description'] = request.profile.description
            creator.knowledge_about['business_name'] = request.profile.business_name

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

            logger.info(f"Wizard onboarding completed for {request.creator_id}: "
                       f"profile={request.profile.business_name}, "
                       f"products={len(request.products)}, "
                       f"bot_active={request.bot_active}")

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
def _update_clone_progress(creator_id: str, status: str = None, step: str = None, step_status: str = None,
                           percent: int = None, error: str = None, extra: dict = None):
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
    from api.database import SessionLocal
    from api.models import Creator
    from datetime import datetime, timezone

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
        logger.debug(f"[Progress] Updated {creator_id}: status={status}, step={step}={step_status}, percent={percent}")

    except Exception as e:
        logger.error(f"[Progress] Error updating progress: {e}")
        session.rollback()
    finally:
        session.close()


class RunWebsitePipelineRequest(BaseModel):
    """Request to run website pipeline for existing creator."""
    creator_id: str
    website_url: str


@router.get("/test-scrape")
async def test_scrape(url: str):
    """
    Test endpoint to scrape a URL and return results without storing.
    For debugging the scraper.
    """
    print(f"[TestScrape] Testing scrape of: {url}", flush=True)

    try:
        from ingestion.deterministic_scraper import DeterministicScraper

        scraper = DeterministicScraper(timeout=10.0, max_pages=3)
        print(f"[TestScrape] Created scraper, starting scrape...", flush=True)

        pages = await scraper.scrape_website(url)
        print(f"[TestScrape] Scraped {len(pages)} pages", flush=True)

        return {
            "status": "success",
            "url": url,
            "pages_count": len(pages),
            "pages": [
                {
                    "url": p.url,
                    "title": p.title,
                    "content_length": len(p.main_content),
                    "sections_count": len(p.sections),
                    "has_content": p.has_content
                }
                for p in pages
            ]
        }
    except Exception as e:
        print(f"[TestScrape] ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


@router.post("/run-website-pipeline")
async def run_website_pipeline(request: RunWebsitePipelineRequest):
    """
    Manually run the website ingestion pipeline for an existing creator.
    Extracts products, FAQs, about sections, and indexes all content in RAG.
    """
    import asyncio
    import time

    print(f"[WebsitePipeline] ====== STARTING for {request.creator_id} ======", flush=True)
    print(f"[WebsitePipeline] URL: {request.website_url}", flush=True)
    start_time = time.time()

    try:
        print(f"[WebsitePipeline] Step 1: Importing modules...", flush=True)
        from api.database import SessionLocal
        from api.models import Creator
        from ingestion.deterministic_scraper import DeterministicScraper
        from ingestion.structured_extractor import get_structured_extractor
        from ingestion.content_store import ContentStore
        print(f"[WebsitePipeline] Imports done", flush=True)

        session = SessionLocal()
        print(f"[WebsitePipeline] DB session created", flush=True)
        try:
            # Verify creator exists
            creator = session.query(Creator).filter_by(name=request.creator_id).first()
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {request.creator_id} not found")
            print(f"[WebsitePipeline] Creator found: {creator.id}", flush=True)

            # Save website_url to creator's knowledge_about
            if not creator.knowledge_about:
                creator.knowledge_about = {}
            creator.knowledge_about['website_url'] = request.website_url
            session.commit()
            print(f"[WebsitePipeline] Saved website_url to knowledge_about", flush=True)

            # Step 1: Scrape website
            print(f"[WebsitePipeline] Step 2: Scraping website...", flush=True)
            scraper = DeterministicScraper(timeout=15.0, max_pages=5)
            pages = await scraper.scrape_website(request.website_url)
            print(f"[WebsitePipeline] Scraped {len(pages)} pages", flush=True)

            if not pages:
                return {
                    "status": "success",
                    "creator_id": request.creator_id,
                    "results": {"pages_scraped": 0, "error": "No content found"}
                }

            # Step 2: Extract structured content
            print(f"[WebsitePipeline] Step 3: Extracting structured content...", flush=True)
            extractor = get_structured_extractor()
            extracted = extractor.extract_all(pages)
            print(f"[WebsitePipeline] Extracted: {len(extracted.products)} products, {len(extracted.faqs)} FAQs, {len(extracted.about_sections)} about, {len(extracted.raw_chunks)} chunks", flush=True)

            # Step 3: Store products
            print(f"[WebsitePipeline] Step 4: Storing products...", flush=True)
            store = ContentStore(db_session=session)
            products_stats = {"created": 0, "updated": 0}
            if extracted.products:
                products_stats = store.store_products(request.creator_id, extracted.products)
            print(f"[WebsitePipeline] Products stored: {products_stats}", flush=True)

            # Step 4: Store RAG documents (skip to avoid N+1 issue for now)
            print(f"[WebsitePipeline] Step 5: Storing RAG documents (limited)...", flush=True)
            rag_stats = {"indexed": 0, "persisted": 0}
            # Only store first 20 chunks to avoid timeout
            limited_chunks = extracted.raw_chunks[:20] if len(extracted.raw_chunks) > 20 else extracted.raw_chunks
            if limited_chunks:
                rag_stats = store.store_rag_documents(request.creator_id, limited_chunks)
            print(f"[WebsitePipeline] RAG stored: {rag_stats}", flush=True)

            duration = time.time() - start_time
            print(f"[WebsitePipeline] ====== COMPLETED in {duration:.1f}s ======", flush=True)

            return {
                "status": "success",
                "creator_id": request.creator_id,
                "website_url": request.website_url,
                "results": {
                    "pages_scraped": len(pages),
                    "products_found": len(extracted.products),
                    "products_created": products_stats.get("created", 0),
                    "faqs_found": len(extracted.faqs),
                    "about_sections_found": len(extracted.about_sections),
                    "rag_documents_indexed": rag_stats.get("indexed", 0),
                    "duration_seconds": duration
                }
            }

        finally:
            session.close()

    except asyncio.TimeoutError:
        print(f"[WebsitePipeline] TIMEOUT after 120s", flush=True)
        raise HTTPException(status_code=504, detail="Website pipeline timeout after 120s")
    except Exception as e:
        print(f"[WebsitePipeline] ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


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
                raise HTTPException(status_code=404, detail=f"Creator {request.creator_id} not found")

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
                creator.knowledge_about['website_url'] = request.website_url

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
            steps = clone_progress_data.get("steps", {
                "instagram": "pending",
                "website": "pending",
                "training": "pending",
                "activating": "pending",
            })

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
    print(f"[CloneCreation] ======= STARTING _run_clone_creation for {creator_id} =======", flush=True)
    print(f"[CloneCreation] Received website_url parameter: {website_url}", flush=True)
    try:
        from api.database import SessionLocal
        from api.models import Creator

        print(f"[CloneCreation] Opening database session...", flush=True)
        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator or not creator.instagram_token:
                print(f"[CloneCreation] ERROR: Creator {creator_id} not found or no Instagram token", flush=True)
                print(f"[CloneCreation] Creator exists: {creator is not None}", flush=True)
                if creator:
                    print(f"[CloneCreation] Creator.id: {creator.id}, has_token: {bool(creator.instagram_token)}", flush=True)
                logger.error(f"Creator {creator_id} not found or no Instagram token")
                _update_clone_progress(creator_id, status="error", error="Creator not found or no Instagram token")
                return

            # Log creator details for debugging
            print(f"[CloneCreation] Creator found: id={creator.id}, name={creator.name}", flush=True)
            access_token = creator.instagram_token
            instagram_user_id = creator.instagram_user_id or ""
            page_id = creator.instagram_page_id or ""

            # If website_url not passed as parameter, try to get from creator.knowledge_about
            if not website_url and creator.knowledge_about:
                website_url = creator.knowledge_about.get('website_url')
                print(f"[CloneCreation] Got website_url from knowledge_about: {website_url}", flush=True)

            print(f"[CloneCreation] Final website_url to use: {website_url}", flush=True)

            # Step 1: Scrape Instagram posts
            logger.info(f"[CloneCreation] Step 1: Scraping Instagram for {creator_id}")
            _update_clone_progress(creator_id, step="instagram", step_status="active", percent=10)

            try:
                from ingestion import MetaGraphAPIScraper
                scraper = MetaGraphAPIScraper(
                    access_token=access_token,
                    instagram_business_id=instagram_user_id
                )
                posts = await scraper.get_posts(limit=50)
                logger.info(f"[CloneCreation] Scraped {len(posts)} posts")
            except Exception as e:
                logger.warning(f"[CloneCreation] Instagram scraping failed: {e}")
                posts = []

            _update_clone_progress(creator_id, step="instagram", step_status="completed", percent=25)

            # Step 2: Scrape website with FULL pipeline (products, FAQs, about, RAG)
            _update_clone_progress(creator_id, step="website", step_status="active", percent=30)

            if website_url:
                print(f"[CloneCreation] Step 2: Starting FULL website pipeline for {website_url}", flush=True)
                logger.info(f"[CloneCreation] Step 2: Scraping website {website_url}")
                try:
                    import asyncio
                    from api.database import SessionLocal
                    from ingestion.pipeline import IngestionPipeline

                    # Get DB session for pipeline
                    pipeline_session = SessionLocal()
                    try:
                        pipeline = IngestionPipeline(db_session=pipeline_session, max_pages=10)

                        # Run with 120s timeout
                        print(f"[CloneCreation] Running IngestionPipeline with 120s timeout...", flush=True)
                        result = await asyncio.wait_for(
                            pipeline.run(
                                creator_id=creator_id,
                                website_url=website_url,
                                clear_existing=True  # Fresh start for new creator
                            ),
                            timeout=120
                        )

                        print(f"[CloneCreation] Website pipeline completed:", flush=True)
                        print(f"  - Pages scraped: {result.pages_scraped}", flush=True)
                        print(f"  - Products found: {result.products_found} ({result.products_with_price} with price)", flush=True)
                        print(f"  - FAQs found: {result.faqs_found}", flush=True)
                        print(f"  - About sections: {result.about_sections_found}", flush=True)
                        print(f"  - RAG documents: {result.rag_documents_indexed}", flush=True)
                        print(f"  - Duration: {result.duration_seconds:.1f}s", flush=True)

                        logger.info(
                            f"[CloneCreation] Website pipeline: {result.products_found} products, "
                            f"{result.faqs_found} FAQs, {result.rag_documents_indexed} RAG docs"
                        )

                        if result.errors:
                            print(f"[CloneCreation] Pipeline warnings: {result.errors}", flush=True)

                    finally:
                        pipeline_session.close()

                except asyncio.TimeoutError:
                    print(f"[CloneCreation] Website pipeline TIMEOUT after 120s - continuing anyway", flush=True)
                    logger.warning(f"[CloneCreation] Website pipeline timeout after 120s")
                except Exception as e:
                    print(f"[CloneCreation] Website pipeline FAILED: {e}", flush=True)
                    logger.warning(f"[CloneCreation] Website pipeline failed: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"[CloneCreation] Step 2: No website provided, skipping", flush=True)
                logger.info(f"[CloneCreation] Step 2: No website provided, skipping")

            _update_clone_progress(creator_id, step="website", step_status="completed", percent=45)

            # Step 3: Generate tone profile (Magic Slice)
            _update_clone_progress(creator_id, step="training", step_status="active", percent=50)
            print(f"[CloneCreation] Step 3: Training clone with {len(posts)} posts", flush=True)
            logger.info(f"[CloneCreation] Step 3: Training clone with {len(posts)} posts")

            if posts:
                try:
                    print(f"[CloneCreation] Importing onboarding service...", flush=True)
                    from core.onboarding_service import OnboardingRequest, get_onboarding_service

                    posts_data = []
                    for p in posts:
                        if p.caption and len(p.caption.strip()) > 10:
                            posts_data.append({
                                "post_id": p.post_id,
                                "caption": p.caption,
                                "post_type": p.post_type,
                            })

                    print(f"[CloneCreation] Created {len(posts_data)} posts for training", flush=True)
                    print(f"[CloneCreation] Getting onboarding service...", flush=True)
                    service = get_onboarding_service()
                    print(f"[CloneCreation] Got service: {type(service)}", flush=True)
                    request = OnboardingRequest(
                        creator_id=creator_id,
                        manual_posts=posts_data,
                        scraping_method="manual"
                    )
                    print(f"[CloneCreation] Created request with {len(posts_data)} posts", flush=True)
                    print(f"[CloneCreation] About to call service.onboard_creator()...", flush=True)
                    result = await service.onboard_creator(request)
                    print(f"[CloneCreation] onboard_creator() returned!", flush=True)
                    print(f"[CloneCreation] Training complete: {result}", flush=True)
                    logger.info(f"[CloneCreation] Training complete: {result}")
                except Exception as e:
                    print(f"[CloneCreation] Training failed: {e}", flush=True)
                    logger.warning(f"[CloneCreation] Training failed: {e}")
                    import traceback
                    print(traceback.format_exc(), flush=True)
            else:
                print(f"[CloneCreation] No posts to train with, skipping", flush=True)

            _update_clone_progress(creator_id, step="training", step_status="completed", percent=70)
            print(f"[CloneCreation] Training step completed, moving to DM sync", flush=True)

            # Step 4: Sync DM history (with pagination)
            _update_clone_progress(creator_id, step="activating", step_status="active", percent=75)
            print(f"[CloneCreation] Step 4: Syncing DM history", flush=True)
            logger.info(f"[CloneCreation] Step 4: Syncing DM history")

            try:
                print(f"[CloneCreation] Importing _simple_dm_sync_internal...", flush=True)
                from api.routers.oauth import _simple_dm_sync_internal
                print(f"[CloneCreation] Calling _simple_dm_sync_internal with max_convs=15", flush=True)
                # QUALITY STRATEGY: 15 conversations with ALL their messages
                # Better than 50 empty conversations - we need messages for categorization
                dm_stats = await _simple_dm_sync_internal(
                    creator_id=creator_id,
                    access_token=access_token,
                    ig_user_id=instagram_user_id,
                    ig_page_id=page_id,
                    max_convs=15  # Quality over quantity
                )
                print(f"[CloneCreation] DM sync complete: {dm_stats}", flush=True)
                logger.info(f"[CloneCreation] DM sync complete: {dm_stats}")
                _update_clone_progress(creator_id, extra={
                    "messages_synced": dm_stats.get("messages_saved", 0),
                    "leads_created": dm_stats.get("leads_created", 0),
                })
            except Exception as e:
                print(f"[CloneCreation] DM sync failed: {e}", flush=True)
                logger.warning(f"[CloneCreation] DM sync failed: {e}")
                import traceback
                print(traceback.format_exc(), flush=True)
                logger.warning(traceback.format_exc())

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

            _update_clone_progress(creator_id, status="complete", step="activating", step_status="completed", percent=100)

            logger.info(f"[CloneCreation] ✅ Clone creation complete for {creator_id}")

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[CloneCreation] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        _update_clone_progress(creator_id, status="error", error=str(e))


# =============================================================================
# MAGIC SLICE ONBOARDING ENDPOINTS
# =============================================================================

@router.post("/magic-slice/quick")
async def quick_onboard(request: QuickOnboardRequest):
    """
    Onboarding rapido con posts manuales.

    Simplificacion para casos donde ya tienes los posts.

    Body:
    ```json
    {
        "creator_id": "creator_123",
        "posts": [
            {"caption": "Mi primer post sobre nutricion..."},
            {"caption": "Hoy quiero hablarles de..."}
        ]
    }
    ```
    """
    from core.onboarding_service import OnboardingRequest, get_onboarding_service

    # Convertir posts a formato esperado
    manual_posts = [p.model_dump() for p in request.posts]

    full_request = OnboardingRequest(
        creator_id=request.creator_id,
        manual_posts=manual_posts,
        scraping_method="manual"
    )

    service = get_onboarding_service()
    result = await service.onboard_creator(full_request)

    if not result.success and not result.posts_processed:
        raise HTTPException(status_code=400, detail=result.errors)

    return result.to_dict()


@router.post("/magic-slice/creator")
async def full_onboard(request: FullOnboardRequest):
    """
    Onboarding completo de un creador.

    Flujo:
    1. Obtiene posts (scraping o manual)
    2. Genera ToneProfile
    3. Indexa contenido para citaciones

    Returns:
        OnboardingResult con estadisticas del proceso
    """
    from core.onboarding_service import OnboardingRequest, get_onboarding_service

    full_request = OnboardingRequest(
        creator_id=request.creator_id,
        instagram_username=request.instagram_username,
        instagram_access_token=request.instagram_access_token,
        manual_posts=request.manual_posts,
        scraping_method=request.scraping_method,
        max_posts=request.max_posts
    )

    service = get_onboarding_service()
    result = await service.onboard_creator(full_request)

    if not result.success and not result.posts_processed:
        raise HTTPException(status_code=400, detail=result.errors)

    return result.to_dict()


@router.get("/magic-slice/{creator_id}/status")
async def get_magic_slice_status(creator_id: str):
    """
    Verifica el estado de onboarding Magic Slice de un creador.

    Returns:
        - has_tone_profile: bool
        - has_content_index: bool
        - tone_summary: dict | null
        - citation_count: int
    """
    from core.tone_service import get_tone_profile
    from core.citation_service import get_content_index

    tone_profile = await get_tone_profile(creator_id)
    content_index = get_content_index(creator_id)

    tone_summary = None
    if tone_profile:
        tone_summary = {
            "formality": tone_profile.formality,
            "energy": tone_profile.energy,
            "warmth": tone_profile.warmth,
            "main_topics": tone_profile.main_topics[:5] if tone_profile.main_topics else []
        }

    return {
        "creator_id": creator_id,
        "has_tone_profile": tone_profile is not None,
        "has_content_index": content_index is not None and len(content_index.chunks) > 0,
        "tone_summary": tone_summary,
        "citation_count": len(content_index.chunks) if content_index else 0
    }


@router.delete("/magic-slice/{creator_id}/reset")
async def reset_magic_slice_data(creator_id: str):
    """
    Resetea los datos de Magic Slice de un creador.

    Util para re-onboarding con nuevo contenido.

    WARNING: Elimina ToneProfile y ContentIndex del creador.
    """
    from core.tone_service import delete_tone_profile
    from core.citation_service import delete_content_index

    tone_deleted = delete_tone_profile(creator_id)
    index_deleted = delete_content_index(creator_id)

    return {
        "creator_id": creator_id,
        "tone_profile_deleted": tone_deleted,
        "content_index_deleted": index_deleted
    }


# =============================================================================
# FULL AUTO-SETUP WITH REAL-TIME PROGRESS
# =============================================================================

@router.post("/full-setup/{creator_id}")
async def start_full_setup(creator_id: str, background_tasks: BackgroundTasks):
    """
    Inicia el setup completo en background.
    El frontend hace polling a /full-setup/{creator_id}/progress para ver progreso.

    Este endpoint simula el proceso completo mientras se conectan las APIs reales.
    En producción, cada paso se conectará a las APIs de Instagram, YouTube, etc.
    """
    # Initialize status
    setup_status[creator_id] = {
        "status": "in_progress",
        "progress": 0,
        "current_step": "starting",
        "steps": {
            "instagram_connected": False,
            "posts_imported": 0,
            "tone_profile_generated": False,
            "tone_summary": None,
            "content_indexed": 0,
            "dms_imported": 0,
            "leads_created": 0,
            "youtube_detected": False,
            "youtube_videos_imported": 0,
            "website_detected": False,
            "website_url": None
        },
        "errors": []
    }

    # Run setup in background
    background_tasks.add_task(run_full_setup_pipeline, creator_id)

    return {
        "status": "started",
        "message": "Setup started",
        "creator_id": creator_id
    }


@router.get("/full-setup/{creator_id}/progress")
async def get_full_setup_progress(creator_id: str):
    """
    Retorna el estado actual del setup.
    El frontend hace polling cada 2 segundos.
    """
    if creator_id not in setup_status:
        return {
            "status": "not_started",
            "progress": 0,
            "steps": {},
            "errors": []
        }

    return setup_status[creator_id]


async def run_full_setup_pipeline(creator_id: str):
    """
    Ejecuta todo el setup secuencialmente.
    Actualiza setup_status en cada paso para que el frontend vea el progreso.
    """
    status = setup_status[creator_id]

    try:
        # Paso 1: Marcar Instagram conectado (simulated - en producción viene de OAuth)
        await asyncio.sleep(0.5)
        status["steps"]["instagram_connected"] = True
        status["current_step"] = "instagram_connected"
        status["progress"] = 10
        logger.info(f"[FullSetup] {creator_id}: Instagram connected")

        # Paso 2: Importar posts
        await asyncio.sleep(1)
        posts = await import_instagram_posts_for_setup(creator_id)
        status["steps"]["posts_imported"] = len(posts) if posts else 25  # Demo value
        status["current_step"] = "posts_imported"
        status["progress"] = 25
        logger.info(f"[FullSetup] {creator_id}: Posts imported: {status['steps']['posts_imported']}")

        # Paso 3: Generar ToneProfile
        await asyncio.sleep(1.5)
        tone_result = await generate_tone_for_setup(creator_id, posts)
        status["steps"]["tone_profile_generated"] = tone_result.get("success", True)
        status["steps"]["tone_summary"] = tone_result.get("summary", "Cercano, dinámico, usa emojis")
        status["current_step"] = "tone_analyzed"
        status["progress"] = 45
        logger.info(f"[FullSetup] {creator_id}: Tone profile generated")

        # Paso 4: Indexar contenido
        await asyncio.sleep(1)
        indexed = await index_content_for_setup(creator_id, posts)
        status["steps"]["content_indexed"] = indexed if indexed else 150  # Demo value
        status["current_step"] = "content_indexed"
        status["progress"] = 60
        logger.info(f"[FullSetup] {creator_id}: Content indexed: {status['steps']['content_indexed']}")

        # Paso 5: Importar DMs (simulated)
        await asyncio.sleep(1)
        dms = await import_dms_for_setup(creator_id)
        status["steps"]["dms_imported"] = len(dms) if dms else 12  # Demo value
        status["current_step"] = "dms_imported"
        status["progress"] = 75
        logger.info(f"[FullSetup] {creator_id}: DMs imported: {status['steps']['dms_imported']}")

        # Paso 6: Crear leads de DMs
        await asyncio.sleep(0.5)
        leads = await convert_dms_to_leads_for_setup(creator_id, dms)
        status["steps"]["leads_created"] = len(leads) if leads else 8  # Demo value
        status["current_step"] = "leads_created"
        status["progress"] = 85
        logger.info(f"[FullSetup] {creator_id}: Leads created: {status['steps']['leads_created']}")

        # Paso 7: Detectar YouTube (simulated - en producción parsea bio)
        await asyncio.sleep(0.5)
        youtube_url = await detect_youtube_from_bio(creator_id)
        if youtube_url:
            status["steps"]["youtube_detected"] = True
            await asyncio.sleep(1)
            status["steps"]["youtube_videos_imported"] = 5  # Demo value
        status["current_step"] = "youtube_checked"
        status["progress"] = 95

        # Paso 8: Detectar website
        website_url = await detect_website_from_bio(creator_id)
        if website_url:
            status["steps"]["website_detected"] = True
            status["steps"]["website_url"] = website_url

        # Completado
        status["progress"] = 100
        status["status"] = "completed"
        status["current_step"] = "completed"
        logger.info(f"[FullSetup] {creator_id}: Setup completed successfully")

    except Exception as e:
        logger.error(f"[FullSetup] {creator_id}: Error - {e}")
        status["status"] = "error"
        status["errors"].append(str(e))


# =============================================================================
# SETUP HELPER FUNCTIONS
# =============================================================================

async def import_instagram_posts_for_setup(creator_id: str) -> List[Dict]:
    """Import Instagram posts for the creator."""
    try:
        # Try to use real onboarding service if posts exist
        from core.tone_service import get_tone_profile
        profile = await get_tone_profile(creator_id)
        if profile and profile.analyzed_posts_count > 0:
            # Return mock list representing existing posts
            return [{"id": i} for i in range(profile.analyzed_posts_count)]
    except Exception as e:
        logger.warning(f"[FullSetup] Could not get existing posts: {e}")

    # Return demo data
    return []


async def generate_tone_for_setup(creator_id: str, posts: List[Dict]) -> Dict:
    """Generate or retrieve ToneProfile for the creator."""
    try:
        from core.tone_service import get_tone_profile
        profile = await get_tone_profile(creator_id)
        if profile:
            # Generate human-readable summary
            traits = []
            if profile.formality in ["informal", "very_informal"]:
                traits.append("Cercano")
            elif profile.formality in ["formal", "very_formal"]:
                traits.append("Formal")
            else:
                traits.append("Neutro")

            if profile.energy in ["high", "very_high"]:
                traits.append("dinámico")
            elif profile.energy in ["low", "very_low"]:
                traits.append("calmado")

            if profile.uses_emojis:
                traits.append("usa emojis")

            return {
                "success": True,
                "summary": ", ".join(traits) if traits else "Personalidad analizada"
            }
    except Exception as e:
        logger.warning(f"[FullSetup] Could not get tone profile: {e}")

    return {"success": True, "summary": "Cercano, dinámico, usa emojis"}


async def index_content_for_setup(creator_id: str, posts: List[Dict]) -> int:
    """Index content for citations."""
    try:
        from core.citation_service import get_content_index
        index = get_content_index(creator_id)
        if index and hasattr(index, 'chunks'):
            return len(index.chunks)
    except Exception as e:
        logger.warning(f"[FullSetup] Could not get content index: {e}")

    return 0


async def import_dms_for_setup(creator_id: str) -> List[Dict]:
    """Import DMs from Instagram (simulated for now)."""
    # In production, this would call Instagram Graph API
    # GET /{ig-user-id}/conversations
    return []


async def convert_dms_to_leads_for_setup(creator_id: str, dms: List[Dict]) -> List[Dict]:
    """Convert imported DMs to leads."""
    try:
        from api.database import DATABASE_URL, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Lead
                leads = session.query(Lead).filter_by(creator_id=creator_id).all()
                return [{"id": str(l.id)} for l in leads]
            finally:
                session.close()
    except Exception as e:
        logger.warning(f"[FullSetup] Could not get leads: {e}")

    return []


async def detect_youtube_from_bio(creator_id: str) -> Optional[str]:
    """Detect YouTube channel from Instagram bio."""
    # In production, would parse bio for youtube.com links
    return None


async def detect_website_from_bio(creator_id: str) -> Optional[str]:
    """Detect website from Instagram bio."""
    # In production, would parse bio for website links
    return None


# =============================================================================
# INSTAGRAM SCRAPER ONBOARDING - Auto-setup desde username público
# =============================================================================

class ScrapeInstagramRequest(BaseModel):
    """Request para scraping automatizado de Instagram."""
    creator_id: str
    instagram_username: str
    max_posts: int = 50


class ScrapeInstagramResponse(BaseModel):
    """Response del scraping de Instagram."""
    success: bool
    creator_id: str
    instagram_username: str
    posts_scraped: int
    tone_profile_generated: bool
    tone_summary: Optional[Dict] = None
    content_indexed: int
    errors: List[str] = []


@router.post("/scrape-instagram", response_model=ScrapeInstagramResponse)
async def scrape_instagram_onboarding(request: ScrapeInstagramRequest):
    """
    Onboarding automatizado desde Instagram público.

    1. Scrapea los últimos N posts públicos del username
    2. Genera ToneProfile analizando el contenido
    3. Indexa el contenido para citations

    Args:
        creator_id: ID del creador en Clonnect
        instagram_username: Username de Instagram público (sin @)
        max_posts: Máximo de posts a scrapear (default 50)

    Returns:
        Resumen del onboarding realizado
    """
    errors = []
    posts_scraped = 0
    tone_generated = False
    tone_summary = None
    content_indexed = 0

    try:
        # Step 1: Scrape Instagram posts
        logger.info(f"[ScrapeOnboarding] Starting for {request.creator_id} from @{request.instagram_username}")

        from ingestion.instagram_scraper import InstaloaderScraper, InstagramScraperError

        scraper = InstaloaderScraper()

        try:
            posts = scraper.get_posts(
                target_username=request.instagram_username,
                limit=request.max_posts
            )
            posts_scraped = len(posts)
            logger.info(f"[ScrapeOnboarding] Scraped {posts_scraped} posts from @{request.instagram_username}")
        except InstagramScraperError as e:
            errors.append(f"Scraping error: {str(e)}")
            logger.error(f"[ScrapeOnboarding] Scraping failed: {e}")
            return ScrapeInstagramResponse(
                success=False,
                creator_id=request.creator_id,
                instagram_username=request.instagram_username,
                posts_scraped=0,
                tone_profile_generated=False,
                content_indexed=0,
                errors=errors
            )

        if posts_scraped == 0:
            errors.append("No posts found or profile is private")
            return ScrapeInstagramResponse(
                success=False,
                creator_id=request.creator_id,
                instagram_username=request.instagram_username,
                posts_scraped=0,
                tone_profile_generated=False,
                content_indexed=0,
                errors=errors
            )

        # Step 2: Generate ToneProfile
        try:
            from ingestion.tone_analyzer import ToneAnalyzer, ToneProfile
            from core.tone_service import save_tone_profile

            # Convert posts to dict format for analyzer
            posts_data = [
                {
                    "caption": post.caption,
                    "post_id": post.post_id,
                    "post_type": post.post_type,
                    "permalink": post.permalink,
                    "timestamp": post.timestamp.isoformat() if post.timestamp else None,
                    "likes_count": post.likes_count,
                    "comments_count": post.comments_count
                }
                for post in posts
            ]

            analyzer = ToneAnalyzer()
            tone_profile = await analyzer.analyze(request.creator_id, posts_data)

            # Save the profile
            await save_tone_profile(tone_profile)
            tone_generated = True

            tone_summary = {
                "formality": tone_profile.formality,
                "energy": tone_profile.energy,
                "warmth": tone_profile.warmth,
                "uses_emojis": tone_profile.uses_emojis,
                "emoji_frequency": tone_profile.emoji_frequency,
                "signature_phrases": tone_profile.signature_phrases[:5],
                "analyzed_posts": tone_profile.analyzed_posts_count,
                "primary_language": tone_profile.primary_language
            }

            logger.info(f"[ScrapeOnboarding] ToneProfile generated: {tone_profile.formality}, {tone_profile.energy}, lang={tone_profile.primary_language}")

            # Step 2b: Create basic creator_config if it doesn't exist
            try:
                config_manager = CreatorConfigManager()
                existing_config = config_manager.get_config(request.creator_id)

                if not existing_config or not existing_config.get('name'):
                    # Create basic config from ToneProfile
                    basic_config = {
                        "name": request.instagram_username,
                        "instagram_username": request.instagram_username,
                        "personality": {
                            "formality": tone_profile.formality,
                            "language": tone_profile.primary_language
                        },
                        "clone_tone": "friendly" if tone_profile.formality in ['informal', 'muy_informal'] else "professional",
                        "bot_active": True
                    }
                    config_manager.save_config(request.creator_id, basic_config)
                    logger.info(f"[ScrapeOnboarding] Created basic creator_config for {request.creator_id}")
            except Exception as config_error:
                logger.warning(f"[ScrapeOnboarding] Could not create creator_config: {config_error}")

        except Exception as e:
            errors.append(f"ToneProfile generation error: {str(e)}")
            logger.error(f"[ScrapeOnboarding] ToneProfile failed: {e}")

        # Step 3: Index content for citations
        try:
            import json
            from pathlib import Path
            from datetime import datetime

            # Create chunks from posts
            chunks = []
            posts_index = {}  # Dict with post_id as key (matches citation_service format)

            for i, post in enumerate(posts):
                if not post.caption or len(post.caption.strip()) < 20:
                    continue

                # Create a title from first line or truncated caption
                title_candidate = post.caption.split('\n')[0][:100]
                if len(title_candidate) < 10:
                    title_candidate = post.caption[:100]

                # Extract keywords from caption
                keywords = []
                # Add hashtags
                keywords.extend(post.hashtags[:5])
                # Add first few words
                words = post.caption.lower().split()[:10]
                keywords.extend([w for w in words if len(w) > 3])

                chunk = {
                    "id": f"{request.creator_id}_post_{post.post_id}",
                    "creator_id": request.creator_id,
                    "source_type": "instagram_post" if post.post_type != "reel" else "instagram_reel",
                    "source_id": post.post_id,
                    "source_url": post.permalink,
                    "title": title_candidate,
                    "content": post.caption[:1000],  # Limit content length
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "metadata": {
                        "post_type": post.post_type,
                        "likes": post.likes_count,
                        "comments": post.comments_count,
                        "hashtags": post.hashtags,
                        "keywords": list(set(keywords))[:10]
                    },
                    "created_at": post.timestamp.isoformat() if post.timestamp else datetime.utcnow().isoformat()
                }
                chunks.append(chunk)

                posts_index[post.post_id] = {
                    "post_id": post.post_id,
                    "caption": post.caption,
                    "post_type": post.post_type,
                    "url": post.permalink,
                    "published_date": post.timestamp.isoformat() if post.timestamp else None,
                    "chunk_count": 1
                }

            content_indexed = len(chunks)

            if content_indexed > 0:
                # Save to content_index directory (JSON backup)
                content_dir = Path("data/content_index") / request.creator_id
                content_dir.mkdir(parents=True, exist_ok=True)

                chunks_path = content_dir / "chunks.json"
                posts_path = content_dir / "posts.json"

                with open(chunks_path, 'w', encoding='utf-8') as f:
                    json.dump(chunks, f, ensure_ascii=False, indent=2)

                with open(posts_path, 'w', encoding='utf-8') as f:
                    json.dump(posts_index, f, ensure_ascii=False, indent=2)

                logger.info(f"[ScrapeOnboarding] Indexed {content_indexed} posts to JSON")

                # Save to PostgreSQL (primary storage)
                try:
                    from core.tone_profile_db import save_content_chunks_db, save_instagram_posts_db

                    # Save chunks to DB
                    chunks_saved = await save_content_chunks_db(request.creator_id, chunks)
                    logger.info(f"[ScrapeOnboarding] Saved {chunks_saved} chunks to PostgreSQL")

                    # Save Instagram posts to DB
                    posts_for_db = [
                        {
                            "id": post.post_id,
                            "caption": post.caption,
                            "permalink": post.permalink,
                            "media_type": post.post_type,
                            "timestamp": post.timestamp.isoformat() if post.timestamp else None,
                            "like_count": post.likes_count,
                            "comments_count": post.comments_count
                        }
                        for post in posts
                    ]
                    posts_saved = await save_instagram_posts_db(request.creator_id, posts_for_db)
                    logger.info(f"[ScrapeOnboarding] Saved {posts_saved} Instagram posts to PostgreSQL")

                    # Hydrate RAG with the new chunks (critical for search)
                    try:
                        from api.main import rag
                        loaded = rag.load_from_db(request.creator_id)
                        logger.info(f"[ScrapeOnboarding] Hydrated RAG with {loaded} chunks for {request.creator_id}")
                    except Exception as rag_error:
                        logger.warning(f"[ScrapeOnboarding] Could not hydrate RAG: {rag_error}")

                except Exception as db_error:
                    logger.warning(f"[ScrapeOnboarding] DB save failed (JSON backup exists): {db_error}")

                # Reload citation index
                try:
                    from core.citation_service import reload_creator_index
                    reload_creator_index(request.creator_id)
                except Exception as reload_error:
                    logger.warning(f"[ScrapeOnboarding] Could not reload index: {reload_error}")

        except Exception as e:
            errors.append(f"Content indexing error: {str(e)}")
            logger.error(f"[ScrapeOnboarding] Indexing failed: {e}")

        success = posts_scraped > 0 and (tone_generated or content_indexed > 0)

        return ScrapeInstagramResponse(
            success=success,
            creator_id=request.creator_id,
            instagram_username=request.instagram_username,
            posts_scraped=posts_scraped,
            tone_profile_generated=tone_generated,
            tone_summary=tone_summary,
            content_indexed=content_indexed,
            errors=errors
        )

    except Exception as e:
        logger.error(f"[ScrapeOnboarding] Unexpected error: {e}")
        errors.append(f"Unexpected error: {str(e)}")
        return ScrapeInstagramResponse(
            success=False,
            creator_id=request.creator_id,
            instagram_username=request.instagram_username,
            posts_scraped=posts_scraped,
            tone_profile_generated=tone_generated,
            content_indexed=content_indexed,
            errors=errors
        )


# =============================================================================
# MANUAL SETUP ENDPOINT - Full onboarding without OAuth
# =============================================================================

# =============================================================================
# STEFANO DATA - Pre-scraped from website
# =============================================================================

STEFANO_DATA = {
    "creator": {
        "name": "Stefano Bonanno",
        "tagline": "Te acompaño a sanar tu DOLOR y convertirlo en tu mayor FORTALEZA",
        "headline": "TRANSFORMA TU REALIDAD",
        "bio": """Coach, Terapeuta y Instructor de Movimiento y Respiración.

Después de años de sobreexigirme físicamente, descuidar mis emociones, tener patrones dependientes en relaciones y vivir inestabilidad financiera, una crisis me obligó a mirar hacia dentro. Esa crisis fue mi mayor regalo.

Hoy acompaño a otros en su viaje de transformación usando bioexistencia consciente, coaching cuántico, hipnosis, reprogramación inconsciente, breathwork y círculos de palabra.

El cambio constante produce una transformación, y al aplicarlo con conocimiento de leyes BIOLÓGICAS y espirituales, podrás desbloquear tu poder interior.""",
        "philosophy": "Trabajo con tres pilares: Mente Consciente (espacio seguro para expresión auténtica), Cuerpo Saludable (respiración y movimiento consciente), y Espíritu Libre (prácticas ancestrales + técnicas modernas).",
        "email": "coach@stefanobonanno.com",
        "phone": "695112016",
        "location": "Barcelona, España",
        "instagram": "@stefanobonanno",
        "website": "www.stefanobonanno.com"
    },
    "products": [
        {
            "id": "sintoma-plenitud",
            "name": "Del Síntoma a la Plenitud - Proceso 1:1",
            "description": """Programa personalizado de coaching 1:1 que combina coaching cuántico, reprogramación hipnótica y terapias holísticas para decodificar tus síntomas y lograr una transformación profunda.

Incluye:
• Análisis de síntomas y exploración de significados
• 3 sesiones de hipnosis para liberación emocional
• Sesiones de integración y coaching
• Soporte continuo por WhatsApp/email
• Acceso a dashboard personalizado con recursos

Duración: 3 meses
Sesiones: Semanales (12 sesiones totales)""",
            "price": 1497.0,
            "currency": "EUR",
            "duration": "3 meses",
            "type": "program",
            "category": "service",
            "product_type": "mentoria",
            "is_free": False,
            "includes": ["12 sesiones semanales", "3 sesiones de hipnosis", "Soporte WhatsApp", "Dashboard personalizado", "Recursos exclusivos"]
        },
        {
            "id": "sesion-coaching",
            "name": "Sesión de Coaching Cuántico",
            "description": """Sesión individual de coaching cuántico para trabajar un tema específico. Ideal si necesitas claridad sobre una situación, desbloquear una creencia limitante o recibir guía en un momento de transición.

La sesión incluye:
• Exploración profunda del tema
• Técnicas de reprogramación
• Plan de acción concreto
• Seguimiento por mensaje

Duración: 90 minutos""",
            "price": 150.0,
            "currency": "EUR",
            "duration": "90 minutos",
            "type": "session",
            "category": "service",
            "product_type": "coaching",
            "is_free": False,
            "includes": ["Sesión de 90 min", "Técnicas de reprogramación", "Plan de acción", "Seguimiento por mensaje"]
        },
        {
            "id": "discovery-call",
            "name": "Sesión Discovery Gratuita",
            "description": """Sesión de 30 minutos para conocernos, entender tu situación actual y ver si podemos trabajar juntos.

Sin compromiso. Solo una conversación honesta sobre dónde estás y dónde quieres llegar.

Reserva tu sesión y empecemos a transformar tu realidad.""",
            "price": 0.0,
            "currency": "EUR",
            "duration": "30 minutos",
            "type": "call",
            "category": "service",
            "product_type": "call",
            "is_free": True,
            "includes": ["Llamada de 30 min", "Análisis de situación", "Recomendación personalizada"]
        },
        {
            "id": "challenge-11-dias",
            "name": "Fitpack Challenge 11 Días",
            "description": """Programa intensivo de 11 días diseñado para transformar tu energía, movimiento y mentalidad.

Incluye:
• Entrenamientos diarios al aire libre
• Sesiones de breathwork
• Comunidad de apoyo
• Acceso al grupo privado
• Material de apoyo

Más de 3,000 personas ya han pasado por este challenge.

Próxima edición: Consultar fechas""",
            "price": 97.0,
            "currency": "EUR",
            "duration": "11 días",
            "type": "challenge",
            "category": "product",
            "product_type": "curso",
            "is_free": False,
            "includes": ["11 entrenamientos", "Sesiones breathwork", "Comunidad privada", "Material de apoyo"]
        },
        {
            "id": "taller-respira",
            "name": "Respira, Siente, Conecta - Taller Grupal",
            "description": """Experiencia transformadora que combina breathwork, meditación y baño de hielo.

Un espacio seguro para:
• Liberar tensiones acumuladas
• Conectar con tu cuerpo
• Superar límites mentales
• Conocer una comunidad consciente

Más de 1,000 personas han vivido esta experiencia.

Duración: 3 horas
Ubicación: Barcelona""",
            "price": 45.0,
            "currency": "EUR",
            "duration": "3 horas",
            "type": "workshop",
            "category": "service",
            "product_type": "sesion",
            "is_free": False,
            "includes": ["Sesión breathwork", "Meditación guiada", "Baño de hielo", "Comunidad"]
        },
        {
            "id": "podcast-sabios",
            "name": "Podcast Sabios y Salvajes",
            "description": """Episodios semanales donde comparto reflexiones, entrevistas y herramientas prácticas sobre desarrollo personal, bienestar y transformación consciente.

Disponible en Spotify y Apple Podcasts.""",
            "price": 0.0,
            "currency": "EUR",
            "type": "podcast",
            "category": "resource",
            "product_type": "podcast",
            "is_free": True,
            "includes": ["Episodios semanales", "Reflexiones prácticas", "Entrevistas exclusivas"]
        }
    ],
    "testimonials": [
        {
            "name": "Dafne Sandoval",
            "text": "Trabajar con Stefano transformó mi vida. Superé bloqueos, fortalecí mi relación conmigo misma y encontré claridad en momentos de confusión. Su enfoque es profundo pero accesible.",
            "program": "Proceso 1:1",
            "result": "Transformación profunda y empoderamiento"
        },
        {
            "name": "Eva González",
            "text": "Stefano me ayudó a desbloquear creencias que me frenaban. Sané patrones que arrastraba desde hace años. Su profesionalismo y cercanía hacen que te sientas en un espacio seguro.",
            "program": "Coaching Cuántico",
            "result": "Desbloqueo de creencias limitantes"
        },
        {
            "name": "Rocío Vargas",
            "text": "La terapia con Stefano marcó un antes y un después. Recuperé confianza en mí misma y me abrí a recibir. Cuatro meses de sesiones semanales que cambiaron mi perspectiva de vida.",
            "program": "Proceso 1:1",
            "result": "Recuperó confianza y apertura"
        },
        {
            "name": "Francisco Chiotta",
            "text": "Un espacio seguro y empático donde pude ser completamente auténtico. Stefano tiene un don para crear conexión genuina y guiarte hacia tu propia verdad.",
            "program": "Coaching Cuántico",
            "result": "Espacio seguro y conexión auténtica"
        },
        {
            "name": "Bianca Ioana Avram",
            "text": "Resultados rápidos y profundos. En pocas sesiones noté cambios significativos. La combinación de técnicas que usa Stefano es muy efectiva.",
            "program": "Proceso 1:1",
            "result": "Sanación profunda y rápida"
        },
        {
            "name": "Josh Feldberg",
            "text": "Llevo años trabajando con Stefano. Desde el bootcamp hasta el coaching individual, el apoyo ha sido integral. Ha sido clave en mi desarrollo personal y profesional.",
            "program": "Bootcamp + Coaching",
            "result": "Apoyo integral multi-año"
        }
    ],
    "faqs": [
        {
            "question": "¿Qué es el coaching cuántico?",
            "answer": "El coaching cuántico combina técnicas de coaching tradicional con principios de física cuántica y reprogramación del inconsciente. Trabajamos a nivel energético para transformar patrones limitantes y crear nuevas posibilidades en tu vida."
        },
        {
            "question": "¿Cuánto dura un proceso de coaching?",
            "answer": "El proceso 'Del Síntoma a la Plenitud' tiene una duración de 3 meses con sesiones semanales. También ofrezco sesiones individuales para temas específicos."
        },
        {
            "question": "¿Las sesiones son presenciales u online?",
            "answer": "Ofrezco ambas modalidades. Las sesiones presenciales son en Barcelona y las online las hacemos por videollamada. Ambas son igual de efectivas."
        },
        {
            "question": "¿Qué incluye el Challenge de 11 Días?",
            "answer": "El Fitpack Challenge incluye 11 días de entrenamientos al aire libre, sesiones de breathwork, acceso a comunidad privada y material de apoyo. Es una experiencia transformadora para tu cuerpo y mente."
        },
        {
            "question": "¿Cómo puedo empezar?",
            "answer": "El primer paso es agendar una Sesión Discovery gratuita de 30 minutos. Ahí hablamos de tu situación y vemos cuál es el mejor camino para ti. Sin compromiso."
        }
    ],
    "methodology": {
        "pillars": ["Mente Consciente", "Cuerpo Saludable", "Espíritu Libre"],
        "approach": "Tres etapas: Consciencia (hacer visible lo invisible), Autenticidad (reconectar con tu ser genuino), Transformación (reprogramar patrones inconscientes)",
        "methods": ["Coaching cuántico", "Hipnosis", "Reprogramación inconsciente", "Breathwork", "Meditación", "Baño de hielo", "Círculos de palabra"]
    },
    "tone_profile": {
        "formality": "informal",
        "energy": "high",
        "warmth": "very_warm",
        "uses_emojis": True,
        "common_emojis": ["🙏", "💪", "✨", "🔥", "❤️", "🌟"],
        "language": "es",
        "addressing": "tuteo",
        "style": "inspiracional, cercano, motivador, empático",
        "signature_phrases": [
            "Transforma tu realidad",
            "Del síntoma a la plenitud",
            "Tu dolor es tu mayor fortaleza",
            "Desbloquea tu poder interior"
        ]
    },
    "impact_numbers": {
        "individual_clients": 100,
        "challenge_participants": 3000,
        "workshop_participants": 1000
    }
}


class SeedDemoRequest(BaseModel):
    """Request para sembrar datos demo cuando Instagram está rate limited."""
    creator_id: str
    force: bool = False  # Si es true, crea datos aunque ya existan


@router.post("/seed-demo")
async def seed_demo_data(request: SeedDemoRequest):
    """
    Seed demo data for a creator when Instagram is rate limited.

    Creates:
    - 8 demo leads with various purchase intents
    - 3 demo products
    - Marks onboarding as completed
    - Activates the bot

    Use this when manual-setup fails due to Instagram rate limiting.
    """
    errors = []
    details = {
        "leads_created": 0,
        "products_created": 0
    }

    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Product
        import uuid as uuid_module
        from datetime import datetime, timedelta
        import random

        if not DATABASE_URL or not SessionLocal:
            return {"success": False, "error": "Database not configured"}

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
                    copilot_mode=True
                )
                session.add(creator)
                session.commit()
                logger.info(f"[SeedDemo] Created new creator: {request.creator_id}")

            creator_uuid = creator.id

            # Create demo products
            demo_products = [
                {"name": "Consultoría 1:1", "price": 150.0, "description": "Sesión de consultoría personalizada de 1 hora"},
                {"name": "Curso Online", "price": 97.0, "description": "Acceso completo al curso con materiales"},
                {"name": "Mentoría Grupal", "price": 49.0, "description": "Sesión grupal mensual con Q&A"},
            ]

            for prod in demo_products:
                existing = session.query(Product).filter_by(
                    creator_id=creator_uuid, name=prod["name"]
                ).first()
                if not existing or request.force:
                    if existing and request.force:
                        session.delete(existing)
                    new_product = Product(
                        id=uuid_module.uuid4(),
                        creator_id=creator_uuid,
                        name=prod["name"],
                        price=prod["price"],
                        description=prod["description"],
                        is_active=True
                    )
                    session.add(new_product)
                    details["products_created"] += 1

            # NOTE: Demo leads DISABLED - only load real Instagram DMs
            # demo_leads = [
            #     {"name": "María García", "platform": "instagram", "intent": 0.8, "status": "hot"},
            #     {"name": "Carlos López", "platform": "instagram", "intent": 0.6, "status": "warm"},
            #     {"name": "Ana Martínez", "platform": "instagram", "intent": 0.9, "status": "hot"},
            #     {"name": "Pedro Sánchez", "platform": "whatsapp", "intent": 0.4, "status": "warm"},
            #     {"name": "Laura Fernández", "platform": "instagram", "intent": 0.3, "status": "cold"},
            #     {"name": "Diego Ruiz", "platform": "instagram", "intent": 0.7, "status": "hot"},
            #     {"name": "Sofia Torres", "platform": "whatsapp", "intent": 0.5, "status": "warm"},
            #     {"name": "Miguel Herrera", "platform": "instagram", "intent": 0.2, "status": "cold"},
            # ]
            # for i, lead_data in enumerate(demo_leads):
            #     platform_user_id = f"demo_{lead_data['name'].lower().replace(' ', '_')}_{i}"
            #     existing = session.query(Lead).filter_by(
            #         creator_id=creator_uuid, platform_user_id=platform_user_id
            #     ).first()
            #     if not existing or request.force:
            #         if existing and request.force:
            #             session.delete(existing)
            #         new_lead = Lead(
            #             id=uuid_module.uuid4(),
            #             creator_id=creator_uuid,
            #             platform=lead_data["platform"],
            #             platform_user_id=platform_user_id,
            #             username=lead_data["name"].lower().replace(" ", "_"),
            #             full_name=lead_data["name"],
            #             purchase_intent=lead_data["intent"],
            #             status=lead_data["status"],
            #             first_contact_at=datetime.utcnow() - timedelta(days=random.randint(1, 30)),
            #             last_contact_at=datetime.utcnow() - timedelta(hours=random.randint(1, 72)),
            #             score=random.randint(30, 90)
            #         )
            #         session.add(new_lead)
            #         details["leads_created"] += 1

            # Mark onboarding as completed and activate bot
            creator.onboarding_completed = True
            creator.bot_active = True

            session.commit()
            logger.info(f"[SeedDemo] Created {details['leads_created']} leads and {details['products_created']} products for {request.creator_id}")

            return {
                "success": True,
                "creator_id": request.creator_id,
                "details": details,
                "onboarding_completed": True,
                "bot_activated": True
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[SeedDemo] Error: {e}")
        return {
            "success": False,
            "creator_id": request.creator_id,
            "error": str(e)
        }


@router.post("/inject-stefano-data")
async def inject_stefano_data():
    """
    Inject pre-scraped Stefano Bonanno data into the system.

    This endpoint:
    1. Creates real products from stefanobonanno.com
    2. Creates realistic demo leads with conversations
    3. Creates demo messages/conversations
    4. Generates ToneProfile based on his style
    5. Indexes all content in RAG for bot responses
    6. Marks onboarding as completed
    7. Activates the bot

    Use this for demos when Instagram is rate-limited.
    """
    creator_id = "stefano_auto"
    details = {
        "products_created": 0,
        "leads_created": 0,
        "messages_created": 0,
        "rag_documents": 0,
        "tone_profile": False
    }
    errors = []

    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Product, Message
        import uuid as uuid_module
        from datetime import datetime, timedelta
        import random
        import json

        if not DATABASE_URL or not SessionLocal:
            return {"success": False, "error": "Database not configured"}

        session = SessionLocal()
        try:
            # ================================================================
            # STEP 1: Get or create creator
            # ================================================================
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                creator = Creator(
                    id=uuid_module.uuid4(),
                    name=creator_id,
                    email="coach@stefanobonanno.com",
                    bot_active=True,
                    onboarding_completed=True,
                    copilot_mode=True,
                    clone_name="Stefano Bonanno",
                    clone_tone="inspirational"
                )
                session.add(creator)
                session.commit()
                logger.info(f"[InjectStefano] Created creator: {creator_id}")
            else:
                creator.clone_name = "Stefano Bonanno"
                creator.email = "coach@stefanobonanno.com"

            creator_uuid = creator.id

            # ================================================================
            # STEP 2: Delete existing data for clean injection
            # ================================================================
            # Delete existing messages for this creator's leads
            existing_leads = session.query(Lead).filter_by(creator_id=creator_uuid).all()
            for lead in existing_leads:
                session.query(Message).filter_by(lead_id=lead.id).delete()
            session.query(Lead).filter_by(creator_id=creator_uuid).delete()
            session.query(Product).filter_by(creator_id=creator_uuid).delete()
            session.commit()

            # ================================================================
            # STEP 3: Create REAL products from website
            # ================================================================
            for prod_data in STEFANO_DATA["products"]:
                new_product = Product(
                    id=uuid_module.uuid4(),
                    creator_id=creator_uuid,
                    name=prod_data["name"],
                    description=prod_data["description"],
                    price=prod_data["price"],
                    currency=prod_data.get("currency", "EUR"),
                    # Taxonomy fields
                    category=prod_data.get("category", "product"),
                    product_type=prod_data.get("product_type", "otro"),
                    is_free=prod_data.get("is_free", False),
                    is_active=True
                )
                session.add(new_product)
                details["products_created"] += 1

            # ================================================================
            # STEP 4: Create realistic leads with conversations
            # ================================================================
            demo_conversations = [
                {
                    "lead": {"name": "Carlos Méndez", "username": "carlos_wellness", "platform": "instagram", "intent": 0.9, "status": "hot"},
                    "messages": [
                        {"role": "user", "content": "Hola Stefano! Vi tu contenido sobre coaching cuántico y me interesa mucho. ¿Cómo funciona el proceso 1:1?"},
                        {"role": "assistant", "content": "¡Hola Carlos! 🙏 Qué bueno que te resuene el coaching cuántico. El proceso 'Del Síntoma a la Plenitud' es un viaje de 3 meses donde trabajamos juntos semanalmente. Combinamos coaching cuántico, hipnosis y reprogramación del inconsciente. ¿Qué te gustaría transformar en tu vida? ✨"},
                        {"role": "user", "content": "Llevo tiempo sintiéndome estancado en mi carrera y relaciones. ¿Cuánto cuesta el programa?"},
                        {"role": "assistant", "content": "Entiendo perfectamente ese sentimiento de estancamiento. El programa completo de 3 meses es €1497 e incluye 12 sesiones semanales, 3 sesiones de hipnosis, soporte por WhatsApp y acceso a recursos exclusivos. ¿Te gustaría agendar una sesión discovery gratuita de 30 min para conocernos? 💪"},
                    ]
                },
                {
                    "lead": {"name": "Laura Torres", "username": "laura_fit", "platform": "instagram", "intent": 0.7, "status": "hot"},
                    "messages": [
                        {"role": "user", "content": "Hola! Me interesa el Challenge de 11 días, ¿cuándo es el próximo?"},
                        {"role": "assistant", "content": "¡Hola Laura! 🔥 El Fitpack Challenge es una experiencia increíble. Más de 3,000 personas ya lo han vivido. Son 11 días de entrenamientos al aire libre, breathwork y comunidad. Cuesta €97 e incluye todo el material. Te escribo por privado las fechas disponibles 💪"},
                        {"role": "user", "content": "Genial! También vi que haces talleres de respiración, ¿me cuentas más?"},
                        {"role": "assistant", "content": "'Respira, Siente, Conecta' es una experiencia de 3 horas donde combinamos breathwork, meditación y baño de hielo 🧊 Es muy transformador. Cuesta €45 y lo hacemos en Barcelona. ¿Te apuntas a la próxima? ✨"},
                    ]
                },
                {
                    "lead": {"name": "Ana Martínez", "username": "ana_coach", "platform": "instagram", "intent": 0.95, "status": "hot"},
                    "messages": [
                        {"role": "user", "content": "Stefano, necesito ayuda. Estoy pasando por un momento muy difícil y siento que necesito un cambio profundo."},
                        {"role": "assistant", "content": "Ana, gracias por compartir esto conmigo 🙏 Los momentos difíciles muchas veces son el inicio de grandes transformaciones. Mi trabajo es acompañarte a convertir ese dolor en tu mayor fortaleza. ¿Quieres que agendemos una sesión discovery gratuita para hablar de tu situación? ❤️"},
                        {"role": "user", "content": "Sí, por favor. ¿Cómo puedo reservar?"},
                        {"role": "assistant", "content": "Perfecto Ana. La sesión discovery es de 30 minutos, sin compromiso. Solo para conocernos y ver si hay conexión para trabajar juntos. Te dejo el enlace para agendar: [link]. Estoy aquí para ti ✨"},
                    ]
                },
                {
                    "lead": {"name": "Miguel Ángel", "username": "miguelangel_bcn", "platform": "instagram", "intent": 0.5, "status": "warm"},
                    "messages": [
                        {"role": "user", "content": "Hola, ¿qué es exactamente el coaching cuántico?"},
                        {"role": "assistant", "content": "¡Hola Miguel Ángel! 🌟 El coaching cuántico combina técnicas de coaching tradicional con principios de física cuántica y reprogramación del inconsciente. Trabajamos a nivel energético para transformar patrones limitantes. Es como reprogramar el software de tu mente para crear nuevas posibilidades. ¿Hay algo específico que te gustaría cambiar en tu vida?"},
                    ]
                },
                {
                    "lead": {"name": "Sofía Navarro", "username": "sofia_yoga", "platform": "instagram", "intent": 0.6, "status": "warm"},
                    "messages": [
                        {"role": "user", "content": "Vi que haces sesiones de breathwork. ¿Qué beneficios tiene?"},
                        {"role": "assistant", "content": "¡Hola Sofía! El breathwork es una herramienta muy poderosa 🌬️ Te ayuda a liberar tensiones acumuladas, procesar emociones y conectar con tu cuerpo de una forma profunda. En el taller 'Respira, Siente, Conecta' lo combinamos con meditación y baño de hielo. Es una experiencia que te marca. ¿Has hecho breathwork antes?"},
                    ]
                },
                {
                    "lead": {"name": "Pedro García", "username": "pedro_wellness", "platform": "whatsapp", "intent": 0.4, "status": "warm"},
                    "messages": [
                        {"role": "user", "content": "Hola Stefano, un amigo me recomendó tu trabajo. ¿Podrías explicarme qué haces?"},
                        {"role": "assistant", "content": "¡Hola Pedro! Qué bien que llegues por recomendación 🙏 Soy coach y terapeuta. Acompaño a personas a transformar su realidad trabajando con mente, cuerpo y espíritu. Uso coaching cuántico, hipnosis, breathwork y otras técnicas. Mi enfoque es convertir tu dolor en tu mayor fortaleza. ¿Qué te gustaría trabajar?"},
                    ]
                },
                {
                    "lead": {"name": "Elena Ruiz", "username": "elena_mindful", "platform": "instagram", "intent": 0.3, "status": "cold"},
                    "messages": [
                        {"role": "user", "content": "Hola, ¿tienes algún recurso gratuito para empezar?"},
                        {"role": "assistant", "content": "¡Hola Elena! 🌟 Claro que sí. Tengo el podcast 'Sabios y Salvajes' en Spotify donde comparto mucho contenido. También puedes suscribirte a mi newsletter y te envío una guía de planificación anual gratis. ¿Te interesa algún tema en particular?"},
                    ]
                },
                {
                    "lead": {"name": "Roberto Sánchez", "username": "roberto_coach", "platform": "instagram", "intent": 0.2, "status": "cold"},
                    "messages": [
                        {"role": "user", "content": "Interesante tu contenido 👍"},
                        {"role": "assistant", "content": "¡Gracias Roberto! 🙏 Me alegra que resuene contigo. Si alguna vez quieres profundizar en algún tema o tienes preguntas, aquí estoy. ¡Un abrazo! ✨"},
                    ]
                },
            ]

            for conv in demo_conversations:
                lead_data = conv["lead"]
                platform_user_id = f"stefano_{lead_data['username']}"

                new_lead = Lead(
                    id=uuid_module.uuid4(),
                    creator_id=creator_uuid,
                    platform=lead_data["platform"],
                    platform_user_id=platform_user_id,
                    username=lead_data["username"],
                    full_name=lead_data["name"],
                    purchase_intent=lead_data["intent"],
                    status=lead_data["status"],
                    score=int(lead_data["intent"] * 100),
                    first_contact_at=datetime.utcnow() - timedelta(days=random.randint(5, 30)),
                    last_contact_at=datetime.utcnow() - timedelta(hours=random.randint(1, 72))
                )
                session.add(new_lead)
                session.flush()  # Get the ID
                details["leads_created"] += 1

                # Add messages
                for i, msg in enumerate(conv["messages"]):
                    new_message = Message(
                        id=uuid_module.uuid4(),
                        lead_id=new_lead.id,
                        role=msg["role"],
                        content=msg["content"],
                        status="sent",
                        created_at=datetime.utcnow() - timedelta(hours=len(conv["messages"]) - i)
                    )
                    session.add(new_message)
                    details["messages_created"] += 1

            # ================================================================
            # STEP 5: Update creator settings
            # ================================================================
            creator.bot_active = True
            creator.onboarding_completed = True
            creator.clone_name = STEFANO_DATA["creator"]["name"]

            # Store tone profile as JSON in a field if available
            tone_data = STEFANO_DATA["tone_profile"]

            session.commit()
            logger.info(f"[InjectStefano] Created {details['products_created']} products, {details['leads_created']} leads, {details['messages_created']} messages")

        finally:
            session.close()

        # ================================================================
        # STEP 6: Index content in RAG
        # ================================================================
        try:
            from core.rag import get_hybrid_rag
            rag = get_hybrid_rag()

            # Index products
            for prod in STEFANO_DATA["products"]:
                doc_id = f"stefano_product_{prod['id']}"
                content = f"""Producto: {prod['name']}
Precio: €{prod['price']}
Duración: {prod['duration']}
Descripción: {prod['description']}
Incluye: {', '.join(prod['includes'])}"""
                rag.add_document(
                    doc_id=doc_id,
                    text=content,
                    metadata={
                        "creator_id": creator_id,
                        "source_type": "product",
                        "product_id": prod["id"],
                        "price": prod["price"]
                    }
                )
                details["rag_documents"] += 1

            # Index testimonials
            for i, test in enumerate(STEFANO_DATA["testimonials"]):
                doc_id = f"stefano_testimonial_{i}"
                content = f"""Testimonio de {test['name']} sobre {test['program']}:
"{test['text']}"
Resultado: {test['result']}"""
                rag.add_document(
                    doc_id=doc_id,
                    text=content,
                    metadata={
                        "creator_id": creator_id,
                        "source_type": "testimonial"
                    }
                )
                details["rag_documents"] += 1

            # Index FAQs
            for i, faq in enumerate(STEFANO_DATA["faqs"]):
                doc_id = f"stefano_faq_{i}"
                content = f"""Pregunta: {faq['question']}
Respuesta: {faq['answer']}"""
                rag.add_document(
                    doc_id=doc_id,
                    text=content,
                    metadata={
                        "creator_id": creator_id,
                        "source_type": "faq"
                    }
                )
                details["rag_documents"] += 1

            # Index methodology
            meth = STEFANO_DATA["methodology"]
            doc_id = "stefano_methodology"
            content = f"""Metodología de Stefano Bonanno:
Pilares: {', '.join(meth['pillars'])}
Enfoque: {meth['approach']}
Métodos: {', '.join(meth['methods'])}"""
            rag.add_document(
                doc_id=doc_id,
                text=content,
                metadata={
                    "creator_id": creator_id,
                    "source_type": "methodology"
                }
            )
            details["rag_documents"] += 1

            # Index bio
            bio = STEFANO_DATA["creator"]
            doc_id = "stefano_bio"
            content = f"""Sobre Stefano Bonanno:
{bio['bio']}

Filosofía: {bio['philosophy']}

Contacto: {bio['email']} | {bio['phone']}
Ubicación: {bio['location']}
Web: {bio['website']}
Instagram: {bio['instagram']}"""
            rag.add_document(
                doc_id=doc_id,
                text=content,
                metadata={
                    "creator_id": creator_id,
                    "source_type": "bio"
                }
            )
            details["rag_documents"] += 1

            logger.info(f"[InjectStefano] Indexed {details['rag_documents']} documents in RAG")

        except Exception as e:
            errors.append(f"RAG indexing failed: {str(e)}")
            logger.error(f"[InjectStefano] RAG error: {e}")

        # ================================================================
        # STEP 7: Save ToneProfile
        # ================================================================
        try:
            from core.tone_service import save_tone_profile
            from ingestion.tone_analyzer import ToneProfile

            tone = STEFANO_DATA["tone_profile"]
            profile = ToneProfile(
                creator_id=creator_id,
                formality=tone["formality"],
                energy=tone["energy"],
                warmth=tone["warmth"],
                uses_emojis=tone["uses_emojis"],
                emoji_frequency="high",
                common_emojis=tone["common_emojis"],
                signature_phrases=tone["signature_phrases"],
                vocabulary_level="medium",
                sentence_length="medium",
                primary_language=tone["language"],
                main_topics=["coaching", "bienestar", "transformación", "breathwork"],
                analyzed_posts_count=50
            )
            await save_tone_profile(profile)
            details["tone_profile"] = True
            logger.info(f"[InjectStefano] ToneProfile saved")

        except Exception as e:
            errors.append(f"ToneProfile failed: {str(e)}")
            logger.error(f"[InjectStefano] ToneProfile error: {e}")

        return {
            "success": True,
            "creator_id": creator_id,
            "details": details,
            "errors": errors if errors else None,
            "products": [p["name"] for p in STEFANO_DATA["products"]],
            "message": "Stefano data injected successfully! Dashboard should show real products and leads."
        }

    except Exception as e:
        logger.error(f"[InjectStefano] Error: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


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
    Setup rápido sin scraping - para testing y demos.

    Solo crea/actualiza el creator y marca onboarding como completado.
    No hace scraping de Instagram ni website.
    """
    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator
        import uuid as uuid_module

        if not DATABASE_URL or not SessionLocal:
            return {
                "success": True,
                "creator_id": request.creator_id,
                "steps_completed": {"onboarding_completed": True, "bot_activated": True},
                "details": {"mode": "no_database"},
                "errors": []
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
                    copilot_mode=True
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
                    "bot_activated": True
                },
                "details": {
                    "posts_count": 0,
                    "mode": "quick_setup",
                    "instagram_username": request.instagram_username
                },
                "errors": []
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
            "errors": [str(e)]
        }


# =============================================================================
# FULL AUTO-SETUP V2 - Uses all V2 technologies for zero-hallucination
# =============================================================================

class FullAutoSetupRequest(BaseModel):
    """Request para auto-configuración completa."""
    creator_id: str
    instagram_username: str
    website_url: Optional[str] = None
    max_posts: int = 50
    transcribe_videos: bool = False  # Disabled by default (slow)


@router.post("/full-auto-setup")
async def full_auto_setup(request: FullAutoSetupRequest, background_tasks: BackgroundTasks):
    """
    Auto-configuración completa V2 del clon.

    Este endpoint ejecuta TODO el pipeline de creación de clon:
    1. Scrapea 50 posts de Instagram con sanity checks V2
    2. Transcribe videos/reels con Whisper (opcional)
    3. Scrapea website y detecta productos con V2 signals
    4. Genera ToneProfile desde el contenido
    5. Indexa todo para RAG con citations
    6. Actualiza el Creator y activa el bot

    El proceso puede tardar 3-5 minutos si transcribe videos.
    Para una UX rápida, usar quick-setup primero y este en background.

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
        AutoConfigResult con estadísticas completas del proceso
    """
    try:
        from core.auto_configurator import auto_configure_clone

        logger.info(f"[FullAutoSetup] Starting for {request.creator_id}")

        result = await auto_configure_clone(
            creator_id=request.creator_id,
            instagram_username=request.instagram_username,
            website_url=request.website_url,
            max_posts=request.max_posts,
            transcribe_videos=request.transcribe_videos
        )

        if not result.success and not result.steps_completed:
            raise HTTPException(
                status_code=400,
                detail=f"Auto-configuration failed: {result.errors}"
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
    request: FullAutoSetupRequest,
    background_tasks: BackgroundTasks
):
    """
    Versión en background de full-auto-setup.

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
        "result": {}
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
        request.transcribe_videos
    )

    return {
        "status": "started",
        "message": "Auto-configuration started in background",
        "creator_id": request.creator_id,
        "check_status_at": f"/onboarding/full-auto-setup/{request.creator_id}/status"
    }


@router.get("/full-auto-setup/{creator_id}/status")
async def get_full_auto_setup_status(creator_id: str):
    """
    Obtiene el estado de la auto-configuración en background.
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
        "message": "Setup not started yet"
    }


async def _run_full_auto_setup_background(
    creator_id: str,
    instagram_username: str,
    website_url: Optional[str],
    max_posts: int,
    transcribe_videos: bool
):
    """Ejecuta auto-setup en background actualizando status en tiempo real."""
    status = setup_status[creator_id]

    def save_progress():
        """Helper to save progress to both memory and DB."""
        _update_clone_status_db(creator_id, status)

    try:
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()

        # Step 1: Instagram scraping
        status["current_step"] = "instagram_scraping"
        status["progress"] = 10
        save_progress()
        logger.info(f"[FullAutoSetup-BG] Step 1: Instagram scraping for {creator_id}")

        try:
            ig_result = await configurator._scrape_instagram(
                creator_id=creator_id,
                instagram_username=instagram_username,
                max_posts=max_posts
            )
            posts_scraped = ig_result.get('posts_scraped', 0)
            posts_passed = ig_result.get('posts_passed_sanity', posts_scraped)
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
                    creator_id=creator_id,
                    website_url=website_url
                )
                products_detected = web_result.get('products_detected', 0)
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
            tone_generated = tone_result.get('success', False)
            tone_confidence = tone_result.get('confidence', 0.0)
            status["steps_completed"].append("tone_profile")
            status["progress"] = 80
            if "result" not in status:
                status["result"] = {}
            status["result"]["tone_profile"] = {
                "generated": tone_generated,
                "confidence": tone_confidence
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
            if dm_result.get('success'):
                status["steps_completed"].append("dm_history")
                if "result" not in status:
                    status["result"] = {}
                status["result"]["dms"] = {
                    "conversations": dm_result.get('conversations_found', 0),
                    "messages": dm_result.get('messages_imported', 0),
                    "leads_created": dm_result.get('leads_created', 0)
                }
                logger.info(f"[FullAutoSetup-BG] DM history loaded: {dm_result.get('messages_imported', 0)} messages")
            else:
                reason = dm_result.get('reason', 'Unknown')
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
            if bio_result.get('success'):
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
            faqs_created = faq_result.get('faqs_created', 0)
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
                tone_confidence=status.get("result", {}).get("tone_profile", {}).get("confidence", 0.0)
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

        logger.info(f"[FullAutoSetup-BG] Completed for {creator_id}: steps={status['steps_completed']}")

    except Exception as e:
        logger.error(f"[FullAutoSetup-BG] Error for {creator_id}: {e}")
        import traceback
        traceback.print_exc()
        status["status"] = "failed"
        status["errors"].append(str(e))
        save_progress()


@router.post("/manual-setup", response_model=ManualSetupResponse)
async def manual_setup(request: ManualSetupRequest):
    """
    Setup manual completo sin OAuth.

    Ideal para demos o cuando no se tiene acceso a Instagram OAuth.

    Este endpoint:
    1. Scrapea 50 posts públicos del Instagram username
    2. Genera ToneProfile con Magic Slice
    3. Indexa contenido en RAG (PostgreSQL + archivos)
    4. Scrapea website y añade al RAG
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
        "bot_activated": False
    }
    details = {
        "posts_count": 0,
        "tone_summary": None,
        "rag_documents": 0,
        "website_pages": 0
    }

    logger.info(f"[ManualSetup] Starting for {request.creator_id} from @{request.instagram_username}")

    # ==========================================================================
    # STEP 1: Scrape Instagram posts (public, no OAuth)
    # Uses delay_between_posts=3.0 to avoid rate limiting
    # ==========================================================================
    posts = []
    try:
        from ingestion.instagram_scraper import InstaloaderScraper, InstagramScraperError

        scraper = InstaloaderScraper()
        posts = scraper.get_posts(
            target_username=request.instagram_username,
            limit=request.max_posts,
            delay_between_posts=3.0  # 3 seconds between each post to avoid rate limits
        )

        if posts:
            steps_completed["posts_scraped"] = True
            details["posts_count"] = len(posts)
            logger.info(f"[ManualSetup] Scraped {len(posts)} posts from @{request.instagram_username}")
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
            from ingestion.tone_analyzer import ToneAnalyzer
            from core.tone_service import save_tone_profile

            # Convert posts to dict format
            posts_data = [
                {
                    "caption": post.caption,
                    "post_id": post.post_id,
                    "post_type": post.post_type,
                    "permalink": post.permalink,
                    "timestamp": post.timestamp.isoformat() if post.timestamp else None,
                    "likes_count": post.likes_count,
                    "comments_count": post.comments_count
                }
                for post in posts if post.caption
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
                    "signature_phrases": tone_profile.signature_phrases[:5]
                }
                logger.info(f"[ManualSetup] ToneProfile generated: {tone_profile.formality}, {tone_profile.energy}")

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
                    "comments": post.comments_count
                }

                rag.add_document(
                    doc_id=doc_id,
                    text=post.caption,
                    metadata=metadata
                )
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
                creator_id=request.creator_id,
                url=request.website_url
            )

            if result.get("success"):
                steps_completed["website_scraped"] = True
                details["website_pages"] = result.get("pages_indexed", 0)
                logger.info(f"[ManualSetup] Website scraped: {result.get('pages_indexed', 0)} pages")
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
            from api.database import DATABASE_URL, SessionLocal
            from api.models import Creator, Lead, Product
            import uuid as uuid_module
            from datetime import datetime, timedelta
            import random

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
                            copilot_mode=True
                        )
                        session.add(creator)
                        session.commit()
                        logger.info(f"[ManualSetup] Created new creator: {request.creator_id}")

                    creator_uuid = creator.id

                    # Create demo products
                    demo_products = [
                        {"name": "Consultoría 1:1", "price": 150.0, "description": "Sesión de consultoría personalizada de 1 hora"},
                        {"name": "Curso Online", "price": 97.0, "description": "Acceso completo al curso con materiales"},
                        {"name": "Mentoría Grupal", "price": 49.0, "description": "Sesión grupal mensual con Q&A"},
                    ]

                    products_created = 0
                    for prod in demo_products:
                        existing = session.query(Product).filter_by(
                            creator_id=creator_uuid, name=prod["name"]
                        ).first()
                        if not existing:
                            new_product = Product(
                                id=uuid_module.uuid4(),
                                creator_id=creator_uuid,
                                name=prod["name"],
                                price=prod["price"],
                                description=prod["description"],
                                is_active=True
                            )
                            session.add(new_product)
                            products_created += 1

                    # NOTE: Demo leads creation DISABLED - we only show real DMs from Instagram
                    # To re-enable for testing, uncomment the code below
                    leads_created = 0
                    # demo_leads = [
                    #     {"name": "María García", "platform": "instagram", "intent": 0.8, "status": "hot"},
                    #     {"name": "Carlos López", "platform": "instagram", "intent": 0.6, "status": "warm"},
                    #     {"name": "Ana Martínez", "platform": "instagram", "intent": 0.9, "status": "hot"},
                    #     {"name": "Pedro Sánchez", "platform": "whatsapp", "intent": 0.4, "status": "warm"},
                    #     {"name": "Laura Fernández", "platform": "instagram", "intent": 0.3, "status": "cold"},
                    #     {"name": "Diego Ruiz", "platform": "instagram", "intent": 0.7, "status": "hot"},
                    #     {"name": "Sofia Torres", "platform": "whatsapp", "intent": 0.5, "status": "warm"},
                    #     {"name": "Miguel Herrera", "platform": "instagram", "intent": 0.2, "status": "cold"},
                    # ]
                    # for i, lead_data in enumerate(demo_leads):
                    #     platform_user_id = f"demo_{lead_data['name'].lower().replace(' ', '_')}_{i}"
                    #     existing = session.query(Lead).filter_by(
                    #         creator_id=creator_uuid, platform_user_id=platform_user_id
                    #     ).first()
                    #     if not existing:
                    #         new_lead = Lead(
                    #             id=uuid_module.uuid4(),
                    #             creator_id=creator_uuid,
                    #             platform=lead_data["platform"],
                    #             platform_user_id=platform_user_id,
                    #             username=lead_data["name"].lower().replace(" ", "_"),
                    #             full_name=lead_data["name"],
                    #             purchase_intent=lead_data["intent"],
                    #             status=lead_data["status"],
                    #             first_contact_at=datetime.utcnow() - timedelta(days=random.randint(1, 30)),
                    #             last_contact_at=datetime.utcnow() - timedelta(hours=random.randint(1, 72)),
                    #             score=random.randint(30, 90)
                    #         )
                    #         session.add(new_lead)
                    #         leads_created += 1

                    session.commit()
                    details["demo_leads_created"] = leads_created
                    details["demo_products_created"] = products_created
                    logger.info(f"[ManualSetup] Created {leads_created} demo leads and {products_created} demo products")

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
                from api.models import Creator
                import uuid as uuid_module

                creator = session.query(Creator).filter_by(name=request.creator_id).first()

                if not creator:
                    # Create creator if doesn't exist
                    creator = Creator(
                        id=uuid_module.uuid4(),
                        name=request.creator_id,
                        email=f"{request.creator_id}@clonnect.io",
                        bot_active=should_complete,
                        onboarding_completed=should_complete,
                        copilot_mode=True
                    )
                    session.add(creator)
                    logger.info(f"[ManualSetup] Created new creator: {request.creator_id}")
                else:
                    # Update existing creator - only complete if setup succeeded
                    if should_complete:
                        creator.bot_active = True
                        creator.onboarding_completed = True
                        logger.info(f"[ManualSetup] Updated creator (completed): {request.creator_id}")
                    else:
                        # Keep onboarding_completed=false so user can retry
                        logger.info(f"[ManualSetup] Setup failed, keeping onboarding incomplete: {request.creator_id}")

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
        steps_completed["posts_scraped"] and
        steps_completed["tone_profile_generated"] and
        steps_completed["bot_activated"]
    )

    logger.info(f"[ManualSetup] Completed for {request.creator_id}: success={success}, steps={steps_completed}")

    return ManualSetupResponse(
        success=success,
        creator_id=request.creator_id,
        steps_completed=steps_completed,
        details=details,
        errors=errors
    )


# =============================================================================
# FULL RESET - Delete ALL data for a creator (for testing)
# =============================================================================

@router.delete("/full-reset/{creator_id}")
async def full_reset_creator(creator_id: str, email: Optional[str] = None):
    """
    Delete ALL data for a creator. Use for testing/starting fresh.

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
        DELETE /onboarding/full-reset/stefano_bonanno?email=stefano@fitpackglobal.com
    """
    deleted = {
        "creator": False,
        "user": False,
        "leads": 0,
        "messages": 0,
        "products": 0,
        "instagram_posts": 0,
        "content_chunks": 0,
        "tone_profile": False,
        "content_index": False
    }
    errors = []

    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Product, Message, UserCreator

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
                deleted["products"] = session.query(Product).filter_by(creator_id=creator_uuid).delete()

                # Delete user_creators relationships (MUST be before creator delete)
                user_creators_deleted = session.query(UserCreator).filter_by(creator_id=creator_uuid).delete()
                logger.info(f"[FullReset] Deleted {user_creators_deleted} user_creators relationships")

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
            from core.tone_profile_db import delete_instagram_posts_db, delete_content_chunks_db

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
            from pathlib import Path
            import shutil

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
            "errors": errors if errors else None
        }

    except Exception as e:
        logger.error(f"[FullReset] Error: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# =============================================================================
# INSTAGRAM API SYNC - Sync posts using Instagram Graph API
# =============================================================================

class InstagramAPISyncRequest(BaseModel):
    """Request para sincronizar posts desde Instagram API."""
    creator_id: str
    limit: int = 25


class InstagramAPISyncResponse(BaseModel):
    """Response de sincronización de Instagram API."""
    success: bool
    creator_id: str
    posts_fetched: int
    posts_saved: int
    rag_chunks_created: int
    tone_profile_updated: bool
    errors: List[str]


@router.post("/sync-instagram-api", response_model=InstagramAPISyncResponse)
async def sync_instagram_from_api(request: InstagramAPISyncRequest):
    """
    Sincroniza posts de Instagram usando la Graph API.

    Requiere que el creator tenga un token de Instagram válido guardado.

    1. Obtiene posts desde Instagram Graph API
    2. Guarda en DB (instagram_posts + content_chunks)
    3. Actualiza ToneProfile con el nuevo contenido

    Ideal para cargar datos históricos después de conectar la cuenta.
    """
    import httpx

    errors = []
    posts_fetched = 0
    posts_saved = 0
    rag_chunks_created = 0
    tone_profile_updated = False

    try:
        # Get creator's token from DB
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=request.creator_id).first()

            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {request.creator_id} not found")

            if not creator.instagram_token:
                raise HTTPException(status_code=400, detail="Creator has no Instagram token")

            access_token = creator.instagram_token

        finally:
            session.close()

        # Fetch posts from Instagram API
        logger.info(f"[InstagramAPISync] Fetching posts for {request.creator_id}")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://graph.instagram.com/v21.0/me/media",
                params={
                    "fields": "id,caption,media_type,timestamp,permalink,like_count,comments_count",
                    "limit": request.limit,
                    "access_token": access_token
                }
            )

            data = response.json()

            if "error" in data:
                error_msg = data["error"].get("message", "Unknown error")
                errors.append(f"Instagram API error: {error_msg}")
                return InstagramAPISyncResponse(
                    success=False,
                    creator_id=request.creator_id,
                    posts_fetched=0,
                    posts_saved=0,
                    rag_chunks_created=0,
                    tone_profile_updated=False,
                    errors=errors
                )

            posts = data.get("data", [])
            posts_fetched = len(posts)

            logger.info(f"[InstagramAPISync] Fetched {posts_fetched} posts")

        if posts_fetched == 0:
            errors.append("No posts found")
            return InstagramAPISyncResponse(
                success=False,
                creator_id=request.creator_id,
                posts_fetched=0,
                posts_saved=0,
                rag_chunks_created=0,
                tone_profile_updated=False,
                errors=errors
            )

        # Convert to DB format and save
        from core.tone_profile_db import (
            save_instagram_posts_db,
            save_content_chunks_db
        )
        import hashlib

        posts_data = []
        chunks_data = []

        for post in posts:
            caption = post.get("caption", "")
            if not caption:
                continue

            post_id = post.get("id", "")

            # Format for instagram_posts table
            posts_data.append({
                "id": post_id,
                "post_id": post_id,
                "caption": caption,
                "permalink": post.get("permalink", ""),
                "media_type": post.get("media_type", ""),
                "timestamp": post.get("timestamp", ""),
                "like_count": post.get("like_count", 0),
                "comments_count": post.get("comments_count", 0)
            })

            # Format for content_chunks (RAG)
            chunk_id = hashlib.sha256(f"{request.creator_id}:{post_id}:0".encode()).hexdigest()[:32]
            first_line = caption.split('\n')[0][:100] if caption else ""

            chunks_data.append({
                "id": chunk_id,
                "chunk_id": chunk_id,
                "creator_id": request.creator_id,
                "content": caption,
                "source_type": "instagram_post",
                "source_id": post_id,
                "source_url": post.get("permalink", ""),
                "title": first_line,
                "chunk_index": 0,
                "total_chunks": 1,
                "metadata": {
                    "media_type": post.get("media_type"),
                    "likes": post.get("like_count", 0),
                    "comments": post.get("comments_count", 0),
                    "timestamp": post.get("timestamp")
                }
            })

        # Save to DB
        if posts_data:
            posts_saved = await save_instagram_posts_db(request.creator_id, posts_data)
            logger.info(f"[InstagramAPISync] Saved {posts_saved} posts to DB")

        if chunks_data:
            rag_chunks_created = await save_content_chunks_db(request.creator_id, chunks_data)
            logger.info(f"[InstagramAPISync] Created {rag_chunks_created} RAG chunks")

        # Update ToneProfile
        try:
            from ingestion.tone_analyzer import ToneAnalyzer
            from core.tone_service import save_tone_profile

            posts_for_tone = [
                {
                    "caption": p.get("caption", ""),
                    "post_id": p.get("post_id"),
                    "post_type": p.get("media_type"),
                    "permalink": p.get("permalink"),
                    "timestamp": p.get("timestamp"),
                    "likes_count": p.get("like_count", 0),
                    "comments_count": p.get("comments_count", 0)
                }
                for p in posts_data if p.get("caption")
            ]

            if posts_for_tone:
                analyzer = ToneAnalyzer()
                tone_profile = await analyzer.analyze(request.creator_id, posts_for_tone)
                await save_tone_profile(tone_profile)
                tone_profile_updated = True
                logger.info(f"[InstagramAPISync] ToneProfile updated")

        except Exception as e:
            errors.append(f"ToneProfile update failed: {str(e)}")
            logger.warning(f"[InstagramAPISync] ToneProfile error: {e}")

        return InstagramAPISyncResponse(
            success=True,
            creator_id=request.creator_id,
            posts_fetched=posts_fetched,
            posts_saved=posts_saved,
            rag_chunks_created=rag_chunks_created,
            tone_profile_updated=tone_profile_updated,
            errors=errors if errors else []
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[InstagramAPISync] Error: {e}")
        import traceback
        traceback.print_exc()
        errors.append(str(e))
        return InstagramAPISyncResponse(
            success=False,
            creator_id=request.creator_id,
            posts_fetched=posts_fetched,
            posts_saved=posts_saved,
            rag_chunks_created=rag_chunks_created,
            tone_profile_updated=tone_profile_updated,
            errors=errors
        )


# =============================================================================
# INSTAGRAM DM HISTORY SYNC
# =============================================================================

class InstagramDMSyncRequest(BaseModel):
    """Request for syncing Instagram DM history"""
    creator_id: str
    max_conversations: int = 50
    max_messages_per_conversation: int = 50
    analyze_insights: bool = True
    run_background: bool = False  # Run as background task


# In-memory status for background sync jobs
dm_sync_status: Dict[str, Dict] = {}


class ConversationInsight(BaseModel):
    """Insights from a conversation"""
    follower_id: str
    follower_username: str
    total_messages: int
    topics: List[str]
    purchase_intent_score: float
    common_questions: List[str]


class InstagramDMSyncResponse(BaseModel):
    """Response from Instagram DM sync"""
    success: bool
    creator_id: str
    conversations_fetched: int = 0
    messages_saved: int = 0
    leads_created: int = 0
    insights: Optional[List[ConversationInsight]] = None
    errors: List[str] = []


@router.post("/sync-instagram-dms", response_model=InstagramDMSyncResponse)
async def sync_instagram_dms(request: InstagramDMSyncRequest):
    """
    Sincroniza mensajes históricos de Instagram DM usando Graph API.

    Implementa:
    - Rate limiting con backoff exponencial
    - Throttling entre llamadas (max 20/min)
    - Procesamiento en batches
    - Retry automático en rate limits
    """
    import asyncio
    import httpx
    from datetime import datetime
    from core.instagram_rate_limiter import (
        InstagramRateLimiter,
        InstagramRateLimitError,
        RateLimitConfig
    )

    errors = []
    conversations_fetched = 0
    messages_saved = 0
    leads_created = 0
    insights = []
    rate_limit_hits = 0

    # Configurar rate limiter
    config = RateLimitConfig(
        max_retries=5,
        base_delay=30.0,
        calls_per_minute=15,  # Conservador para evitar limits
        batch_size=5,
        batch_delay=10.0
    )
    limiter = InstagramRateLimiter(config)

    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message

        if not DATABASE_URL or not SessionLocal:
            raise HTTPException(status_code=500, detail="Database not configured")

        session = SessionLocal()
        try:
            # Get creator and token
            creator = session.query(Creator).filter_by(name=request.creator_id).first()
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator not found: {request.creator_id}")

            if not creator.instagram_token:
                raise HTTPException(status_code=400, detail="Instagram token not configured")

            ig_user_id = creator.instagram_user_id or creator.instagram_page_id
            page_id = creator.instagram_page_id
            if not ig_user_id:
                raise HTTPException(status_code=400, detail="Instagram user ID not configured")

            access_token = creator.instagram_token

            # Estrategia dual: usar Facebook API con page_id si existe, sino Instagram API
            if page_id:
                api_base = "https://graph.facebook.com/v21.0"
                conv_id_for_api = page_id
                conv_extra_params = {"platform": "instagram"}
            else:
                api_base = "https://graph.instagram.com/v21.0"
                conv_id_for_api = ig_user_id
                conv_extra_params = {}

            logger.info(f"[DMSync] Starting sync for {request.creator_id} using {'Facebook' if page_id else 'Instagram'} API")

            async with httpx.AsyncClient(timeout=60.0) as client:

                # Helper para hacer llamadas con rate limiting
                async def fetch_with_retry(url: str, params: dict, max_retries: int = 5) -> dict:
                    nonlocal rate_limit_hits

                    for attempt in range(max_retries):
                        await limiter.throttle()

                        response = await client.get(url, params=params)
                        data = response.json()

                        # Verificar rate limit
                        error = data.get("error", {})
                        if error.get("code") in [4, 17] or error.get("error_subcode") == 1349210:
                            rate_limit_hits += 1
                            if attempt == max_retries - 1:
                                raise InstagramRateLimitError(error.get("message", "Rate limit"))

                            delay = limiter.calculate_backoff(attempt)
                            logger.warning(f"[DMSync] Rate limit hit, waiting {delay:.0f}s (attempt {attempt + 1})")
                            await asyncio.sleep(delay)
                            continue

                        if response.status_code != 200:
                            return {"error": data.get("error", {}), "data": []}

                        return data

                    return {"error": {"message": "Max retries exceeded"}, "data": []}

                # 1. Fetch conversations (1 llamada)
                conv_url = f"{api_base}/{conv_id_for_api}/conversations"
                conv_params = {
                    **conv_extra_params,
                    "access_token": access_token,
                    "limit": min(request.max_conversations, 50)
                }
                conv_data = await fetch_with_retry(conv_url, conv_params)

                if "error" in conv_data and conv_data["error"]:
                    error_msg = conv_data["error"].get("message", "Unknown error")
                    errors.append(f"Conversations API error: {error_msg}")
                    logger.error(f"[DMSync] Conversations error: {conv_data['error']}")
                    return InstagramDMSyncResponse(
                        success=False,
                        creator_id=request.creator_id,
                        errors=errors
                    )

                conversations = conv_data.get("data", [])
                conversations_fetched = len(conversations)
                logger.info(f"[DMSync] Found {conversations_fetched} conversations")

                # 2. Process conversations in batches
                batch_size = config.batch_size
                total_batches = (len(conversations) + batch_size - 1) // batch_size

                for batch_idx in range(total_batches):
                    batch_start = batch_idx * batch_size
                    batch_end = min(batch_start + batch_size, len(conversations))
                    batch = conversations[batch_start:batch_end]

                    logger.info(f"[DMSync] Processing batch {batch_idx + 1}/{total_batches} ({len(batch)} conversations)")

                    for conv in batch:
                        conv_id = conv.get("id")
                        if not conv_id:
                            continue

                        try:
                            # Fetch messages for this conversation
                            msg_url = f"{api_base}/{conv_id}/messages"
                            msg_data = await fetch_with_retry(msg_url, {
                                "fields": "id,message,from,to,created_time",
                                "access_token": access_token,
                                "limit": min(request.max_messages_per_conversation, 50)
                            })

                            if "error" in msg_data and msg_data["error"]:
                                logger.warning(f"[DMSync] Messages error for conv {conv_id}: {msg_data['error']}")
                                continue

                            messages = msg_data.get("data", [])
                            if not messages:
                                continue

                            # Find the follower
                            follower_id = None
                            follower_username = None

                            for msg in messages:
                                from_data = msg.get("from", {})
                                from_id = from_data.get("id")
                                from_username = from_data.get("username", "")

                                if from_id and from_id != ig_user_id:
                                    follower_id = from_id
                                    follower_username = from_username
                                    break

                            if not follower_id:
                                for msg in messages:
                                    to_data = msg.get("to", {}).get("data", [])
                                    for recipient in to_data:
                                        if recipient.get("id") != ig_user_id:
                                            follower_id = recipient.get("id")
                                            follower_username = recipient.get("username", "")
                                            break
                                    if follower_id:
                                        break

                            if not follower_id:
                                continue

                            # Create or get Lead
                            lead = session.query(Lead).filter_by(
                                creator_id=creator.id,
                                platform="instagram",
                                platform_user_id=follower_id
                            ).first()

                            if not lead:
                                lead = Lead(
                                    creator_id=creator.id,
                                    platform="instagram",
                                    platform_user_id=follower_id,
                                    username=follower_username,
                                    status="active"
                                )
                                session.add(lead)
                                session.commit()
                                leads_created += 1

                            # Save messages
                            conv_messages_saved = 0
                            conv_topics = []
                            conv_questions = []

                            for msg in messages:
                                msg_id = msg.get("id")
                                msg_text = msg.get("message", "")
                                msg_from = msg.get("from", {})
                                msg_time = msg.get("created_time")

                                if not msg_text:
                                    continue

                                existing = session.query(Message).filter_by(
                                    platform_message_id=msg_id
                                ).first()

                                if existing:
                                    continue

                                is_from_creator = msg_from.get("id") == ig_user_id
                                role = "assistant" if is_from_creator else "user"

                                created_at = None
                                if msg_time:
                                    try:
                                        created_at = datetime.fromisoformat(msg_time.replace("+0000", "+00:00"))
                                    except:
                                        pass

                                new_msg = Message(
                                    lead_id=lead.id,
                                    role=role,
                                    content=msg_text,
                                    status="sent",
                                    platform_message_id=msg_id,
                                    approved_by="historical_sync"
                                )
                                if created_at:
                                    new_msg.created_at = created_at

                                session.add(new_msg)
                                conv_messages_saved += 1
                                messages_saved += 1

                                if role == "user":
                                    if "?" in msg_text:
                                        conv_questions.append(msg_text.strip())
                                    lower_text = msg_text.lower()
                                    if any(w in lower_text for w in ["precio", "cuesta", "vale", "pagar"]):
                                        conv_topics.append("precio")
                                    if any(w in lower_text for w in ["info", "información", "detalles"]):
                                        conv_topics.append("información")
                                    if any(w in lower_text for w in ["comprar", "quiero", "interesa"]):
                                        conv_topics.append("intención_compra")

                            # Calculate intent score
                            intent_score = 0.0
                            if "intención_compra" in conv_topics:
                                intent_score += 0.4
                            if "precio" in conv_topics:
                                intent_score += 0.3
                            if "información" in conv_topics:
                                intent_score += 0.2
                            if conv_questions:
                                intent_score += 0.1
                            intent_score = min(intent_score, 1.0)

                            lead.purchase_intent = intent_score
                            if intent_score >= 0.6:
                                lead.status = "hot"
                            elif intent_score >= 0.35:
                                lead.status = "active"
                            else:
                                lead.status = "new"

                            session.commit()

                            if conv_messages_saved > 0:
                                logger.info(f"[DMSync] Saved {conv_messages_saved} msgs for {follower_username}")

                                if request.analyze_insights:
                                    insights.append(ConversationInsight(
                                        follower_id=follower_id,
                                        follower_username=follower_username or "unknown",
                                        total_messages=len(messages),
                                        topics=list(set(conv_topics)),
                                        purchase_intent_score=intent_score,
                                        common_questions=conv_questions[:5]
                                    ))

                        except InstagramRateLimitError as e:
                            logger.error(f"[DMSync] Rate limit exceeded for conv {conv_id}: {e.message}")
                            errors.append(f"Rate limit: {e.message}")
                            # Guardar progreso parcial
                            session.commit()
                            break
                        except Exception as e:
                            logger.warning(f"[DMSync] Error processing conv {conv_id}: {e}")
                            continue

                    # Pausa entre batches
                    if batch_idx < total_batches - 1:
                        logger.info(f"[DMSync] Batch complete, waiting {config.batch_delay}s")
                        await asyncio.sleep(config.batch_delay)

        finally:
            session.close()

        logger.info(f"[DMSync] Complete: {conversations_fetched} convs, {messages_saved} msgs, {leads_created} leads, {rate_limit_hits} rate limits")

        return InstagramDMSyncResponse(
            success=True,
            creator_id=request.creator_id,
            conversations_fetched=conversations_fetched,
            messages_saved=messages_saved,
            leads_created=leads_created,
            insights=insights if insights else None,
            errors=errors if errors else []
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DMSync] Error: {e}")
        import traceback
        traceback.print_exc()
        errors.append(str(e))
        return InstagramDMSyncResponse(
            success=False,
            creator_id=request.creator_id,
            conversations_fetched=conversations_fetched,
            messages_saved=messages_saved,
            leads_created=leads_created,
            errors=errors
        )


# =============================================================================
# BACKGROUND DM SYNC
# =============================================================================

async def _background_dm_sync(
    creator_id: str,
    max_conversations: int,
    max_messages_per_conversation: int,
    job_id: str
):
    """
    Background task for DM sync.
    Updates dm_sync_status with progress.
    """
    import asyncio
    import httpx
    from datetime import datetime
    from core.instagram_rate_limiter import (
        InstagramRateLimiter,
        InstagramRateLimitError,
        RateLimitConfig
    )

    # Initialize status
    dm_sync_status[job_id] = {
        "status": "running",
        "creator_id": creator_id,
        "started_at": datetime.now().isoformat(),
        "conversations_fetched": 0,
        "messages_saved": 0,
        "leads_created": 0,
        "current_batch": 0,
        "total_batches": 0,
        "errors": [],
        "completed_at": None
    }

    errors = []
    conversations_fetched = 0
    messages_saved = 0
    leads_created = 0

    config = RateLimitConfig(
        max_retries=5,
        base_delay=30.0,
        calls_per_minute=15,
        batch_size=5,
        batch_delay=10.0
    )
    limiter = InstagramRateLimiter(config)

    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message

        if not DATABASE_URL or not SessionLocal:
            dm_sync_status[job_id]["status"] = "failed"
            dm_sync_status[job_id]["errors"].append("Database not configured")
            return

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator or not creator.instagram_token:
                dm_sync_status[job_id]["status"] = "failed"
                dm_sync_status[job_id]["errors"].append("Creator or token not found")
                return

            ig_user_id = creator.instagram_user_id or creator.instagram_page_id
            page_id = creator.instagram_page_id
            access_token = creator.instagram_token

            # Estrategia dual: usar Facebook API con page_id si existe, sino Instagram API
            if page_id:
                api_base = "https://graph.facebook.com/v21.0"
                conv_id_for_api = page_id
                conv_extra_params = {"platform": "instagram"}
            else:
                api_base = "https://graph.instagram.com/v21.0"
                conv_id_for_api = ig_user_id
                conv_extra_params = {}

            logger.info(f"[BGSync] Starting background sync for {creator_id} using {'Facebook' if page_id else 'Instagram'} API")

            async with httpx.AsyncClient(timeout=60.0) as client:
                async def fetch_with_retry(url: str, params: dict, max_retries: int = 5) -> dict:
                    for attempt in range(max_retries):
                        await limiter.throttle()
                        response = await client.get(url, params=params)
                        data = response.json()
                        error = data.get("error", {})
                        if error.get("code") in [4, 17] or error.get("error_subcode") == 1349210:
                            if attempt == max_retries - 1:
                                raise InstagramRateLimitError(error.get("message", "Rate limit"))
                            delay = limiter.calculate_backoff(attempt)
                            logger.warning(f"[BGSync] Rate limit, waiting {delay:.0f}s")
                            await asyncio.sleep(delay)
                            continue
                        if response.status_code != 200:
                            return {"error": data.get("error", {}), "data": []}
                        return data
                    return {"error": {"message": "Max retries"}, "data": []}

                # Fetch conversations
                conv_url = f"{api_base}/{conv_id_for_api}/conversations"
                conv_params = {
                    **conv_extra_params,
                    "access_token": access_token,
                    "limit": min(max_conversations, 50)
                }
                conv_data = await fetch_with_retry(conv_url, conv_params)

                if "error" in conv_data and conv_data["error"]:
                    dm_sync_status[job_id]["status"] = "failed"
                    dm_sync_status[job_id]["errors"].append(f"API error: {conv_data['error'].get('message')}")
                    return

                conversations = conv_data.get("data", [])
                conversations_fetched = len(conversations)
                dm_sync_status[job_id]["conversations_fetched"] = conversations_fetched

                batch_size = config.batch_size
                total_batches = (len(conversations) + batch_size - 1) // batch_size
                dm_sync_status[job_id]["total_batches"] = total_batches

                for batch_idx in range(total_batches):
                    dm_sync_status[job_id]["current_batch"] = batch_idx + 1
                    batch_start = batch_idx * batch_size
                    batch_end = min(batch_start + batch_size, len(conversations))
                    batch = conversations[batch_start:batch_end]

                    logger.info(f"[BGSync] Batch {batch_idx + 1}/{total_batches}")

                    for conv in batch:
                        conv_id = conv.get("id")
                        if not conv_id:
                            continue

                        try:
                            msg_url = f"{api_base}/{conv_id}/messages"
                            msg_data = await fetch_with_retry(msg_url, {
                                "fields": "id,message,from,to,created_time",
                                "access_token": access_token,
                                "limit": min(max_messages_per_conversation, 50)
                            })

                            if "error" in msg_data and msg_data["error"]:
                                continue

                            messages = msg_data.get("data", [])
                            if not messages:
                                continue

                            # Find follower
                            follower_id = None
                            follower_username = None
                            for msg in messages:
                                from_data = msg.get("from", {})
                                from_id = from_data.get("id")
                                if from_id and from_id != ig_user_id:
                                    follower_id = from_id
                                    follower_username = from_data.get("username", "")
                                    break
                            if not follower_id:
                                for msg in messages:
                                    to_data = msg.get("to", {}).get("data", [])
                                    for recipient in to_data:
                                        if recipient.get("id") != ig_user_id:
                                            follower_id = recipient.get("id")
                                            follower_username = recipient.get("username", "")
                                            break
                                    if follower_id:
                                        break
                            if not follower_id:
                                continue

                            # Get or create lead
                            lead = session.query(Lead).filter_by(
                                creator_id=creator.id,
                                platform="instagram",
                                platform_user_id=follower_id
                            ).first()

                            if not lead:
                                lead = Lead(
                                    creator_id=creator.id,
                                    platform="instagram",
                                    platform_user_id=follower_id,
                                    username=follower_username,
                                    status="active"
                                )
                                session.add(lead)
                                session.commit()
                                leads_created += 1
                                dm_sync_status[job_id]["leads_created"] = leads_created

                            # Save messages
                            for msg in messages:
                                msg_id = msg.get("id")
                                msg_content = msg.get("message", "")
                                from_data = msg.get("from", {})
                                from_id = from_data.get("id")
                                role = "user" if from_id == follower_id else "assistant"

                                existing = session.query(Message).filter_by(
                                    lead_id=lead.id,
                                    platform_message_id=msg_id
                                ).first()

                                if not existing and msg_content:
                                    new_msg = Message(
                                        lead_id=lead.id,
                                        role=role,
                                        content=msg_content,
                                        platform_message_id=msg_id
                                    )
                                    if msg.get("created_time"):
                                        try:
                                            new_msg.created_at = datetime.fromisoformat(
                                                msg["created_time"].replace("Z", "+00:00")
                                            )
                                        except:
                                            pass
                                    session.add(new_msg)
                                    messages_saved += 1
                                    dm_sync_status[job_id]["messages_saved"] = messages_saved

                            session.commit()

                        except InstagramRateLimitError as e:
                            logger.error(f"[BGSync] Rate limit: {e.message}")
                            errors.append(f"Rate limit: {e.message}")
                            session.commit()
                            break
                        except Exception as e:
                            logger.warning(f"[BGSync] Error: {e}")
                            continue

                    # Pause between batches
                    if batch_idx < total_batches - 1:
                        await asyncio.sleep(config.batch_delay)

        finally:
            session.close()

        dm_sync_status[job_id]["status"] = "completed"
        dm_sync_status[job_id]["completed_at"] = datetime.now().isoformat()
        dm_sync_status[job_id]["errors"] = errors
        logger.info(f"[BGSync] Complete: {conversations_fetched} convs, {messages_saved} msgs")

    except Exception as e:
        logger.error(f"[BGSync] Error: {e}")
        dm_sync_status[job_id]["status"] = "failed"
        dm_sync_status[job_id]["errors"].append(str(e))
        dm_sync_status[job_id]["completed_at"] = datetime.now().isoformat()


@router.post("/sync-instagram-dms-background")
async def sync_instagram_dms_background(
    request: InstagramDMSyncRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a background DM sync job.
    Returns immediately with a job_id to check status.
    """
    import uuid
    from datetime import datetime

    job_id = f"dmsync_{request.creator_id}_{uuid.uuid4().hex[:8]}"

    background_tasks.add_task(
        _background_dm_sync,
        request.creator_id,
        request.max_conversations,
        request.max_messages_per_conversation,
        job_id
    )

    return {
        "status": "started",
        "job_id": job_id,
        "creator_id": request.creator_id,
        "check_status_url": f"/onboarding/sync-instagram-dms-status/{job_id}",
        "started_at": datetime.now().isoformat()
    }


@router.get("/sync-instagram-dms-status/{job_id}")
async def get_dm_sync_status(job_id: str):
    """
    Check the status of a background DM sync job.
    """
    if job_id not in dm_sync_status:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return dm_sync_status[job_id]


@router.get("/sync-instagram-dms-jobs/{creator_id}")
async def list_dm_sync_jobs(creator_id: str):
    """
    List all DM sync jobs for a creator.
    """
    jobs = []
    for job_id, status in dm_sync_status.items():
        if status.get("creator_id") == creator_id:
            jobs.append({"job_id": job_id, **status})

    return {"creator_id": creator_id, "jobs": jobs}
