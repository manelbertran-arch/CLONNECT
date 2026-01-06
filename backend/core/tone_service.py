"""
Tone Service - Gestiona ToneProfiles de creadores.
Conecta Magic Slice con el sistema existente.
"""

import json
import logging
from typing import Optional, Dict, List
from pathlib import Path

from ingestion import ToneProfile, ToneAnalyzer

logger = logging.getLogger(__name__)

# Cache en memoria de tone profiles
_tone_cache: Dict[str, ToneProfile] = {}

# Directorio para persistencia
TONE_PROFILES_DIR = Path("data/tone_profiles")


def _ensure_dir():
    """Asegura que el directorio de perfiles exista."""
    TONE_PROFILES_DIR.mkdir(parents=True, exist_ok=True)


async def get_tone_profile(creator_id: str) -> Optional[ToneProfile]:
    """
    Obtiene el ToneProfile de un creador.

    Args:
        creator_id: ID del creador

    Returns:
        ToneProfile o None si no existe
    """
    # Primero buscar en cache
    if creator_id in _tone_cache:
        logger.debug(f"ToneProfile for {creator_id} found in cache")
        return _tone_cache[creator_id]

    # Luego buscar en archivo
    profile_path = TONE_PROFILES_DIR / f"{creator_id}.json"
    if profile_path.exists():
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            profile = ToneProfile.from_dict(data)
            _tone_cache[creator_id] = profile
            logger.info(f"ToneProfile for {creator_id} loaded from file")
            return profile
        except Exception as e:
            logger.error(f"Error loading ToneProfile for {creator_id}: {e}")

    return None


async def save_tone_profile(profile: ToneProfile) -> bool:
    """
    Guarda un ToneProfile.

    Args:
        profile: ToneProfile a guardar

    Returns:
        True si se guardo correctamente
    """
    try:
        _ensure_dir()

        profile_path = TONE_PROFILES_DIR / f"{profile.creator_id}.json"
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)

        # Actualizar cache
        _tone_cache[profile.creator_id] = profile

        logger.info(f"ToneProfile for {profile.creator_id} saved to {profile_path}")
        return True

    except Exception as e:
        logger.error(f"Error saving ToneProfile: {e}")
        return False


async def generate_tone_profile(
    creator_id: str,
    posts: List[Dict],
    save: bool = True
) -> ToneProfile:
    """
    Genera un ToneProfile analizando posts del creador.

    Args:
        creator_id: ID del creador
        posts: Lista de posts con 'caption'
        save: Si guardar el perfil generado

    Returns:
        ToneProfile generado
    """
    analyzer = ToneAnalyzer()
    profile = await analyzer.analyze(creator_id, posts)

    if save:
        await save_tone_profile(profile)

    return profile


def get_tone_prompt_section(creator_id: str) -> str:
    """
    Obtiene la seccion de prompt para un creador.
    Version sincrona para usar en el flujo actual de dm_agent.

    Args:
        creator_id: ID del creador

    Returns:
        String para inyectar en system prompt, o vacio si no hay perfil
    """
    # Buscar en cache
    if creator_id in _tone_cache:
        return _tone_cache[creator_id].to_system_prompt_section()

    # Intentar cargar de archivo
    profile_path = TONE_PROFILES_DIR / f"{creator_id}.json"
    if profile_path.exists():
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            profile = ToneProfile.from_dict(data)
            _tone_cache[creator_id] = profile
            logger.info(f"ToneProfile for {creator_id} loaded (sync)")
            return profile.to_system_prompt_section()
        except Exception as e:
            logger.error(f"Error loading ToneProfile (sync): {e}")

    return ""


def get_tone_language(creator_id: str) -> Optional[str]:
    """
    Obtiene el primary_language del ToneProfile de un creador.

    Args:
        creator_id: ID del creador

    Returns:
        Código de idioma ("es", "en", "pt") o None si no hay perfil
    """
    # Buscar en cache
    if creator_id in _tone_cache:
        return _tone_cache[creator_id].primary_language

    # Intentar cargar de archivo
    profile_path = TONE_PROFILES_DIR / f"{creator_id}.json"
    if profile_path.exists():
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            profile = ToneProfile.from_dict(data)
            _tone_cache[creator_id] = profile
            logger.info(f"ToneProfile for {creator_id} loaded for language check")
            return profile.primary_language
        except Exception as e:
            logger.error(f"Error loading ToneProfile for language: {e}")

    return None


def clear_cache(creator_id: Optional[str] = None):
    """
    Limpia el cache de perfiles.

    Args:
        creator_id: Si se especifica, solo limpia ese creador
    """
    if creator_id:
        _tone_cache.pop(creator_id, None)
        logger.debug(f"Cleared cache for {creator_id}")
    else:
        _tone_cache.clear()
        logger.debug("Cleared all tone profile cache")


def list_profiles() -> List[str]:
    """
    Lista todos los creator_ids con ToneProfile guardado.

    Returns:
        Lista de creator_ids
    """
    _ensure_dir()
    return [p.stem for p in TONE_PROFILES_DIR.glob("*.json")]


def delete_tone_profile(creator_id: str) -> bool:
    """
    Elimina el ToneProfile de un creador.

    Args:
        creator_id: ID del creador

    Returns:
        True si se elimino, False si no existia
    """
    filepath = TONE_PROFILES_DIR / f"{creator_id}.json"
    if filepath.exists():
        filepath.unlink()
        # Limpiar cache
        if creator_id in _tone_cache:
            del _tone_cache[creator_id]
        logger.info(f"Deleted ToneProfile for {creator_id}")
        return True
    return False
