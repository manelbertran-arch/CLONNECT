"""Nurturing sequences endpoints - Full implementation"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from core.nurturing import NURTURING_SEQUENCES, SequenceType, get_nurturing_manager
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

# Telegram proxy config
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "")
TELEGRAM_PROXY_SECRET = os.getenv("TELEGRAM_PROXY_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Scheduler state
_scheduler_running = False
_scheduler_task = None
_scheduler_last_run: Optional[str] = None
_scheduler_run_count = 0
_scheduler_interval = int(os.getenv("NURTURING_SCHEDULER_INTERVAL", "300"))  # 5 minutes production

# P0 FIX: Nurturing dry_run controlled by env var, defaults to FALSE (messages WILL send)
NURTURING_DRY_RUN = os.getenv("NURTURING_DRY_RUN", "false").lower() == "true"

# SPEC-006: Real sending controls
NURTURING_SEND_REAL = os.getenv("NURTURING_SEND_REAL", "false").lower() == "true"
NURTURING_MAX_PER_CYCLE = int(os.getenv("NURTURING_MAX_PER_CYCLE", "5"))
NURTURING_WINDOW_HOURS = int(os.getenv("NURTURING_WINDOW_HOURS", "24"))

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
        meta = sequence_meta.get(
            seq_type, {"name": seq_type.replace("_", " ").title(), "id": f"seq_{seq_type}"}
        )
        sequences.append(
            {
                "id": meta["id"],
                "type": seq_type,
                "name": meta["name"],
                "is_active": False,  # Default to inactive - user must enable
                "steps": [{"delay_hours": delay, "message": msg} for delay, msg in steps],
                "enrolled_count": 0,
                "sent_count": 0,
            }
        )

    return sequences


def _load_sequences_config(creator_id: str) -> Dict[str, Any]:
    """Load sequence configurations for a creator"""
    config_path = f"data/nurturing/{creator_id}_sequences.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
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
        with open(config_path, "w", encoding="utf-8") as f:
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
    return {"status": "ok", "creator_id": creator_id, "sequences": sequences}


@router.get("/{creator_id}/followups")
async def get_nurturing_followups(creator_id: str, status: Optional[str] = None, limit: int = 50):
    """Get all followups for a creator"""
    manager = get_nurturing_manager()
    followups = manager.get_all_followups(creator_id, status)

    # Limit results
    followups = followups[:limit]

    return {
        "status": "ok",
        "creator_id": creator_id,
        "followups": [fu.to_dict() for fu in followups],
        "count": len(followups),
    }


@router.get("/{creator_id}/stats")
@router.get("/{creator_id}/status")  # Alias for /stats
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
        "by_sequence": stats.get("by_sequence", {}),
    }


@router.post("/{creator_id}/sequences/{sequence_type}/toggle")
async def toggle_nurturing_sequence(
    creator_id: str, sequence_type: str, data: Optional[ToggleSequenceRequest] = Body(default=None)
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

    return {"status": "ok", "sequence_type": sequence_type, "is_active": new_active}


@router.put("/{creator_id}/sequences/{sequence_type}")
async def update_nurturing_sequence(
    creator_id: str, sequence_type: str, data: UpdateSequenceRequest
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
        {"delay_hours": step.delay_hours, "message": step.message} for step in data.steps
    ]

    _save_sequences_config(creator_id, config)

    logger.info(f"Updated sequence {sequence_type} for {creator_id} with {len(data.steps)} steps")

    return {
        "status": "ok",
        "sequence_type": sequence_type,
        "steps": config["sequences"][sequence_type]["steps"],
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
                "pending_steps": [],
            }

        enrolled_map[fid]["pending_steps"].append(
            {
                "step": fu.step,
                "scheduled_at": fu.scheduled_at,
                "message_preview": (
                    fu.message_template[:50] + "..."
                    if len(fu.message_template) > 50
                    else fu.message_template
                ),
            }
        )

        # Update next_scheduled to earliest
        if fu.scheduled_at < enrolled_map[fid]["next_scheduled"]:
            enrolled_map[fid]["next_scheduled"] = fu.scheduled_at

    enrolled_list = list(enrolled_map.values())

    return {
        "status": "ok",
        "sequence_type": sequence_type,
        "enrolled": enrolled_list,
        "count": len(enrolled_list),
    }


@router.delete("/{creator_id}/cancel/{follower_id}")
async def cancel_nurturing(creator_id: str, follower_id: str, sequence_type: Optional[str] = None):
    """Cancel nurturing for a follower"""
    manager = get_nurturing_manager()
    cancelled = manager.cancel_followups(creator_id, follower_id, sequence_type)

    logger.info(
        f"Cancelled {cancelled} followups for {follower_id} (creator: {creator_id}, sequence: {sequence_type})"
    )

    return {"status": "ok", "follower_id": follower_id, "cancelled": cancelled}


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

    headers = {}
    if TELEGRAM_PROXY_SECRET:
        headers["X-Telegram-Proxy-Secret"] = TELEGRAM_PROXY_SECRET

    # Use same payload structure as main.py (params nested)
    payload = {
        "bot_token": TELEGRAM_BOT_TOKEN,
        "method": "sendMessage",
        "params": {"chat_id": int(chat_id), "text": text, "parse_mode": "HTML"},
    }

    logger.info(f"[NURTURING] Sending to {chat_id}: '{text[:50]}...'")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(TELEGRAM_PROXY_URL, json=payload, headers=headers)
            result = response.json()

            if response.status_code == 200 and result.get("ok"):
                logger.info(f"[NURTURING] ✓ Telegram message sent to {chat_id}")
                return True
            else:
                logger.error(f"[NURTURING] Telegram proxy error: {response.status_code} - {result}")
                return False
    except Exception as e:
        logger.error(f"[NURTURING] Telegram send failed: {e}")
        return False


def _get_creator_info_by_name(creator_id: str) -> Optional[Dict[str, Any]]:
    """Get creator Instagram credentials from DB by creator name."""
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter(Creator.name == creator_id).first()
            if not creator or not creator.instagram_token:
                return None
            return {
                "creator_id": creator.name,
                "creator_uuid": str(creator.id),
                "instagram_token": creator.instagram_token,
                "instagram_page_id": creator.instagram_page_id,
                "instagram_user_id": creator.instagram_user_id,
            }
        finally:
            session.close()
    except Exception as e:
        logger.error(f"[NURTURING] Error getting creator info: {e}")
        return None


def _check_message_window(creator_id: str, follower_id: str) -> Optional[float]:
    """
    Check if follower's last inbound message is within Meta's messaging window.

    Returns hours since last inbound message, or None if no messages found.
    """
    try:
        from datetime import timezone

        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter(Creator.name == creator_id).first()
            if not creator:
                return None

            lead = (
                session.query(Lead)
                .filter(Lead.creator_id == creator.id, Lead.platform_user_id == follower_id)
                .first()
            )
            if not lead:
                return None

            last_msg = (
                session.query(Message)
                .filter(Message.lead_id == lead.id, Message.role == "user")
                .order_by(Message.created_at.desc())
                .first()
            )
            if not last_msg or not last_msg.created_at:
                return None

            now = datetime.now(timezone.utc)
            msg_time = last_msg.created_at
            if msg_time.tzinfo is None:
                msg_time = msg_time.replace(tzinfo=timezone.utc)

            delta = now - msg_time
            return delta.total_seconds() / 3600
        finally:
            session.close()
    except Exception as e:
        logger.error(f"[NURTURING] Error checking message window: {e}")
        return None


def _save_nurturing_message_to_db(creator_id: str, follower_id: str, message_text: str) -> bool:
    """Save sent nurturing message to messages table for inbox visibility."""
    try:
        import uuid as uuid_mod

        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter(Creator.name == creator_id).first()
            if not creator:
                logger.warning(f"[NURTURING] Creator {creator_id} not found for message save")
                return False

            lead = (
                session.query(Lead)
                .filter(Lead.creator_id == creator.id, Lead.platform_user_id == follower_id)
                .first()
            )
            if not lead:
                logger.warning(f"[NURTURING] Lead {follower_id} not found for message save")
                return False

            msg = Message(
                id=uuid_mod.uuid4(),
                lead_id=lead.id,
                role="assistant",
                content=message_text,
                status="sent",
                msg_metadata={"source": "nurturing"},
            )
            session.add(msg)

            lead.last_contact_at = datetime.now()

            session.commit()
            logger.info(f"[NURTURING] Saved nurturing message to DB for {follower_id}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"[NURTURING] Error saving message to DB: {e}")
            return False
        finally:
            session.close()
    except Exception as e:
        logger.error(f"[NURTURING] Error in save_nurturing_message: {e}")
        return False


async def _try_send_message(creator_id: str, follower_id: str, message: str) -> dict:
    """
    Try to send message via available integrations (async).
    Returns {"sent": bool, "simulated": bool, "error": str|None}

    When NURTURING_SEND_REAL=false (default), all sends are simulated.
    When NURTURING_SEND_REAL=true, messages are sent via the real platform API.
    """
    channel = _guess_channel(follower_id)

    # If not sending real messages, simulate all sends
    if not NURTURING_SEND_REAL:
        logger.info(f"[NURTURING] [SIMULATED] Would send to {follower_id}: {message[:50]}...")
        return {"sent": True, "simulated": True, "error": None}

    logger.info(f"[NURTURING] Sending REAL to {follower_id} via {channel}")

    # Telegram
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

    # Instagram (explicit ig_ prefix or unknown/legacy IDs)
    if channel in ("instagram", "unknown"):
        try:
            creator_info = await asyncio.to_thread(_get_creator_info_by_name, creator_id)
            if not creator_info:
                logger.error(f"[NURTURING] Creator {creator_id} not found or no IG token")
                return {
                    "sent": False,
                    "simulated": False,
                    "error": f"Creator {creator_id} not found or no Instagram token",
                }

            from api.routers.instagram import get_handler_for_creator

            handler = get_handler_for_creator(creator_info)

            if not handler or not handler.connector:
                return {"sent": False, "simulated": False, "error": "Instagram handler not initialized"}

            # send_response handles ig_ prefix stripping internally
            sent = await handler.send_response(follower_id, message)

            if sent:
                logger.info(f"[NURTURING] REAL message sent to {follower_id} via Instagram")
                return {"sent": True, "simulated": False, "error": None}
            else:
                return {
                    "sent": False,
                    "simulated": False,
                    "error": "Instagram send_response returned False",
                }
        except Exception as e:
            logger.error(f"[NURTURING] Instagram send error: {e}")
            return {"sent": False, "simulated": False, "error": str(e)}

    # WhatsApp - not implemented for nurturing yet
    if channel == "whatsapp":
        logger.info(f"[NURTURING] [SIMULATED] WhatsApp nurturing not yet implemented")
        return {"sent": True, "simulated": True, "error": None}

    logger.warning(f"[NURTURING] Unknown channel {channel} for {follower_id}")
    return {"sent": False, "simulated": False, "error": f"Unknown channel: {channel}"}


@router.post("/{creator_id}/run")
async def run_nurturing_followups(
    creator_id: str,
    due_only: bool = True,
    dry_run: Optional[bool] = None,  # P0 FIX: Now uses NURTURING_DRY_RUN env var as default
    limit: int = 50,
    force_due: bool = False,
):
    """
    Execute pending nurturing followups for a creator.

    Args:
        creator_id: The creator ID
        due_only: If True, only process followups where scheduled_at <= now (default: True)
        dry_run: If True, don't send/mark sent, just return what would be sent.
                 Default: NURTURING_DRY_RUN env var (false = messages WILL send)
        limit: Max followups to process (default: 50)
        force_due: If True, treat ALL pending as due regardless of scheduled_at (default: False)

    Returns:
        - dry_run=True: list of followups that would be processed
        - dry_run=False: summary with processed/sent/simulated/errors counts
    """
    # P0 FIX: Use env var default if not explicitly provided
    if dry_run is None:
        dry_run = NURTURING_DRY_RUN
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

    logger.info(
        f"[NURTURING RUN] creator={creator_id} due_only={due_only} dry_run={dry_run} force_due={force_due} found={len(followups)}"
    )

    if dry_run:
        # Return detailed list without changing anything
        items = []
        for fu in followups:
            message = manager.get_followup_message(fu)
            items.append(
                {
                    "followup_id": fu.id,
                    "follower_id": fu.follower_id,
                    "sequence_type": fu.sequence_type,
                    "step": fu.step,
                    "scheduled_at": fu.scheduled_at,
                    "message_preview": message[:100] + "..." if len(message) > 100 else message,
                    "channel_guess": _guess_channel(fu.follower_id),
                }
            )

        return {
            "status": "ok",
            "creator_id": creator_id,
            "dry_run": True,
            "would_process": len(items),
            "items": items,
        }

    # Actually process followups
    processed = 0
    sent_real = 0
    sent_simulated = 0
    window_expired_count = 0
    errors = []
    by_sequence: Dict[str, Dict[str, int]] = {}

    for fu in followups:
        seq_type = fu.sequence_type
        if seq_type not in by_sequence:
            by_sequence[seq_type] = {
                "processed": 0,
                "sent": 0,
                "simulated": 0,
                "window_expired": 0,
                "errors": 0,
            }

        # 24h window check (only when sending real messages - Meta policy)
        if NURTURING_SEND_REAL:
            hours_since = await asyncio.to_thread(_check_message_window, creator_id, fu.follower_id)
            if hours_since is None:
                manager.mark_as_window_expired(fu, reason="no_prior_inbound_message")
                window_expired_count += 1
                by_sequence[seq_type]["window_expired"] += 1
                continue

            if hours_since > NURTURING_WINDOW_HOURS:
                manager.mark_as_window_expired(fu, reason=f"last_msg_{hours_since:.0f}h_ago")
                window_expired_count += 1
                by_sequence[seq_type]["window_expired"] += 1
                continue

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
                    # Save real sent message to DB for inbox visibility
                    await asyncio.to_thread(_save_nurturing_message_to_db, creator_id, fu.follower_id, message)

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
        "window_expired": window_expired_count,
        "errors": errors,
        "by_sequence": by_sequence,
        "stats_after": {
            "pending": stats.get("pending", 0),
            "sent": stats.get("sent", 0),
            "cancelled": stats.get("cancelled", 0),
        },
    }


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

    session = SessionLocal()
    try:
        # Get pending profile retries
        pending = (
            session.query(SyncQueue)
            .filter(
                SyncQueue.conversation_id.like("profile_retry:%"),
                SyncQueue.status == "pending",
                SyncQueue.attempts < 5,  # Max 5 attempts
            )
            .order_by(SyncQueue.created_at)
            .limit(max_per_cycle)
            .all()
        )

        if not pending:
            return result

        for item in pending:
            result["processed"] += 1

            # Extract sender_id from conversation_id
            sender_id = item.conversation_id.replace("profile_retry:", "")

            # Get creator info
            creator = session.query(Creator).filter_by(name=item.creator_id).first()
            if not creator or not creator.instagram_token:
                item.status = "failed"
                item.last_error = "Creator not found or no token"
                session.commit()
                result["failed"] += 1
                continue

            # Try to fetch profile
            try:
                profile_result = await fetch_instagram_profile_with_retry(
                    sender_id, creator.instagram_token
                )

                if profile_result.success and profile_result.profile:
                    profile = profile_result.profile

                    # Find and update lead
                    lead = (
                        session.query(Lead)
                        .filter(
                            Lead.creator_id == creator.id,
                            Lead.platform_user_id == f"ig_{sender_id}",
                        )
                        .first()
                    )

                    if lead:
                        # Update lead with profile data
                        if profile.get("username"):
                            lead.username = profile["username"]
                        if profile.get("name"):
                            lead.full_name = profile["name"]

                        # Upload profile pic to Cloudinary
                        if profile.get("profile_pic"):
                            cloudinary_svc = get_cloudinary_service()
                            if cloudinary_svc.is_configured:
                                cloud_result = cloudinary_svc.upload_from_url(
                                    url=profile["profile_pic"],
                                    media_type="image",
                                    folder=f"clonnect/{item.creator_id}/profiles",
                                    public_id=f"profile_{sender_id}",
                                )
                                if cloud_result.success and cloud_result.url:
                                    lead.profile_pic_url = cloud_result.url
                                else:
                                    lead.profile_pic_url = profile["profile_pic"]
                            else:
                                lead.profile_pic_url = profile["profile_pic"]

                        # Clear pending flag from context
                        if lead.context:
                            lead.context.pop("profile_pending", None)
                            lead.context.pop("profile_retry_at", None)
                        else:
                            lead.context = {}

                        session.commit()
                        logger.info(
                            f"[ProfileRetry] Success for {sender_id}: @{profile.get('username', 'N/A')}"
                        )

                    # Mark queue item as done
                    item.status = "done"
                    item.processed_at = datetime.now()
                    session.commit()
                    result["success"] += 1

                else:
                    # Failed - increment attempts
                    item.attempts += 1
                    item.last_error = profile_result.error_message or "Unknown error"

                    if item.attempts >= 5:
                        item.status = "failed"
                        logger.warning(f"[ProfileRetry] Giving up on {sender_id} after 5 attempts")
                    session.commit()
                    result["failed"] += 1

            except Exception as e:
                item.attempts += 1
                item.last_error = str(e)
                if item.attempts >= 5:
                    item.status = "failed"
                session.commit()
                result["failed"] += 1
                logger.error(f"[ProfileRetry] Error for {sender_id}: {e}")

    finally:
        session.close()

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

    if run_heavy_ops:
        logger.info("[NURTURING SCHEDULER] Running heavy operations (every 6th cycle)")

        # 0a. Run message reconciliation (recover missing messages from Instagram)
        try:
            from core.message_reconciliation import run_periodic_reconciliation

            recon_result = await run_periodic_reconciliation()
            if recon_result.get("total_inserted", 0) > 0:
                logger.info(
                    f"[NURTURING SCHEDULER] Reconciliation: {recon_result['total_inserted']} messages recovered"
                )
        except Exception as e:
            logger.error(f"[NURTURING SCHEDULER] Reconciliation error: {e}")

        await asyncio.sleep(0)  # Yield to event loop between heavy operations

        # 0a2. Enrich leads without profile (fix ig_XXXX leads)
        try:
            from api.database import SessionLocal
            from api.models import Creator
            from core.message_reconciliation import enrich_leads_without_profile

            def _get_enrichment_creators():
                session = SessionLocal()
                try:
                    creators = (
                        session.query(Creator)
                        .filter(
                            Creator.instagram_token.isnot(None),
                            Creator.instagram_token != "",
                            Creator.bot_active == True,
                        )
                        .all()
                    )
                    return [{"name": c.name, "token": c.instagram_token} for c in creators]
                finally:
                    session.close()

            creator_list = await asyncio.to_thread(_get_enrichment_creators)

            total_enriched = 0
            for c in creator_list:
                enrich_result = await enrich_leads_without_profile(c["name"], c["token"], limit=5)
                total_enriched += enrich_result.get("enriched", 0)

            if total_enriched > 0:
                logger.info(f"[NURTURING SCHEDULER] Lead enrichment: {total_enriched} profiles updated")

        except Exception as e:
            logger.error(f"[NURTURING SCHEDULER] Lead enrichment error: {e}")

        await asyncio.sleep(0)  # Yield to event loop between heavy operations

        # 0b. Process pending profile retries (automatic enrichment)
        try:
            profile_result = await _process_profile_retries()
            if profile_result.get("processed", 0) > 0:
                logger.info(
                    f"[NURTURING SCHEDULER] Profile retry: {profile_result['processed']} processed, "
                    f"{profile_result['success']} success, {profile_result['failed']} failed"
                )
        except Exception as e:
            logger.error(f"[NURTURING SCHEDULER] Profile retry error: {e}")

        await asyncio.sleep(0)  # Yield to event loop between heavy operations

        # 1. Run ghost reactivation (find and schedule re-engagement for ghosts)
        try:
            from core.ghost_reactivation import run_ghost_reactivation_cycle

            ghost_result = await run_ghost_reactivation_cycle()
            if ghost_result.get("total_scheduled", 0) > 0:
                logger.info(
                    f"[NURTURING SCHEDULER] Ghost reactivation: {ghost_result['total_scheduled']} scheduled"
                )
        except Exception as e:
            logger.error(f"[NURTURING SCHEDULER] Ghost reactivation error: {e}")

        await asyncio.sleep(0)  # Yield to event loop after heavy operations
    else:
        logger.debug(f"[NURTURING SCHEDULER] Skipping heavy ops (cycle {_scheduler_run_count})")

    # 2. Get ALL pending followups that are due (no creator_id = all creators)
    followups = await asyncio.to_thread(manager.get_pending_followups)

    if not followups:
        logger.info("[NURTURING SCHEDULER] No due followups found")
        _scheduler_last_run = datetime.now().isoformat()
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
                manager.mark_as_window_expired(fu, reason="no_prior_inbound_message")
                window_expired_count += 1
                logger.info(
                    f"[NURTURING SCHEDULER] Window expired for {fu.id}: no prior inbound message"
                )
                continue

            if hours_since > NURTURING_WINDOW_HOURS:
                manager.mark_as_window_expired(fu, reason=f"last_msg_{hours_since:.0f}h_ago")
                window_expired_count += 1
                logger.info(
                    f"[NURTURING SCHEDULER] Window expired for {fu.id}: {hours_since:.0f}h since last msg"
                )
                continue

        try:
            message = manager.get_followup_message(fu)
            result = await _try_send_message(creator_id, fu.follower_id, message)

            if result["sent"]:
                manager.mark_as_sent(fu)
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

    _scheduler_last_run = datetime.now().isoformat()
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


@router.get("/scheduler/status")
async def get_scheduler_status():
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
async def run_scheduler_now():
    """Manually trigger a scheduler run (for testing)"""
    result = await _run_scheduler_cycle()
    return {"status": "ok", "result": result}


@router.get("/reconciliation/status")
async def get_reconciliation_status():
    """Get message reconciliation status"""
    from core.message_reconciliation import get_reconciliation_status

    return {
        "status": "ok",
        "reconciliation": get_reconciliation_status(),
    }


@router.get("/reconciliation/health")
async def check_reconciliation_health():
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
async def run_reconciliation_now(lookback_hours: int = 24):
    """
    Manually trigger message reconciliation.

    Args:
        lookback_hours: How many hours to look back (default 24)
    """
    from core.message_reconciliation import run_reconciliation_cycle

    result = await run_reconciliation_cycle(lookback_hours=lookback_hours)
    return {"status": "ok", "result": result}
