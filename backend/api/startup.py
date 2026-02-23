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

        # JOB 15: Copilot daily evaluation (autolearning)
        async def start_copilot_daily_eval_scheduler():
            enable = os.getenv("ENABLE_COPILOT_EVAL", "true").lower() == "true"
            await asyncio.sleep(420)
            if not enable:
                logger.info("[COPILOT_EVAL] Disabled via env var")
                return
            logger.info("[COPILOT_EVAL] Daily evaluation scheduler started — runs every 24h")

            while True:
                try:
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
                except Exception as e:
                    logger.error(f"[COPILOT_EVAL] Daily scheduler error: {e}")

                await asyncio.sleep(86400)  # 24 hours

        asyncio.create_task(start_copilot_daily_eval_scheduler())
        logger.info("Copilot daily eval scheduler scheduled (every 24h, 420s delay)")

        # JOB 16: Copilot weekly recalibration (autolearning)
        async def start_copilot_weekly_recal_scheduler():
            enable = os.getenv("ENABLE_COPILOT_RECAL", "true").lower() == "true"
            await asyncio.sleep(450)
            if not enable:
                logger.info("[COPILOT_RECAL] Disabled via env var")
                return
            logger.info("[COPILOT_RECAL] Weekly recalibration scheduler started — runs every 7d")

            while True:
                try:
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
                except Exception as e:
                    logger.error(f"[COPILOT_RECAL] Weekly scheduler error: {e}")

                await asyncio.sleep(604800)  # 7 days

        asyncio.create_task(start_copilot_weekly_recal_scheduler())
        logger.info("Copilot weekly recalibration scheduler scheduled (every 7d, 450s delay)")

        # JOB 18: Learning rule consolidation (24h, 510s delay, ENABLE_LEARNING_CONSOLIDATION)
        async def start_learning_consolidation_scheduler():
            enable = os.getenv("ENABLE_LEARNING_CONSOLIDATION", "false").lower() == "true"
            await asyncio.sleep(510)
            if not enable:
                logger.info("[LEARNING_CONSOLIDATION] Disabled via env var")
                return
            logger.info("[LEARNING_CONSOLIDATION] Scheduler started — runs every 24h")

            while True:
                try:
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
                except Exception as e:
                    logger.error(f"[LEARNING_CONSOLIDATION] Scheduler error: {e}")

                await asyncio.sleep(86400)  # 24 hours

        asyncio.create_task(start_learning_consolidation_scheduler())
        logger.info("Learning consolidation scheduler scheduled (every 24h, 510s delay)")

        # JOB 19: Pattern analyzer — batch LLM-as-Judge (12h, 540s delay, ENABLE_PATTERN_ANALYZER)
        async def start_pattern_analyzer_scheduler():
            enable = os.getenv("ENABLE_PATTERN_ANALYZER", "false").lower() == "true"
            await asyncio.sleep(540)
            if not enable:
                logger.info("[PATTERN_ANALYZER] Disabled via env var")
                return
            logger.info("[PATTERN_ANALYZER] Scheduler started — runs every 12h")

            while True:
                try:
                    from services.pattern_analyzer import run_pattern_analysis_all

                    results = await run_pattern_analysis_all()
                    for creator_name, result in results.items():
                        if result.get("status") == "done":
                            logger.info(
                                f"[PATTERN_ANALYZER] {creator_name}: "
                                f"pairs={result.get('pairs_analyzed', 0)} "
                                f"rules={result.get('rules_created', 0)}"
                            )
                except Exception as e:
                    logger.error(f"[PATTERN_ANALYZER] Scheduler error: {e}")

                await asyncio.sleep(43200)  # 12 hours

        asyncio.create_task(start_pattern_analyzer_scheduler())
        logger.info("Pattern analyzer scheduler scheduled (every 12h, 540s delay)")

        # JOB 20: Gold examples curation + preference pairs + preference profile (12h, 570s delay)
        async def start_gold_examples_scheduler():
            enable_gold = os.getenv("ENABLE_GOLD_EXAMPLES", "false").lower() == "true"
            enable_profile = os.getenv("ENABLE_PREFERENCE_PROFILE", "false").lower() == "true"
            enable_pairs = os.getenv("ENABLE_PREFERENCE_PAIRS", "true").lower() == "true"
            await asyncio.sleep(570)
            if not enable_gold and not enable_profile and not enable_pairs:
                logger.info("[GOLD_EXAMPLES] Gold examples, preference pairs and preference profile all disabled")
                return
            logger.info("[GOLD_EXAMPLES] Scheduler started — runs every 12h")

            while True:
                try:
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

                except Exception as e:
                    logger.error(f"[GOLD_EXAMPLES] Scheduler error: {e}")

                await asyncio.sleep(43200)  # 12 hours

        asyncio.create_task(start_gold_examples_scheduler())
        logger.info("Gold examples + preference pairs scheduler scheduled (every 12h, 570s delay)")

        # JOB 21: CloneScore daily evaluation (24h, 600s delay, ENABLE_CLONE_SCORE_EVAL)
        async def start_clone_score_daily_scheduler():
            enable = os.getenv("ENABLE_CLONE_SCORE_EVAL", "false").lower() == "true"
            await asyncio.sleep(600)
            if not enable:
                logger.info("[CLONE_SCORE] Disabled via ENABLE_CLONE_SCORE_EVAL")
                return
            logger.info("[CLONE_SCORE] Daily scheduler started — runs every 24h")

            while True:
                try:
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

                except Exception as e:
                    logger.error(f"[CLONE_SCORE] Daily scheduler error: {e}")

                await asyncio.sleep(86400)  # 24 hours

        asyncio.create_task(start_clone_score_daily_scheduler())
        logger.info("CloneScore daily eval scheduler scheduled (every 24h, 600s delay, ENABLE_CLONE_SCORE_EVAL)")

        # JOB 22: Memory decay — Ebbinghaus eviction of stale lead memories (24h, 630s delay)
        async def start_memory_decay_scheduler():
            enable = os.getenv("ENABLE_MEMORY_DECAY", "false").lower() == "true"
            await asyncio.sleep(630)
            if not enable:
                logger.info("[MEMORY-DECAY] Disabled via ENABLE_MEMORY_DECAY")
                return
            logger.info("[MEMORY-DECAY] Scheduler started — runs every 24h")

            while True:
                try:
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
                except Exception as e:
                    logger.error("[MEMORY-DECAY] Job failed: %s", e)

                await asyncio.sleep(86400)  # 24 hours

        asyncio.create_task(start_memory_decay_scheduler())
        logger.info("Memory decay scheduler scheduled (every 24h, 630s delay)")

        # JOB 23: Commitment cleanup — expire overdue commitments (24h, 660s delay)
        async def start_commitment_cleanup_scheduler():
            enable = os.getenv("ENABLE_COMMITMENT_CLEANUP", "true").lower() == "true"
            await asyncio.sleep(660)
            if not enable:
                logger.info("[COMMITMENT_CLEANUP] Disabled via ENABLE_COMMITMENT_CLEANUP")
                return
            logger.info("[COMMITMENT_CLEANUP] Scheduler started — runs every 24h")

            while True:
                try:
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
                            expired = tracker.expire_overdue(creator_name)
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
                except Exception as e:
                    logger.error(f"[COMMITMENT_CLEANUP] Scheduler error: {e}")

                await asyncio.sleep(86400)  # 24 hours

        asyncio.create_task(start_commitment_cleanup_scheduler())
        logger.info("Commitment cleanup scheduler scheduled (every 24h, 660s delay)")

        # JOB 24: Style recalculation — re-analyze StyleProfile (30 days, 690s delay)
        async def start_style_recalc_scheduler():
            enable = os.getenv("ENABLE_STYLE_RECALC", "true").lower() == "true"
            await asyncio.sleep(690)
            if not enable:
                logger.info("[STYLE_RECALC] Disabled via ENABLE_STYLE_RECALC")
                return
            logger.info("[STYLE_RECALC] Scheduler started — runs every 30 days")

            while True:
                try:
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
                except Exception as e:
                    logger.error(f"[STYLE_RECALC] Scheduler error: {e}")

                await asyncio.sleep(2592000)  # 30 days

        asyncio.create_task(start_style_recalc_scheduler())
        logger.info("Style recalculation scheduler scheduled (every 30d, 690s delay)")

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

        # Keep-alive task - DB ping to keep connection pool alive
        # NOTE: Cache warming is done at startup (_do_prewarm) + naturally by
        # frontend polling (refetchInterval=30s). Keep-alive must NOT call
        # get_conversations() — it uses synchronous DB calls that block the event loop.
        async def keep_alive_task():
            import time

            KEEP_ALIVE_INTERVAL = 60  # 1 minute - prevent Railway scale-to-zero

            await asyncio.sleep(3)
            logger.info("[KEEP-ALIVE] Started - DB ping every 1 min")

            while True:
                try:
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

                except Exception as e:
                    logger.error(f"[KEEP-ALIVE] Error: {e}")

                await asyncio.sleep(KEEP_ALIVE_INTERVAL)

        asyncio.create_task(keep_alive_task())
        logger.info("Keep-alive task scheduled (every 1 minute)")

        # =====================================================================
        # Job 15: Evolution API health check (WhatsApp 401 monitoring)
        # =====================================================================
        enable_evolution_check = os.getenv(
            "ENABLE_EVOLUTION_HEALTH_CHECK", "true"
        ).lower() == "true"

        if enable_evolution_check:
            async def start_evolution_health_check():
                await asyncio.sleep(420)  # 7 min after boot
                logger.info("[EVOLUTION_HEALTH] Started — checks every 5 min")

                last_state = {}  # instance -> "ok" | "error"

                while True:
                    try:
                        from api.routers.messaging_webhooks import (
                            EVOLUTION_INSTANCE_MAP,
                        )
                        from services.evolution_api import (
                            EVOLUTION_API_URL,
                            get_instance_status,
                        )

                        if not EVOLUTION_API_URL:
                            await asyncio.sleep(300)
                            continue

                        for instance, creator_id in EVOLUTION_INSTANCE_MAP.items():
                            try:
                                status = await get_instance_status(instance)
                                state = (
                                    status.get("instance", {}).get("state", "unknown")
                                )

                                if state == "open":
                                    if last_state.get(instance) == "error":
                                        logger.info(
                                            f"[EVOLUTION_HEALTH] {instance} reconnected"
                                        )
                                    last_state[instance] = "ok"
                                else:
                                    logger.warning(
                                        f"[EVOLUTION_HEALTH] {instance} state={state}"
                                    )
                                    if last_state.get(instance) != "error":
                                        last_state[instance] = "error"
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
                                if last_state.get(instance) != "error":
                                    last_state[instance] = "error"
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

                    except Exception as e:
                        logger.error(f"[EVOLUTION_HEALTH] Scheduler error: {e}")

                    await asyncio.sleep(300)  # 5 minutes

            asyncio.create_task(start_evolution_health_check())
            logger.info(
                "Evolution API health check scheduled (every 5min, 420s delay)"
            )

        # Job 16: Auto-expire stale pending_approval messages (>24h)
        enable_pending_expiry = os.getenv(
            "ENABLE_PENDING_EXPIRY", "true"
        ).lower() == "true"
        if enable_pending_expiry:

            async def start_pending_expiry_job():
                await asyncio.sleep(450)  # 7.5 min after boot
                while True:
                    try:
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
                    except Exception as e:
                        logger.error(f"[A15] Pending expiry error: {e}")
                    await asyncio.sleep(3600)  # 1 hour

            asyncio.create_task(start_pending_expiry_job())
            logger.info(
                "Pending approval expiry job scheduled (every 1h, 450s delay)"
            )

        # Job 17: Instagram token expiry warning (daily)
        enable_token_expiry_check = os.getenv(
            "ENABLE_TOKEN_EXPIRY_CHECK", "true"
        ).lower() == "true"
        if enable_token_expiry_check:

            async def start_token_expiry_check():
                await asyncio.sleep(480)  # 8 min after boot
                while True:
                    try:
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
                    except Exception as e:
                        logger.error(f"[B11] Token expiry check error: {e}")
                    await asyncio.sleep(86400)  # 24 hours

            asyncio.create_task(start_token_expiry_check())
            logger.info(
                "Instagram token expiry check scheduled (daily, 480s delay)"
            )

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
