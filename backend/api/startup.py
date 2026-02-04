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
        from core.dm_agent_v2 import _dm_agent_cache_timestamp, get_dm_agent
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

        # Run message reconciliation on startup (recover last 24 hours)
        async def startup_reconciliation():
            await asyncio.sleep(10)  # Wait for DB to be ready
            try:
                from core.message_reconciliation import run_startup_reconciliation

                result = await run_startup_reconciliation()
                if result.get("total_inserted", 0) > 0:
                    logger.info(
                        f"[Reconciliation] Startup: recovered {result['total_inserted']} "
                        f"messages for {result['creators_processed']} creators"
                    )
                else:
                    logger.info("[Reconciliation] Startup: no missing messages found")
            except Exception as e:
                logger.error(f"[Reconciliation] Startup reconciliation failed: {e}")

        asyncio.create_task(startup_reconciliation())
        logger.info("Message reconciliation scheduled (startup task)")

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

        # Keep-alive task
        async def keep_alive_task():
            import time

            KEEP_ALIVE_INTERVAL = 240

            await asyncio.sleep(3)
            logger.warning(
                f"[KEEP-ALIVE] ===== STARTED - will ping every {KEEP_ALIVE_INTERVAL}s (4 min) ====="
            )

            while True:
                try:
                    _t_start = time.time()
                    active_creators = set(["stefano_auto", "stefano_bonanno"])

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
                        except Exception:
                            pass

                    try:
                        from core.telegram_registry import get_telegram_registry

                        registry = get_telegram_registry()
                        for bot in registry.list_bots():
                            if bot.get("is_active") and bot.get("creator_id"):
                                active_creators.add(bot["creator_id"])
                    except Exception:
                        pass

                    active_creators = list(active_creators)

                    for creator_id in active_creators:
                        try:
                            agent = get_dm_agent(creator_id)
                            cache_age = time.time() - _dm_agent_cache_timestamp.get(creator_id, 0)
                            if hasattr(agent, "_build_system_prompt"):
                                _ = agent._build_system_prompt("")
                            logger.info(
                                f"[KEEP-ALIVE] Agent for {creator_id} kept warm (cache age: {cache_age:.1f}s)"
                            )
                        except Exception as e:
                            logger.warning(
                                f"[KEEP-ALIVE] DM agent warm failed for {creator_id}: {e}"
                            )

                    try:
                        from core.semantic_memory import ENABLE_SEMANTIC_MEMORY, _get_embeddings

                        if ENABLE_SEMANTIC_MEMORY:
                            _get_embeddings()
                    except Exception:
                        pass

                    try:
                        from core.citation_service import get_content_index
                        from core.tone_service import get_tone_prompt_section

                        for creator_id in active_creators:
                            try:
                                get_tone_prompt_section(creator_id)
                                get_content_index(creator_id)
                            except Exception:
                                pass
                    except Exception:
                        pass

                    if SessionLocal:
                        try:
                            from sqlalchemy import text

                            session = SessionLocal()
                            session.execute(text("SELECT 1"))
                            session.close()
                        except Exception:
                            pass

                    _t_end = time.time()
                    logger.warning(
                        f"[KEEP-ALIVE] ===== Ping completed in {_t_end - _t_start:.2f}s ====="
                    )

                except Exception as e:
                    logger.error(f"[KEEP-ALIVE] Error: {e}", exc_info=True)

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

    _t_end = time.time()
    logger.info(f"Pre-warmed caches in {_t_end - _t_start:.2f}s for {active_creators}")
