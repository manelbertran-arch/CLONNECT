"""Nurturing sequences endpoints - Full implementation"""
from fastapi import APIRouter, Body, HTTPException
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import logging
import os
import json
import asyncio
import httpx
from datetime import datetime

from core.nurturing import (
    get_nurturing_manager,
    NURTURING_SEQUENCES,
    SequenceType,
)

# Telegram proxy config
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "")
TELEGRAM_PROXY_SECRET = os.getenv("TELEGRAM_PROXY_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Scheduler state
_scheduler_running = False
_scheduler_task = None
_scheduler_last_run: Optional[str] = None
_scheduler_run_count = 0
_scheduler_interval = int(os.getenv("NURTURING_SCHEDULER_INTERVAL", "60"))  # 1 minute for testing (was 300)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nurturing", tags=["nurturing"])

# Storage path for sequence configurations
SEQUENCES_CONFIG_PATH = "data/nurturing/sequences_config.json"


# ============================================================================
# Pydantic Models
# ============================================================================

class SequenceStep(BaseModel):
    delay_hours: int
    message: str


class UpdateSequenceRequest(BaseModel):
    steps: List[SequenceStep]


class ToggleSequenceRequest(BaseModel):
    enabled: Optional[bool] = None


# ============================================================================
# Sequence Configuration Manager
# ============================================================================

def _get_default_sequences() -> List[Dict[str, Any]]:
    """Get default sequences from NURTURING_SEQUENCES"""
    sequence_meta = {
        "interest_cold": {"name": "Cold Interest Followup", "id": "seq_interest_cold"},
        "objection_price": {"name": "Price Objection", "id": "seq_objection_price"},
        "objection_time": {"name": "Time Objection", "id": "seq_objection_time"},
        "objection_doubt": {"name": "Doubt Objection", "id": "seq_objection_doubt"},
        "objection_later": {"name": "Later Objection", "id": "seq_objection_later"},
        "abandoned": {"name": "Abandoned Cart", "id": "seq_abandoned"},
        "re_engagement": {"name": "Re-engagement", "id": "seq_re_engagement"},
        "post_purchase": {"name": "Post Purchase", "id": "seq_post_purchase"},
    }

    sequences = []
    for seq_type, steps in NURTURING_SEQUENCES.items():
        meta = sequence_meta.get(seq_type, {"name": seq_type.replace("_", " ").title(), "id": f"seq_{seq_type}"})
        sequences.append({
            "id": meta["id"],
            "type": seq_type,
            "name": meta["name"],
            "is_active": False,  # Default to inactive - user must enable
            "steps": [{"delay_hours": delay, "message": msg} for delay, msg in steps],
            "enrolled_count": 0,
            "sent_count": 0,
        })

    return sequences


def _load_sequences_config(creator_id: str) -> Dict[str, Any]:
    """Load sequence configurations for a creator"""
    config_path = f"data/nurturing/{creator_id}_sequences.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading sequences config for {creator_id}: {e}")

    # Return default config
    return {"sequences": {}}


def _save_sequences_config(creator_id: str, config: Dict[str, Any]):
    """Save sequence configurations for a creator"""
    os.makedirs("data/nurturing", exist_ok=True)
    config_path = f"data/nurturing/{creator_id}_sequences.json"
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving sequences config for {creator_id}: {e}")


