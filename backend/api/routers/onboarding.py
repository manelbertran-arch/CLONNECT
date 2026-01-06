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
# IN-MEMORY SETUP STATUS (Use Redis in production)
# =============================================================================

setup_status: Dict[str, Dict] = {}


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
                "analyzed_posts": tone_profile.analyzed_posts_count
            }

            logger.info(f"[ScrapeOnboarding] ToneProfile generated: {tone_profile.formality}, {tone_profile.energy}")

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
            posts_index = []

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

                posts_index.append({
                    "id": post.post_id,
                    "url": post.permalink,
                    "caption_preview": post.caption[:200],
                    "post_type": post.post_type,
                    "timestamp": post.timestamp.isoformat() if post.timestamp else None
                })

            content_indexed = len(chunks)

            if content_indexed > 0:
                # Save to content_index directory
                content_dir = Path("data/content_index") / request.creator_id
                content_dir.mkdir(parents=True, exist_ok=True)

                chunks_path = content_dir / "chunks.json"
                posts_path = content_dir / "posts.json"

                with open(chunks_path, 'w', encoding='utf-8') as f:
                    json.dump(chunks, f, ensure_ascii=False, indent=2)

                with open(posts_path, 'w', encoding='utf-8') as f:
                    json.dump(posts_index, f, ensure_ascii=False, indent=2)

                logger.info(f"[ScrapeOnboarding] Indexed {content_indexed} posts to {content_dir}")

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
