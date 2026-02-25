"""Service for retrying failed Instagram message sends."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_

from api.database import SessionLocal
from api.models import PendingMessage

logger = logging.getLogger(__name__)

BACKOFF_MINUTES = [1, 5, 15, 60, 360]  # Retry at 1m, 5m, 15m, 1h, 6h


async def queue_failed_message(
    creator_id: str,
    recipient_id: str,
    content: str,
    lead_id: str = None,
    error: str = None,
) -> None:
    """Queue a message for retry after send failure."""
    with SessionLocal() as session:
        pending = PendingMessage(
            creator_id=creator_id,
            recipient_id=recipient_id,
            content=content,
            lead_id=lead_id,
            last_error=error,
            next_retry_at=datetime.now(timezone.utc) + timedelta(minutes=BACKOFF_MINUTES[0]),
        )
        session.add(pending)
        session.commit()
        logger.info(f"Queued message for retry: {pending.id} to {recipient_id}")


async def process_retry_queue() -> int:
    """Process all messages due for retry. Returns count of messages processed."""
    processed = 0
    with SessionLocal() as session:
        pending_messages = (
            session.query(PendingMessage)
            .filter(
                and_(
                    PendingMessage.status == "pending",
                    PendingMessage.next_retry_at <= datetime.now(timezone.utc),
                )
            )
            .order_by(PendingMessage.next_retry_at)
            .limit(50)  # Process in batches
            .all()
        )

        for msg in pending_messages:
            try:
                # Import here to avoid circular imports
                from core.instagram_handler import get_instagram_handler

                handler = get_instagram_handler(str(msg.creator_id))
                success = await handler.send_response(msg.recipient_id, msg.content)

                if success:
                    msg.status = "sent"
                    logger.info(f"Retry success: {msg.id}")
                else:
                    _handle_retry_failure(msg, "send_response returned False")

            except Exception as e:
                _handle_retry_failure(msg, str(e))

            processed += 1

        session.commit()

    return processed


def _handle_retry_failure(msg: PendingMessage, error: str) -> None:
    """Update retry state after a failure."""
    msg.attempt_count += 1
    msg.last_error = error

    if msg.attempt_count >= msg.max_attempts:
        msg.status = "failed_permanent"
        logger.error(f"Message permanently failed after {msg.attempt_count} attempts: {msg.id}")
    else:
        backoff_idx = min(msg.attempt_count, len(BACKOFF_MINUTES) - 1)
        msg.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=BACKOFF_MINUTES[backoff_idx])
        logger.warning(f"Retry {msg.attempt_count}/{msg.max_attempts} failed for {msg.id}, next at {msg.next_retry_at}")


async def retry_worker_loop():
    """Background worker that processes the retry queue every 60 seconds."""
    while True:
        try:
            count = await process_retry_queue()
            if count > 0:
                logger.info(f"Retry worker processed {count} messages")
        except Exception as e:
            logger.error(f"Retry worker error: {e}", exc_info=True)
        await asyncio.sleep(60)
