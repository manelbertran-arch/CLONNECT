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

from core.dm_agent_v2 import DMResponderAgent, DMResponse
from core.instagram import InstagramConnector, InstagramMessage
from core.rate_limiter import get_rate_limiter

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
        creator_id: str = None  # Changed from "manel" to None for auto-detection
    ):
        """
        Initialize Instagram handler.

        Args:
            access_token: Meta Graph API access token
            page_id: Facebook Page ID linked to Instagram
            ig_user_id: Instagram Business/Creator account ID
            app_secret: App secret for webhook signature verification
            verify_token: Token for webhook verification (GET request)
            creator_id: Creator ID to use for DMResponderAgent (auto-detected if None)
        """
        # Try ENV vars first
        self.access_token = access_token or os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        self.page_id = page_id or os.getenv("INSTAGRAM_PAGE_ID", "")
        self.ig_user_id = ig_user_id or os.getenv("INSTAGRAM_USER_ID", "")
        self.app_secret = app_secret or os.getenv("INSTAGRAM_APP_SECRET", "")
        self.verify_token = verify_token or os.getenv("INSTAGRAM_VERIFY_TOKEN", "clonnect_verify_2024")
        self.creator_id = creator_id

        # If credentials not in ENV, try to load from database
        if not self.access_token or not self.page_id:
            self._load_credentials_from_db()

        # If still no creator_id, use default
        if not self.creator_id:
            self.creator_id = os.getenv("DEFAULT_CREATOR_ID", "stefano_bonanno")

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

    def _load_credentials_from_db(self):
        """
        Load Instagram credentials from database if not in ENV vars.
        Finds the first creator with valid Instagram credentials.
        """
        try:
            from api.database import SessionLocal
            from api.models import Creator

            if SessionLocal is None:
                logger.warning("Database not configured, cannot load Instagram credentials from DB")
                return

            db = SessionLocal()
            try:
                # Find first creator with Instagram token
                creator = db.query(Creator).filter(
                    Creator.instagram_token.isnot(None),
                    Creator.instagram_token != ""
                ).first()

                if creator:
                    self.access_token = creator.instagram_token
                    self.page_id = creator.instagram_page_id or ""
                    self.ig_user_id = creator.instagram_user_id or ""
                    self.creator_id = creator.name

                    logger.info(f"Loaded Instagram credentials from DB for creator: {creator.name}")
                    logger.info(f"  - page_id: {self.page_id or 'N/A'}")
                    logger.info(f"  - ig_user_id: {self.ig_user_id or 'N/A'}")
                    logger.info(f"  - token: {len(self.access_token)} chars")

                    # If page_id missing, try to fetch from Meta API
                    if not self.page_id and self.access_token:
                        self._fetch_page_id_from_api(creator, db)
                else:
                    logger.warning("No creator with Instagram credentials found in database")

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error loading Instagram credentials from DB: {e}")

    def _fetch_page_id_from_api(self, creator, db):
        """
        Fetch the Facebook Page ID from Meta API using the access token.
        The Page ID is required for sending messages via Instagram.
        """
        import requests

        try:
            # Get pages connected to this token
            url = f"https://graph.facebook.com/v18.0/me/accounts"
            params = {"access_token": self.access_token}

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                pages = data.get("data", [])

                if pages:
                    # Use the first page (most users have only one)
                    page = pages[0]
                    self.page_id = page.get("id", "")

                    logger.info(f"Fetched page_id from Meta API: {self.page_id}")

                    # Save to database for future use
                    if self.page_id:
                        try:
                            creator.instagram_page_id = self.page_id
                            db.commit()
                            logger.info(f"Saved page_id to database for {creator.name}")
                        except Exception as save_error:
                            logger.warning(f"Could not save page_id to DB: {save_error}")
                else:
                    logger.warning("No Facebook pages found for this token")
            else:
                logger.warning(f"Meta API error fetching pages: {response.status_code} - {response.text[:200]}")

        except Exception as e:
            logger.error(f"Error fetching page_id from Meta API: {e}")

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

        # ANTI-DUPLICATION: Extract and record echo messages (creator's manual responses)
        # This must happen BEFORE we process incoming messages
        echo_messages = await self._extract_echo_messages(payload)
        echo_recorded = 0
        for echo_msg in echo_messages:
            if await self._record_creator_manual_response(echo_msg):
                echo_recorded += 1

        # Extract messages from webhook
        messages = await self._extract_messages(payload)

        if not messages:
            return {
                "status": "ok",
                "messages_processed": 0,
                "echo_messages_recorded": echo_recorded,
                "results": []
            }

        # Check if copilot mode is enabled for this creator
        copilot_enabled = await self._is_copilot_enabled()

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

            # Rate limit check - prevent spam and control costs
            rate_limiter = get_rate_limiter()
            allowed, reason = rate_limiter.check_limit(message.sender_id)
            if not allowed:
                logger.warning(f"[IG:{message.sender_id}] Rate limited: {reason}")
                results.append({
                    "message_id": message.message_id,
                    "sender_id": message.sender_id,
                    "status": "rate_limited",
                    "reason": reason
                })
                continue

            try:
                # DEDUPLICATION: Check if we've already processed this message_id
                if hasattr(self, '_processed_message_ids'):
                    if message.message_id in self._processed_message_ids:
                        logger.warning(f"[IG:{message.sender_id}] Skipping duplicate message_id: {message.message_id}")
                        results.append({
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "status": "duplicate_skipped"
                        })
                        continue
                else:
                    self._processed_message_ids = set()

                # Add to processed set (keep last 1000 to prevent memory leak)
                self._processed_message_ids.add(message.message_id)
                if len(self._processed_message_ids) > 1000:
                    # Remove oldest entries (convert to list, slice, back to set)
                    self._processed_message_ids = set(list(self._processed_message_ids)[-500:])

                # Process with DM agent to get suggested response
                response = await self.process_message(message)

                # V2 compatibility: response.content (V2) or response_text (V1)
                response_text = getattr(response, 'content', None) or getattr(response, 'response_text', '')
                intent_str = response.intent.value if hasattr(response.intent, 'value') else str(response.intent)

                # CRITICAL: Never send error messages to users
                error_patterns = ["[LLM not configured]", "[Error", "[error", "error:", "Error:"]
                is_error_response = any(pattern in response_text for pattern in error_patterns)

                if is_error_response:
                    logger.error(f"[IG:{message.sender_id}] LLM returned error, NOT sending to user: {response_text[:100]}")
                    results.append({
                        "message_id": message.message_id,
                        "sender_id": message.sender_id,
                        "status": "llm_error",
                        "error": "LLM not available - response not sent"
                    })
                    continue

                # Get username and display name if available
                username = ""
                full_name = ""
                try:
                    if self.connector:
                        profile = await self.connector.get_user_profile(message.sender_id)
                        if profile:
                            username = profile.username
                            full_name = profile.name or ""  # Display name (e.g., "Nahuel A. Sastre")
                except Exception as e:
                    logger.warning("Failed to get user profile for %s: %s", message.sender_id, e)

                if copilot_enabled:
                    # COPILOT MODE: Save as pending approval, don't send
                    from core.copilot_service import get_copilot_service
                    copilot = get_copilot_service()

                    pending = await copilot.create_pending_response(
                        creator_id=self.creator_id,
                        lead_id="",  # Will be set by service
                        follower_id=message.sender_id,
                        platform="instagram",
                        user_message=message.text,
                        user_message_id=message.message_id,
                        suggested_response=response_text,
                        intent=intent_str,
                        confidence=response.confidence,
                        username=username,
                        full_name=full_name
                    )

                    logger.info(f"[Copilot] Created pending response {pending.id} for {message.sender_id}")

                    results.append({
                        "message_id": message.message_id,
                        "sender_id": message.sender_id,
                        "copilot_mode": True,
                        "pending_id": pending.id,
                        "suggested_response": response_text,
                        "intent": intent_str,
                        "confidence": response.confidence,
                        "status": "pending_approval"
                    })
                else:
                    # AUTOPILOT MODE: Check if creator already responded before sending
                    creator_already_responded = await self._has_creator_responded_recently(
                        message.sender_id,
                        window_seconds=300  # 5 minute window
                    )

                    if creator_already_responded:
                        # Creator already replied manually, skip bot response
                        logger.info(
                            f"[AntiDup] Skipping autopilot response to {message.sender_id} - "
                            f"creator already responded"
                        )
                        results.append({
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "copilot_mode": False,
                            "status": "skipped_creator_responded",
                            "reason": "Creator already responded manually"
                        })
                    else:
                        # AUTOPILOT MODE: Send response immediately
                        await self.send_response(message.sender_id, response.response_text)
                        self._record_response(message, response)

                        results.append({
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "copilot_mode": False,
                            "response": response.response_text,
                            "intent": response.intent.value if hasattr(response.intent, 'value') else str(response.intent),
                            "confidence": response.confidence,
                            "status": "sent"
                        })

            except Exception as e:
                import traceback
                logger.error(f"Error processing message {message.message_id}: {e}\n{traceback.format_exc()}")
                self.status.errors += 1
                results.append({
                    "message_id": message.message_id,
                    "sender_id": message.sender_id,
                    "error": str(e)
                })

        return {
            "status": "ok",
            "messages_processed": len(messages),
            "echo_messages_recorded": echo_recorded,
            "copilot_mode": copilot_enabled,
            "results": results
        }

    async def _is_copilot_enabled(self) -> bool:
        """
        Check if copilot mode is enabled for this creator.
        FIX P1: Uses cached copilot_service to avoid duplicate DB queries.
        """
        try:
            from core.copilot_service import get_copilot_service
            copilot = get_copilot_service()
            return copilot.is_copilot_enabled(self.creator_id)
        except Exception as e:
            logger.error(f"Error checking copilot mode: {e}")
            return True  # Default to copilot mode on error

    async def _extract_echo_messages(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract echo messages (creator's manual responses) from webhook payload.
        These are messages sent BY the creator/page, not by followers.
        """
        echo_messages = []

        try:
            for entry in payload.get("entry", []):
                for messaging in entry.get("messaging", []):
                    if "message" in messaging:
                        message_data = messaging["message"]

                        # Only capture echo messages (sent BY the page/creator)
                        if message_data.get("is_echo"):
                            sender_id = messaging.get("sender", {}).get("id", "")
                            recipient_id = messaging.get("recipient", {}).get("id", "")
                            text = message_data.get("text", "")

                            if text:  # Only record text messages
                                echo_messages.append({
                                    "message_id": message_data.get("mid", ""),
                                    "sender_id": sender_id,  # This is the page/creator
                                    "recipient_id": recipient_id,  # This is the follower
                                    "text": text,
                                    "timestamp": messaging.get("timestamp", 0)
                                })
                                logger.info(f"[Echo] Detected creator response to {recipient_id}: {text[:50]}...")

        except Exception as e:
            logger.error(f"Error extracting echo messages: {e}")

        return echo_messages

    async def _record_creator_manual_response(self, echo_msg: Dict[str, Any]) -> bool:
        """
        Record a creator's manual response in the database.
        This allows us to detect if creator already responded before bot sends.
        """
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead, Message

            session = SessionLocal()
            try:
                # Find creator
                creator = session.query(Creator).filter_by(name=self.creator_id).first()
                if not creator:
                    logger.warning(f"[Echo] Creator {self.creator_id} not found")
                    return False

                # The recipient of an echo message is the follower
                follower_id = echo_msg["recipient_id"]

                # Find or create lead
                lead = session.query(Lead).filter_by(
                    creator_id=creator.id,
                    platform_user_id=follower_id
                ).first()

                if not lead:
                    # Also check with ig_ prefix
                    lead = session.query(Lead).filter_by(
                        creator_id=creator.id,
                        platform_user_id=f"ig_{follower_id}"
                    ).first()

                if not lead:
                    logger.info(f"[Echo] Lead not found for {follower_id}, skipping record")
                    return False

                # Check if this exact message already exists (avoid duplicates)
                existing = session.query(Message).filter_by(
                    lead_id=lead.id,
                    platform_message_id=echo_msg["message_id"]
                ).first()

                if existing:
                    logger.debug(f"[Echo] Message {echo_msg['message_id']} already recorded")
                    return True

                # Record the creator's manual response
                msg = Message(
                    lead_id=lead.id,
                    role="assistant",
                    content=echo_msg["text"],
                    status="sent",
                    approved_by="creator_manual",  # Mark as manually sent by creator
                    platform_message_id=echo_msg["message_id"],
                    msg_metadata={"source": "instagram_echo", "is_manual": True}
                )
                session.add(msg)

                # Update lead last_contact
                lead.last_contact_at = datetime.now(timezone.utc)
                session.commit()

                logger.info(f"[Echo] Recorded creator manual response to {follower_id}")
                return True

            finally:
                session.close()

        except Exception as e:
            logger.error(f"[Echo] Error recording creator response: {e}")
            return False

    async def _has_creator_responded_recently(self, follower_id: str, window_seconds: int = 300) -> bool:
        """
        Check if the creator has manually responded to this follower recently.
        Used to prevent duplicate bot responses when creator already replied.

        Args:
            follower_id: The follower's Instagram ID
            window_seconds: Time window to check (default 5 minutes)

        Returns:
            True if creator responded recently, False otherwise
        """
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead, Message

            session = SessionLocal()
            try:
                # Find creator
                creator = session.query(Creator).filter_by(name=self.creator_id).first()
                if not creator:
                    return False

                # Find lead (try both with and without ig_ prefix)
                lead = session.query(Lead).filter_by(
                    creator_id=creator.id,
                    platform_user_id=follower_id
                ).first()

                if not lead:
                    lead = session.query(Lead).filter_by(
                        creator_id=creator.id,
                        platform_user_id=f"ig_{follower_id}"
                    ).first()

                if not lead:
                    return False

                # Check for recent creator messages
                from datetime import timedelta
                cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)

                recent_creator_msg = session.query(Message).filter(
                    Message.lead_id == lead.id,
                    Message.role == "assistant",
                    Message.created_at >= cutoff_time
                ).order_by(Message.created_at.desc()).first()

                if recent_creator_msg:
                    # Check if it was a manual response or recent bot response
                    is_manual = (
                        recent_creator_msg.approved_by == "creator_manual" or
                        (recent_creator_msg.msg_metadata or {}).get("is_manual") == True
                    )

                    # Get the most recent user message
                    last_user_msg = session.query(Message).filter(
                        Message.lead_id == lead.id,
                        Message.role == "user"
                    ).order_by(Message.created_at.desc()).first()

                    # If creator responded AFTER the last user message, skip bot
                    if last_user_msg and recent_creator_msg.created_at > last_user_msg.created_at:
                        logger.info(
                            f"[AntiDup] Creator already responded to {follower_id} "
                            f"(manual={is_manual}, msg_id={recent_creator_msg.id})"
                        )
                        return True

                return False

            finally:
                session.close()

        except Exception as e:
            logger.error(f"[AntiDup] Error checking creator response: {e}")
            return False  # On error, allow bot to respond

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

        # Process with DM agent (V2 signature: message, sender_id, metadata) - FIX 2026-01-29
        logger.info(f"[V2-FIX] Calling process_dm with V2 signature for {message.sender_id}")
        response = await self.dm_agent.process_dm(
            message=message.text,
            sender_id=f"ig_{message.sender_id}",
            metadata={
                "message_id": message.message_id,
                "username": username,
                "platform": "instagram"
            }
        )

        # V2 compatibility for logging
        response_text = getattr(response, 'content', None) or getattr(response, 'response_text', '')
        intent_str = response.intent.value if hasattr(response.intent, 'value') else str(response.intent)
        logger.info(f"[IG:{message.sender_id}] Intent: {intent_str} ({response.confidence:.0%})")
        logger.info(f"[IG:{message.sender_id}] Output: {response_text[:100]}...")

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
            recipient_id: Instagram user ID to send to (may have "ig_" prefix)
            text: Message text

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
        # V2 compatibility
        response_text = getattr(response, 'content', None) or getattr(response, 'response_text', '')
        intent_str = response.intent.value if hasattr(response.intent, 'value') else str(response.intent)
        record = {
            "follower_id": f"ig_{msg.sender_id}",
            "sender_id": msg.sender_id,
            "input": msg.text,
            "response": response_text,
            "intent": intent_str,
            "confidence": response.confidence,
            "product": getattr(response, 'product_mentioned', None),
            "escalate": getattr(response, 'escalate_to_human', False),
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

    async def handle_comment(self, comment_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process an Instagram comment and send auto-DM if applicable.

        Args:
            comment_data: Comment data from webhook containing:
                - from: {id, username} of commenter
                - text: Comment text
                - media: {id} of the media post

        Returns:
            Dict with action taken or None if no action
        """
        commenter_id = comment_data.get("from", {}).get("id")
        commenter_username = comment_data.get("from", {}).get("username", "")
        comment_text = comment_data.get("text", "")
        media_id = comment_data.get("media", {}).get("id")

        if not commenter_id or not comment_text:
            logger.debug("Comment missing required fields")
            return None

        # Check if auto-DM on comments is enabled
        auto_dm_enabled = os.getenv("AUTO_DM_ON_COMMENTS", "false").lower() == "true"
        if not auto_dm_enabled:
            logger.debug("Auto-DM on comments disabled")
            return None

        # Check for interest keywords
        interest_keywords = [
            "interesa", "precio", "info", "información", "quiero", "cómo",
            "como", "comprar", "cuánto", "cuanto", "dónde", "donde",
            "interested", "price", "how", "want", "buy", "cost"
        ]
        has_interest = any(kw.lower() in comment_text.lower() for kw in interest_keywords)

        if not has_interest:
            logger.debug(f"Comment from {commenter_username} has no interest keywords")
            return None

        logger.info(f"Interest detected in comment from @{commenter_username}: {comment_text[:50]}...")

        # Get DM template from config or use default
        dm_template = os.getenv(
            "COMMENT_DM_TEMPLATE",
            "¡Hola! Vi tu comentario y me encantó. 😊 ¿Te cuento más sobre lo que preguntabas?"
        )

        # Send DM
        success = await self.send_response(commenter_id, dm_template)

        if success:
            # Register as lead with source "comment"
            await self._register_comment_lead(
                commenter_id=commenter_id,
                commenter_username=commenter_username,
                comment_text=comment_text,
                media_id=media_id
            )

            return {
                "action": "dm_sent",
                "commenter_id": commenter_id,
                "commenter_username": commenter_username,
                "comment_preview": comment_text[:50]
            }

        return {"action": "dm_failed", "commenter_id": commenter_id}

    async def _register_comment_lead(
        self,
        commenter_id: str,
        commenter_username: str,
        comment_text: str,
        media_id: str
    ):
        """Register a lead from a comment interaction"""
        try:
            # Import here to avoid circular imports
            from core.memory import MemoryStore, FollowerMemory

            memory_store = MemoryStore()
            follower_id = f"ig_{commenter_id}"

            # Try to load existing or create new
            follower = await memory_store.load(self.creator_id, follower_id)
            if not follower:
                follower = FollowerMemory(
                    follower_id=follower_id,
                    creator_id=self.creator_id,
                    platform="instagram"
                )

            follower.name = commenter_username
            follower.is_lead = True
            follower.source = "comment"

            # Store comment in notes
            if not hasattr(follower, 'notes') or not follower.notes:
                follower.notes = []
            follower.notes.append({
                "type": "comment",
                "text": comment_text,
                "media_id": media_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            await memory_store.save(follower)
            logger.info(f"Registered lead from comment: @{commenter_username}")

        except Exception as e:
            logger.error(f"Failed to register comment lead: {e}")

    async def close(self):
        """Close connections"""
        if self.connector:
            await self.connector.close()
            self.status.connected = False
            logger.info("Instagram handler closed")


# Global handler instance
_handler: Optional[InstagramHandler] = None


def get_instagram_handler(
    creator_id: str = None,  # Changed from "manel" to None for auto-detection
    access_token: Optional[str] = None,
    page_id: Optional[str] = None
) -> InstagramHandler:
    """Get or create Instagram handler. Credentials auto-loaded from DB if not provided."""
    global _handler
    if _handler is None:
        _handler = InstagramHandler(
            access_token=access_token,
            page_id=page_id,
            creator_id=creator_id
        )
    return _handler
