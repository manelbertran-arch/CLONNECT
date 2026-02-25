"""
WhatsApp Business API Connector.

Handles sending/receiving messages via Meta's WhatsApp Business Platform.

Required environment variables:
- WHATSAPP_PHONE_NUMBER_ID: WhatsApp Business phone number ID
- WHATSAPP_ACCESS_TOKEN: Meta Graph API access token
- WHATSAPP_VERIFY_TOKEN: Token for webhook verification
"""

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

from core.whatsapp.models import WhatsAppMessage

logger = logging.getLogger("clonnect-whatsapp")


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
        app_secret: str = None,
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
        self.verify_token = verify_token or os.getenv("WHATSAPP_VERIFY_TOKEN", "")
        self.app_secret = app_secret or os.getenv("WHATSAPP_APP_SECRET", "")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
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

        expected = hmac.new(self.app_secret.encode(), payload, hashlib.sha256).hexdigest()
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
        logger.warning(
            f"WhatsApp webhook verification failed: mode={mode}, token_match={token == self.verify_token}"
        )
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
                            attachments.append(
                                {
                                    "type": msg_type,
                                    "id": media.get("id", ""),
                                    "mime_type": media.get("mime_type", ""),
                                    "caption": media.get("caption", ""),
                                }
                            )
                            text = media.get("caption", f"[{msg_type}]")

                        # Get context (if reply)
                        context = {}
                        if "context" in msg:
                            context = {
                                "message_id": msg["context"].get("id", ""),
                                "from": msg["context"].get("from", ""),
                            }

                        message = WhatsAppMessage(
                            message_id=msg.get("id", ""),
                            sender_id=sender_id,
                            recipient_id=self.phone_number_id,
                            text=text,
                            timestamp=datetime.fromtimestamp(
                                int(msg.get("timestamp", 0)), tz=timezone.utc
                            ),
                            message_type=msg_type,
                            sender_name=contacts.get(sender_id, ""),
                            attachments=attachments,
                            context=context,
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
            "text": {"body": text},
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
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
        components: List[dict] = None,
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

        template = {"name": template_name, "language": {"code": language_code}}

        if components:
            template["components"] = components

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": template,
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
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
        footer_text: str = None,
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
                            "title": btn.get("title", "")[:20],  # Max 20 chars
                        },
                    }
                    for btn in buttons[:3]  # Max 3 buttons
                ]
            },
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
            "interactive": interactive,
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
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

        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
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
# EMBEDDED SIGNUP HELPERS
# =============================================================================


async def register_phone_number(
    phone_number_id: str, access_token: str, pin: str = None
) -> dict:
    """
    Register a phone number for WhatsApp Cloud API.

    Required after Embedded Signup to activate the number.
    POST /{phone_number_id}/register

    Args:
        phone_number_id: WhatsApp phone number ID from Embedded Signup
        access_token: System User Access Token
        pin: Optional 2FA PIN (6 digits). If not provided, uses default.

    Returns:
        API response dict
    """
    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/register"
    payload = {
        "messaging_product": "whatsapp",
        "pin": pin or "000000",
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            result = await resp.json()
            if "error" in result:
                logger.error(f"Phone registration failed for {phone_number_id}: {result['error']}")
            else:
                logger.info(f"Phone {phone_number_id} registered successfully")
            return result


async def subscribe_waba_webhooks(waba_id: str, access_token: str) -> dict:
    """
    Subscribe the app to receive webhooks for a WhatsApp Business Account.

    POST /{waba_id}/subscribed_apps

    Args:
        waba_id: WhatsApp Business Account ID
        access_token: System User Access Token

    Returns:
        API response dict
    """
    url = f"https://graph.facebook.com/v21.0/{waba_id}/subscribed_apps"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async with session.post(url, headers=headers) as resp:
            result = await resp.json()
            if "error" in result:
                logger.error(f"WABA webhook subscription failed for {waba_id}: {result['error']}")
            else:
                logger.info(f"WABA {waba_id} webhook subscription successful")
            return result
