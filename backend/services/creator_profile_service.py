"""CreatorProfileService — read/write CPE profiles from DB.

Single source of truth for baseline_metrics, bfi_profile, length_by_intent,
and any other per-creator profiles. Falls back gracefully if DB is unavailable.

Profile types:
  - baseline_metrics: quantitative style stats (length, emoji, punctuation, etc.)
  - bfi_profile: Big Five personality scores
  - length_by_intent: per-intent response length distribution
  - compressed_doc_d: pre-built personality prompt text
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory cache: {(creator_id, profile_type): data_dict}
_profile_cache: dict[tuple[str, str], Optional[dict]] = {}


def _resolve_creator_uuid(session, creator_slug: str):
    """Resolve creator slug (e.g. 'iris_bertran') to UUID."""
    from api.models.creator import Creator
    creator = session.query(Creator.id).filter(Creator.name == creator_slug).first()
    return creator.id if creator else None


def get_profile(creator_id: str, profile_type: str) -> Optional[dict]:
    """Read a profile from DB. Returns None if not found.

    Results are cached in memory for the process lifetime.
    """
    cache_key = (creator_id, profile_type)
    if cache_key in _profile_cache:
        return _profile_cache[cache_key]

    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            creator_uuid = _resolve_creator_uuid(session, creator_id)
            if not creator_uuid:
                _profile_cache[cache_key] = None
                return None

            row = session.execute(
                text("""
                    SELECT data FROM creator_profiles
                    WHERE creator_id = :cid AND profile_type = :ptype
                """),
                {"cid": str(creator_uuid), "ptype": profile_type},
            ).fetchone()

            result = row[0] if row else None
            _profile_cache[cache_key] = result
            return result
        finally:
            session.close()
    except Exception as e:
        logger.debug("get_profile(%s, %s) failed: %s", creator_id, profile_type, e)
        _profile_cache[cache_key] = None
        return None


def save_profile(creator_id: str, profile_type: str, data: dict) -> bool:
    """Save/update a profile in the DB (upsert). Returns True on success."""
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            creator_uuid = _resolve_creator_uuid(session, creator_id)
            if not creator_uuid:
                logger.warning("save_profile: creator '%s' not found in DB", creator_id)
                return False

            # Upsert via INSERT ON CONFLICT
            # json.dumps needed because text() + psycopg2 doesn't auto-serialize dicts to JSONB
            data_json = json.dumps(data, ensure_ascii=False, default=str)
            session.execute(
                text("""
                    INSERT INTO creator_profiles (creator_id, profile_type, data, updated_at)
                    VALUES (:cid, :ptype, CAST(:data AS jsonb), NOW())
                    ON CONFLICT ON CONSTRAINT uq_creator_profiles_creator_type
                    DO UPDATE SET data = CAST(:data AS jsonb), updated_at = NOW()
                """),
                {"cid": str(creator_uuid), "ptype": profile_type, "data": data_json},
            )
            session.commit()

            # Invalidate cache
            cache_key = (creator_id, profile_type)
            _profile_cache.pop(cache_key, None)

            logger.info("save_profile: %s/%s saved", creator_id, profile_type)
            return True
        finally:
            session.close()
    except Exception as e:
        logger.error("save_profile(%s, %s) failed: %s", creator_id, profile_type, e)
        return False


def get_baseline(creator_id: str) -> Optional[dict]:
    """Get baseline_metrics profile."""
    return get_profile(creator_id, "baseline_metrics")


def get_bfi(creator_id: str) -> Optional[dict]:
    """Get bfi_profile."""
    return get_profile(creator_id, "bfi_profile")


def get_length_profile(creator_id: str) -> Optional[dict]:
    """Get length_by_intent profile."""
    return get_profile(creator_id, "length_by_intent")


def clear_cache():
    """Clear the in-memory profile cache."""
    _profile_cache.clear()
