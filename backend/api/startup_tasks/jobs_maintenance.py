"""
Maintenance scheduled jobs — token refresh, content refresh, profile pics,
media capture, post context, score decay, cleanup tasks, reconciliation,
lead enrichment, ghost reactivation.
"""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


# --- Token refresh (every 6h) ---
async def token_refresh_job():
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


# --- Content refresh scheduler ---
async def content_refresh_scheduler():
    try:
        from services.content_refresh import content_refresh_loop

        await content_refresh_loop()
    except Exception as e:
        logger.error(f"[CONTENT-REFRESH] Scheduler crashed: {e}")


# --- Profile pic refresh (every 24h) ---
async def profile_pic_refresh_job():
    from services.profile_pic_refresh import refresh_profile_pics_job

    await refresh_profile_pics_job()


# --- Media capture (every 6h) ---
async def media_capture_job():
    from services.media_capture_job import ENABLE_MEDIA_CAPTURE, media_capture_job

    if not ENABLE_MEDIA_CAPTURE:
        logger.debug("[MEDIA_CAPTURE] Disabled via env var, skipping")
        return
    await media_capture_job()


# --- Post context refresh (every 12h) ---
async def post_context_refresh_job():
    from services.post_context_scheduler import refresh_expired_contexts

    stats = await refresh_expired_contexts()
    logger.info(
        f"[POST_CONTEXT] Done: {stats['refreshed']} refreshed, "
        f"{stats['errors']} errors"
    )


# --- Score decay (every 24h) ---
async def score_decay_job():
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
            result = batch_recalculate_scores(session, str(creator.id))
            total_updated += result.get("updated", 0)
        logger.info(
            f"[SCORE_DECAY] Done: {total_updated} leads "
            f"recalculated across {len(creators)} creators"
        )
    finally:
        session.close()


# --- Followup cleanup (every 24h) ---
async def followup_cleanup_job():
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


# --- Activities cleanup (every 24h) ---
async def activities_cleanup_job():
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


# --- Queue cleanup (every 24h) ---
async def queue_cleanup_job():
    enable = os.getenv("ENABLE_QUEUE_CLEANUP", "true").lower() == "true"
    if not enable:
        logger.debug("[QUEUE_CLEANUP] Disabled via env var, skipping")
        return
    from api.database import SessionLocal
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


# --- Reconciliation (every 30min) ---
async def reconciliation_job():
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


# --- Lead enrichment (every 6h) ---
async def lead_enrichment_job():
    enable = os.getenv("ENABLE_LEAD_ENRICHMENT", "true").lower() == "true"
    if not enable:
        logger.debug("[LEAD_ENRICHMENT] Disabled via env var, skipping")
        return
    from api.database import SessionLocal
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


# --- Ghost reactivation (every 24h) ---
async def ghost_reactivation_job():
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


def register_maintenance_jobs(scheduler):
    """Register all maintenance scheduled jobs with the task scheduler."""
    from services.media_capture_job import (
        MEDIA_CAPTURE_INITIAL_DELAY,
        MEDIA_CAPTURE_INTERVAL,
    )

    scheduler.register("token_refresh", token_refresh_job, interval_seconds=21600, initial_delay_seconds=60)
    scheduler.register("profile_pic_refresh", profile_pic_refresh_job, interval_seconds=86400, initial_delay_seconds=90)
    scheduler.register("media_capture", media_capture_job, interval_seconds=MEDIA_CAPTURE_INTERVAL, initial_delay_seconds=MEDIA_CAPTURE_INITIAL_DELAY)
    scheduler.register("post_context_refresh", post_context_refresh_job, interval_seconds=43200, initial_delay_seconds=150)
    scheduler.register("score_decay", score_decay_job, interval_seconds=86400, initial_delay_seconds=210)
    scheduler.register("followup_cleanup", followup_cleanup_job, interval_seconds=86400, initial_delay_seconds=240)
    scheduler.register("activities_cleanup", activities_cleanup_job, interval_seconds=86400, initial_delay_seconds=270)
    scheduler.register("queue_cleanup", queue_cleanup_job, interval_seconds=86400, initial_delay_seconds=300)
    scheduler.register("reconciliation", reconciliation_job, interval_seconds=1800, initial_delay_seconds=330)
    scheduler.register("lead_enrichment", lead_enrichment_job, interval_seconds=21600, initial_delay_seconds=360)
    scheduler.register("ghost_reactivation", ghost_reactivation_job, interval_seconds=86400, initial_delay_seconds=390)