def _get_sequences_with_stats(creator_id: str) -> List[Dict[str, Any]]:
    """Get all sequences with real stats"""
    manager = get_nurturing_manager()
    config = _load_sequences_config(creator_id)
    stats = manager.get_stats(creator_id)
    by_sequence = stats.get("by_sequence", {})

    # Ensure sequences config is a dict (fix for legacy list data)
    sequences_config = config.get("sequences", {})
    if not isinstance(sequences_config, dict):
        sequences_config = {}

    sequences = []
    for seq in _get_default_sequences():
        seq_type = seq["type"]

        # Apply config overrides
        if seq_type in sequences_config:
            seq_config = sequences_config[seq_type]
            if "is_active" in seq_config:
                seq["is_active"] = seq_config["is_active"]
            if "steps" in seq_config:
                seq["steps"] = seq_config["steps"]

        # Apply real stats
        seq_stats = by_sequence.get(seq_type, {})
        seq["enrolled_count"] = seq_stats.get("pending", 0)
        seq["sent_count"] = seq_stats.get("sent", 0)

        sequences.append(seq)

    return sequences


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/{creator_id}/sequences")
async def get_nurturing_sequences(creator_id: str):
    """Get all nurturing sequences with configuration and stats"""
    sequences = _get_sequences_with_stats(creator_id)
    return {
        "status": "ok",
        "creator_id": creator_id,
        "sequences": sequences
    }


@router.get("/{creator_id}/followups")
async def get_nurturing_followups(
    creator_id: str,
    status: Optional[str] = None,
    limit: int = 50
):
    """Get all followups for a creator"""
    manager = get_nurturing_manager()
    followups = manager.get_all_followups(creator_id, status)

    # Limit results
    followups = followups[:limit]

    return {
        "status": "ok",
        "creator_id": creator_id,
        "followups": [fu.to_dict() for fu in followups],
        "count": len(followups)
    }


@router.get("/{creator_id}/stats")
async def get_nurturing_stats(creator_id: str):
    """Get nurturing statistics"""
    manager = get_nurturing_manager()
    stats = manager.get_stats(creator_id)

    # Count active sequences
    config = _load_sequences_config(creator_id)
    # Ensure sequences config is a dict (fix for legacy list data)
    sequences_config = config.get("sequences", {})
    if not isinstance(sequences_config, dict):
        sequences_config = {}

    active_count = 0
    for seq in _get_default_sequences():
        seq_type = seq["type"]
        is_active = False  # Default matches _get_default_sequences()
        if seq_type in sequences_config:
            is_active = sequences_config[seq_type].get("is_active", False)
        if is_active:
            active_count += 1

    return {
        "status": "ok",
        "creator_id": creator_id,
        "total": stats.get("total", 0),
        "pending": stats.get("pending", 0),
        "sent": stats.get("sent", 0),
        "cancelled": stats.get("cancelled", 0),
        "active_sequences": active_count,
        "by_sequence": stats.get("by_sequence", {})
    }


@router.post("/{creator_id}/sequences/{sequence_type}/toggle")
async def toggle_nurturing_sequence(
    creator_id: str,
    sequence_type: str,
    data: Optional[ToggleSequenceRequest] = Body(default=None)
):
    """Toggle a nurturing sequence on/off"""
    config = _load_sequences_config(creator_id)

    # Ensure sequences is a dict, not a list (fix for legacy data)
    if "sequences" not in config or not isinstance(config.get("sequences"), dict):
        config["sequences"] = {}

    if sequence_type not in config["sequences"]:
        config["sequences"][sequence_type] = {}

    # Toggle or set explicitly
    # Default to False to match _get_default_sequences() which sets is_active=False
    current_active = config["sequences"][sequence_type].get("is_active", False)
    if data and data.enabled is not None:
        new_active = data.enabled
    else:
        new_active = not current_active

    config["sequences"][sequence_type]["is_active"] = new_active
    _save_sequences_config(creator_id, config)

    logger.info(f"Toggled sequence {sequence_type} for {creator_id}: is_active={new_active}")

    return {
        "status": "ok",
        "sequence_type": sequence_type,
        "is_active": new_active
    }


