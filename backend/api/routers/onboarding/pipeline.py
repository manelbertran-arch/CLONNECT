"""Magic Slice onboarding and full setup pipeline endpoints."""

import asyncio
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from api.auth import require_admin

from .helpers import FullOnboardRequest, QuickOnboardRequest, setup_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


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
        creator_id=request.creator_id, manual_posts=manual_posts, scraping_method="manual"
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
        max_posts=request.max_posts,
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
    from core.citation_service import get_content_index
    from core.tone_service import get_tone_profile

    tone_profile = await get_tone_profile(creator_id)
    content_index = get_content_index(creator_id)

    tone_summary = None
    if tone_profile:
        tone_summary = {
            "formality": tone_profile.formality,
            "energy": tone_profile.energy,
            "warmth": tone_profile.warmth,
            "main_topics": tone_profile.main_topics[:5] if tone_profile.main_topics else [],
        }

    return {
        "creator_id": creator_id,
        "has_tone_profile": tone_profile is not None,
        "has_content_index": content_index is not None and len(content_index.chunks) > 0,
        "tone_summary": tone_summary,
        "citation_count": len(content_index.chunks) if content_index else 0,
    }


@router.delete("/magic-slice/{creator_id}/reset")
async def reset_magic_slice_data(creator_id: str, admin: str = Depends(require_admin)):
    """
    Resetea los datos de Magic Slice de un creador.

    Requires admin API key (X-API-Key header).

    Util para re-onboarding con nuevo contenido.

    WARNING: Elimina ToneProfile y ContentIndex del creador.
    """
    from core.citation_service import delete_content_index
    from core.tone_service import delete_tone_profile

    tone_deleted = delete_tone_profile(creator_id)
    index_deleted = delete_content_index(creator_id)

    return {
        "creator_id": creator_id,
        "tone_profile_deleted": tone_deleted,
        "content_index_deleted": index_deleted,
    }


# =============================================================================
# WHATSAPP ONBOARDING — TRIGGER + STATUS
# =============================================================================


@router.post("/whatsapp/trigger/{creator_id}/{instance_name}")
async def trigger_whatsapp_onboarding(
    creator_id: str,
    instance_name: str,
    background_tasks: BackgroundTasks,
):
    """Manually trigger WhatsApp onboarding pipeline (admin/debug)."""
    from services.whatsapp_onboarding_pipeline import WhatsAppOnboardingPipeline

    async def _run():
        pipeline = WhatsAppOnboardingPipeline(creator_id, instance_name)
        result = await pipeline.run()
        logger.info(f"[WA-PIPELINE] Manual trigger done for {creator_id}: {result}")

    background_tasks.add_task(_run)
    return {"status": "started", "creator_id": creator_id, "instance": instance_name}


@router.get("/whatsapp/status/{creator_id}")
async def whatsapp_onboarding_status(creator_id: str):
    """Get WhatsApp onboarding pipeline progress."""
    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(404, "Creator not found")

        progress = creator.clone_progress or {}
        return {
            "creator_id": creator_id,
            "status": creator.clone_status,
            "progress": progress,
            "started_at": creator.clone_started_at.isoformat() if creator.clone_started_at else None,
            "completed_at": creator.clone_completed_at.isoformat() if creator.clone_completed_at else None,
            "error": creator.clone_error,
        }
    finally:
        session.close()


# =============================================================================
# FULL AUTO-SETUP WITH REAL-TIME PROGRESS
# =============================================================================


@router.post("/full-setup/{creator_id}")
async def start_full_setup(creator_id: str, background_tasks: BackgroundTasks):
    """
    Inicia el setup completo en background.
    El frontend hace polling a /full-setup/{creator_id}/progress para ver progreso.

    Este endpoint simula el proceso completo mientras se conectan las APIs reales.
    En produccion, cada paso se conectara a las APIs de Instagram, YouTube, etc.
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
            "website_url": None,
        },
        "errors": [],
    }

    # Run setup in background
    background_tasks.add_task(run_full_setup_pipeline, creator_id)

    return {"status": "started", "message": "Setup started", "creator_id": creator_id}


@router.get("/full-setup/{creator_id}/progress")
async def get_full_setup_progress(creator_id: str):
    """
    Retorna el estado actual del setup.
    El frontend hace polling cada 2 segundos.
    """
    if creator_id not in setup_status:
        return {"status": "not_started", "progress": 0, "steps": {}, "errors": []}

    return setup_status[creator_id]


async def run_full_setup_pipeline(creator_id: str):
    """
    Ejecuta todo el setup secuencialmente.
    Actualiza setup_status en cada paso para que el frontend vea el progreso.
    """
    status = setup_status[creator_id]

    try:
        # Paso 1: Marcar Instagram conectado (simulated - en produccion viene de OAuth)
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
        logger.info(
            f"[FullSetup] {creator_id}: Posts imported: {status['steps']['posts_imported']}"
        )

        # Paso 3: Generar ToneProfile
        await asyncio.sleep(1.5)
        tone_result = await generate_tone_for_setup(creator_id, posts)
        status["steps"]["tone_profile_generated"] = tone_result.get("success", True)
        status["steps"]["tone_summary"] = tone_result.get(
            "summary", "Cercano, dinamico, usa emojis"
        )
        status["current_step"] = "tone_analyzed"
        status["progress"] = 45
        logger.info(f"[FullSetup] {creator_id}: Tone profile generated")

        # Paso 4: Indexar contenido
        await asyncio.sleep(1)
        indexed = await index_content_for_setup(creator_id, posts)
        status["steps"]["content_indexed"] = indexed if indexed else 150  # Demo value
        status["current_step"] = "content_indexed"
        status["progress"] = 60
        logger.info(
            f"[FullSetup] {creator_id}: Content indexed: {status['steps']['content_indexed']}"
        )

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

        # Paso 7: Detectar YouTube (simulated - en produccion parsea bio)
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
                traits.append("dinamico")
            elif profile.energy in ["low", "very_low"]:
                traits.append("calmado")

            if profile.uses_emojis:
                traits.append("usa emojis")

            return {
                "success": True,
                "summary": ", ".join(traits) if traits else "Personalidad analizada",
            }
    except Exception as e:
        logger.warning(f"[FullSetup] Could not get tone profile: {e}")

    return {"success": True, "summary": "Cercano, dinamico, usa emojis"}


async def index_content_for_setup(creator_id: str, posts: List[Dict]) -> int:
    """Index content for citations."""
    try:
        from core.citation_service import get_content_index

        index = get_content_index(creator_id)
        if index and hasattr(index, "chunks"):
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
