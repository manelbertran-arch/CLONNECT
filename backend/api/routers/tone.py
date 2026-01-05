"""
API endpoints para gestion de ToneProfile.
Parte de Magic Slice - Fase 1.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from core.tone_service import (
    get_tone_profile,
    save_tone_profile,
    generate_tone_profile,
    list_profiles,
    clear_cache
)

router = APIRouter(prefix="/tone", tags=["tone"])


class PostInput(BaseModel):
    """Entrada de un post para analisis."""
    caption: str
    post_id: Optional[str] = None


class GenerateToneRequest(BaseModel):
    """Request para generar ToneProfile."""
    creator_id: str
    posts: List[PostInput]


class ToneProfileResponse(BaseModel):
    """Response con datos del ToneProfile."""
    creator_id: str
    formality: str
    energy: str
    warmth: str
    signature_phrases: List[str]
    favorite_emojis: List[str]
    uses_emojis: bool
    confidence_score: float
    analyzed_posts_count: int


@router.get("/profiles")
async def list_tone_profiles():
    """Lista todos los ToneProfiles guardados."""
    profiles = list_profiles()
    return {
        "profiles": profiles,
        "count": len(profiles)
    }


@router.get("/{creator_id}")
async def get_creator_tone(creator_id: str):
    """Obtiene el ToneProfile de un creador."""
    profile = await get_tone_profile(creator_id)
    if not profile:
        raise HTTPException(status_code=404, detail="ToneProfile not found")

    return ToneProfileResponse(
        creator_id=profile.creator_id,
        formality=profile.formality,
        energy=profile.energy,
        warmth=profile.warmth,
        signature_phrases=profile.signature_phrases[:10],
        favorite_emojis=profile.favorite_emojis[:10],
        uses_emojis=profile.uses_emojis,
        confidence_score=profile.confidence_score,
        analyzed_posts_count=profile.analyzed_posts_count
    )


@router.post("/generate")
async def generate_creator_tone(request: GenerateToneRequest):
    """Genera un ToneProfile analizando posts del creador."""
    if len(request.posts) < 3:
        raise HTTPException(
            status_code=400,
            detail="Se necesitan al menos 3 posts para generar un ToneProfile"
        )

    posts = [{"caption": p.caption} for p in request.posts]

    profile = await generate_tone_profile(
        creator_id=request.creator_id,
        posts=posts,
        save=True
    )

    return {
        "status": "success",
        "creator_id": profile.creator_id,
        "confidence_score": profile.confidence_score,
        "analyzed_posts": profile.analyzed_posts_count,
        "formality": profile.formality,
        "energy": profile.energy,
        "warmth": profile.warmth
    }


@router.get("/{creator_id}/prompt")
async def get_tone_prompt(creator_id: str):
    """Obtiene la seccion de prompt generada por el ToneProfile."""
    profile = await get_tone_profile(creator_id)
    if not profile:
        raise HTTPException(status_code=404, detail="ToneProfile not found")

    return {
        "creator_id": creator_id,
        "prompt_section": profile.to_system_prompt_section()
    }


@router.delete("/{creator_id}")
async def delete_tone_profile(creator_id: str):
    """Elimina el ToneProfile de un creador (del cache)."""
    clear_cache(creator_id)
    return {
        "status": "success",
        "message": f"Cache cleared for {creator_id}"
    }


@router.post("/{creator_id}/refresh")
async def refresh_tone_cache(creator_id: str):
    """Recarga el ToneProfile desde archivo."""
    clear_cache(creator_id)
    profile = await get_tone_profile(creator_id)
    if not profile:
        raise HTTPException(status_code=404, detail="ToneProfile not found")

    return {
        "status": "success",
        "creator_id": creator_id,
        "message": "ToneProfile reloaded from file"
    }