@router.put("/{creator_id}/sequences/{sequence_type}")
async def update_nurturing_sequence(
    creator_id: str,
    sequence_type: str,
    data: UpdateSequenceRequest
):
    """Update nurturing sequence steps"""
    config = _load_sequences_config(creator_id)

    # Ensure sequences is a dict, not a list (fix for legacy data)
    if "sequences" not in config or not isinstance(config.get("sequences"), dict):
        config["sequences"] = {}

    if sequence_type not in config["sequences"]:
        config["sequences"][sequence_type] = {}

    # Update steps
    config["sequences"][sequence_type]["steps"] = [
        {"delay_hours": step.delay_hours, "message": step.message}
        for step in data.steps
    ]

    _save_sequences_config(creator_id, config)

    logger.info(f"Updated sequence {sequence_type} for {creator_id} with {len(data.steps)} steps")

    return {
        "status": "ok",
        "sequence_type": sequence_type,
        "steps": config["sequences"][sequence_type]["steps"]
    }


@router.get("/{creator_id}/sequences/{sequence_type}/enrolled")
async def get_enrolled_followers(creator_id: str, sequence_type: str):
    """Get followers enrolled in a specific sequence"""
    manager = get_nurturing_manager()
    followups = manager.get_all_followups(creator_id, status="pending")

    # Group by follower_id for this sequence type
    enrolled_map: Dict[str, Dict[str, Any]] = {}

    for fu in followups:
        if fu.sequence_type != sequence_type:
            continue

        fid = fu.follower_id
        if fid not in enrolled_map:
            enrolled_map[fid] = {
                "follower_id": fid,
                "next_scheduled": fu.scheduled_at,
                "pending_steps": []
            }

        enrolled_map[fid]["pending_steps"].append({
            "step": fu.step,
            "scheduled_at": fu.scheduled_at,
            "message_preview": fu.message_template[:50] + "..." if len(fu.message_template) > 50 else fu.message_template
        })

        # Update next_scheduled to earliest
        if fu.scheduled_at < enrolled_map[fid]["next_scheduled"]:
            enrolled_map[fid]["next_scheduled"] = fu.scheduled_at

    enrolled_list = list(enrolled_map.values())

    return {
        "status": "ok",
        "sequence_type": sequence_type,
        "enrolled": enrolled_list,
        "count": len(enrolled_list)
    }


@router.delete("/{creator_id}/cancel/{follower_id}")
async def cancel_nurturing(
    creator_id: str,
    follower_id: str,
    sequence_type: Optional[str] = None
):
    """Cancel nurturing for a follower"""
    manager = get_nurturing_manager()
    cancelled = manager.cancel_followups(creator_id, follower_id, sequence_type)

    logger.info(f"Cancelled {cancelled} followups for {follower_id} (creator: {creator_id}, sequence: {sequence_type})")

    return {
        "status": "ok",
        "follower_id": follower_id,
        "cancelled": cancelled
    }


# Legacy endpoint for backwards compatibility
@router.delete("/{creator_id}/followers/{follower_id}/nurturing")
async def cancel_nurturing_legacy(creator_id: str, follower_id: str):
    """Cancel all nurturing for a follower (legacy endpoint)"""
    return await cancel_nurturing(creator_id, follower_id, None)


def _guess_channel(follower_id: str) -> str:
    """Guess messaging channel from follower_id prefix"""
    if follower_id.startswith("tg_"):
        return "telegram"
    elif follower_id.startswith("ig_"):
        return "instagram"
    elif follower_id.startswith("wa_"):
        return "whatsapp"
    return "unknown"


