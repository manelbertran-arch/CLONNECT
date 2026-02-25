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

        # =====================================================================
        # Register recurring tasks with centralized TaskScheduler
        # =====================================================================
        from core.task_scheduler import scheduler

        # --- Token refresh (every 6h) ---
        async def _token_refresh_job():
            from api.database import SessionLocal
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

        scheduler.register("token_refresh", _token_refresh_job, interval_seconds=21600, initial_delay_seconds=60)

        # Start daily content refresh scheduler (re-scrape IG posts, chunk, embed)
        async def start_content_refresh_scheduler():
            try:
                from services.content_refresh import content_refresh_loop

                await content_refresh_loop()
            except Exception as e:
                logger.error(f"[CONTENT-REFRESH] Scheduler crashed: {e}")

        asyncio.create_task(start_content_refresh_scheduler())
        logger.info("Content refresh scheduler scheduled (every 24h, 120s delay)")

        # --- Profile pic refresh (every 24h) ---
        async def _profile_pic_refresh_job():
            from services.profile_pic_refresh import refresh_profile_pics_job

            await refresh_profile_pics_job()

        scheduler.register("profile_pic_refresh", _profile_pic_refresh_job, interval_seconds=86400, initial_delay_seconds=90)

        # --- Media capture (every 6h) ---
        from services.media_capture_job import (
            MEDIA_CAPTURE_INITIAL_DELAY,
            MEDIA_CAPTURE_INTERVAL,
        )

        async def _media_capture_job():
            from services.media_capture_job import ENABLE_MEDIA_CAPTURE, media_capture_job

            if not ENABLE_MEDIA_CAPTURE:
                logger.debug("[MEDIA_CAPTURE] Disabled via env var, skipping")
                return
            await media_capture_job()

        scheduler.register("media_capture", _media_capture_job, interval_seconds=MEDIA_CAPTURE_INTERVAL, initial_delay_seconds=MEDIA_CAPTURE_INITIAL_DELAY)

        # --- Post context refresh (every 12h) ---
        async def _post_context_refresh_job():
            from services.post_context_scheduler import refresh_expired_contexts

            stats = await refresh_expired_contexts()
            logger.info(
                f"[POST_CONTEXT] Done: {stats['refreshed']} refreshed, "
                f"{stats['errors']} errors"
            )

        scheduler.register("post_context_refresh", _post_context_refresh_job, interval_seconds=43200, initial_delay_seconds=150)

        # --- Score decay (every 24h) ---
        async def _score_decay_job():
            if os.getenv("ENABLE_SCORE_DECAY", "true").lower() != "true":
                logger.debug("[SCORE_DECAY] Disabled via ENABLE_SCORE_DECAY=false")
                return
            from api.database import SessionLocal
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
                    result = await asyncio.to_thread(batch_recalculate_scores, session, str(creator.id))
                    total_updated += result.get("updated", 0)
                logger.info(
                    f"[SCORE_DECAY] Done: {total_updated} leads "
                    f"recalculated across {len(creators)} creators"
                )
            finally:
                session.close()

        scheduler.register("score_decay", _score_decay_job, interval_seconds=86400, initial_delay_seconds=210)

        # --- Followup cleanup (every 24h) ---
        async def _followup_cleanup_job():
            if os.getenv("ENABLE_FOLLOWUP_CLEANUP", "true").lower() != "true":
                logger.debug("[FOLLOWUP_CLEANUP] Disabled via env var")
                return
            from api.database import SessionLocal
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

        scheduler.register("followup_cleanup", _followup_cleanup_job, interval_seconds=86400, initial_delay_seconds=240)

        # --- Activities cleanup (every 24h) ---
        async def _activities_cleanup_job():
            if os.getenv("ENABLE_ACTIVITIES_CLEANUP", "true").lower() != "true":
                logger.debug("[ACTIVITIES_CLEANUP] Disabled via env var")
                return
            from api.database import SessionLocal
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

        scheduler.register("activities_cleanup", _activities_cleanup_job, interval_seconds=86400, initial_delay_seconds=270)

        # JOB 11: Cleanup unmatched_webhooks + sync_queue (> 7 days)
        async def _queue_cleanup_job():
            enable = os.getenv("ENABLE_QUEUE_CLEANUP", "true").lower() == "true"
            if not enable:
                logger.debug("[QUEUE_CLEANUP] Disabled via env var, skipping")
                return
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

        scheduler.register("queue_cleanup", _queue_cleanup_job, interval_seconds=86400, initial_delay_seconds=300)

        # JOB 12: Periodic message reconciliation (separated from nurturing)
        async def _reconciliation_job():
            enable = os.getenv("ENABLE_RECONCILIATION", "true").lower() == "true"
            if not enable:
                logger.debug("[RECONCILIATION] Disabled via env var, skipping")
                return
            from core.message_reconciliation import (
                run_periodic_reconciliation,
            )

            result = await run_periodic_reconciliation()
            inserted = result.get("total_inserted", 0)
            if inserted > 0:
                logger.info(
                    f"[RECONCILIATION] Recovered {inserted} missing messages"
                )

        scheduler.register("reconciliation", _reconciliation_job, interval_seconds=1800, initial_delay_seconds=330)

        # JOB 13: Enrich leads without profile (fix ig_XXXX leads)
        async def _lead_enrichment_job():
            enable = os.getenv("ENABLE_LEAD_ENRICHMENT", "true").lower() == "true"
            if not enable:
                logger.debug("[LEAD_ENRICHMENT] Disabled via env var, skipping")
                return
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

        scheduler.register("lead_enrichment", _lead_enrichment_job, interval_seconds=21600, initial_delay_seconds=360)

        # JOB 14: Ghost reactivation (find and schedule re-engagement)
        async def _ghost_reactivation_job():
            enable = os.getenv("ENABLE_GHOST_REACTIVATION", "true").lower() == "true"
            if not enable:
                logger.debug("[GHOST_REACTIVATION] Disabled via env var, skipping")
                return
            from core.ghost_reactivation import (
                run_ghost_reactivation_cycle,
            )

            result = await run_ghost_reactivation_cycle()
            scheduled = result.get("total_scheduled", 0)
            if scheduled > 0:
                logger.info(
                    f"[GHOST_REACTIVATION] Scheduled {scheduled} re-engagements"
                )

        scheduler.register("ghost_reactivation", _ghost_reactivation_job, interval_seconds=86400, initial_delay_seconds=390)

        # JOB 15: Copilot daily evaluation (autolearning)
        async def _copilot_daily_eval_job():
            enable = os.getenv("ENABLE_COPILOT_EVAL", "true").lower() == "true"
            if not enable:
                logger.debug("[COPILOT_EVAL] Disabled via env var, skipping")
                return
            from api.models import Creator
            from core.autolearning_evaluator import run_daily_evaluation

            session = SessionLocal()
            try:
                creators = (
                    session.query(Creator.id, Creator.name)
                    .filter(Creator.bot_active.is_(True))
                    .all()
                )
                results = []
                for creator_db_id, creator_name in creators:
                    result = await run_daily_evaluation(creator_name, creator_db_id)
                    if result.get("stored"):
                        results.append(creator_name)
                if results:
                    logger.info(
                        f"[COPILOT_EVAL] Daily evals stored for: {', '.join(results)}"
                    )
            finally:
                session.close()

        scheduler.register("copilot_daily_eval", _copilot_daily_eval_job, interval_seconds=86400, initial_delay_seconds=420)

        # JOB 16: Copilot weekly recalibration (autolearning)
        async def _copilot_weekly_recal_job():
            enable = os.getenv("ENABLE_COPILOT_RECAL", "true").lower() == "true"
            if not enable:
                logger.debug("[COPILOT_RECAL] Disabled via env var, skipping")
                return
            from api.models import Creator
            from core.autolearning_evaluator import run_weekly_recalibration

            session = SessionLocal()
            try:
                creators = (
                    session.query(Creator.id, Creator.name)
                    .filter(Creator.bot_active.is_(True))
                    .all()
                )
                results = []
                for creator_db_id, creator_name in creators:
                    result = await run_weekly_recalibration(creator_name, creator_db_id)
                    if result.get("stored"):
                        results.append(creator_name)
                if results:
                    logger.info(
                        f"[COPILOT_RECAL] Weekly recalibration stored for: {', '.join(results)}"
                    )
            finally:
                session.close()

        scheduler.register("copilot_weekly_recal", _copilot_weekly_recal_job, interval_seconds=604800, initial_delay_seconds=450)

        # JOB 18: Learning rule consolidation (24h, 510s delay, ENABLE_LEARNING_CONSOLIDATION)
        async def _learning_consolidation_job():
            enable = os.getenv("ENABLE_LEARNING_CONSOLIDATION", "false").lower() == "true"
            if not enable:
                logger.debug("[LEARNING_CONSOLIDATION] Disabled via env var, skipping")
                return
            from api.models import Creator
            from services.learning_consolidator import consolidate_rules_for_creator

            session = SessionLocal()
            try:
                creators = (
                    session.query(Creator.id, Creator.name)
                    .filter(Creator.bot_active.is_(True))
                    .all()
                )
                for creator_db_id, creator_name in creators:
                    try:
                        result = await consolidate_rules_for_creator(
                            creator_name, creator_db_id
                        )
                        if result.get("status") == "done":
                            logger.info(
                                f"[LEARNING_CONSOLIDATION] {creator_name}: "
                                f"consolidated={result.get('consolidated', 0)} "
                                f"deactivated={result.get('deactivated', 0)}"
                            )
                    except Exception as creator_err:
                        logger.error(
                            f"[LEARNING_CONSOLIDATION] Error for {creator_name}: {creator_err}"
                        )
            finally:
                session.close()

        scheduler.register("learning_consolidation", _learning_consolidation_job, interval_seconds=86400, initial_delay_seconds=510)

        # JOB 19: Pattern analyzer — batch LLM-as-Judge (12h, 540s delay, ENABLE_PATTERN_ANALYZER)
        async def _pattern_analyzer_job():
            enable = os.getenv("ENABLE_PATTERN_ANALYZER", "false").lower() == "true"
            if not enable:
                logger.debug("[PATTERN_ANALYZER] Disabled via env var, skipping")
                return
            from services.pattern_analyzer import run_pattern_analysis_all

            results = await run_pattern_analysis_all()
            for creator_name, result in results.items():
                if result.get("status") == "done":
                    logger.info(
                        f"[PATTERN_ANALYZER] {creator_name}: "
                        f"pairs={result.get('pairs_analyzed', 0)} "
                        f"rules={result.get('rules_created', 0)}"
                    )

        scheduler.register("pattern_analyzer", _pattern_analyzer_job, interval_seconds=43200, initial_delay_seconds=540)

        # JOB 20: Gold examples curation + preference pairs + preference profile (12h, 570s delay)
        async def _gold_examples_job():
            enable_gold = os.getenv("ENABLE_GOLD_EXAMPLES", "false").lower() == "true"
            enable_profile = os.getenv("ENABLE_PREFERENCE_PROFILE", "false").lower() == "true"
            enable_pairs = os.getenv("ENABLE_PREFERENCE_PAIRS", "true").lower() == "true"
            if not enable_gold and not enable_profile and not enable_pairs:
                logger.debug("[GOLD_EXAMPLES] All sub-tasks disabled, skipping")
                return
            from api.models import Creator

            session = SessionLocal()
            try:
                creators = (
                    session.query(Creator.id, Creator.name)
                    .filter(Creator.bot_active.is_(True))
                    .all()
                )
            finally:
                session.close()

            for creator_db_id, creator_name in creators:
                try:
                    if enable_gold:
                        from services.gold_examples_service import curate_examples
                        result = await curate_examples(creator_name, creator_db_id)
                        if result.get("status") == "done":
                            logger.info(
                                f"[GOLD_EXAMPLES] {creator_name}: "
                                f"created={result.get('created', 0)} "
                                f"expired={result.get('expired', 0)}"
                            )
                    if enable_pairs:
                        from services.preference_pairs_service import curate_pairs
                        pairs_result = await curate_pairs(creator_name, creator_db_id)
                        if pairs_result.get("historical_created", 0) > 0:
                            logger.info(
                                f"[PREF_PAIRS] {creator_name}: "
                                f"historical_created={pairs_result.get('historical_created', 0)}"
                            )
                except Exception as creator_err:
                    logger.error(f"[GOLD_EXAMPLES] Error for {creator_name}: {creator_err}")

        scheduler.register("gold_examples", _gold_examples_job, interval_seconds=43200, initial_delay_seconds=570)

        # JOB 21: CloneScore daily evaluation (24h, 600s delay, ENABLE_CLONE_SCORE_EVAL)
        async def _clone_score_daily_job():
            enable = os.getenv("ENABLE_CLONE_SCORE_EVAL", "false").lower() == "true"
            if not enable:
                logger.debug("[CLONE_SCORE] Disabled via ENABLE_CLONE_SCORE_EVAL, skipping")
                return
            from api.models import Creator
            from services.clone_score_engine import get_clone_score_engine

            session = SessionLocal()
            try:
                creators = (
                    session.query(Creator.id, Creator.name)
                    .filter(Creator.bot_active.is_(True))
                    .all()
                )
            finally:
                session.close()

            engine = get_clone_score_engine()
            for creator_db_id, creator_name in creators:
                try:
                    result = await engine.evaluate_batch(
                        creator_id=creator_name,
                        creator_db_id=creator_db_id,
                        sample_size=50,
                    )
                    if result.get("overall_score"):
                        logger.info(
                            f"[CLONE_SCORE] {creator_name}: "
                            f"{result['overall_score']:.1f}"
                        )
                except Exception as e:
                    logger.error(
                        f"[CLONE_SCORE] Error for {creator_name}: {e}"
                    )
                await asyncio.sleep(30)

        scheduler.register("clone_score_daily", _clone_score_daily_job, interval_seconds=86400, initial_delay_seconds=600)

        # JOB 22: Memory decay — Ebbinghaus eviction of stale lead memories (24h, 630s delay)
        async def _memory_decay_job():
            enable = os.getenv("ENABLE_MEMORY_DECAY", "false").lower() == "true"
            if not enable:
                logger.debug("[MEMORY-DECAY] Disabled via ENABLE_MEMORY_DECAY, skipping")
                return
            from services.memory_engine import get_memory_engine
            from sqlalchemy import text

            engine = get_memory_engine()
            session = SessionLocal()
            try:
                rows = session.execute(
                    text("SELECT id FROM creators WHERE bot_active = true")
                ).fetchall()
                creator_ids = [str(r[0]) for r in rows]
            finally:
                session.close()

            total_deactivated = 0
            for cid in creator_ids:
                try:
                    count = await engine.decay_memories(cid)
                    total_deactivated += count
                except Exception as decay_err:
                    logger.error(
                        "[MEMORY-DECAY] Failed for creator %s: %s",
                        cid[:8], decay_err,
                    )

            logger.info(
                "[MEMORY-DECAY] Processed %d creators, deactivated %d memories",
                len(creator_ids),
                total_deactivated,
            )

        scheduler.register("memory_decay", _memory_decay_job, interval_seconds=86400, initial_delay_seconds=630)

        # JOB 23: Commitment cleanup — expire overdue commitments (24h, 660s delay)
        async def _commitment_cleanup_job():
            enable = os.getenv("ENABLE_COMMITMENT_CLEANUP", "true").lower() == "true"
            if not enable:
                logger.debug("[COMMITMENT_CLEANUP] Disabled via env var, skipping")
                return
            from api.models import Creator
            from services.commitment_tracker import get_commitment_tracker

            tracker = get_commitment_tracker()
            session = SessionLocal()
            try:
                creators = (
                    session.query(Creator.id, Creator.name)
                    .filter(Creator.bot_active.is_(True))
                    .all()
                )
            finally:
                session.close()

            total_expired = 0
            for creator_db_id, creator_name in creators:
                try:
                    expired = await asyncio.to_thread(tracker.expire_overdue, creator_name)
                    total_expired += expired
                except Exception as creator_err:
                    logger.error(
                        f"[COMMITMENT_CLEANUP] Error for {creator_name}: {creator_err}"
                    )

            if total_expired > 0:
                logger.info(
                    f"[COMMITMENT_CLEANUP] Expired {total_expired} overdue "
                    f"commitments across {len(creators)} creators"
                )

        scheduler.register("commitment_cleanup", _commitment_cleanup_job, interval_seconds=86400, initial_delay_seconds=660)

        # JOB 24: Style recalculation — re-analyze StyleProfile (30 days, 690s delay)
        async def _style_recalc_job():
            enable = os.getenv("ENABLE_STYLE_RECALC", "true").lower() == "true"
            if not enable:
                logger.debug("[STYLE_RECALC] Disabled via ENABLE_STYLE_RECALC, skipping")
                return
            from api.models import Creator
            from core.style_analyzer import analyze_and_persist

            session = SessionLocal()
            try:
                creators = (
                    session.query(Creator.id, Creator.name)
                    .filter(Creator.bot_active.is_(True))
                    .all()
                )
            finally:
                session.close()

            for creator_db_id, creator_name in creators:
                try:
                    result = await analyze_and_persist(
                        creator_name, str(creator_db_id), force=True
                    )
                    if result:
                        logger.info(
                            f"[STYLE_RECALC] {creator_name}: "
                            f"confidence={result.get('confidence', 0)}"
                        )
                except Exception as creator_err:
                    logger.error(
                        f"[STYLE_RECALC] Error for {creator_name}: {creator_err}"
                    )
                await asyncio.sleep(60)  # Stagger between creators

        scheduler.register("style_recalc", _style_recalc_job, interval_seconds=2592000, initial_delay_seconds=690)

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
        from api.startup.cache import _do_prewarm

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

        # Keep-alive task - DB ping to keep connection pool alive
        # NOTE: Cache warming is done at startup (_do_prewarm) + naturally by
        # frontend polling (refetchInterval=30s). Keep-alive must NOT call
        # get_conversations() — it uses synchronous DB calls that block the event loop.
        async def _keep_alive_job():
            import time

            _t_start = time.time()

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

        scheduler.register("keep_alive", _keep_alive_job, interval_seconds=60, initial_delay_seconds=3)

        # =====================================================================
        # Job 15: Evolution API health check (WhatsApp 401 monitoring)
        # =====================================================================
        _evolution_last_state = {}  # instance -> "ok" | "error"

        async def _evolution_health_check_job():
            enable = os.getenv("ENABLE_EVOLUTION_HEALTH_CHECK", "true").lower() == "true"
            if not enable:
                logger.debug("[EVOLUTION_HEALTH] Disabled via env var, skipping")
                return
            from api.routers.messaging_webhooks import (
                EVOLUTION_INSTANCE_MAP,
            )
            from services.evolution_api import (
                EVOLUTION_API_URL,
                get_instance_status,
            )

            if not EVOLUTION_API_URL:
                return

            for instance, creator_id in EVOLUTION_INSTANCE_MAP.items():
                try:
                    status = await get_instance_status(instance)
                    state = (
                        status.get("instance", {}).get("state", "unknown")
                    )

                    if state == "open":
                        if _evolution_last_state.get(instance) == "error":
                            logger.info(
                                f"[EVOLUTION_HEALTH] {instance} reconnected"
                            )
                        _evolution_last_state[instance] = "ok"
                    else:
                        logger.warning(
                            f"[EVOLUTION_HEALTH] {instance} state={state}"
                        )
                        if _evolution_last_state.get(instance) != "error":
                            _evolution_last_state[instance] = "error"
                            try:
                                from core.alerts import get_alert_manager

                                mgr = get_alert_manager()
                                await mgr.critical(
                                    title="Evolution API Disconnected",
                                    message=(
                                        f"Instance {instance} state={state}. "
                                        f"WhatsApp messages may be lost."
                                    ),
                                    creator_id=creator_id,
                                    metadata={
                                        "instance": instance,
                                        "state": state,
                                    },
                                )
                            except Exception as alert_err:
                                logger.error(
                                    f"[EVOLUTION_HEALTH] Alert failed: {alert_err}"
                                )

                except Exception as inst_err:
                    err_str = str(inst_err)
                    is_401 = "401" in err_str or "Unauthorized" in err_str
                    logger.error(
                        f"[EVOLUTION_HEALTH] {instance} check failed: {inst_err}"
                    )
                    if _evolution_last_state.get(instance) != "error":
                        _evolution_last_state[instance] = "error"
                        try:
                            from core.alerts import get_alert_manager

                            mgr = get_alert_manager()
                            await mgr.critical(
                                title=(
                                    "Evolution API 401 Unauthorized"
                                    if is_401
                                    else "Evolution API Error"
                                ),
                                message=(
                                    f"Instance {instance}: {err_str[:200]}. "
                                    f"Check EVOLUTION_API_KEY."
                                ),
                                creator_id=creator_id,
                                metadata={
                                    "instance": instance,
                                    "error": err_str[:200],
                                    "is_401": is_401,
                                },
                            )
                        except Exception as alert_err:
                            logger.error(
                                f"[EVOLUTION_HEALTH] Alert failed: {alert_err}"
                            )

        scheduler.register("evolution_health_check", _evolution_health_check_job, interval_seconds=300, initial_delay_seconds=420)

        # Job 16: Auto-expire stale pending_approval messages (>24h)
        async def _pending_expiry_job():
            enable = os.getenv("ENABLE_PENDING_EXPIRY", "true").lower() == "true"
            if not enable:
                logger.debug("[A15] Pending expiry disabled via env var, skipping")
                return
            from api.database import SessionLocal as _SL16
            from sqlalchemy import text

            session = _SL16()
            try:
                result = session.execute(
                    text(
                        """
                        UPDATE messages
                        SET status = 'expired',
                            msg_metadata = COALESCE(msg_metadata, '{}'::jsonb)
                                || '{"expired_reason": "auto_24h"}'::jsonb
                        WHERE status = 'pending_approval'
                        AND created_at < NOW() - INTERVAL '24 hours'
                        """
                    )
                )
                count = result.rowcount
                session.commit()
                if count > 0:
                    logger.info(
                        f"[A15] Auto-expired {count} stale pending_approval messages (>24h)"
                    )
            finally:
                session.close()

        scheduler.register("pending_expiry", _pending_expiry_job, interval_seconds=3600, initial_delay_seconds=450)

        # Job 17: Instagram token expiry warning (daily)
        async def _token_expiry_check_job():
            enable = os.getenv("ENABLE_TOKEN_EXPIRY_CHECK", "true").lower() == "true"
            if not enable:
                logger.debug("[B11] Token expiry check disabled via env var, skipping")
                return
            from datetime import datetime, timedelta, timezone

            from api.database import SessionLocal as _SL17
            from api.models import Creator

            session = _SL17()
            try:
                creators = (
                    session.query(Creator)
                    .filter(
                        Creator.instagram_token.isnot(None),
                        Creator.instagram_token_expires_at.isnot(None),
                        Creator.bot_active.is_(True),
                    )
                    .all()
                )
                now = datetime.now(timezone.utc)
                for c in creators:
                    expires = c.instagram_token_expires_at
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    days_left = (expires - now).days
                    if days_left <= 0:
                        from core.alerts import get_alert_manager

                        mgr = get_alert_manager()
                        await mgr.critical(
                            title=f"Token IG EXPIRADO: {c.name}",
                            message=f"El token de Instagram de {c.name} ha expirado. Bot detenido.",
                            source="token_expiry_check",
                        )
                    elif days_left <= 3:
                        from core.alerts import get_alert_manager

                        mgr = get_alert_manager()
                        await mgr.critical(
                            title=f"URGENTE: Token IG de {c.name} expira en {days_left} dias",
                            message=f"El token de Instagram de {c.name} expira en {days_left} dias. Renovar ASAP.",
                            source="token_expiry_check",
                        )
                    elif days_left <= 14:
                        from core.alerts import get_alert_manager

                        mgr = get_alert_manager()
                        await mgr.warning(
                            title=f"Token IG de {c.name} expira en {days_left} dias",
                            message=f"Token de Instagram de {c.name} expira el {expires.strftime('%Y-%m-%d')}. Planificar renovacion.",
                            source="token_expiry_check",
                        )
                        logger.info(
                            f"[B11] Token expiry warning: {c.name} expires in {days_left} days"
                        )
            finally:
                session.close()

        scheduler.register("token_expiry_check", _token_expiry_check_job, interval_seconds=86400, initial_delay_seconds=480)

        # Message retry worker
        async def _message_retry_job():
            from services.message_retry_service import process_retry_queue
            await process_retry_queue()

        scheduler.register("message_retry", _message_retry_job, interval_seconds=60, initial_delay_seconds=60)

        # Start all registered scheduled tasks
        await scheduler.start_all()

        logger.info("Ready to receive requests!")

    @app.on_event("shutdown")
    async def shutdown_event():
        from core.task_scheduler import scheduler
        await scheduler.shutdown()
