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
                creators = session.query(Creator).filter_by(bot_active=True).all()
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
                await get_conversations(creator_id, limit=50, offset=0)
                logger.info(f"[CACHE-WARM] {creator_id}: conversations cached")
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
        from api.routers.messages import get_pipeline_score
        from api.services import db_service

        # Get active creators from DB
        active_creators = []
        if SessionLocal:
            session = SessionLocal()
            try:
                creators = session.query(Creator).filter_by(bot_active=True).all()
                active_creators = [c.name for c in creators if c.name]
            finally:
                session.close()

        # Always include stefano_bonanno (main production creator)
        if "stefano_bonanno" not in active_creators:
            active_creators.append("stefano_bonanno")

        for creator_id in active_creators:
            # Refresh conversations cache
            try:
                result = db_service.get_conversations_with_counts(creator_id, limit=50, offset=0)
                if result:
                    conversations_data = result.get("conversations", [])
                    conversations = []
                    for c in conversations_data:
                        lead_status = c.get("status", "new")
                        intent = c.get("purchase_intent_score", 0)
                        conversations.append({
                            "follower_id": c.get("platform_user_id") or c.get("follower_id"),
                            "id": c.get("id"),
                            "username": c.get("username"),
                            "name": c.get("name"),
                            "profile_pic_url": c.get("profile_pic_url"),
                            "platform": c.get("platform", "instagram"),
                            "total_messages": c.get("total_messages", 0),
                            "purchase_intent": intent,
                            "purchase_intent_score": round(intent * 100) if intent <= 1 else int(intent),
                            "lead_status": lead_status,
                            "status": lead_status,
                            "pipeline_score": get_pipeline_score(lead_status),
                            "last_messages": [],
                            "last_contact": c.get("last_contact"),
                            "first_contact": c.get("first_contact"),
                            "last_message_preview": c.get("last_message_preview"),
                            "last_message_role": c.get("last_message_role"),
                            "is_unread": c.get("is_unread", False),
                            "is_verified": c.get("is_verified", False),
                            "email": c.get("email") or "",
                            "phone": c.get("phone") or "",
                            "notes": c.get("notes") or "",
                            "tags": c.get("tags") or [],
                            "deal_value": c.get("deal_value"),
                        })
                    cached_result = {
                        "status": "ok",
                        "conversations": conversations,
                        "count": len(conversations),
                        "total_count": result.get("total_count", 0),
                        "limit": 50,
                        "offset": 0,
                        "has_more": result.get("has_more", False),
                        "product_price": 97.0,
                    }
                    # Set for BOTH endpoints (dm.py and messages.py use different keys)
                    # Use 60s TTL to ensure cache survives between refresh cycles (every 20s)
                    api_cache.set(f"conversations:{creator_id}:50:0", cached_result, ttl_seconds=60)  # messages.py
                    api_cache.set(f"conversations:{creator_id}:50", cached_result, ttl_seconds=60)    # dm.py
                    logger.info(f"[CACHE-REFRESH] {creator_id}: cached {len(conversations)} conversations")
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
