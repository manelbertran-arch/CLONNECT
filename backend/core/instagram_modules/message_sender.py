"""Message sending sub-module extracted from InstagramHandler."""
import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("clonnect-instagram")


class MessageSender:
    """Handles sending messages via Instagram API."""

    def __init__(self, connector, creator_id: str, status):
        self.connector = connector
        self.creator_id = creator_id
        self.status = status

    async def send_response(self, recipient_id: str, text: str, approved: bool = False) -> bool:
        """
        Send a response message via Instagram — GUARDED by send_guard.

        Args:
            recipient_id: Instagram user ID to send to (may have "ig_" prefix)
            text: Message text
            approved: True if message was explicitly approved by creator

        Returns:
            True if sent successfully
        """
        from core.send_guard import SendBlocked, check_send_permission

        try:
            check_send_permission(self.creator_id, approved=approved, caller="ig_handler.send_response")
        except SendBlocked:
            return False

        if not self.connector:
            logger.error("Instagram connector not initialized")
            return False

        # Strip "ig_" prefix if present - API expects numeric ID only
        if recipient_id.startswith("ig_"):
            recipient_id = recipient_id[3:]

        try:
            # Send typing indicator
            await self.connector.send_typing_indicator(recipient_id, True)

            # Send the message
            result = await self.connector.send_message(recipient_id, text)

            if "error" in result:
                logger.error(f"Error sending message: {result['error']}")
                self.status.errors += 1
                # Queue for retry
                try:
                    from services.message_retry_service import queue_failed_message
                    asyncio.create_task(queue_failed_message(
                        creator_id=self.creator_id,
                        recipient_id=recipient_id,
                        content=text,
                        error=str(result['error']),
                    ))
                except Exception as retry_err:
                    logger.debug(f"Failed to queue message for retry: {retry_err}")
                return False

            self.status.messages_sent += 1
            return True

        except Exception as e:
            logger.error(f"Error sending response: {e}")
            self.status.errors += 1
            # Queue for retry
            try:
                from services.message_retry_service import queue_failed_message
                asyncio.create_task(queue_failed_message(
                    creator_id=self.creator_id,
                    recipient_id=recipient_id,
                    content=text,
                    error=str(e),
                ))
            except Exception as retry_err:
                logger.debug(f"Failed to queue message for retry: {retry_err}")
            return False

    async def send_message_with_buttons(
        self, recipient_id: str, text: str, buttons: List[Dict[str, str]]
    ) -> bool:
        """
        Send a message with quick reply buttons.

        Args:
            recipient_id: Instagram user ID (may have "ig_" prefix)
            text: Message text
            buttons: List of button configs with 'title' and 'payload'

        Returns:
            True if sent successfully
        """
        if not self.connector:
            logger.error("Instagram connector not initialized")
            return False

        # Strip "ig_" prefix if present - API expects numeric ID only
        if recipient_id.startswith("ig_"):
            recipient_id = recipient_id[3:]

        try:
            result = await self.connector.send_message_with_buttons(recipient_id, text, buttons)

            if "error" in result:
                logger.error(f"Error sending message with buttons: {result['error']}")
                self.status.errors += 1
                return False

            self.status.messages_sent += 1
            return True

        except Exception as e:
            logger.error(f"Error sending message with buttons: {e}")
            self.status.errors += 1
            return False
