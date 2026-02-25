"""Nurturing followup management endpoints and helpers"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from core.nurturing import get_nurturing_manager
from fastapi import APIRouter, Depends

from api.auth import require_creator_access
from api.routers.nurturing.sequences import _get_default_sequences, _load_sequences_config

# Telegram proxy config
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "")
TELEGRAM_PROXY_SECRET = os.getenv("TELEGRAM_PROXY_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# P0 FIX: Nurturing dry_run controlled by env var, defaults to FALSE (messages WILL send)
NURTURING_DRY_RUN = os.getenv("NURTURING_DRY_RUN", "false").lower() == "true"

# SPEC-006: Real sending controls
NURTURING_SEND_REAL = os.getenv("NURTURING_SEND_REAL", "false").lower() == "true"
NURTURING_MAX_PER_CYCLE = int(os.getenv("NURTURING_MAX_PER_CYCLE", "5"))
NURTURING_WINDOW_HOURS = int(os.getenv("NURTURING_WINDOW_HOURS", "24"))

logger = logging.getLogger(__name__)
router = APIRouter()


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

            lead.last_contact_at = datetime.now(timezone.utc)

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

    # A16: If copilot_mode is enabled, create pending_approval instead of sending
    try:
        from api.database import SessionLocal as _SL_nurture
        from api.models import Creator as _Creator_nurture

        _sess = _SL_nurture()
        try:
            _creator = _sess.query(_Creator_nurture).filter_by(name=creator_id).first()
            if _creator and getattr(_creator, "copilot_mode", False):
                logger.info(
                    f"[A16] Copilot mode active for {creator_id}, "
                    f"creating pending_approval for nurturing to {follower_id}"
                )
                from core.copilot_service import get_copilot_service

                svc = get_copilot_service()
                # Get lead_id for this follower
                from api.models import Lead as _Lead_nurture

                _lead = (
                    _sess.query(_Lead_nurture)
                    .filter_by(creator_id=_creator.id, platform_user_id=follower_id)
                    .first()
                )
                if _lead:
                    await svc.create_pending_response(
                        creator_id=creator_id,
                        lead_id=str(_lead.id),
                        follower_id=follower_id,
                        platform=channel,
                        user_message="[nurturing followup]",
                        user_message_id="",
                        suggested_response=message,
                        intent="nurturing",
                        confidence=1.0,
                        username=_lead.username or "",
                        full_name=_lead.full_name or "",
                    )
                return {"sent": True, "simulated": False, "copilot_pending": True, "error": None}
        finally:
            _sess.close()
    except Exception as copilot_err:
        logger.warning(f"[A16] Copilot check failed (proceeding with direct send): {copilot_err}")

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
            sent = await handler.send_response(follower_id, message, approved=True)

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
        logger.info("[NURTURING] [SIMULATED] WhatsApp nurturing not yet implemented")
        return {"sent": True, "simulated": True, "error": None}

    logger.warning(f"[NURTURING] Unknown channel {channel} for {follower_id}")
    return {"sent": False, "simulated": False, "error": f"Unknown channel: {channel}"}


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/{creator_id}/followups")
async def get_nurturing_followups(creator_id: str, status: Optional[str] = None, limit: int = 50, _auth: str = Depends(require_creator_access)):
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
async def get_nurturing_stats(creator_id: str, _auth: str = Depends(require_creator_access)):
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


@router.post("/{creator_id}/run")
async def run_nurturing_followups(
    creator_id: str,
    due_only: bool = True,
    dry_run: Optional[bool] = None,  # P0 FIX: Now uses NURTURING_DRY_RUN env var as default
    limit: int = 50,
    force_due: bool = False,
    _auth: str = Depends(require_creator_access),
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
    _now = datetime.now(timezone.utc)

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
