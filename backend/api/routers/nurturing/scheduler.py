"""Nurturing scheduler and reconciliation endpoints (admin-protected)"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.nurturing import get_nurturing_manager
from fastapi import APIRouter, Depends

from api.auth import require_admin
from api.routers.nurturing.followups import (
    NURTURING_MAX_PER_CYCLE,
    NURTURING_SEND_REAL,
    NURTURING_WINDOW_HOURS,
    _check_message_window,
    _save_nurturing_message_to_db,
    _try_send_message,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Scheduler state
_scheduler_running = False
_scheduler_task = None
_scheduler_last_run: Optional[str] = None
_scheduler_run_count = 0
_scheduler_interval = int(os.getenv("NURTURING_SCHEDULER_INTERVAL", "300"))  # 5 minutes production


# ============================================================================
# Automatic Scheduler
# ============================================================================


async def _process_profile_retries(max_per_cycle: int = 10) -> Dict[str, int]:
    """
    Process pending profile retry queue.
    Automatically retries failed profile fetches for leads.

    Returns:
        Dict with counts: processed, success, failed
    """
    from api.database import SessionLocal
    from api.models import Creator, Lead, SyncQueue
    from core.instagram_profile import fetch_instagram_profile_with_retry
    from services.cloudinary_service import get_cloudinary_service

    result = {"processed": 0, "success": 0, "failed": 0}

    def _get_pending_retries():
        """Get pending profile retries from DB (sync)."""
        session = SessionLocal()
        try:
            pending = (
                session.query(SyncQueue)
                .filter(
                    SyncQueue.conversation_id.like("profile_retry:%"),
                    SyncQueue.status == "pending",
                    SyncQueue.attempts < 5,
                )
                .order_by(SyncQueue.created_at)
                .limit(max_per_cycle)
                .all()
            )
            # Extract data we need before closing session
            items = []
            for item in pending:
                sender_id = item.conversation_id.replace("profile_retry:", "")
                creator = session.query(Creator).filter_by(name=item.creator_id).first()
                items.append({
                    "queue_id": item.id,
                    "sender_id": sender_id,
                    "creator_id": item.creator_id,
                    "creator_uuid": creator.id if creator else None,
                    "token": creator.instagram_token if creator else None,
                    "attempts": item.attempts,
                })
            return items
        finally:
            session.close()

    pending_items = await asyncio.to_thread(_get_pending_retries)
    if not pending_items:
        return result

    for item_info in pending_items:
        result["processed"] += 1
        sender_id = item_info["sender_id"]

        if not item_info["creator_uuid"] or not item_info["token"]:
            def _mark_no_token(queue_id):
                session = SessionLocal()
                try:
                    item = session.query(SyncQueue).get(queue_id)
                    if item:
                        item.status = "failed"
                        item.last_error = "Creator not found or no token"
                        session.commit()
                finally:
                    session.close()
            await asyncio.to_thread(_mark_no_token, item_info["queue_id"])
            result["failed"] += 1
            continue

        try:
            profile_result = await fetch_instagram_profile_with_retry(
                sender_id, item_info["token"]
            )

            def _update_after_fetch(queue_id, creator_uuid, profile_res):
                """Update DB after profile fetch (sync)."""
                session = SessionLocal()
                try:
                    queue_item = session.query(SyncQueue).get(queue_id)
                    if not queue_item:
                        return False

                    if profile_res.success and profile_res.profile:
                        profile = profile_res.profile

                        lead = (
                            session.query(Lead)
                            .filter(
                                Lead.creator_id == creator_uuid,
                                Lead.platform_user_id == f"ig_{sender_id}",
                            )
                            .first()
                        )

                        if lead:
                            if profile.get("username"):
                                lead.username = profile["username"]
                            if profile.get("name"):
                                lead.full_name = profile["name"]

                            if profile.get("profile_pic"):
                                cloudinary_svc = get_cloudinary_service()
                                if cloudinary_svc.is_configured:
                                    cloud_result = cloudinary_svc.upload_from_url(
                                        url=profile["profile_pic"],
                                        media_type="image",
                                        folder=f"clonnect/{item_info['creator_id']}/profiles",
                                        public_id=f"profile_{sender_id}",
                                    )
                                    if cloud_result.success and cloud_result.url:
                                        lead.profile_pic_url = cloud_result.url
                                    else:
                                        lead.profile_pic_url = profile["profile_pic"]
                                else:
                                    lead.profile_pic_url = profile["profile_pic"]

                            if lead.context:
                                lead.context.pop("profile_pending", None)
                                lead.context.pop("profile_retry_at", None)
                            else:
                                lead.context = {}

                            session.commit()
                            logger.info(
                                f"[ProfileRetry] Success for {sender_id}: @{profile.get('username', 'N/A')}"
                            )

                        queue_item.status = "done"
                        queue_item.processed_at = datetime.now(timezone.utc)
                        session.commit()
                        return True
                    else:
                        queue_item.attempts += 1
                        queue_item.last_error = profile_res.error_message or "Unknown error"
                        if queue_item.attempts >= 5:
                            queue_item.status = "failed"
                            logger.warning(f"[ProfileRetry] Giving up on {sender_id} after 5 attempts")
                        session.commit()
                        return False
                finally:
                    session.close()

            success = await asyncio.to_thread(
                _update_after_fetch, item_info["queue_id"], item_info["creator_uuid"], profile_result
            )
            if success:
                result["success"] += 1
            else:
                result["failed"] += 1

        except Exception as e:
            def _mark_error(queue_id, error_msg, attempts):
                session = SessionLocal()
                try:
                    item = session.query(SyncQueue).get(queue_id)
                    if item:
                        item.attempts = attempts + 1
                        item.last_error = error_msg
                        if item.attempts >= 5:
                            item.status = "failed"
                        session.commit()
                finally:
                    session.close()
            await asyncio.to_thread(_mark_error, item_info["queue_id"], str(e), item_info["attempts"])
            result["failed"] += 1
            logger.error(f"[ProfileRetry] Error for {sender_id}: {e}")

        # Yield between items
        await asyncio.sleep(0)

    return result


async def _run_scheduler_cycle():
    """Run a single scheduler cycle - process all due followups across all creators.

    PERF: Heavy operations (Instagram API, enrichment) only run every 6th cycle
    to avoid blocking the event loop too frequently.
    """
    global _scheduler_last_run, _scheduler_run_count

    manager = get_nurturing_manager()

    # PERF: Only run heavy operations every 6th cycle (every 30 min with 5 min interval)
    # This prevents blocking API requests with Instagram API calls
    run_heavy_ops = (_scheduler_run_count % 6) == 0

    # NOTE: Reconciliation, lead enrichment, and ghost reactivation have been
    # moved to their own dedicated startup jobs (12, 13, 14) so they don't
    # depend on the nurturing scheduler being alive.
    if run_heavy_ops:
        # Process pending profile retries (lightweight, nurturing-specific)
        try:
            profile_result = await _process_profile_retries()
            if profile_result.get("processed", 0) > 0:
                logger.info(
                    f"[NURTURING SCHEDULER] Profile retry: {profile_result['processed']} processed, "
                    f"{profile_result['success']} success, {profile_result['failed']} failed"
                )
        except Exception as e:
            logger.error(f"[NURTURING SCHEDULER] Profile retry error: {e}")

    # 2. Get ALL pending followups that are due (no creator_id = all creators)
    followups = await asyncio.to_thread(manager.get_pending_followups)

    if not followups:
        logger.info("[NURTURING SCHEDULER] No due followups found")
        _scheduler_last_run = datetime.now(timezone.utc).isoformat()
        _scheduler_run_count += 1
        return {
            "pending": 0,
            "processed": 0,
            "sent": 0,
            "simulated": 0,
            "window_expired": 0,
            "rate_limited": 0,
            "errors": 0,
        }

    logger.info(
        f"[NURTURING SCHEDULER] Found {len(followups)} due followups (send_real={NURTURING_SEND_REAL})"
    )

    processed = 0
    sent_real = 0
    sent_simulated = 0
    window_expired_count = 0
    rate_limited_count = 0
    error_count = 0

    # Rate limit tracking per creator
    sends_per_creator: Dict[str, int] = {}

    for fu in followups:
        creator_id = fu.creator_id

        # Rate limit check per creator (only when sending real)
        if NURTURING_SEND_REAL and sends_per_creator.get(creator_id, 0) >= NURTURING_MAX_PER_CYCLE:
            rate_limited_count += 1
            logger.debug(
                f"[NURTURING SCHEDULER] Rate limited for {creator_id} (max {NURTURING_MAX_PER_CYCLE}/cycle)"
            )
            continue

        # 24h window check (only when sending real - Meta messaging policy)
        if NURTURING_SEND_REAL:
            hours_since = await asyncio.to_thread(_check_message_window, creator_id, fu.follower_id)
            if hours_since is None:
                await asyncio.to_thread(manager.mark_as_window_expired, fu, "no_prior_inbound_message")
                window_expired_count += 1
                logger.info(
                    f"[NURTURING SCHEDULER] Window expired for {fu.id}: no prior inbound message"
                )
                continue

            if hours_since > NURTURING_WINDOW_HOURS:
                await asyncio.to_thread(manager.mark_as_window_expired, fu, f"last_msg_{hours_since:.0f}h_ago")
                window_expired_count += 1
                logger.info(
                    f"[NURTURING SCHEDULER] Window expired for {fu.id}: {hours_since:.0f}h since last msg"
                )
                continue

        try:
            message = manager.get_followup_message(fu)
            result = await _try_send_message(creator_id, fu.follower_id, message)

            if result["sent"]:
                await asyncio.to_thread(manager.mark_as_sent, fu)
                processed += 1
                sends_per_creator[creator_id] = sends_per_creator.get(creator_id, 0) + 1

                if result["simulated"]:
                    sent_simulated += 1
                else:
                    sent_real += 1
                    # Save real sent message to DB for inbox visibility
                    await asyncio.to_thread(_save_nurturing_message_to_db, creator_id, fu.follower_id, message)
            else:
                error_count += 1
                logger.error(
                    f"[NURTURING SCHEDULER] Failed to send {fu.id}: {result.get('error')}"
                )
        except Exception as e:
            error_count += 1
            logger.error(f"[NURTURING SCHEDULER] Exception processing {fu.id}: {e}")

        # Yield to event loop every 5 followups to avoid blocking
        if (processed + error_count + window_expired_count) % 5 == 0:
            await asyncio.sleep(0)

    _scheduler_last_run = datetime.now(timezone.utc).isoformat()
    _scheduler_run_count += 1

    logger.info(
        f"[NURTURING SCHEDULER] Completed: {processed} processed, {sent_real} sent, "
        f"{sent_simulated} simulated, {window_expired_count} expired, "
        f"{rate_limited_count} rate_limited, {error_count} errors"
    )

    return {
        "pending": len(followups),
        "processed": processed,
        "sent": sent_real,
        "simulated": sent_simulated,
        "window_expired": window_expired_count,
        "rate_limited": rate_limited_count,
        "errors": error_count,
    }


async def _scheduler_loop():
    """Background task that runs the scheduler periodically"""
    global _scheduler_running

    logger.info(f"[NURTURING SCHEDULER] Starting with interval={_scheduler_interval}s")
    _scheduler_running = True

    while _scheduler_running:
        try:
            await _run_scheduler_cycle()
        except Exception as e:
            logger.error(f"[NURTURING SCHEDULER] Error in cycle: {e}")

        # Wait for next cycle
        await asyncio.sleep(_scheduler_interval)

    logger.info("[NURTURING SCHEDULER] Stopped")


def start_scheduler():
    """Start the nurturing scheduler background task"""
    global _scheduler_task, _scheduler_running

    if _scheduler_task is not None and not _scheduler_task.done():
        logger.warning("[NURTURING SCHEDULER] Already running")
        return False

    _scheduler_running = True
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("[NURTURING SCHEDULER] Started")
    return True


def stop_scheduler():
    """Stop the nurturing scheduler"""
    global _scheduler_running, _scheduler_task

    _scheduler_running = False
    if _scheduler_task:
        _scheduler_task.cancel()
        _scheduler_task = None
    logger.info("[NURTURING SCHEDULER] Stop requested")


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/scheduler/status")
async def get_scheduler_status(admin: str = Depends(require_admin)):
    """Get nurturing scheduler status"""
    return {
        "status": "ok",
        "scheduler": {
            "running": _scheduler_running
            and _scheduler_task is not None
            and not _scheduler_task.done(),
            "interval_seconds": _scheduler_interval,
            "last_run": _scheduler_last_run,
            "total_runs": _scheduler_run_count,
        },
    }


@router.post("/scheduler/run-now")
async def run_scheduler_now(admin: str = Depends(require_admin)):
    """Manually trigger a scheduler run (for testing)"""
    result = await _run_scheduler_cycle()
    return {"status": "ok", "result": result}


@router.get("/reconciliation/status")
async def get_reconciliation_status(admin: str = Depends(require_admin)):
    """Get message reconciliation status"""
    from core.message_reconciliation import get_reconciliation_status

    return {
        "status": "ok",
        "reconciliation": get_reconciliation_status(),
    }


@router.get("/reconciliation/health")
async def check_reconciliation_health(admin: str = Depends(require_admin)):
    """
    Health check to detect gaps between Instagram and DB.
    Returns creators with message gaps that may need sync.
    """
    from core.message_reconciliation import check_message_gaps

    result = await check_message_gaps()

    status = "healthy" if result["gaps_detected"] == 0 else "gaps_detected"

    return {
        "status": status,
        "gaps_detected": result["gaps_detected"],
        "creators_checked": result["creators_checked"],
        "creators_with_gaps": result["creators_with_gaps"],
        "timestamp": result["timestamp"],
    }


@router.post("/reconciliation/run-now")
async def run_reconciliation_now(lookback_hours: int = 24, admin: str = Depends(require_admin)):
    """
    Manually trigger message reconciliation.

    Args:
        lookback_hours: How many hours to look back (default 24)
    """
    from core.message_reconciliation import run_reconciliation_cycle

    result = await run_reconciliation_cycle(lookback_hours=lookback_hours)
    return {"status": "ok", "result": result}
