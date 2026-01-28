"""
Instagram Service.

Extracted from dm_agent.py as part of REFACTOR-PHASE2.
Provides Instagram API integration, message formatting, and webhook parsing.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Instagram message character limit
MAX_MESSAGE_LENGTH = 1000

# Rate limiting defaults
DEFAULT_RATE_LIMIT = 200  # requests per hour
RATE_LIMIT_WINDOW = 3600  # seconds (1 hour)


@dataclass
class WebhookMessage:
    """
    Parsed webhook message from Instagram.

    Attributes:
        message: The text content of the message
        sender_id: Instagram user ID of the sender
        recipient_id: Instagram user ID of the recipient
        timestamp: Unix timestamp of the message
    """

    message: str
    sender_id: str
    recipient_id: str = ""
    timestamp: int = 0
    received_at: datetime = field(default_factory=datetime.utcnow)


class InstagramService:
    """
    Service for Instagram API integration.

    Provides:
    - Message formatting with length limits
    - User data parsing from API responses
    - Webhook message parsing
    - Rate limiting tracking
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        rate_limit: int = DEFAULT_RATE_LIMIT,
    ) -> None:
        """
        Initialize Instagram service.

        Args:
            access_token: Instagram API access token
            rate_limit: Maximum requests per hour
        """
        self.access_token = access_token
        self.rate_limit = rate_limit
        self._request_count = 0
        self._window_start = datetime.utcnow()

        logger.info("[InstagramService] Initialized")

    def format_message(self, text: str) -> str:
        """
        Format message for Instagram API.

        Truncates messages exceeding MAX_MESSAGE_LENGTH.

        Args:
            text: Raw message text

        Returns:
            Formatted message within character limit
        """
        if not text:
            return ""

        if len(text) <= MAX_MESSAGE_LENGTH:
            return text

        # Truncate with ellipsis
        truncated = text[: MAX_MESSAGE_LENGTH - 3] + "..."
        logger.debug(
            f"[InstagramService] Message truncated from {len(text)} "
            f"to {len(truncated)} chars"
        )
        return truncated

    def parse_user(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse user data from Instagram API response.

        Args:
            raw_data: Raw user data from API

        Returns:
            Normalized user dictionary with username and user_id
        """
        return {
            "username": raw_data.get("username", ""),
            "user_id": raw_data.get("id", ""),
            "name": raw_data.get("name", ""),
            "profile_pic": raw_data.get("profile_picture_url", ""),
        }

    def is_rate_limited(self) -> bool:
        """
        Check if service is currently rate limited.

        Returns:
            True if rate limit exceeded, False otherwise
        """
        # Reset window if expired
        now = datetime.utcnow()
        elapsed = (now - self._window_start).total_seconds()

        if elapsed >= RATE_LIMIT_WINDOW:
            self._request_count = 0
            self._window_start = now
            return False

        return self._request_count >= self.rate_limit

    def increment_request_count(self) -> None:
        """Increment the API request counter."""
        self._request_count += 1
        logger.debug(
            f"[InstagramService] Request count: {self._request_count}/{self.rate_limit}"
        )

    def parse_webhook_message(
        self, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Parse incoming webhook message from Instagram.

        Expected payload structure:
        {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "123"},
                    "recipient": {"id": "456"},
                    "timestamp": 1234567890,
                    "message": {"text": "Hello!"}
                }]
            }]
        }

        Args:
            payload: Raw webhook payload

        Returns:
            Parsed message dict or None if invalid
        """
        try:
            entry = payload.get("entry", [])
            if not entry:
                return None

            messaging = entry[0].get("messaging", [])
            if not messaging:
                return None

            msg_data = messaging[0]
            message_obj = msg_data.get("message", {})

            if not message_obj:
                return None

            return {
                "message": message_obj.get("text", ""),
                "sender_id": msg_data.get("sender", {}).get("id", ""),
                "recipient_id": msg_data.get("recipient", {}).get("id", ""),
                "timestamp": msg_data.get("timestamp", 0),
            }

        except (IndexError, KeyError, TypeError) as e:
            logger.warning(f"[InstagramService] Failed to parse webhook: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "request_count": self._request_count,
            "rate_limit": self.rate_limit,
            "is_rate_limited": self.is_rate_limited(),
            "has_access_token": self.access_token is not None,
        }
