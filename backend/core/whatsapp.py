"""
WhatsApp Business API Connector and Handler for Clonnect Creators.

Provides WhatsApp Cloud API integration for DM processing.
Follows the same pattern as instagram.py and instagram_handler.py.

Required environment variables:
- WHATSAPP_PHONE_NUMBER_ID: WhatsApp Business phone number ID
- WHATSAPP_ACCESS_TOKEN: Meta Graph API access token
- WHATSAPP_VERIFY_TOKEN: Token for webhook verification
"""

import os
import json
import aiohttp
import hashlib
import hmac
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone

logger = logging.getLogger("clonnect-whatsapp")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class WhatsAppMessage:
    """Represents a WhatsApp message"""
    message_id: str
    sender_id: str  # Phone number (wa_id)
    recipient_id: str
    text: str
    timestamp: datetime
    message_type: str = "text"  # text, image, audio, video, document, etc.
    attachments: List[dict] = None
    context: Dict[str, Any] = None  # Reply context

    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []
        if self.context is None:
            self.context = {}


@dataclass
class WhatsAppContact:
    """Represents a WhatsApp contact"""
    wa_id: str  # WhatsApp ID (phone number)
    profile_name: str = ""
    phone_number: str = ""


@dataclass
class WhatsAppHandlerStatus:
    """Status of the WhatsApp handler"""
    connected: bool = False
    phone_number_id: str = ""
    messages_received: int = 0
    messages_sent: int = 0
    last_message_time: Optional[str] = None
    errors: int = 0
    started_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# WHATSAPP CONNECTOR
# =============================================================================

