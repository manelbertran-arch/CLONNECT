"""
Tone Profile repository — PostgreSQL persistence for creator tone profiles.

Domain
------
Tone / personality signature for a creator. The `profile_data` JSON blob is
the source of truth for voice, cadence, catch-phrases and vocabulary, and is
consumed at BOOTSTRAP by `DMResponderAgentV2` to build Doc D (persona).

Pipeline phase
--------------
BOOTSTRAP / cold path. Read once at agent init and by `auto_configurator`
when refreshing persona. Never read per-DM-message.

Storage
-------
Table: `tone_profiles` (SQLAlchemy model `api.models.ToneProfile`).

In-memory cache
---------------
`_tone_cache: BoundedTTLCache` (module-level, Domain-A-exclusive).
Sized via env vars (defaults preserve prior behaviour):
  - TONE_CACHE_MAX_SIZE   (default 50)
  - TONE_CACHE_TTL_SECONDS (default 600)

Public accessors
----------------
- save_tone_profile_db(creator_id, profile_data) -> bool
- get_tone_profile_db(creator_id)                -> Optional[dict]   (async)
- get_tone_profile_db_sync(creator_id)           -> Optional[dict]   (sync)
- delete_tone_profile_db(creator_id)             -> bool
- list_profiles_db()                             -> List[str]
- clear_cache(creator_id=None)                   -> None
- get_tone_cache_stats()                         -> dict             (NEW, B-06 fix)

Notes
-----
- `_tone_cache` is intentionally prefixed with `_`; external consumers MUST
  use `get_tone_cache_stats()` instead of reaching into the private instance.
- The cache-hit read path uses `.get()` (not subscript) to encapsulate the
  "present and not expired" check atomically (B-01 fix).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.cache import BoundedTTLCache

logger = logging.getLogger(__name__)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _env_int(name: str, default: int, low: int, high: int) -> int:
    """Parse an env int; fall back to default on any error; clamp to sane range."""
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return _clamp(int(raw), low, high)
    except (TypeError, ValueError):
        logger.warning("[tone_profile_repo] invalid %s=%r, falling back to %d", name, raw, default)
        return default


TONE_CACHE_MAX_SIZE = _env_int("TONE_CACHE_MAX_SIZE", default=50, low=1, high=10_000)
TONE_CACHE_TTL_SECONDS = _env_int("TONE_CACHE_TTL_SECONDS", default=600, low=1, high=86_400)

_tone_cache: BoundedTTLCache = BoundedTTLCache(
    max_size=TONE_CACHE_MAX_SIZE,
    ttl_seconds=TONE_CACHE_TTL_SECONDS,
)


def get_tone_cache_stats() -> Dict[str, Any]:
    """Public accessor for cache telemetry (admin/debug).

    Replaces the private `_tone_cache.stats()` access pattern from
    `api/routers/admin/debug.py` (B-06 encapsulation fix).
    """
    return _tone_cache.stats()


async def save_tone_profile_db(creator_id: str, profile_data: dict) -> bool:
    """Save ToneProfile to PostgreSQL (upsert)."""
    try:
        from api.database import get_db_session
        from api.models import ToneProfile as ToneProfileModel

        with get_db_session() as db:
            existing = db.query(ToneProfileModel).filter(
                ToneProfileModel.creator_id == creator_id
            ).first()

            analyzed_count = profile_data.get("analyzed_posts_count", 0)
            confidence = profile_data.get("confidence_score", 0.0)

            if existing:
                existing.profile_data = profile_data
                existing.analyzed_posts_count = analyzed_count
                existing.confidence_score = confidence
                existing.updated_at = datetime.now(timezone.utc)
                logger.info("Updated ToneProfile in DB for %s", creator_id)
            else:
                new_profile = ToneProfileModel(
                    creator_id=creator_id,
                    profile_data=profile_data,
                    analyzed_posts_count=analyzed_count,
                    confidence_score=confidence,
                )
                db.add(new_profile)
                logger.info("Inserted ToneProfile in DB for %s", creator_id)

            db.commit()
            _tone_cache.set(creator_id, profile_data)
            return True

    except Exception as e:
        logger.error("Error saving ToneProfile to DB: %s", e)
        return False


async def get_tone_profile_db(creator_id: str) -> Optional[dict]:
    """Get ToneProfile from PostgreSQL (cache-first)."""
    # B-01 fix: `.get()` encapsulates "present AND not expired" atomically.
    cached = _tone_cache.get(creator_id)
    if cached is not None:
        logger.debug("ToneProfile for %s found in cache", creator_id)
        return cached

    try:
        from api.database import get_db_session
        from api.models import ToneProfile as ToneProfileModel

        with get_db_session() as db:
            profile = db.query(ToneProfileModel).filter(
                ToneProfileModel.creator_id == creator_id
            ).first()

            if profile:
                data = profile.profile_data
                _tone_cache.set(creator_id, data)
                logger.info("ToneProfile for %s loaded from DB", creator_id)
                return data

    except Exception as e:
        logger.error("Error loading ToneProfile from DB: %s", e)

    return None


def get_tone_profile_db_sync(creator_id: str) -> Optional[dict]:
    """Synchronous ToneProfile read (for non-async callers, e.g. bootstrap)."""
    cached = _tone_cache.get(creator_id)
    if cached is not None:
        return cached

    try:
        from api.database import get_db_session
        from api.models import ToneProfile as ToneProfileModel

        with get_db_session() as db:
            profile = db.query(ToneProfileModel).filter(
                ToneProfileModel.creator_id == creator_id
            ).first()

            if profile:
                data = profile.profile_data
                _tone_cache.set(creator_id, data)
                logger.info("ToneProfile for %s loaded from DB (sync)", creator_id)
                return data

    except Exception as e:
        logger.error("Error loading ToneProfile from DB (sync): %s", e)

    return None


async def delete_tone_profile_db(creator_id: str) -> bool:
    """Delete ToneProfile from PostgreSQL."""
    try:
        from api.database import get_db_session
        from api.models import ToneProfile as ToneProfileModel

        with get_db_session() as db:
            deleted = db.query(ToneProfileModel).filter(
                ToneProfileModel.creator_id == creator_id
            ).delete()

            db.commit()
            _tone_cache.pop(creator_id, None)

            if deleted:
                logger.info("Deleted ToneProfile from DB for %s", creator_id)
                return True
            return False

    except Exception as e:
        logger.error("Error deleting ToneProfile from DB: %s", e)
        return False


def list_profiles_db() -> List[str]:
    """Enumerate creator_ids that have a tone profile persisted."""
    try:
        from api.database import get_db_session
        from api.models import ToneProfile as ToneProfileModel

        with get_db_session() as db:
            profiles = db.query(ToneProfileModel.creator_id).all()
            return [p[0] for p in profiles]

    except Exception as e:
        logger.error("Error listing ToneProfiles from DB: %s", e)
        return []


def clear_cache(creator_id: Optional[str] = None) -> None:
    """Clear the in-memory tone cache (single key if provided, else all)."""
    if creator_id:
        _tone_cache.pop(creator_id, None)
        logger.debug("Cleared tone cache for %s", creator_id)
    else:
        _tone_cache.clear()
        logger.debug("Cleared all tone profile cache")
