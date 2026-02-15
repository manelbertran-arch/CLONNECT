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

        # Start daily OAuth token refresh scheduler
        async def start_token_refresh_scheduler():
            """Check and refresh OAuth tokens once daily (every 24h)."""
            await asyncio.sleep(60)  # Wait for DB to be ready
            logger.info("[TOKEN-REFRESH] Scheduler started — runs every 24h")

            while True:
                try:
                    from core.token_refresh_service import refresh_all_creator_tokens

                    session = SessionLocal()
                    try:
                        stats = await refresh_all_creator_tokens(session)
                        logger.info(
                            "[TOKEN-REFRESH] Completed: "
                            f"{stats.get('refreshed', 0)} refreshed, "
                            f"{stats.get('failed', 0)} failed"
                        )
                    finally:
                        session.close()
                except Exception as e:
                    logger.error(f"[TOKEN-REFRESH] Scheduler error: {e}")

                await asyncio.sleep(86400)  # 24 hours

        asyncio.create_task(start_token_refresh_scheduler())
        logger.info("Token refresh scheduler scheduled (every 24h)")

        # Start daily content refresh scheduler (re-scrape IG posts, chunk, embed)
        async def start_content_refresh_scheduler():
            try:
                from services.content_refresh import content_refresh_loop

                await content_refresh_loop()
            except Exception as e:
                logger.error(f"[CONTENT-REFRESH] Scheduler crashed: {e}")

        asyncio.create_task(start_content_refresh_scheduler())
        logger.info("Content refresh scheduler scheduled (every 24h, 120s delay)")

        # Start daily profile picture refresh (every 24h, delayed 90s)
        async def start_profile_pic_refresh_scheduler():
            await asyncio.sleep(90)  # Wait for DB + other jobs to be ready
            logger.info("[PROFILE_PICS] Scheduler started — runs every 24h")

            while True:
                try:
                    from services.profile_pic_refresh import refresh_profile_pics_job

                    await refresh_profile_pics_job()
                except Exception as e:
                    logger.error(f"[PROFILE_PICS] Scheduler error: {e}")

                await asyncio.sleep(86400)  # 24 hours

        asyncio.create_task(start_profile_pic_refresh_scheduler())
        logger.info("Profile pic refresh scheduler scheduled (every 24h)")

        # Start periodic media capture (capture expiring CDN URLs before they expire)
        async def start_media_capture_scheduler():
            from services.media_capture_job import (
                ENABLE_MEDIA_CAPTURE,
                MEDIA_CAPTURE_INITIAL_DELAY,
                MEDIA_CAPTURE_INTERVAL,
            )

            await asyncio.sleep(MEDIA_CAPTURE_INITIAL_DELAY)
            if not ENABLE_MEDIA_CAPTURE:
                logger.info("[MEDIA_CAPTURE] Disabled via env var")
                return
            logger.info(
                f"[MEDIA_CAPTURE] Scheduler started — runs every "
                f"{MEDIA_CAPTURE_INTERVAL // 3600}h"
            )

            while True:
                try:
                    from services.media_capture_job import media_capture_job

                    await media_capture_job()
                except Exception as e:
                    logger.error(f"[MEDIA_CAPTURE] Scheduler error: {e}")

                await asyncio.sleep(MEDIA_CAPTURE_INTERVAL)

        asyncio.create_task(start_media_capture_scheduler())
        logger.info("Media capture scheduler scheduled (every 6h, 180s delay)")

        # Start periodic post context refresh (refresh expired post contexts)
        async def start_post_context_refresh_scheduler():
            await asyncio.sleep(150)  # Wait for DB + other jobs to be ready
            logger.info("[POST_CONTEXT] Scheduler started — runs every 12h")

            while True:
                try:
                    from services.post_context_scheduler import (
                        refresh_expired_contexts,
                    )

                    stats = await refresh_expired_contexts()
                    logger.info(
                        f"[POST_CONTEXT] Done: {stats['refreshed']} refreshed, "
                        f"{stats['errors']} errors"
                    )
                except Exception as e:
                    logger.error(f"[POST_CONTEXT] Scheduler error: {e}")

                await asyncio.sleep(43200)  # 12 hours

        asyncio.create_task(start_post_context_refresh_scheduler())
        logger.info("Post context refresh scheduler scheduled (every 12h)")

        # JOB 8: Score decay — recalculate lead scores daily so ghost
        # scores drop naturally via the recency component.
        async def start_score_decay_scheduler():
            enable = os.getenv("ENABLE_SCORE_DECAY", "true").lower() == "true"
            await asyncio.sleep(210)
            if not enable:
                logger.info("[SCORE_DECAY] Disabled via ENABLE_SCORE_DECAY=false")
                return
            logger.info("[SCORE_DECAY] Scheduler started — runs every 24h")

            while True:
                try:
                    from api.models import Creator
                    from services.lead_scoring import batch_recalculate_scores

                    session = SessionLocal()
                    try:
                        creators = (
                            session.query(Creator)
                            .filter(Creator.bot_active.is_(True))
                            .all()
                        )
                        total_updated = 0
                        for creator in creators:
                            result = batch_recalculate_scores(session, str(creator.id))
                            total_updated += result.get("updated", 0)
                        logger.info(
                            f"[SCORE_DECAY] Done: {total_updated} leads "
                            f"recalculated across {len(creators)} creators"
                        )
                    finally:
                        session.close()
                except Exception as e:
                    logger.error(f"[SCORE_DECAY] Scheduler error: {e}")

                await asyncio.sleep(86400)  # 24 hours

        asyncio.create_task(start_score_decay_scheduler())
        logger.info("Score decay scheduler scheduled (every 24h, 210s delay)")

        # JOB 9: Cleanup old nurturing followups (sent/cancelled/failed > 30 days)
        async def start_followup_cleanup_scheduler():
            enable = os.getenv("ENABLE_FOLLOWUP_CLEANUP", "true").lower() == "true"
            await asyncio.sleep(240)
            if not enable:
                logger.info("[FOLLOWUP_CLEANUP] Disabled via env var")
                return
            logger.info("[FOLLOWUP_CLEANUP] Scheduler started — runs every 24h")

            while True:
                try:
                    from sqlalchemy import text

                    session = SessionLocal()
                    try:
                        result = session.execute(
                            text(
                                "DELETE FROM nurturing_followups "
                                "WHERE status NOT IN ('pending','scheduled') "
                                "AND created_at < NOW() - INTERVAL '30 days'"
                            )
                        )
                        session.commit()
                        deleted = result.rowcount
                        if deleted > 0:
                            logger.info(f"[FOLLOWUP_CLEANUP] Deleted {deleted} old followups")
                        else:
                            logger.debug("[FOLLOWUP_CLEANUP] Nothing to clean")
                    finally:
                        session.close()
                except Exception as e:
                    logger.error(f"[FOLLOWUP_CLEANUP] Scheduler error: {e}")

                await asyncio.sleep(86400)  # 24 hours

        asyncio.create_task(start_followup_cleanup_scheduler())
        logger.info("Followup cleanup scheduler scheduled (every 24h, 240s delay)")

        # JOB 10: Cleanup old lead_activities (> 90 days)
        async def start_activities_cleanup_scheduler():
            enable = os.getenv("ENABLE_ACTIVITIES_CLEANUP", "true").lower() == "true"
            await asyncio.sleep(270)
            if not enable:
                logger.info("[ACTIVITIES_CLEANUP] Disabled via env var")
                return
            logger.info("[ACTIVITIES_CLEANUP] Scheduler started — runs every 24h")

            while True:
                try:
                    from sqlalchemy import text

                    session = SessionLocal()
                    try:
                        result = session.execute(
                            text(
                                "DELETE FROM lead_activities "
                                "WHERE created_at < NOW() - INTERVAL '90 days'"
                            )
                        )
                        session.commit()
                        deleted = result.rowcount
                        if deleted > 0:
                            logger.info(f"[ACTIVITIES_CLEANUP] Deleted {deleted} old activities")
                        else:
                            logger.debug("[ACTIVITIES_CLEANUP] Nothing to clean")
                    finally:
                        session.close()
                except Exception as e:
                    logger.error(f"[ACTIVITIES_CLEANUP] Scheduler error: {e}")

                await asyncio.sleep(86400)  # 24 hours

        asyncio.create_task(start_activities_cleanup_scheduler())
        logger.info("Activities cleanup scheduler scheduled (every 24h, 270s delay)")

        # JOB 11: Cleanup unmatched_webhooks + sync_queue (> 7 days)
        async def start_queue_cleanup_scheduler():
            enable = os.getenv("ENABLE_QUEUE_CLEANUP", "true").lower() == "true"
            await asyncio.sleep(300)
            if not enable:
                logger.info("[QUEUE_CLEANUP] Disabled via env var")
                return
            logger.info("[QUEUE_CLEANUP] Scheduler started — runs every 24h")

            while True:
                try:
                    from sqlalchemy import text

                    session = SessionLocal()
                    try:
                        r1 = session.execute(
                            text(
                                "DELETE FROM unmatched_webhooks "
                                "WHERE received_at < NOW() - INTERVAL '7 days'"
                            )
                        )
                        r2 = session.execute(
                            text(
                                "DELETE FROM sync_queue "
                                "WHERE created_at < NOW() - INTERVAL '7 days'"
                            )
                        )
                        session.commit()
                        total = r1.rowcount + r2.rowcount
                        if total > 0:
                            logger.info(
                                f"[QUEUE_CLEANUP] Deleted {r1.rowcount} webhooks, "
                                f"{r2.rowcount} sync items"
                            )
                    finally:
                        session.close()
                except Exception as e:
                    logger.error(f"[QUEUE_CLEANUP] Scheduler error: {e}")

                await asyncio.sleep(86400)  # 24 hours

        asyncio.create_task(start_queue_cleanup_scheduler())
        logger.info("Queue cleanup scheduler scheduled (every 24h, 300s delay)")

        # JOB 12: Periodic message reconciliation (separated from nurturing)
        async def start_reconciliation_scheduler():
            enable = os.getenv("ENABLE_RECONCILIATION", "true").lower() == "true"
            await asyncio.sleep(330)
            if not enable:
                logger.info("[RECONCILIATION] Disabled via env var")
                return
            logger.info("[RECONCILIATION] Scheduler started — runs every 30min")

            while True:
                try:
                    from core.message_reconciliation import (
                        run_periodic_reconciliation,
                    )

                    result = await run_periodic_reconciliation()
                    inserted = result.get("total_inserted", 0)
                    if inserted > 0:
                        logger.info(
                            f"[RECONCILIATION] Recovered {inserted} missing messages"
                        )
                except Exception as e:
                    logger.error(f"[RECONCILIATION] Scheduler error: {e}")

                await asyncio.sleep(1800)  # 30 minutes

        asyncio.create_task(start_reconciliation_scheduler())
        logger.info("Reconciliation scheduler scheduled (every 30min, 330s delay)")

        # JOB 13: Enrich leads without profile (fix ig_XXXX leads)
        async def start_lead_enrichment_scheduler():
            enable = os.getenv("ENABLE_LEAD_ENRICHMENT", "true").lower() == "true"
            await asyncio.sleep(360)
            if not enable:
                logger.info("[LEAD_ENRICHMENT] Disabled via env var")
                return
            logger.info("[LEAD_ENRICHMENT] Scheduler started — runs every 6h")

            while True:
                try:
                    from api.models import Creator
                    from core.message_reconciliation import (
                        enrich_leads_without_profile,
                    )

                    session = SessionLocal()
                    try:
                        creators = (
                            session.query(Creator)
                            .filter(
                                Creator.instagram_token.isnot(None),
                                Creator.bot_active.is_(True),
                            )
                            .all()
                        )
                        creator_list = [
                            {"name": c.name, "token": c.instagram_token}
                            for c in creators
                        ]
                    finally:
                        session.close()

                    total_enriched = 0
                    for c in creator_list:
                        result = await enrich_leads_without_profile(
                            c["name"], c["token"], limit=10
                        )
                        total_enriched += result.get("enriched", 0)

                    if total_enriched > 0:
                        logger.info(
                            f"[LEAD_ENRICHMENT] Enriched {total_enriched} profiles"
                        )
                except Exception as e:
                    logger.error(f"[LEAD_ENRICHMENT] Scheduler error: {e}")

                await asyncio.sleep(21600)  # 6 hours

        asyncio.create_task(start_lead_enrichment_scheduler())
        logger.info("Lead enrichment scheduler scheduled (every 6h, 360s delay)")

        # JOB 14: Ghost reactivation (find and schedule re-engagement)
        async def start_ghost_reactivation_scheduler():
            enable = os.getenv("ENABLE_GHOST_REACTIVATION", "true").lower() == "true"
            await asyncio.sleep(390)
            if not enable:
                logger.info("[GHOST_REACTIVATION] Disabled via env var")
                return
            logger.info("[GHOST_REACTIVATION] Scheduler started — runs every 24h")

            while True:
                try:
                    from core.ghost_reactivation import (
                        run_ghost_reactivation_cycle,
                    )

                    result = await run_ghost_reactivation_cycle()
                    scheduled = result.get("total_scheduled", 0)
                    if scheduled > 0:
                        logger.info(
                            f"[GHOST_REACTIVATION] Scheduled {scheduled} re-engagements"
                        )
                except Exception as e:
                    logger.error(f"[GHOST_REACTIVATION] Scheduler error: {e}")

                await asyncio.sleep(86400)  # 24 hours

        asyncio.create_task(start_ghost_reactivation_scheduler())
        logger.info("Ghost reactivation scheduler scheduled (every 24h, 390s delay)")

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

        # Cache refresh task - DISABLED: was blocking event loop
        # async def cache_refresh_task():
        #     REFRESH_INTERVAL = 45  # seconds - less frequent to reduce blocking
        #     await asyncio.sleep(30)  # Wait for initial warmup to complete
        #     logger.info("[CACHE-REFRESH] Started - refreshing every 20s")
        #
        #     while True:
        #         try:
        #             await asyncio.sleep(REFRESH_INTERVAL)
        #             await _do_cache_refresh(SessionLocal)
        #         except Exception as e:
        #             logger.error(f"[CACHE-REFRESH] Error: {e}")
        #
        # asyncio.create_task(cache_refresh_task())
        logger.warning("Cache refresh task DISABLED - was blocking event loop")

        # Keep-alive task - SIMPLIFIED: just DB ping to prevent cold starts
        async def keep_alive_task():
            import time

            KEEP_ALIVE_INTERVAL = 60  # 1 minute - prevent Railway scale-to-zero

            await asyncio.sleep(3)
            logger.info("[KEEP-ALIVE] Started - DB ping every 1 min")

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
        logger.info("Keep-alive task scheduled (every 1 minute)")

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
                    # Set for BOTH endpoints (dm.py and messages.py use different keys)
                    api_cache.set(cache_key, cached_result, ttl_seconds=60)  # messages.py (with offset)
                    api_cache.set(f"conversations:{creator_id}:50", cached_result, ttl_seconds=60)  # dm.py (no offset)
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
