"""
Meta API Retry Queue.

Handles failed Instagram/WhatsApp message sends with exponential backoff.
In-memory queue that processes retries asynchronously.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class QueuedMessage:
    """A message queued for retry."""

    recipient_id: str
    message: str
    creator_id: str
    platform: str = "instagram"  # instagram or whatsapp
    attempts: int = 0
    max_retries: int = 5
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_error: Optional[str] = None


class MetaRetryQueue:
    """
    Retry queue for failed Meta API message sends.

    Uses exponential backoff with configurable max retries.
    Queue is in-memory (not persistent across restarts).
    """

    def __init__(
        self,
        max_retries: int = 5,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        max_queue_size: int = 10000,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._queue: deque = deque(maxlen=max_queue_size)
        self._processing = False
        self._stats = {
            "enqueued": 0,
            "succeeded": 0,
            "failed_permanent": 0,
            "retries_total": 0,
        }
        self._send_fn: Optional[Callable] = None

    def set_send_function(
        self, fn: Callable[[str, str, str], Coroutine]
    ) -> None:
        """
        Set the async function used to send messages.

        Args:
            fn: Async callable(recipient_id, message, creator_id) -> bool
        """
        self._send_fn = fn

    async def enqueue(
        self,
        recipient_id: str,
        message: str,
        creator_id: str,
        platform: str = "instagram",
        error: Optional[str] = None,
    ) -> None:
        """
        Add a failed message to the retry queue.

        Args:
            recipient_id: Target user ID
            message: Message text to send
            creator_id: Creator who owns this conversation
            platform: Platform (instagram/whatsapp)
            error: Error message from the failed attempt
        """
        item = QueuedMessage(
            recipient_id=recipient_id,
            message=message,
            creator_id=creator_id,
            platform=platform,
            max_retries=self.max_retries,
            last_error=error,
        )
        self._queue.append(item)
        self._stats["enqueued"] += 1
        logger.info(
            f"[RetryQueue] Enqueued for {recipient_id} "
            f"(queue size: {len(self._queue)})"
        )

        # Start processing if not already running
        if not self._processing:
            asyncio.create_task(self._process_queue())

    async def _process_queue(self) -> None:
        """Process all queued messages with exponential backoff."""
        if self._processing:
            return

        self._processing = True
        logger.info("[RetryQueue] Starting queue processor")

        try:
            while self._queue:
                item = self._queue.popleft()

                if item.attempts >= item.max_retries:
                    logger.error(
                        f"[RetryQueue] Permanent failure for {item.recipient_id} "
                        f"after {item.attempts} attempts: {item.last_error}"
                    )
                    self._stats["failed_permanent"] += 1
                    continue

                # Exponential backoff with cap
                delay = min(
                    self.base_delay * (2 ** item.attempts),
                    self.max_delay,
                )
                await asyncio.sleep(delay)

                item.attempts += 1
                self._stats["retries_total"] += 1

                try:
                    success = await self._send_message(item)
                    if success:
                        self._stats["succeeded"] += 1
                        logger.info(
                            f"[RetryQueue] Retry succeeded for {item.recipient_id} "
                            f"(attempt {item.attempts})"
                        )
                    else:
                        item.last_error = "send returned False"
                        if item.attempts < item.max_retries:
                            self._queue.append(item)
                        else:
                            self._stats["failed_permanent"] += 1

                except Exception as e:
                    item.last_error = str(e)
                    logger.warning(
                        f"[RetryQueue] Retry failed for {item.recipient_id} "
                        f"(attempt {item.attempts}): {e}"
                    )
                    if item.attempts < item.max_retries:
                        self._queue.append(item)
                    else:
                        self._stats["failed_permanent"] += 1

        finally:
            self._processing = False
            logger.info("[RetryQueue] Queue processor stopped")

    async def _send_message(self, item: QueuedMessage) -> bool:
        """
        Send a queued message via the configured send function.

        Falls back to importing InstagramHandler if no send function set.
        """
        if self._send_fn:
            return await self._send_fn(
                item.recipient_id, item.message, item.creator_id
            )

        # Default: try Instagram handler
        try:
            from core.instagram_handler import InstagramHandler

            handler = InstagramHandler(creator_id=item.creator_id)
            # BUG-09 fix: do NOT hardcode approved=True on retry. The original
            # message may have been authorized via C2 (approved=True) OR via
            # autopilot premium flags. If the creator has since revoked consent
            # (TCPA 2025: 10 business days to honor revocation), the retry must
            # re-validate against current flags. Passing approved=False forces
            # the guard to evaluate R3/R4 — letting current flags decide.
            return await handler.send_response(
                item.recipient_id, item.message, approved=False
            )
        except Exception as e:
            logger.error(f"[RetryQueue] Default send failed: {e}")
            raise

    def get_stats(self) -> Dict:
        """Get queue statistics."""
        return {
            **self._stats,
            "queue_size": len(self._queue),
            "processing": self._processing,
        }

    def get_pending(self) -> List[Dict]:
        """Get list of pending messages (for monitoring)."""
        return [
            {
                "recipient_id": item.recipient_id,
                "creator_id": item.creator_id,
                "platform": item.platform,
                "attempts": item.attempts,
                "created_at": item.created_at.isoformat(),
                "last_error": item.last_error,
            }
            for item in self._queue
        ]


# Singleton
_queue: Optional[MetaRetryQueue] = None


def get_retry_queue() -> MetaRetryQueue:
    """Get or create the global retry queue singleton."""
    global _queue
    if _queue is None:
        _queue = MetaRetryQueue()
    return _queue
