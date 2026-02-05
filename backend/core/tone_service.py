"""
Tone Service - Gestiona ToneProfiles de creadores.
Conecta Magic Slice con el sistema existente.

MIGRADO: Usa PostgreSQL como almacenamiento principal con JSON como fallback.
"""

import json
import logging
from typing import Optional, Dict, List
from pathlib import Path

from ingestion import ToneProfile, ToneAnalyzer

logger = logging.getLogger(__name__)

# Cache en memoria de tone profiles
_tone_cache: Dict[str, ToneProfile] = {}

# Directorio para persistencia JSON (fallback)
TONE_PROFILES_DIR = Path("data/tone_profiles")


def _ensure_dir():
    """Asegura que el directorio de perfiles exista."""
    TONE_PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def _try_load_from_db(creator_id: str) -> Optional[dict]:
    """Intenta cargar desde PostgreSQL."""
    try:
        from core.tone_profile_db import get_tone_profile_db_sync
        data = get_tone_profile_db_sync(creator_id)
        if data:
            logger.info(f"ToneProfile for {creator_id} loaded from PostgreSQL")
            return data
    except Exception as e:
        logger.warning(f"DB read failed for {creator_id}, will try JSON: {e}")
    return None


def _try_load_from_json(creator_id: str) -> Optional[dict]:
    """Intenta cargar desde archivo JSON."""
    profile_path = TONE_PROFILES_DIR / f"{creator_id}.json"
    if profile_path.exists():
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"ToneProfile for {creator_id} loaded from JSON file")
            return data
        except Exception as e:
            logger.error(f"Error loading ToneProfile from JSON: {e}")
    return None


def _save_to_json(creator_id: str, data: dict) -> bool:
    """Guarda en archivo JSON (backup)."""
    try:
        _ensure_dir()
        profile_path = TONE_PROFILES_DIR / f"{creator_id}.json"
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving to JSON: {e}")
        return False


async def get_tone_profile(creator_id: str) -> Optional[ToneProfile]:
    """
    Obtiene el ToneProfile de un creador.
    Busca en: 1) Cache, 2) PostgreSQL, 3) JSON file

    Args:
        creator_id: ID del creador

    Returns:
        ToneProfile o None si no existe
    """
    # 1. Buscar en cache
    if creator_id in _tone_cache:
        logger.debug(f"ToneProfile for {creator_id} found in cache")
        return _tone_cache[creator_id]

    # 2. Intentar PostgreSQL
    data = _try_load_from_db(creator_id)

    # 3. Fallback a JSON
    if not data:
        data = _try_load_from_json(creator_id)

    if data:
        # Ensure creator_id is in data for ToneProfile
        if 'creator_id' not in data:
            data['creator_id'] = creator_id
        profile = ToneProfile.from_dict(data)
        _tone_cache[creator_id] = profile
        return profile

    return None


async def save_tone_profile(profile: ToneProfile) -> bool:
    """
    Guarda un ToneProfile.
    Guarda en: 1) PostgreSQL (principal), 2) JSON (backup)

    Args:
        profile: ToneProfile a guardar

    Returns:
        True si se guardo correctamente
    """
    logger.debug(f"[save_tone_profile] Starting for {profile.creator_id}")
    creator_id = profile.creator_id
    profile_data = profile.to_dict()
    logger.debug("[save_tone_profile] Converted to dict")

    db_success = False
    json_success = False

    # 1. Intentar guardar en PostgreSQL
    try:
        logger.debug("[save_tone_profile] Importing save_tone_profile_db...")
        from core.tone_profile_db import save_tone_profile_db
        logger.debug("[save_tone_profile] Saving to PostgreSQL...")
        db_success = await save_tone_profile_db(creator_id, profile_data)
        logger.debug(f"[save_tone_profile] PostgreSQL save result: {db_success}")
        if db_success:
            logger.info(f"ToneProfile for {creator_id} saved to PostgreSQL")
    except Exception as e:
        logger.exception(f"[save_tone_profile] PostgreSQL error: {e}")

    # 2. También guardar en JSON como backup
    logger.debug("[save_tone_profile] Saving to JSON...")
    json_success = _save_to_json(creator_id, profile_data)
    logger.debug(f"[save_tone_profile] JSON save result: {json_success}")
    if json_success:
        logger.info(f"ToneProfile for {creator_id} saved to JSON (backup)")

    # 3. Actualizar cache
    _tone_cache[creator_id] = profile
    logger.debug(f"[save_tone_profile] Done, db={db_success}, json={json_success}")

    return db_success or json_success


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
    # 1. Buscar en cache
    if creator_id in _tone_cache:
        return _tone_cache[creator_id].to_system_prompt_section()

    # 2. Intentar PostgreSQL
    data = _try_load_from_db(creator_id)

    # 3. Fallback a JSON
    if not data:
        data = _try_load_from_json(creator_id)

    if data:
        # Ensure creator_id is in data for ToneProfile
        if 'creator_id' not in data:
            data['creator_id'] = creator_id
        profile = ToneProfile.from_dict(data)
        _tone_cache[creator_id] = profile
        return profile.to_system_prompt_section()

    return ""