async def _send_telegram_via_proxy(chat_id: str, text: str) -> bool:
    """Send Telegram message via Cloudflare Worker proxy (async)"""
    if not TELEGRAM_PROXY_URL or not TELEGRAM_BOT_TOKEN:
        logger.warning("[NURTURING] Telegram proxy or bot token not configured")
        return False

    headers = {"Content-Type": "application/json"}
    if TELEGRAM_PROXY_SECRET:
        headers["X-Telegram-Proxy-Secret"] = TELEGRAM_PROXY_SECRET

    payload = {
        "method": "sendMessage",
        "bot_token": TELEGRAM_BOT_TOKEN,
        "chat_id": int(chat_id),
        "text": text,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(TELEGRAM_PROXY_URL, json=payload, headers=headers)
            if response.status_code == 200:
                logger.info(f"[NURTURING] ✓ Telegram message sent to {chat_id}")
                return True
            else:
                logger.error(f"[NURTURING] Telegram proxy error: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"[NURTURING] Telegram send failed: {e}")
        return False


async def _try_send_message(creator_id: str, follower_id: str, message: str) -> dict:
    """
    Try to send message via available integrations (async).
    Returns {"sent": bool, "simulated": bool, "error": str|None}
    """
    channel = _guess_channel(follower_id)
    logger.info(f"[NURTURING] Sending to {follower_id} via {channel}")

    # Try Telegram
    if channel == "telegram":
        try:
            chat_id = follower_id.replace("tg_", "")
            result = await _send_telegram_via_proxy(chat_id, message)
            if result:
                return {"sent": True, "simulated": False, "error": None}
            else:
                return {"sent": False, "simulated": False, "error": "Telegram proxy failed"}
        except Exception as e:
            logger.error(f"[NURTURING] Telegram send exception: {e}")
            return {"sent": False, "simulated": False, "error": str(e)}

    # Try Instagram
    if channel == "instagram":
        try:
            from core.instagram_handler import send_instagram_dm
            ig_user_id = follower_id.replace("ig_", "")
            result = await send_instagram_dm(creator_id, ig_user_id, message)
            if result:
                return {"sent": True, "simulated": False, "error": None}
        except Exception as e:
            logger.debug(f"[NURTURING] Instagram send failed: {e}")

    # No real integration available - simulate send
    logger.info(f"[NURTURING] [SIMULATED] Would send to {follower_id}: {message[:50]}...")
    return {"sent": True, "simulated": True, "error": None}


@router.post("/{creator_id}/run")
async def run_nurturing_followups(
    creator_id: str,
    due_only: bool = True,
    dry_run: bool = True,
    limit: int = 50,
    force_due: bool = False
):
    """
    Execute pending nurturing followups for a creator.

    Args:
        creator_id: The creator ID
        due_only: If True, only process followups where scheduled_at <= now (default: True)
        dry_run: If True, don't send/mark sent, just return what would be sent (default: True)
        limit: Max followups to process (default: 50)
        force_due: If True, treat ALL pending as due regardless of scheduled_at (default: False)

    Returns:
        - dry_run=True: list of followups that would be processed
        - dry_run=False: summary with processed/sent/simulated/errors counts
    """
    manager = get_nurturing_manager()
    now = datetime.now()

    # Get followups based on due_only and force_due
    if force_due:
        # Treat all pending as due (for manual testing)
        followups = manager.get_all_followups(creator_id, status="pending")
    elif due_only:
        # Only those with scheduled_at <= now
        followups = manager.get_pending_followups(creator_id)
    else:
        # All pending regardless of schedule
        followups = manager.get_all_followups(creator_id, status="pending")

    # Apply limit
    followups = followups[:limit]

    logger.info(f"[NURTURING RUN] creator={creator_id} due_only={due_only} dry_run={dry_run} force_due={force_due} found={len(followups)}")

    if dry_run:
        # Return detailed list without changing anything
        items = []
        for fu in followups:
            message = manager.get_followup_message(fu)
            items.append({
                "followup_id": fu.id,
                "follower_id": fu.follower_id,
                "sequence_type": fu.sequence_type,
                "step": fu.step,
                "scheduled_at": fu.scheduled_at,
                "message_preview": message[:100] + "..." if len(message) > 100 else message,
                "channel_guess": _guess_channel(fu.follower_id)
            })

        return {
            "status": "ok",
            "creator_id": creator_id,
            "dry_run": True,
            "would_process": len(items),
            "items": items
        }

    # Actually process followups
    processed = 0
    sent_real = 0
    sent_simulated = 0
    errors = []
    by_sequence: Dict[str, Dict[str, int]] = {}

    for fu in followups:
        seq_type = fu.sequence_type
        if seq_type not in by_sequence:
            by_sequence[seq_type] = {"processed": 0, "sent": 0, "simulated": 0, "errors": 0}

        try:
            message = manager.get_followup_message(fu)
            result = await _try_send_message(creator_id, fu.follower_id, message)

            if result["sent"]:
                # Mark as sent in storage
                manager.mark_as_sent(fu)
                processed += 1
                by_sequence[seq_type]["processed"] += 1

                if result["simulated"]:
                    sent_simulated += 1
                    by_sequence[seq_type]["simulated"] += 1
                else:
                    sent_real += 1
                    by_sequence[seq_type]["sent"] += 1

                logger.info(f"Followup {fu.id} marked as sent (simulated={result['simulated']})")
            else:
                error_msg = f"Failed {fu.id}: {result.get('error', 'unknown')}"
                errors.append(error_msg)
                by_sequence[seq_type]["errors"] += 1

        except Exception as e:
            error_msg = f"Exception processing {fu.id}: {str(e)}"
            errors.append(error_msg)
            by_sequence[seq_type]["errors"] += 1
            logger.error(error_msg)

    # Get updated stats
    stats = manager.get_stats(creator_id)

    return {
        "status": "ok",
        "creator_id": creator_id,
        "dry_run": False,
        "processed": processed,
        "sent": sent_real,
        "simulated": sent_simulated,
        "errors": errors,
        "by_sequence": by_sequence,
        "stats_after": {
            "pending": stats.get("pending", 0),
            "sent": stats.get("sent", 0),
            "cancelled": stats.get("cancelled", 0)
        }
    }


# ============================================================================
# Automatic Scheduler
# ============================================================================

async def _run_scheduler_cycle():
    """Run a single scheduler cycle - process all due followups across all creators"""
    global _scheduler_last_run, _scheduler_run_count

    manager = get_nurturing_manager()

    # Get ALL pending followups that are due (no creator_id = all creators)
    followups = manager.get_pending_followups()

    if not followups:
        logger.info(f"[NURTURING SCHEDULER] No due followups found")
        _scheduler_last_run = datetime.now().isoformat()
        _scheduler_run_count += 1
        return {"pending": 0, "processed": 0, "sent": 0, "simulated": 0, "errors": 0}

    logger.info(f"[NURTURING SCHEDULER] Found {len(followups)} due followups")

    processed = 0
    sent_real = 0
    sent_simulated = 0
    error_count = 0

    for fu in followups:
        try:
            message = manager.get_followup_message(fu)
            result = await _try_send_message(fu.creator_id, fu.follower_id, message)

            if result["sent"]:
                manager.mark_as_sent(fu)
                processed += 1
                if result["simulated"]:
                    sent_simulated += 1
                else:
                    sent_real += 1
            else:
                error_count += 1
                logger.error(f"[NURTURING SCHEDULER] Failed to send {fu.id}: {result.get('error')}")
        except Exception as e:
            error_count += 1
            logger.error(f"[NURTURING SCHEDULER] Exception processing {fu.id}: {e}")

    _scheduler_last_run = datetime.now().isoformat()
    _scheduler_run_count += 1

    logger.info(f"[NURTURING SCHEDULER] Completed: {processed} processed, {sent_real} sent, {sent_simulated} simulated, {error_count} errors")

    return {
        "pending": len(followups),
        "processed": processed,
        "sent": sent_real,
        "simulated": sent_simulated,
        "errors": error_count
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


@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get nurturing scheduler status"""
    return {
        "status": "ok",
        "scheduler": {
            "running": _scheduler_running and _scheduler_task is not None and not _scheduler_task.done(),
            "interval_seconds": _scheduler_interval,
            "last_run": _scheduler_last_run,
            "total_runs": _scheduler_run_count
        }
    }


@router.post("/scheduler/run-now")
async def run_scheduler_now():
    """Manually trigger a scheduler run (for testing)"""
    result = await _run_scheduler_cycle()
    return {
        "status": "ok",
        "result": result
    }
