"""
Safety Guard: Prevents bot messages from being sent without explicit approval.

LAST LINE OF DEFENSE against accidental auto-send.
Every outbound bot message MUST pass through check_send_permission().

The ONLY ways a message can pass:
1. approved=True (creator approved in dashboard, or creator manual send)
2. Autopilot premium: copilot_mode=False AND autopilot_premium_enabled=True

DO NOT REMOVE THIS MODULE.
"""

import logging

logger = logging.getLogger(__name__)


class SendBlocked(Exception):
    """Raised when a send is blocked by the safety guard."""

    pass


def check_send_permission(
    creator_id: str,
    approved: bool = False,
    caller: str = "unknown",
) -> bool:
    """
    Check if an outbound message is allowed to be sent.

    Args:
        creator_id: Creator name/ID
        approved: True if message was explicitly approved by creator or is creator-initiated
        caller: Identifier for who is calling (for logging)

    Returns:
        True if allowed

    Raises:
        SendBlocked if not allowed
    """
    # Pre-approved messages always pass
    if approved:
        return True

    # Not approved — check autopilot premium flags
    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            logger.critical(
                f"[BLOCKED AUTO-SEND] creator={creator_id} caller={caller} — "
                f"Creator not found"
            )
            raise SendBlocked(f"Creator {creator_id} not found")

        # Autopilot requires BOTH flags
        if not creator.copilot_mode and creator.autopilot_premium_enabled:
            logger.info(
                f"[AUTOPILOT] Send allowed for {creator_id} caller={caller} "
                f"(premium autopilot active)"
            )
            return True

        # BLOCK
        logger.critical(
            f"[BLOCKED AUTO-SEND] creator={creator_id} caller={caller} — "
            f"copilot_mode={creator.copilot_mode} "
            f"autopilot_premium={creator.autopilot_premium_enabled} — "
            f"Bot message not approved by creator. "
            f"Only dashboard toggle + premium flag can enable autopilot."
        )
        raise SendBlocked("Message blocked — not approved by creator")
    finally:
        session.close()
