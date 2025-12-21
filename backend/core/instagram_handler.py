#!/usr/bin/env python3
"""
Instagram Handler for Clonnect Creators DM System.

Provides Instagram webhook handling and DM processing using Meta Graph API.
Follows the same pattern as telegram_adapter.py.

Usage:
    Webhook (prod): Used via FastAPI endpoints in api/main.py
"""
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict

from core.dm_agent import DMResponderAgent, DMResponse
from core.instagram import InstagramConnector, InstagramMessage

logger = logging.getLogger("clonnect-instagram")


@dataclass
class InstagramHandlerStatus:
    """Status of the Instagram handler"""
    connected: bool = False
    page_id: str = ""
    ig_user_id: str = ""
    messages_received: int = 0
    messages_sent: int = 0
    last_message_time: Optional[str] = None
    errors: int = 0
    started_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class InstagramHandler:
    """
    Instagram handler for Clonnect DM system.

    Bridges Instagram DMs to DMResponderAgent and sends responses back via Meta API.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        page_id: Optional[str] = None,
        ig_user_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        verify_token: Optional[str] = None,
        creator_id: str = "manel"
    ):
        """
        Initialize Instagram handler.

        Args:
            access_token: Meta Graph API access token
            page_id: Facebook Page ID linked to Instagram
            ig_user_id: Instagram Business/Creator account ID
            app_secret: App secret for webhook signature verification
            verify_token: Token for webhook verification (GET request)
            creator_id: Creator ID to use for DMResponderAgent
        """
        self.access_token = access_token or os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        self.page_id = page_id or os.getenv("INSTAGRAM_PAGE_ID", "")
        self.ig_user_id = ig_user_id or os.getenv("INSTAGRAM_USER_ID", "")
        self.app_secret = app_secret or os.getenv("INSTAGRAM_APP_SECRET", "")
        self.verify_token = verify_token or os.getenv("INSTAGRAM_VERIFY_TOKEN", "clonnect_verify_2024")
        self.creator_id = creator_id

        # Status tracking
        self.status = InstagramHandlerStatus()
        self.recent_messages: List[Dict[str, Any]] = []  # Last 10 messages
        self.recent_responses: List[Dict[str, Any]] = []  # Last 10 responses

        # DM Agent
        self.dm_agent: Optional[DMResponderAgent] = None

        # Instagram connector
        self.connector: Optional[InstagramConnector] = None

        self._init_connector()
        self._init_agent()

    def _init_connector(self):
        """Initialize Instagram connector"""
        if not self.access_token or not self.page_id:
            logger.warning("Instagram credentials not configured (INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_PAGE_ID)")
            return

        try:
            self.connector = InstagramConnector(
                access_token=self.access_token,
                page_id=self.page_id,
                ig_user_id=self.ig_user_id,
                app_secret=self.app_secret,
                verify_token=self.verify_token
            )
            self.status.connected = True
            self.status.page_id = self.page_id
            self.status.ig_user_id = self.ig_user_id
            self.status.started_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"Instagram connector initialized for page: {self.page_id}")
        except Exception as e:
            logger.error(f"Failed to initialize Instagram connector: {e}")

    def _init_agent(self):
        """Initialize DM agent"""
        try:
            self.dm_agent = DMResponderAgent(creator_id=self.creator_id)
            logger.info(f"DM Agent initialized for creator: {self.creator_id}")
        except Exception as e:
            logger.error(f"Failed to initialize DM agent: {e}")

    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """
        Verify webhook subscription (GET request from Meta).

        Args:
            mode: hub.mode parameter (should be "subscribe")
            token: hub.verify_token parameter
            challenge: hub.challenge parameter

        Returns:
            Challenge string if valid, None otherwise
        """
        if mode == "subscribe" and token == self.verify_token:
            logger.info("Webhook verification successful")
            return challenge
        logger.warning(f"Webhook verification failed: mode={mode}, token_match={token == self.verify_token}")
        return None

    async def handle_webhook(self, payload: Dict[str, Any], signature: str = "") -> Dict[str, Any]:
        """
        Handle incoming webhook from Meta (POST request).

        Args:
            payload: Webhook payload from Meta
            signature: X-Hub-Signature-256 header for verification

        Returns:
            Processing result with status and responses
        """
        # Verify signature if app_secret is configured
        if self.connector and self.app_secret and signature:
            import json
            payload_bytes = json.dumps(payload, separators=(',', ':')).encode()
            if not self.connector.verify_webhook_signature(payload_bytes, signature):
                logger.warning("Invalid webhook signature")
                self.status.errors += 1
                return {"status": "error", "reason": "invalid_signature"}

        # Extract messages from webhook
        messages = await self._extract_messages(payload)

        if not messages:
            return {"status": "ok", "messages_processed": 0, "results": []}

        results = []
        for message in messages:
            # Skip messages from our own page/account (prevent self-reply loop)
            if message.sender_id == self.page_id:
                logger.info(f"Skipping message from page_id: {message.sender_id}")
                continue
            if self.ig_user_id and message.sender_id == self.ig_user_id:
                logger.info(f"Skipping message from ig_user_id: {message.sender_id}")
                continue

            # Additional safety: skip if recipient_id matches sender_id
            if message.recipient_id and message.sender_id == message.recipient_id:
                logger.info(f"Skipping self-message: {message.sender_id}")
                continue

            self._record_received(message)
            logger.info(f"[IG:{message.sender_id}] Input: {message.text[:100]}")

            try:
                # Process with DM agent
                response = await self.process_message(message)

                # Send response via Instagram
                await self.send_response(message.sender_id, response.response_text)

                self._record_response(message, response)

                results.append({
                    "message_id": message.message_id,
                    "sender_id": message.sender_id,
                    "response": response.response_text,
                    "intent": response.intent.value if hasattr(response.intent, 'value') else str(response.intent),
                    "confidence": response.confidence
                })

            except Exception as e:
                logger.error(f"Error processing message {message.message_id}: {e}")
                self.status.errors += 1
                results.append({
                    "message_id": message.message_id,
                    "sender_id": message.sender_id,
                    "error": str(e)
                })

        return {
            "status": "ok",
            "messages_processed": len(messages),
            "results": results
        }

    async def _extract_messages(self, payload: Dict[str, Any]) -> List[InstagramMessage]:
        """Extract messages from webhook payload"""
        messages = []

        try:
            for entry in payload.get("entry", []):
                for messaging in entry.get("messaging", []):
                    if "message" in messaging:
                        message_data = messaging["message"]

                        # CRITICAL: Skip echo messages (messages sent BY the page/bot)
                        # Meta sends is_echo=true for messages we sent
                        if message_data.get("is_echo"):
                            logger.info(f"Skipping echo message (sent by bot)")
                            continue

                        # Skip if sender is same as recipient (edge case)
                        sender_id = messaging.get("sender", {}).get("id", "")
                        recipient_id = messaging.get("recipient", {}).get("id", "")
                        if sender_id == recipient_id:
                            logger.info(f"Skipping message where sender==recipient")
                            continue

                        msg = InstagramMessage(
                            message_id=message_data.get("mid", ""),
                            sender_id=sender_id,
                            recipient_id=recipient_id,
                            text=message_data.get("text", ""),
                            timestamp=datetime.fromtimestamp(
                                messaging.get("timestamp", 0) / 1000
                            ),
                            attachments=message_data.get("attachments", [])
                        )
                        if msg.text:  # Only process text messages
                            messages.append(msg)
        except Exception as e:
            logger.error(f"Error extracting messages from webhook: {e}")

        return messages

    async def process_message(self, message: InstagramMessage) -> DMResponse:
        """
        Process an Instagram message through DMResponderAgent.

        Args:
            message: Instagram message to process

        Returns:
            DMResponse from the agent
        """
        if not self.dm_agent:
            self._init_agent()

        if not self.dm_agent:
            raise RuntimeError("DM Agent not initialized")

        # Get username for personalization (try to fetch from API)
        username = await self._get_username(message.sender_id)

        # Process with DM agent
        response = await self.dm_agent.process_dm(
            sender_id=f"ig_{message.sender_id}",
            message_text=message.text,
            message_id=message.message_id,
            username=username
        )

        logger.info(f"[IG:{message.sender_id}] Intent: {response.intent.value} ({response.confidence:.0%})")
        logger.info(f"[IG:{message.sender_id}] Output: {response.response_text[:100]}...")

        return response

    async def _get_username(self, sender_id: str) -> str:
        """Try to get username from Instagram API"""
        if not self.connector:
            return "amigo"

        try:
            profile = await self.connector.get_user_profile(sender_id)
            if profile:
                return profile.name or profile.username or "amigo"
        except Exception as e:
            logger.debug(f"Could not fetch user profile: {e}")

        return "amigo"

    async def send_response(self, recipient_id: str, text: str) -> bool:
        """
        Send a response message via Instagram.

        Args:
            recipient_id: Instagram user ID to send to
            text: Message text

        Returns:
            True if sent successfully
        """
        if not self.connector:
            logger.error("Instagram connector not initialized")
            return False

        try:
            # Send typing indicator
            await self.connector.send_typing_indicator(recipient_id, True)

            # Send the message
            result = await self.connector.send_message(recipient_id, text)

            if "error" in result:
                logger.error(f"Error sending message: {result['error']}")
                self.status.errors += 1
                return False

            self._record_sent()
            return True

        except Exception as e:
            logger.error(f"Error sending response: {e}")
            self.status.errors += 1
            return False

    async def send_message_with_buttons(
        self,
        recipient_id: str,
        text: str,
        buttons: List[Dict[str, str]]
    ) -> bool:
        """
        Send a message with quick reply buttons.

        Args:
            recipient_id: Instagram user ID
            text: Message text
            buttons: List of button configs with 'title' and 'payload'

        Returns:
            True if sent successfully
        """
        if not self.connector:
            logger.error("Instagram connector not initialized")
            return False

        try:
            result = await self.connector.send_message_with_buttons(recipient_id, text, buttons)

            if "error" in result:
                logger.error(f"Error sending message with buttons: {result['error']}")
                self.status.errors += 1
                return False

            self._record_sent()
            return True

        except Exception as e:
            logger.error(f"Error sending message with buttons: {e}")
            self.status.errors += 1
            return False

    def _record_received(self, msg: InstagramMessage):
        """Record received message"""
        self.status.messages_received += 1
        self.status.last_message_time = datetime.now(timezone.utc).isoformat()

        record = {
            "type": "received",
            "follower_id": f"ig_{msg.sender_id}",
            "sender_id": msg.sender_id,
            "text": msg.text,
            "timestamp": self.status.last_message_time
        }
        self.recent_messages.append(record)
        if len(self.recent_messages) > 10:
            self.recent_messages = self.recent_messages[-10:]

    def _record_sent(self):
        """Record sent message"""
        self.status.messages_sent += 1

    def _record_response(self, msg: InstagramMessage, response: DMResponse):
        """Record response"""
        record = {
            "follower_id": f"ig_{msg.sender_id}",
            "sender_id": msg.sender_id,
            "input": msg.text,
            "response": response.response_text,
            "intent": response.intent.value if hasattr(response.intent, 'value') else str(response.intent),
            "confidence": response.confidence,
            "product": response.product_mentioned,
            "escalate": response.escalate_to_human,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.recent_responses.append(record)
        if len(self.recent_responses) > 10:
            self.recent_responses = self.recent_responses[-10:]

    def get_status(self) -> Dict[str, Any]:
        """Get current handler status"""
        return self.status.to_dict()

    def get_recent_messages(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent messages"""
        return self.recent_messages[-limit:]

    def get_recent_responses(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent responses"""
        return self.recent_responses[-limit:]

    async def close(self):
        """Close connections"""
        if self.connector:
            await self.connector.close()
            self.status.connected = False
            logger.info("Instagram handler closed")


# Global handler instance
_handler: Optional[InstagramHandler] = None


def get_instagram_handler(
    creator_id: str = "manel",
    access_token: Optional[str] = None,
    page_id: Optional[str] = None
) -> InstagramHandler:
    """Get or create Instagram handler"""
    global _handler
    if _handler is None:
        _handler = InstagramHandler(
            access_token=access_token,
            page_id=page_id,
            creator_id=creator_id
        )
    return _handler
