"""
Cache warming and refresh logic.
Extracted from api/startup.py — standalone module-level helpers.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def _do_prewarm(SessionLocal):
    """Pre-warm caches for active creators."""
    import time

    _t_start = time.time()

    active_creators = set()

    if SessionLocal:
        try:
            from api.models import Creator

            session = SessionLocal()
            try:
                creators = session.query(Creator).filter_by(bot_active=True).limit(50).all()
                for c in creators:
                    if c.name:
                        active_creators.add(c.name)
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Could not get creators from DB: {e}")

    try:
        from core.telegram_registry import get_telegram_registry

        registry = get_telegram_registry()
        for bot in registry.list_bots():
            if bot.get("is_active") and bot.get("creator_id"):
                active_creators.add(bot["creator_id"])
    except Exception as e:
        logger.warning("Suppressed error in from core.telegram_registry import get_telegram...: %s", e)

    if not active_creators:
        active_creators = {"stefano_auto"}

    active_creators = list(active_creators)
    logger.info(f"Pre-warming caches for {len(active_creators)} creators: {active_creators}")

    try:
        from core.semantic_memory import ENABLE_SEMANTIC_MEMORY, _get_embeddings

        if ENABLE_SEMANTIC_MEMORY:
            _t_emb = time.time()
            _get_embeddings()
            logger.info(f"Pre-loaded embedding model in {time.time() - _t_emb:.2f}s")
    except Exception as e:
        logger.warning(f"Could not pre-load embedding model: {e}")

    from core.tone_service import get_tone_prompt_section

    for creator_id in active_creators:
        try:
            get_tone_prompt_section(creator_id)
        except Exception as e:
            logger.debug(f"ToneProfile not found for {creator_id}: {e}")

    from core.citation_service import get_content_index

    for creator_id in active_creators:
        try:
            get_content_index(creator_id)
        except Exception as e:
            logger.debug(f"CitationIndex not found for {creator_id}: {e}")

    # === Warm conversations cache by calling the real endpoint logic ===
    try:
        from api.routers.dm import get_conversations

        for creator_id in active_creators:
            try:
                await get_conversations(creator_id)
                logger.info(f"[CACHE-WARM] {creator_id}: conversations cached (90d window)")
            except Exception as e:
                logger.warning(f"[CACHE-WARM] Failed for {creator_id}: {e}")
    except Exception as e:
        logger.error(f"[CACHE-WARM] Failed to warm API caches: {e}")

    _t_end = time.time()
    logger.info(f"Pre-warmed caches in {_t_end - _t_start:.2f}s for {active_creators}")


async def _do_cache_refresh(SessionLocal):
    """Refresh cache for active creators - runs periodically to keep cache warm."""
    try:
        from api.cache import api_cache
        from api.models import Creator
        from api.services import db_service

        # Get active creators from DB
        active_creators = []
        if SessionLocal:
            session = SessionLocal()
            try:
                creators = session.query(Creator).filter_by(bot_active=True).limit(50).all()
                active_creators = [c.name for c in creators if c.name]
            finally:
                session.close()

        # Always include stefano_bonanno (main production creator)
        if "stefano_bonanno" not in active_creators:
            active_creators.append("stefano_bonanno")

        for creator_id in active_creators:
            # Refresh conversations cache — call the real endpoint (90d window)
            try:
                from api.routers.dm import get_conversations
                result = await get_conversations(creator_id)
                # The endpoint already caches via api_cache
                logger.info(f"[CACHE-REFRESH] {creator_id}: conversations refreshed (90d window)")
            except Exception as e:
                logger.warning(f"[CACHE-REFRESH] conversations {creator_id} FAILED: {e}")

            # Refresh leads cache
            try:
                leads = db_service.get_leads(creator_id, limit=100)
                if leads is not None:
                    cached_result = {"status": "ok", "leads": leads, "count": len(leads)}
                    api_cache.set(f"leads:{creator_id}:100", cached_result, ttl_seconds=60)
            except Exception as e:
                logger.debug(f"[CACHE-REFRESH] leads {creator_id}: {e}")

        logger.info(f"[CACHE-REFRESH] Refreshed cache for {active_creators}")
    except Exception as e:
        logger.warning(f"[CACHE-REFRESH] Error: {e}")