class WhatsAppConnector:
    """
    Connector for WhatsApp Cloud API.

    Handles sending/receiving messages via Meta's WhatsApp Business Platform.
    """

    BASE_URL = "https://graph.facebook.com/v18.0"

    def __init__(
        self,
        phone_number_id: str = None,
        access_token: str = None,
        verify_token: str = None,
        app_secret: str = None
    ):
        """
        Initialize WhatsApp connector.

        Args:
            phone_number_id: WhatsApp Business phone number ID
            access_token: Meta Graph API access token
            verify_token: Token for webhook verification
            app_secret: App secret for webhook signature verification
        """
        self.phone_number_id = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self.access_token = access_token or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        self.verify_token = verify_token or os.getenv("WHATSAPP_VERIFY_TOKEN", "clonnect_wa_verify_2024")
        self.app_secret = app_secret or os.getenv("WHATSAPP_APP_SECRET", "")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify HMAC signature from Meta webhook.

        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value

        Returns:
            True if signature is valid
        """
        if not self.app_secret:
            return True  # Skip in development

        expected = hmac.new(
            self.app_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

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
            logger.info("WhatsApp webhook verification successful")
            return challenge
        logger.warning(f"WhatsApp webhook verification failed: mode={mode}, token_match={token == self.verify_token}")
        return None

    async def handle_webhook_event(self, payload: dict) -> List[WhatsAppMessage]:
        """
        Process webhook event and extract messages.

        Args:
            payload: Webhook payload from Meta

        Returns:
            List of WhatsAppMessage objects
        """
        messages = []

        try:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})

                    # Get contacts info
                    contacts = {
                        c.get("wa_id"): c.get("profile", {}).get("name", "")
                        for c in value.get("contacts", [])
                    }

                    # Extract messages
                    for msg in value.get("messages", []):
                        sender_id = msg.get("from", "")
                        msg_type = msg.get("type", "text")

                        # Extract text based on message type
                        text = ""
                        attachments = []

                        if msg_type == "text":
                            text = msg.get("text", {}).get("body", "")
                        elif msg_type == "button":
                            text = msg.get("button", {}).get("text", "")
                        elif msg_type == "interactive":
                            interactive = msg.get("interactive", {})
                            if interactive.get("type") == "button_reply":
                                text = interactive.get("button_reply", {}).get("title", "")
                            elif interactive.get("type") == "list_reply":
                                text = interactive.get("list_reply", {}).get("title", "")
                        elif msg_type in ["image", "audio", "video", "document"]:
                            media = msg.get(msg_type, {})
                            attachments.append({
                                "type": msg_type,
                                "id": media.get("id", ""),
                                "mime_type": media.get("mime_type", ""),
                                "caption": media.get("caption", "")
                            })
                            text = media.get("caption", f"[{msg_type}]")

                        # Get context (if reply)
                        context = {}
                        if "context" in msg:
                            context = {
                                "message_id": msg["context"].get("id", ""),
                                "from": msg["context"].get("from", "")
                            }

                        message = WhatsAppMessage(
                            message_id=msg.get("id", ""),
                            sender_id=sender_id,
                            recipient_id=self.phone_number_id,
                            text=text,
                            timestamp=datetime.fromtimestamp(
                                int(msg.get("timestamp", 0)),
                                tz=timezone.utc
                            ),
                            message_type=msg_type,
                            attachments=attachments,
                            context=context
                        )

                        if message.text:  # Only process messages with text
                            messages.append(message)

        except Exception as e:
            logger.error(f"Error parsing WhatsApp webhook: {e}")

        return messages

    async def send_message(self, recipient: str, text: str) -> dict:
        """
        Send a text message.

        Args:
            recipient: Phone number (with country code, no +)
            text: Message text

        Returns:
            API response dict
        """
        session = await self._get_session()
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"body": text}
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        async with session.post(url, json=payload, headers=headers) as resp:
            result = await resp.json()
            if "error" in result:
                logger.error(f"Error sending WhatsApp message: {result['error']}")
            return result

    async def send_template(
        self,
        recipient: str,
        template_name: str,
        language_code: str = "es",
        components: List[dict] = None
    ) -> dict:
        """
        Send a template message (for initiating conversations).

        Args:
            recipient: Phone number
            template_name: Name of approved template
            language_code: Template language code
            components: Template components (header, body, buttons params)

        Returns:
            API response dict
        """
        session = await self._get_session()
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"

        template = {
            "name": template_name,
            "language": {"code": language_code}
        }

        if components:
            template["components"] = components

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": template
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        async with session.post(url, json=payload, headers=headers) as resp:
            result = await resp.json()
            if "error" in result:
                logger.error(f"Error sending WhatsApp template: {result['error']}")
            return result

    async def send_interactive_buttons(
        self,
        recipient: str,
        body_text: str,
        buttons: List[Dict[str, str]],
        header_text: str = None,
        footer_text: str = None
    ) -> dict:
        """
        Send interactive message with buttons.

        Args:
            recipient: Phone number
            body_text: Main message text
            buttons: List of buttons (max 3) with 'id' and 'title'
            header_text: Optional header
            footer_text: Optional footer

        Returns:
            API response dict
        """
        session = await self._get_session()
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"

        interactive = {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": btn.get("id", btn.get("title", "")[:20]),
                            "title": btn.get("title", "")[:20]  # Max 20 chars
                        }
                    }
                    for btn in buttons[:3]  # Max 3 buttons
                ]
            }
        }

        if header_text:
            interactive["header"] = {"type": "text", "text": header_text}
        if footer_text:
            interactive["footer"] = {"text": footer_text}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "interactive",
            "interactive": interactive
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        async with session.post(url, json=payload, headers=headers) as resp:
            result = await resp.json()
            if "error" in result:
                logger.error(f"Error sending interactive message: {result['error']}")
            return result

    async def mark_as_read(self, message_id: str) -> dict:
        """
        Mark a message as read.

        Args:
            message_id: WhatsApp message ID

        Returns:
            API response dict
        """
        session = await self._get_session()
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        async with session.post(url, json=payload, headers=headers) as resp:
            return await resp.json()

    async def get_media_url(self, media_id: str) -> Optional[str]:
        """
        Get URL to download media.

        Args:
            media_id: WhatsApp media ID

        Returns:
            Download URL or None
        """
        session = await self._get_session()
        url = f"{self.BASE_URL}/{media_id}"

        headers = {"Authorization": f"Bearer {self.access_token}"}

        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            return data.get("url")


# =============================================================================
# WHATSAPP HANDLER
# =============================================================================

class WhatsAppHandler:
    """
    WhatsApp handler for Clonnect DM system.

    Bridges WhatsApp messages to DMResponderAgent and sends responses back.
    """

    def __init__(
        self,
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None,
        verify_token: Optional[str] = None,
        app_secret: Optional[str] = None,
        creator_id: str = "manel"
    ):
        """
        Initialize WhatsApp handler.

        Args:
            phone_number_id: WhatsApp Business phone number ID
            access_token: Meta Graph API access token
            verify_token: Token for webhook verification
            app_secret: App secret for signature verification
            creator_id: Creator ID for DMResponderAgent
        """
        self.phone_number_id = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self.access_token = access_token or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        self.verify_token = verify_token or os.getenv("WHATSAPP_VERIFY_TOKEN", "clonnect_wa_verify_2024")
        self.app_secret = app_secret or os.getenv("WHATSAPP_APP_SECRET", "")
        self.creator_id = creator_id

        # Status tracking
        self.status = WhatsAppHandlerStatus()
        self.recent_messages: List[Dict[str, Any]] = []
        self.recent_responses: List[Dict[str, Any]] = []

        # Components
        self.dm_agent = None
        self.connector: Optional[WhatsAppConnector] = None

        self._init_connector()
        self._init_agent()

    def _init_connector(self):
        """Initialize WhatsApp connector"""
        if not self.access_token or not self.phone_number_id:
            logger.warning("WhatsApp credentials not configured (WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID)")
            return

        try:
            self.connector = WhatsAppConnector(
                phone_number_id=self.phone_number_id,
                access_token=self.access_token,
                verify_token=self.verify_token,
                app_secret=self.app_secret
            )
            self.status.connected = True
            self.status.phone_number_id = self.phone_number_id
            self.status.started_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"WhatsApp connector initialized for phone: {self.phone_number_id}")
        except Exception as e:
            logger.error(f"Failed to initialize WhatsApp connector: {e}")

    def _init_agent(self):
        """Initialize DM agent"""
        try:
            from core.dm_agent import DMResponderAgent
            self.dm_agent = DMResponderAgent(creator_id=self.creator_id)
            logger.info(f"DM Agent initialized for creator: {self.creator_id}")
        except Exception as e:
            logger.error(f"Failed to initialize DM agent: {e}")

    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """Verify webhook subscription"""
        if self.connector:
            return self.connector.verify_webhook(mode, token, challenge)

        # Fallback verification
        if mode == "subscribe" and token == self.verify_token:
            return challenge
        return None

    async def handle_webhook(self, payload: Dict[str, Any], signature: str = "") -> Dict[str, Any]:
        """
        Handle incoming webhook from Meta.

        Args:
            payload: Webhook payload
            signature: X-Hub-Signature-256 header

        Returns:
            Processing result
        """
        # Verify signature
        if self.connector and self.app_secret and signature:
            payload_bytes = json.dumps(payload, separators=(',', ':')).encode()
            if not self.connector.verify_webhook_signature(payload_bytes, signature):
                logger.warning("Invalid WhatsApp webhook signature")
                self.status.errors += 1
                return {"status": "error", "reason": "invalid_signature"}

        # Extract messages
        if self.connector:
            messages = await self.connector.handle_webhook_event(payload)
        else:
            messages = await self._extract_messages_fallback(payload)

        if not messages:
            return {"status": "ok", "messages_processed": 0, "results": []}

        results = []
        for message in messages:
            self._record_received(message)
            logger.info(f"[WA:{message.sender_id}] Input: {message.text[:100]}")

            try:
                # Process with DM agent
                response = await self.process_message(message)

                # Send response
                await self.send_response(message.sender_id, response.response_text)

                # Mark as read
                if self.connector:
                    await self.connector.mark_as_read(message.message_id)

                self._record_response(message, response)

                results.append({
                    "message_id": message.message_id,
                    "sender_id": message.sender_id,
                    "response": response.response_text,
                    "intent": response.intent.value if hasattr(response.intent, 'value') else str(response.intent),
                    "confidence": response.confidence
                })

            except Exception as e:
                logger.error(f"Error processing WhatsApp message {message.message_id}: {e}")
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

    async def _extract_messages_fallback(self, payload: Dict[str, Any]) -> List[WhatsAppMessage]:
        """Fallback message extraction when connector not available"""
        messages = []
        try:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    for msg in value.get("messages", []):
                        if msg.get("type") == "text":
                            messages.append(WhatsAppMessage(
                                message_id=msg.get("id", ""),
                                sender_id=msg.get("from", ""),
                                recipient_id=self.phone_number_id,
                                text=msg.get("text", {}).get("body", ""),
                                timestamp=datetime.now(timezone.utc)
                            ))
        except Exception as e:
            logger.error(f"Error in fallback message extraction: {e}")
        return messages

    async def process_message(self, message: WhatsAppMessage):
        """
        Process a WhatsApp message through DMResponderAgent.

        Args:
            message: WhatsApp message

        Returns:
            DMResponse from agent
        """
        if not self.dm_agent:
            self._init_agent()

        if not self.dm_agent:
            raise RuntimeError("DM Agent not initialized")

        # Process with DM agent
        response = await self.dm_agent.process_dm(
            sender_id=f"wa_{message.sender_id}",
            message_text=message.text,
            message_id=message.message_id,
            username="amigo"  # WhatsApp doesn't provide username
        )

        logger.info(f"[WA:{message.sender_id}] Intent: {response.intent.value} ({response.confidence:.0%})")
        logger.info(f"[WA:{message.sender_id}] Output: {response.response_text[:100]}...")

        return response

    async def send_response(self, recipient: str, text: str) -> bool:
        """
        Send response via WhatsApp.

        Args:
            recipient: Phone number
            text: Message text

        Returns:
            True if sent successfully
        """
        if not self.connector:
            logger.error("WhatsApp connector not initialized")
            return False

        try:
            result = await self.connector.send_message(recipient, text)

            if "error" in result:
                logger.error(f"Error sending WhatsApp message: {result['error']}")
                self.status.errors += 1
                return False

            self._record_sent()
            return True

        except Exception as e:
            logger.error(f"Error sending WhatsApp response: {e}")
            self.status.errors += 1
            return False

    async def send_template(
        self,
        recipient: str,
        template_name: str,
        language_code: str = "es",
        components: List[dict] = None
    ) -> bool:
        """Send a template message"""
        if not self.connector:
            return False

        try:
            result = await self.connector.send_template(
                recipient, template_name, language_code, components
            )
            if "error" not in result:
                self._record_sent()
                return True
        except Exception as e:
            logger.error(f"Error sending template: {e}")

        self.status.errors += 1
        return False

    def _record_received(self, msg: WhatsAppMessage):
        """Record received message"""
        self.status.messages_received += 1
        self.status.last_message_time = datetime.now(timezone.utc).isoformat()

        record = {
            "type": "received",
            "follower_id": f"wa_{msg.sender_id}",
            "sender_id": msg.sender_id,
            "text": msg.text,
            "message_type": msg.message_type,
            "timestamp": self.status.last_message_time
        }
        self.recent_messages.append(record)
        if len(self.recent_messages) > 10:
            self.recent_messages = self.recent_messages[-10:]

    def _record_sent(self):
        """Record sent message"""
        self.status.messages_sent += 1

    def _record_response(self, msg: WhatsAppMessage, response):
        """Record response"""
        record = {
            "follower_id": f"wa_{msg.sender_id}",
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
            logger.info("WhatsApp handler closed")


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_handler: Optional[WhatsAppHandler] = None


def get_whatsapp_handler(
    creator_id: str = "manel",
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None
) -> WhatsAppHandler:
    """Get or create WhatsApp handler singleton"""
    global _handler
    if _handler is None:
        _handler = WhatsAppHandler(
            phone_number_id=phone_number_id,
            access_token=access_token,
            creator_id=creator_id
        )
    return _handler
