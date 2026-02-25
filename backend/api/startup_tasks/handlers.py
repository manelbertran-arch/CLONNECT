"""
Application startup/shutdown event handlers.

Registers FastAPI lifecycle events:
- Database initialization (background)
- Test data cleanup (background)
- Nurturing scheduler (delayed)
- Scheduled jobs (via TaskScheduler)
- RAG hydration + reranker warmup
- Cache pre-warming
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

        # Start nurturing scheduler (delayed to avoid competing with startup)
        async def start_nurturing_delayed():
            await asyncio.sleep(30)
            try:
                from api.routers.nurturing import start_scheduler

                start_scheduler()
                logger.info("Nurturing scheduler started (delayed 30s)")
            except Exception as e:
                logger.error(f"Failed to start nurturing scheduler: {e}")

        asyncio.create_task(start_nurturing_delayed())
        logger.info("Nurturing scheduler scheduled to start in 30s")

        # =====================================================================
        # Register recurring tasks with centralized TaskScheduler
        # =====================================================================
        from core.task_scheduler import scheduler

        from api.startup_tasks.jobs_maintenance import (
            content_refresh_scheduler,
            register_maintenance_jobs,
        )
        from api.startup_tasks.jobs_ai import register_ai_jobs
        from api.startup_tasks.jobs_infra import register_infra_jobs

        register_maintenance_jobs(scheduler)
        register_ai_jobs(scheduler)
        register_infra_jobs(scheduler)

        # Content refresh runs as a standalone asyncio task (not via scheduler)
        asyncio.create_task(content_refresh_scheduler())
        logger.info("Content refresh scheduler scheduled (every 24h, 120s delay)")

        logger.info("Message reconciliation on startup DISABLED (use /maintenance/reconcile)")

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

        # Warm up reranker model (background, after RAG)
        async def warmup_reranker_background():
            await asyncio.sleep(10)
            try:
                from core.rag.reranker import warmup_reranker
                # Run in thread to avoid blocking event loop during model load
                await asyncio.to_thread(warmup_reranker)
            except Exception as e:
                logger.warning(f"Reranker warmup failed: {e}")

        asyncio.create_task(warmup_reranker_background())
        logger.info("Reranker warmup scheduled (background task)")

        # Pre-warm caches
        from api.startup_tasks.cache import do_prewarm

        async def prewarm_creator_caches():
            await asyncio.sleep(2)
            try:
                await asyncio.wait_for(do_prewarm(SessionLocal), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Pre-warming timeout after 10s, continuing anyway")
            except Exception as e:
                logger.error(f"Failed to pre-warm caches: {e}")

        asyncio.create_task(prewarm_creator_caches())
        logger.info("Cache pre-warming scheduled (background task)")

        # Cache refresh task - DISABLED: was blocking event loop
        logger.warning("Cache refresh task DISABLED - was blocking event loop")

        # Start all registered scheduled tasks
        await scheduler.start_all()

        logger.info("Ready to receive requests!")

    @app.on_event("shutdown")
    async def shutdown_event():
        from core.task_scheduler import scheduler
        await scheduler.shutdown()
