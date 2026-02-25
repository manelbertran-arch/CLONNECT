"""
WhatsApp Handler for Clonnect DM system.

Bridges WhatsApp messages to DMResponderAgent and sends responses back.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.whatsapp.connector import WhatsAppConnector
from core.whatsapp.models import WhatsAppHandlerStatus, WhatsAppMessage

logger = logging.getLogger("clonnect-whatsapp")


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
        creator_id: str = "manel",
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
        self.verify_token = verify_token or os.getenv("WHATSAPP_VERIFY_TOKEN", "")
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
            logger.warning(
                "WhatsApp credentials not configured (WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID)"
            )
            return

        try:
            self.connector = WhatsAppConnector(
                phone_number_id=self.phone_number_id,
                access_token=self.access_token,
                verify_token=self.verify_token,
                app_secret=self.app_secret,
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
            from core.dm_agent_v2 import get_dm_agent

            self.dm_agent = get_dm_agent(self.creator_id)
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
            payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
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
                response_text = response.content if hasattr(response, "content") else str(response)
                intent = str(response.intent) if hasattr(response, "intent") else "unknown"
                confidence = response.confidence if hasattr(response, "confidence") else 0.0

                # Mark as read (so user knows we received it)
                if self.connector:
                    await self.connector.mark_as_read(message.message_id)

                # Check copilot mode
                copilot_enabled = True
                try:
                    from api.database import SessionLocal as _WaSL
                    from api.models import Creator as _WaCreator
                    _wa_sess = _WaSL()
                    try:
                        _wa_creator = _wa_sess.query(_WaCreator).filter_by(name=self.creator_id).first()
                        if _wa_creator:
                            copilot_enabled = _wa_creator.copilot_mode
                    finally:
                        _wa_sess.close()
                except Exception:
                    pass

                if copilot_enabled:
                    # Copilot mode: save as pending for approval
                    logger.info(
                        f"[WA:{message.sender_id}] Saving as pending for copilot approval"
                    )

                    from core.copilot_service import get_copilot_service
                    copilot = get_copilot_service()

                    # Carry Best-of-N candidates from DM response metadata
                    _wa_cloud_meta = {}
                    if hasattr(response, "metadata") and response.metadata and response.metadata.get("best_of_n"):
                        _wa_cloud_meta["best_of_n"] = response.metadata["best_of_n"]

                    pending = await copilot.create_pending_response(
                        creator_id=self.creator_id,
                        lead_id="",
                        follower_id=f"wa_{message.sender_id}",
                        platform="whatsapp",
                        user_message=message.text,
                        user_message_id=message.message_id,
                        suggested_response=response_text,
                        intent=intent,
                        confidence=confidence,
                        username="",
                        full_name="",
                        msg_metadata=_wa_cloud_meta if _wa_cloud_meta else None,
                    )

                    self._record_response(message, response)

                    results.append(
                        {
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "suggested_response": response_text,
                            "intent": intent,
                            "confidence": confidence,
                            "status": "pending_approval",
                        }
                    )
                else:
                    # Autopilot mode: attempt direct send.
                    # Safety guard in send_response() will block unless
                    # creator has both copilot_mode=False AND autopilot_premium_enabled=True.
                    sent = await self.send_response(message.sender_id, response_text)

                    self._record_response(message, response)

                    if sent:
                        results.append(
                            {
                                "message_id": message.message_id,
                                "sender_id": message.sender_id,
                                "response": response_text[:50] + "...",
                                "intent": intent,
                                "confidence": confidence,
                                "status": "sent",
                            }
                        )
                    else:
                        # Guard blocked it -- save as pending instead
                        from core.copilot_service import get_copilot_service
                        copilot = get_copilot_service()

                        # Carry Best-of-N candidates
                        _wa_guard_meta = {}
                        if hasattr(response, "metadata") and response.metadata and response.metadata.get("best_of_n"):
                            _wa_guard_meta["best_of_n"] = response.metadata["best_of_n"]

                        pending = await copilot.create_pending_response(
                            creator_id=self.creator_id,
                            lead_id="",
                            follower_id=f"wa_{message.sender_id}",
                            platform="whatsapp",
                            user_message=message.text,
                            user_message_id=message.message_id,
                            suggested_response=response_text,
                            intent=intent,
                            confidence=confidence,
                            username="",
                            full_name="",
                            msg_metadata=_wa_guard_meta if _wa_guard_meta else None,
                        )

                        results.append(
                            {
                                "message_id": message.message_id,
                                "sender_id": message.sender_id,
                                "autopilot_blocked": True,
                                "pending_id": pending.id,
                                "suggested_response": response_text,
                                "intent": intent,
                                "confidence": confidence,
                                "status": "pending_approval",
                            }
                        )

            except Exception as e:
                logger.error(f"Error processing WhatsApp message {message.message_id}: {e}")
                self.status.errors += 1
                results.append(
                    {
                        "message_id": message.message_id,
                        "sender_id": message.sender_id,
                        "error": str(e),
                    }
                )

        return {"status": "ok", "messages_processed": len(messages), "results": results}

    async def _extract_messages_fallback(self, payload: Dict[str, Any]) -> List[WhatsAppMessage]:
        """Fallback message extraction when connector not available"""
        messages = []
        try:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    for msg in value.get("messages", []):
                        if msg.get("type") == "text":
                            messages.append(
                                WhatsAppMessage(
                                    message_id=msg.get("id", ""),
                                    sender_id=msg.get("from", ""),
                                    recipient_id=self.phone_number_id,
                                    text=msg.get("text", {}).get("body", ""),
                                    timestamp=datetime.now(timezone.utc),
                                )
                            )
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

        # Process with DM agent (V2 signature)
        response = await self.dm_agent.process_dm(
            message=message.text,
            sender_id=f"wa_{message.sender_id}",
            metadata={
                "message_id": message.message_id,
                "username": "amigo",
                "platform": "whatsapp",
            },
        )

        intent = str(response.intent) if hasattr(response, "intent") else "unknown"
        confidence = response.confidence if hasattr(response, "confidence") else 0.0
        response_text = response.content if hasattr(response, "content") else str(response)
        logger.info(f"[WA:{message.sender_id}] Intent: {intent} ({confidence:.0%})")
        logger.info(f"[WA:{message.sender_id}] Output: {response_text[:100]}...")

        return response

    async def send_response(self, recipient: str, text: str, approved: bool = False) -> bool:
        """
        Send response via WhatsApp -- GUARDED by send_guard.

        Args:
            recipient: Phone number
            text: Message text
            approved: True if message was explicitly approved by creator

        Returns:
            True if sent successfully
        """
        from core.send_guard import SendBlocked, check_send_permission

        try:
            check_send_permission(self.creator_id, approved=approved, caller="wa_handler.send_response")
        except SendBlocked:
            return False

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
        components: List[dict] = None,
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
            "timestamp": self.status.last_message_time,
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
            "response": response.content if hasattr(response, "content") else str(response),
            "intent": str(response.intent) if hasattr(response, "intent") else "unknown",
            "confidence": response.confidence if hasattr(response, "confidence") else 0.0,
            "product": response.metadata.get("product_mentioned") if hasattr(response, "metadata") else None,
            "escalate": response.metadata.get("escalate_to_human", False) if hasattr(response, "metadata") else False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
    access_token: Optional[str] = None,
) -> WhatsAppHandler:
    """Get or create WhatsApp handler singleton"""
    global _handler
    if _handler is None:
        _handler = WhatsAppHandler(
            phone_number_id=phone_number_id, access_token=access_token, creator_id=creator_id
        )
    return _handler
