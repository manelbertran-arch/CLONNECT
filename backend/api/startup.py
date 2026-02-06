"""
Application startup handlers.
Extracted from main.py following TDD methodology.

Contains:
- Database initialization
- RAG hydration
- Cache warming
- Keep-alive setup
"""

import asyncio
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


def register_startup_handlers(app: "FastAPI"):
    """Register startup and shutdown handlers on the FastAPI app."""

    @app.on_event("startup")
    async def startup_event():
        """Application startup handler"""
        # Import dependencies here to avoid circular imports
        from api.database import SessionLocal
        from api.init_db import init_database
        from core.rag import get_simple_rag

        rag = get_simple_rag()

        logger.info("Clonnect Creators API starting...")
        logger.info(f"LLM Provider: {os.getenv('LLM_PROVIDER', 'openai')}")

        # Log database configuration
        db_url = os.getenv("DATABASE_URL")
        json_fallback = os.getenv("ENABLE_JSON_FALLBACK", "false").lower() == "true"
        if db_url:
            logger.info("Database: PostgreSQL configured")
            if json_fallback:
                logger.warning("JSON Fallback: ENABLED - DB errors will fall back to JSON files")
            else:
                logger.info("JSON Fallback: DISABLED - DB errors will raise exceptions")
        else:
            logger.warning("Database: No DATABASE_URL - using JSON files only")

        # Initialize database in background to not block healthcheck
        async def init_db_background():
            await asyncio.sleep(1)
            try:
                if db_url:
                    logger.info("Starting database initialization (background)...")
                    init_database()
                    logger.info("Database initialization complete")
            except Exception as e:
                logger.error(f"Database initialization failed: {e}")

        asyncio.create_task(init_db_background())
        logger.info("Database initialization scheduled (background task)")

        # Clean test data on startup
        async def cleanup_test_data():
            await asyncio.sleep(3)  # Wait for DB to be ready
            try:
                from sqlalchemy import text

                session = SessionLocal()
                try:
                    # Delete test leads with 999999% pattern
                    result1 = session.execute(
                        text("DELETE FROM leads WHERE platform_user_id LIKE '999999%'")
                    )
                    result2 = session.execute(
                        text("DELETE FROM leads WHERE platform_user_id LIKE 'ig_999%'")
                    )
                    result3 = session.execute(
                        text("DELETE FROM leads WHERE username LIKE 'test_%'")
                    )
                    session.commit()
                    total_deleted = result1.rowcount + result2.rowcount + result3.rowcount
                    if total_deleted > 0:
                        logger.info(f"[Cleanup] Deleted {total_deleted} test leads on startup")
                finally:
                    session.close()
            except Exception as e:
                logger.error(f"[Cleanup] Failed to clean test data: {e}")

        asyncio.create_task(cleanup_test_data())
        logger.info("Test data cleanup scheduled (background task)")

        # Start nurturing scheduler
        try:
            from api.routers.nurturing import start_scheduler

            start_scheduler()
            logger.info("Nurturing scheduler started")
        except Exception as e:
            logger.error(f"Failed to start nurturing scheduler: {e}")

        # DISABLED: Startup reconciliation was making 20+ Instagram API calls
        # causing slow startup and 403 errors. Run manually via /maintenance/reconcile if needed.
        logger.info("Message reconciliation DISABLED on startup (use /maintenance/reconcile)")

        # Hydrate RAG from PostgreSQL
        async def hydrate_rag_background():
            await asyncio.sleep(5)
            try:
                loaded = rag.load_from_db()
                logger.info(f"RAG hydrated with {loaded} documents from database")
            except Exception as e:
                logger.error(f"Failed to hydrate RAG from database: {e}")

        asyncio.create_task(hydrate_rag_background())
        logger.info("RAG hydration scheduled (background task)")

        # Pre-warm caches
        async def prewarm_creator_caches():
            await asyncio.sleep(2)
            try:
                await asyncio.wait_for(_do_prewarm(SessionLocal), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Pre-warming timeout after 10s, continuing anyway")
            except Exception as e:
                logger.error(f"Failed to pre-warm caches: {e}")

        asyncio.create_task(prewarm_creator_caches())
        logger.info("Cache pre-warming scheduled (background task)")

        # Cache refresh task - keeps cache warm continuously
        async def cache_refresh_task():
            REFRESH_INTERVAL = 25  # seconds (less than 30s TTL)
            await asyncio.sleep(30)  # Wait for initial warmup to complete
            logger.info("[CACHE-REFRESH] Started - refreshing every 25s")

            while True:
                try:
                    await asyncio.sleep(REFRESH_INTERVAL)
                    await _do_cache_refresh(SessionLocal)
                except Exception as e:
                    logger.error(f"[CACHE-REFRESH] Error: {e}")

        asyncio.create_task(cache_refresh_task())
        logger.info("Cache refresh task scheduled (every 25 seconds)")

        # Keep-alive task - SIMPLIFIED: just DB ping to prevent cold starts
        async def keep_alive_task():
            import time

            KEEP_ALIVE_INTERVAL = 240  # 4 minutes

            await asyncio.sleep(3)
            logger.info("[KEEP-ALIVE] Started - simple DB ping every 4 min")

            while True:
                try:
                    _t_start = time.time()

                    # SIMPLE: Just ping the database - no Instagram, no LLM, no heavy ops
                    if SessionLocal:
                        try:
                            from sqlalchemy import text

                            session = SessionLocal()
                            session.execute(text("SELECT 1"))
                            session.close()
                        except Exception as e:
                            logger.warning(f"[KEEP-ALIVE] DB ping failed: {e}")

                    _t_end = time.time()
                    logger.debug(f"[KEEP-ALIVE] Ping OK in {_t_end - _t_start:.3f}s")

                except Exception as e:
                    logger.error(f"[KEEP-ALIVE] Error: {e}")

                await asyncio.sleep(KEEP_ALIVE_INTERVAL)

        asyncio.create_task(keep_alive_task())
        logger.info("Keep-alive task scheduled (every 4 minutes)")

        logger.info("Ready to receive requests!")


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
    except Exception:
        pass

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

    # === NEW: Warm API response cache for conversations and leads ===
    try:
        from api.cache import api_cache
        from api.services import db_service

        for creator_id in active_creators:
            try:
                # Warm conversations cache (limit=50, offset=0 - default params)
                result = db_service.get_conversations_with_counts(creator_id, limit=50, offset=0)
                if result:
                    cache_key = f"conversations:{creator_id}:50:0"
                    # Format like the endpoint does
                    conversations_data = result.get("conversations", [])
                    from api.routers.messages import get_pipeline_score

                    conversations = []
                    for c in conversations_data:
                        lead_status = c.get("status", "new")
                        intent = c.get("purchase_intent_score", 0)
                        conversations.append(
                            {
                                "follower_id": c.get("platform_user_id") or c.get("follower_id"),
                                "id": c.get("id"),
                                "username": c.get("username"),
                                "name": c.get("name"),
                                "profile_pic_url": c.get("profile_pic_url"),
                                "platform": c.get("platform", "instagram"),
                                "total_messages": c.get("total_messages", 0),
                                "purchase_intent": intent,
                                "purchase_intent_score": (
                                    round(intent * 100) if intent <= 1 else int(intent)
                                ),
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
                            }
                        )
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
                    api_cache.set(
                        cache_key, cached_result, ttl_seconds=60
                    )  # 60s for startup warmup
                    logger.info(
                        f"[CACHE-WARM] {creator_id}: conversations cached ({len(conversations)} items)"
                    )
            except Exception as e:
                logger.warning(f"[CACHE-WARM] Failed to warm conversations for {creator_id}: {e}")

            try:
                # Warm leads cache (limit=100 - default param)
                # Note: get_leads() returns list of dicts, not Lead objects
                leads = db_service.get_leads(creator_id, limit=100)
                if leads is not None:
                    cache_key = f"leads:{creator_id}:100"
                    # get_leads already returns properly formatted dicts
                    cached_result = {"status": "ok", "leads": leads, "count": len(leads)}
                    api_cache.set(cache_key, cached_result, ttl_seconds=60)  # 60s for warming
                    logger.info(f"[CACHE-WARM] {creator_id}: leads cached ({len(leads)} items)")
            except Exception as e:
                logger.warning(f"[CACHE-WARM] Failed to warm leads for {creator_id}: {e}")

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

        if not active_creators:
            active_creators = ["stefano_bonanno"]

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
                    api_cache.set(f"conversations:{creator_id}:50:0", cached_result, ttl_seconds=30)
            except Exception as e:
                logger.debug(f"[CACHE-REFRESH] conversations {creator_id}: {e}")

            # Refresh leads cache
            try:
                leads = db_service.get_leads(creator_id, limit=100)
                if leads is not None:
                    cached_result = {"status": "ok", "leads": leads, "count": len(leads)}
                    api_cache.set(f"leads:{creator_id}:100", cached_result, ttl_seconds=30)
            except Exception as e:
                logger.debug(f"[CACHE-REFRESH] leads {creator_id}: {e}")

        logger.debug(f"[CACHE-REFRESH] Refreshed cache for {len(active_creators)} creators")
    except Exception as e:
        logger.warning(f"[CACHE-REFRESH] Error: {e}")