def get_tone_language(creator_id: str) -> Optional[str]:
    """
    Obtiene el primary_language del ToneProfile de un creador.

    Args:
        creator_id: ID del creador

    Returns:
        Código de idioma ("es", "en", "pt") o None si no hay perfil
    """
    # 1. Buscar en cache
    if creator_id in _tone_cache:
        return _tone_cache[creator_id].primary_language

    # 2. Intentar PostgreSQL
    data = _try_load_from_db(creator_id)

    # 3. Fallback a JSON
    if not data:
        data = _try_load_from_json(creator_id)

    if data:
        # Ensure creator_id is in data for ToneProfile
        if 'creator_id' not in data:
            data['creator_id'] = creator_id
        profile = ToneProfile.from_dict(data)
        _tone_cache[creator_id] = profile
        return profile.primary_language

    return None


def get_tone_dialect(creator_id: str) -> str:
    """
    Obtiene el dialect del ToneProfile de un creador.

    Args:
        creator_id: ID del creador

    Returns:
        Dialecto ("neutral", "rioplatense", "mexicano", "español") o "neutral" por defecto
    """
    # 1. Buscar en cache
    if creator_id in _tone_cache:
        return getattr(_tone_cache[creator_id], 'dialect', 'neutral')

    # 2. Intentar PostgreSQL
    data = _try_load_from_db(creator_id)

    # 3. Fallback a JSON
    if not data:
        data = _try_load_from_json(creator_id)

    if data:
        # Ensure creator_id is in data for ToneProfile
        if 'creator_id' not in data:
            data['creator_id'] = creator_id
        profile = ToneProfile.from_dict(data)
        _tone_cache[creator_id] = profile
        return getattr(profile, 'dialect', 'neutral')

    return "neutral"


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

    # También limpiar cache de DB service
    try:
        from core.tone_profile_db import clear_cache as clear_db_cache
        clear_db_cache(creator_id)
    except Exception:
        pass


def list_profiles() -> List[str]:
    """
    Lista todos los creator_ids con ToneProfile guardado.
    Combina resultados de PostgreSQL y JSON.

    Returns:
        Lista de creator_ids
    """
    profiles = set()

    # 1. Desde PostgreSQL
    try:
        from core.tone_profile_db import list_profiles_db
        db_profiles = list_profiles_db()
        profiles.update(db_profiles)
        logger.debug(f"Found {len(db_profiles)} profiles in PostgreSQL")
    except Exception as e:
        logger.warning(f"Could not list profiles from DB: {e}")

    # 2. Desde JSON
    _ensure_dir()
    json_profiles = [p.stem for p in TONE_PROFILES_DIR.glob("*.json")]
    profiles.update(json_profiles)
    logger.debug(f"Found {len(json_profiles)} profiles in JSON")

    return list(profiles)


def delete_tone_profile(creator_id: str) -> bool:
    """
    Elimina el ToneProfile de un creador.
    Elimina de PostgreSQL y JSON.

    Args:
        creator_id: ID del creador

    Returns:
        True si se elimino de algún lugar
    """
    deleted_any = False

    # 1. Eliminar de PostgreSQL
    try:
        from core.tone_profile_db import delete_tone_profile_db
        import asyncio

        # Run async function
        loop = asyncio.new_event_loop()
        db_deleted = loop.run_until_complete(delete_tone_profile_db(creator_id))
        loop.close()

        if db_deleted:
            logger.info(f"Deleted ToneProfile for {creator_id} from PostgreSQL")
            deleted_any = True
    except Exception as e:
        logger.warning(f"Could not delete from DB: {e}")

    # 2. Eliminar de JSON
    filepath = TONE_PROFILES_DIR / f"{creator_id}.json"
    if filepath.exists():
        filepath.unlink()
        logger.info(f"Deleted ToneProfile for {creator_id} from JSON")
        deleted_any = True

    # 3. Limpiar cache
    _tone_cache.pop(creator_id, None)

    return deleted_any
