#!/usr/bin/env python3
"""
Instagram Handler for Clonnect Creators DM System.

Provides Instagram webhook handling and DM processing using Meta Graph API.
Follows the same pattern as telegram_adapter.py.

Usage:
    Webhook (prod): Used via FastAPI endpoints in api/main.py
"""
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.dm_agent_v2 import DMResponderAgent, DMResponse
from core.instagram import InstagramConnector, InstagramMessage
from core.rate_limiter import get_rate_limiter
from services.cloudinary_service import get_cloudinary_service

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
        creator_id: str = None,  # Changed from "manel" to None for auto-detection
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
        self.verify_token = verify_token or os.getenv("INSTAGRAM_VERIFY_TOKEN", "")
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
                creator = (
                    db.query(Creator)
                    .filter(Creator.instagram_token.isnot(None), Creator.instagram_token != "")
                    .first()
                )

                if creator:
                    self.access_token = creator.instagram_token
                    self.page_id = creator.instagram_page_id or ""
                    self.ig_user_id = creator.instagram_user_id or ""
                    self.creator_id = creator.name
                    # Store all known creator IDs to prevent creating leads for creator's own accounts
                    self.known_creator_ids = set()
                    if self.page_id:
                        self.known_creator_ids.add(self.page_id)
                    if self.ig_user_id:
                        self.known_creator_ids.add(self.ig_user_id)
                    # Add legacy ID that was previously used (prevents ghost leads)
                    self.known_creator_ids.add("17841400506734756")

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
            url = "https://graph.facebook.com/v18.0/me/accounts"
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
                logger.warning(
                    f"Meta API error fetching pages: {response.status_code} - {response.text[:200]}"
                )

        except Exception as e:
            logger.error(f"Error fetching page_id from Meta API: {e}")

    def _init_connector(self):
        """Initialize Instagram connector"""
        if not self.access_token or not self.page_id:
            logger.warning(
                "Instagram credentials not configured (INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_PAGE_ID)"
            )
            return

        try:
            self.connector = InstagramConnector(
                access_token=self.access_token,
                page_id=self.page_id,
                ig_user_id=self.ig_user_id,
                app_secret=self.app_secret,
                verify_token=self.verify_token,
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
        logger.warning(
            f"Webhook verification failed: mode={mode}, token_match={token == self.verify_token}"
        )
        return None

    async def handle_webhook(
        self, payload: Dict[str, Any], signature: str = "", raw_body: bytes = None
    ) -> Dict[str, Any]:
        """
        Handle incoming webhook from Meta (POST request).

        Args:
            payload: Webhook payload from Meta
            signature: X-Hub-Signature-256 header for verification
            raw_body: Original raw HTTP body bytes for accurate HMAC verification

        Returns:
            Processing result with status and responses
        """
        # Verify signature if app_secret is configured
        if self.connector and self.app_secret and signature:
            # Use raw body bytes for HMAC verification (re-serializing JSON
            # produces different bytes than the original, breaking the signature)
            if raw_body:
                payload_bytes = raw_body
            else:
                import json

                payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
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

        # Record message reactions (❤️ on a message) — don't trigger bot response
        reactions_recorded = await self._process_reaction_events(payload)

        # Extract messages from webhook
        messages = await self._extract_messages(payload)

        if not messages:
            return {
                "status": "ok",
                "messages_processed": 0,
                "echo_messages_recorded": echo_recorded,
                "reactions_recorded": reactions_recorded,
                "results": [],
            }

        # Check if copilot mode is enabled for this creator
        copilot_enabled = await self._is_copilot_enabled()

        results = []
        for message in messages:
            # Skip messages from any known creator ID (prevent self-reply loop and ghost leads)
            known_ids = getattr(self, "known_creator_ids", set())
            if not known_ids:
                # Fallback if known_creator_ids not initialized
                known_ids = {self.page_id, self.ig_user_id, "17841400506734756"}

            if message.sender_id in known_ids:
                logger.info(f"Skipping message from known creator ID: {message.sender_id}")
                continue

            # Additional safety: skip if recipient_id matches sender_id
            if message.recipient_id and message.sender_id == message.recipient_id:
                logger.info(f"Skipping self-message: {message.sender_id}")
                continue

            self._record_received(message)
            # FIX 2026-02-02: Handle media messages without text
            input_preview = (
                message.text[:100]
                if message.text
                else f"[Media: {len(message.attachments)} attachment(s)]"
            )
            logger.info(f"[IG:{message.sender_id}] Input: {input_preview}")

            # =================================================================
            # LEAD ENRICHMENT: Check if lead exists, if not load history
            # This ensures returning customers are properly categorized
            # =================================================================
            lead_exists = await self._check_lead_exists(message.sender_id)
            lead_status = None

            if not lead_exists:
                logger.info(f"[IG:{message.sender_id}] New lead detected - loading history...")

                # Get username for the new lead
                username = ""
                full_name = ""
                try:
                    if self.connector:
                        profile = await self.connector.get_user_profile(message.sender_id)
                        if profile:
                            username = profile.username or ""
                            full_name = profile.name or ""
                except Exception as e:
                    logger.warning(f"[IG:{message.sender_id}] Could not get profile: {e}")

                # Enrich lead with history (creates lead + loads messages)
                lead_status = await self._enrich_new_lead(
                    sender_id=message.sender_id, username=username, full_name=full_name
                )

                if lead_status:
                    logger.info(
                        f"[IG:{message.sender_id}] Lead enriched with status: {lead_status}"
                    )
                else:
                    logger.warning(
                        f"[IG:{message.sender_id}] Lead enrichment failed, will create as 'new'"
                    )

            # Rate limit check - prevent spam and control costs
            rate_limiter = get_rate_limiter()
            allowed, reason = rate_limiter.check_limit(message.sender_id)
            if not allowed:
                logger.warning(f"[IG:{message.sender_id}] Rate limited: {reason}")

                # Still save user message even if rate-limited
                await self._save_user_message_to_db(
                    msg=message,
                    username="",
                    full_name="",
                )

                results.append(
                    {
                        "message_id": message.message_id,
                        "sender_id": message.sender_id,
                        "status": "rate_limited",
                        "reason": reason,
                    }
                )
                continue

            try:
                # DEDUPLICATION: Check if we've already processed this message_id
                if hasattr(self, "_processed_message_ids"):
                    if message.message_id in self._processed_message_ids:
                        logger.warning(
                            f"[IG:{message.sender_id}] Skipping duplicate message_id: {message.message_id}"
                        )
                        results.append(
                            {
                                "message_id": message.message_id,
                                "sender_id": message.sender_id,
                                "status": "duplicate_skipped",
                            }
                        )
                        continue
                else:
                    self._processed_message_ids = set()

                # Add to processed set (keep last 1000 to prevent memory leak)
                self._processed_message_ids.add(message.message_id)
                if len(self._processed_message_ids) > 1000:
                    # Remove oldest entries (convert to list, slice, back to set)
                    self._processed_message_ids = set(list(self._processed_message_ids)[-500:])

                # PERSISTENT DEDUP: Check if message already exists in DB
                # (survives redeploys, unlike the in-memory set above)
                if message.message_id:
                    try:
                        from api.database import SessionLocal
                        from api.models import Message as MsgModel

                        _dedup_session = SessionLocal()
                        try:
                            existing_in_db = (
                                _dedup_session.query(MsgModel.id)
                                .filter(MsgModel.platform_message_id == message.message_id)
                                .first()
                            )
                            if existing_in_db:
                                logger.info(
                                    f"[DEDUP:DB] Message {message.message_id} already in DB — skipping"
                                )
                                results.append({
                                    "message_id": message.message_id,
                                    "sender_id": message.sender_id,
                                    "status": "duplicate_db_skipped",
                                })
                                continue
                        finally:
                            _dedup_session.close()
                    except Exception as e:
                        logger.warning(f"[DEDUP:DB] Check failed: {e}")

                # Process with DM agent to get suggested response
                response = await self.process_message(message)

                # V2 compatibility: response.content (V2) or response_text (V1)
                response_text = getattr(response, "content", None) or getattr(
                    response, "response_text", ""
                )
                intent_str = (
                    response.intent.value
                    if hasattr(response.intent, "value")
                    else str(response.intent)
                )

                # CRITICAL: Never send error messages to users
                error_patterns = ["[LLM not configured]", "[Error", "[error", "error:", "Error:"]
                is_error_response = any(pattern in response_text for pattern in error_patterns)

                if is_error_response:
                    logger.error(
                        f"[IG:{message.sender_id}] LLM returned error, NOT sending to user: {response_text[:100]}"
                    )

                    # Still save user message even if LLM errored
                    await self._save_user_message_to_db(
                        msg=message,
                        username="",
                        full_name="",
                    )

                    results.append(
                        {
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "status": "llm_error",
                            "error": "LLM not available - response not sent",
                        }
                    )
                    continue

                # Get username and display name if available
                username = ""
                full_name = ""
                try:
                    if self.connector:
                        profile = await self.connector.get_user_profile(message.sender_id)
                        if profile:
                            username = profile.username
                            full_name = (
                                profile.name or ""
                            )  # Display name (e.g., "Nahuel A. Sastre")
                except Exception as e:
                    logger.warning("Failed to get user profile for %s: %s", message.sender_id, e)

                if copilot_enabled:
                    # COPILOT MODE: Save as pending approval, don't send
                    from core.copilot_service import get_copilot_service

                    copilot = get_copilot_service()

                    # --- Anti-zombie check #1: Creator already responded? ---
                    creator_already_responded = await self._has_creator_responded_recently(
                        message.sender_id, window_seconds=1800  # 30 min window
                    )
                    if creator_already_responded:
                        logger.info(
                            f"[Copilot:AntiZombie] Skipping suggestion for {message.sender_id} — "
                            "creator already responded"
                        )
                        # Still save user message to DB
                        await self._save_user_message_to_db(
                            msg=message, username=username, full_name=full_name,
                        )
                        results.append({
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "copilot_mode": True,
                            "status": "skipped_creator_responded",
                        })
                        continue

                    # --- Anti-zombie check #2: Already has pending suggestion? ---
                    try:
                        from api.database import SessionLocal
                        from api.models import Creator, Lead, Message as MsgModel

                        _session = SessionLocal()
                        try:
                            _creator = _session.query(Creator).filter_by(name=self.creator_id).first()
                            if _creator:
                                _lead = (
                                    _session.query(Lead)
                                    .filter(
                                        Lead.creator_id == _creator.id,
                                        Lead.platform_user_id.in_([message.sender_id, f"ig_{message.sender_id}"]),
                                    )
                                    .first()
                                )
                                if _lead:
                                    existing_pending = (
                                        _session.query(MsgModel)
                                        .filter(
                                            MsgModel.lead_id == _lead.id,
                                            MsgModel.role == "assistant",
                                            MsgModel.status == "pending_approval",
                                        )
                                        .first()
                                    )
                                    if existing_pending:
                                        logger.info(
                                            f"[Copilot:AntiZombie] Skipping — already has pending "
                                            f"suggestion {existing_pending.id} for {message.sender_id}"
                                        )
                                        # Still save user message
                                        await self._save_user_message_to_db(
                                            msg=message, username=username, full_name=full_name,
                                        )
                                        results.append({
                                            "message_id": message.message_id,
                                            "sender_id": message.sender_id,
                                            "copilot_mode": True,
                                            "status": "skipped_existing_pending",
                                        })
                                        continue
                        finally:
                            _session.close()
                    except Exception as e:
                        logger.warning(f"[Copilot:AntiZombie] Pending check failed: {e}")

                    # Extract media info for attachment messages (same as _save_user_message_to_db)
                    copilot_user_msg = message.text
                    copilot_msg_metadata = {}

                    # Handle story messages first (story data is separate from attachments)
                    if message.story:
                        story_data = message.story
                        if story_data.get("reply_to"):
                            copilot_msg_metadata["type"] = "story_reply"
                            copilot_msg_metadata["link"] = story_data["reply_to"].get("link", "")
                        elif story_data.get("mention"):
                            copilot_msg_metadata["type"] = "story_mention"
                            copilot_msg_metadata["link"] = story_data["mention"].get("link", "")
                        # Extract CDN URL from attachments for stories
                        if message.attachments:
                            att = message.attachments[0]
                            cdn_url = (
                                att.get("video_data", {}).get("url")
                                or att.get("image_data", {}).get("url")
                                or (att.get("payload", {}).get("url") if isinstance(att.get("payload"), dict) else None)
                                or att.get("url")
                            )
                            if cdn_url:
                                copilot_msg_metadata["url"] = cdn_url
                    elif message.attachments:
                        media_info = self._extract_media_info(message.attachments)
                        if media_info:
                            copilot_msg_metadata["type"] = media_info.get("type", "unknown")
                            if media_info.get("url"):
                                copilot_msg_metadata["url"] = media_info["url"]
                            if media_info.get("permalink"):
                                copilot_msg_metadata["permalink"] = media_info["permalink"]
                            if not copilot_user_msg:
                                media_type = media_info.get("type", "media")
                                copilot_user_msg = {
                                    "image": "Sent a photo",
                                    "video": "Sent a video",
                                    "audio": "Sent a voice message",
                                    "gif": "Sent a GIF",
                                    "sticker": "Sent a sticker",
                                    "story_mention": "Mentioned you in their story",
                                    "share": "Shared a post",
                                    "shared_reel": "Shared a reel",
                                }.get(media_type, "Sent an attachment")
                    if not copilot_user_msg:
                        copilot_user_msg = "[Media/Attachment]"

                    pending = await copilot.create_pending_response(
                        creator_id=self.creator_id,
                        lead_id="",  # Will be set by service
                        follower_id=message.sender_id,
                        platform="instagram",
                        user_message=copilot_user_msg,
                        user_message_id=message.message_id,
                        suggested_response=response_text,
                        intent=intent_str,
                        confidence=response.confidence,
                        username=username,
                        full_name=full_name,
                        msg_metadata=copilot_msg_metadata if copilot_msg_metadata else None,
                    )

                    logger.info(
                        f"[Copilot] Created pending response {pending.id} for {message.sender_id}"
                    )

                    results.append(
                        {
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "copilot_mode": True,
                            "pending_id": pending.id,
                            "suggested_response": response_text,
                            "intent": intent_str,
                            "confidence": response.confidence,
                            "status": "pending_approval",
                        }
                    )
                else:
                    # AUTOPILOT MODE: Check if creator already responded before sending
                    creator_already_responded = await self._has_creator_responded_recently(
                        message.sender_id, window_seconds=300  # 5 minute window
                    )

                    if creator_already_responded:
                        # Creator already replied manually, skip bot response
                        # BUT still save user message to database!
                        logger.info(
                            f"[AntiDup] Skipping autopilot response to {message.sender_id} - "
                            "creator already responded"
                        )

                        # Save user message even if bot doesn't respond
                        await self._save_user_message_to_db(
                            msg=message,
                            username=username,
                            full_name=full_name,
                        )

                        results.append(
                            {
                                "message_id": message.message_id,
                                "sender_id": message.sender_id,
                                "copilot_mode": False,
                                "status": "skipped_creator_responded",
                                "reason": "Creator already responded manually",
                            }
                        )
                    else:
                        # AUTOPILOT MODE: Send response immediately
                        await self.send_response(message.sender_id, response.response_text)
                        self._record_response(message, response)

                        # CRITICAL FIX: Save messages to database
                        # Without this, messages only exist in memory and are lost!
                        await self._save_messages_to_db(
                            msg=message,
                            response=response,
                            username=username,
                            full_name=full_name,
                        )

                        results.append(
                            {
                                "message_id": message.message_id,
                                "sender_id": message.sender_id,
                                "copilot_mode": False,
                                "response": response.response_text,
                                "intent": (
                                    response.intent.value
                                    if hasattr(response.intent, "value")
                                    else str(response.intent)
                                ),
                                "confidence": response.confidence,
                                "status": "sent",
                            }
                        )

            except Exception as e:
                import traceback

                logger.error(
                    f"Error processing message {message.message_id}: {e}\n{traceback.format_exc()}"
                )
                self.status.errors += 1
                results.append(
                    {
                        "message_id": message.message_id,
                        "sender_id": message.sender_id,
                        "error": str(e),
                    }
                )

        return {
            "status": "ok",
            "messages_processed": len(messages),
            "echo_messages_recorded": echo_recorded,
            "copilot_mode": copilot_enabled,
            "results": results,
        }

    # =========================================================================
    # LEAD HISTORY ENRICHMENT (Beta feature - Feb 2026)
    # When a new lead sends a message, load their conversation history
    # to properly categorize them (new vs returning vs existing customer)
    # =========================================================================

    async def _check_lead_exists(self, sender_id: str) -> bool:
        """Check if a lead already exists in the database."""
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=self.creator_id).first()
                if not creator:
                    return False

                # Check both with and without ig_ prefix
                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, platform_user_id=sender_id)
                    .first()
                )

                if not lead:
                    lead = (
                        session.query(Lead)
                        .filter_by(creator_id=creator.id, platform_user_id=f"ig_{sender_id}")
                        .first()
                    )

                return lead is not None
            finally:
                session.close()
        except Exception as e:
            logger.error(f"[LeadCheck] Error checking lead existence: {e}")
            return False  # Assume doesn't exist on error

    async def _find_conversation_for_user(self, sender_id: str) -> Optional[str]:
        """Find the conversation ID for a specific user by searching conversations."""
        if not self.connector:
            return None

        try:
            # Get recent conversations and find the one with this participant
            conversations = await self.connector.get_conversations(limit=50)

            for conv in conversations:
                participants = conv.get("participants", {}).get("data", [])
                for participant in participants:
                    if participant.get("id") == sender_id:
                        logger.info(
                            f"[LeadHistory] Found conversation {conv['id']} for user {sender_id}"
                        )
                        return conv.get("id")

            logger.info(f"[LeadHistory] No existing conversation found for {sender_id}")
            return None

        except Exception as e:
            logger.error(f"[LeadHistory] Error finding conversation: {e}")
            return None

    async def _fetch_conversation_history(self, sender_id: str) -> Optional[dict]:
        """
        Fetch conversation history from Instagram API for a new lead.
        Returns dict with messages and oldest_message_date if found.
        """
        if not self.connector:
            logger.warning("[LeadHistory] No connector available")
            return None

        try:
            # Find the conversation for this user
            conv_id = await self._find_conversation_for_user(sender_id)
            if not conv_id:
                return None

            # Get all messages from this conversation (last year)
            from datetime import timedelta

            cutoff_date = datetime.now(timezone.utc) - timedelta(days=365)

            messages = await self.connector.get_all_conversation_messages(
                conversation_id=conv_id,
                max_pages=10,  # Limit to prevent too many API calls
                cutoff_date=cutoff_date,
            )

            if not messages:
                logger.info(f"[LeadHistory] No messages found for {sender_id}")
                return None

            # Find oldest message date
            oldest_date = None
            for msg in messages:
                created_time_str = msg.get("created_time", "")
                if created_time_str:
                    try:
                        created_time = datetime.fromisoformat(
                            created_time_str.replace("Z", "+00:00").replace("+0000", "+00:00")
                        )
                        if oldest_date is None or created_time < oldest_date:
                            oldest_date = created_time
                    except Exception as e:
                        logger.warning("Suppressed error in created_time = datetime.fromisoformat(: %s", e)

            logger.info(
                f"[LeadHistory] Found {len(messages)} messages for {sender_id}, "
                f"oldest: {oldest_date}"
            )

            return {
                "messages": messages,
                "oldest_message_date": oldest_date,
                "conversation_id": conv_id,
                "message_count": len(messages),
            }

        except Exception as e:
            logger.error(f"[LeadHistory] Error fetching history: {e}")
            return None

    def _categorize_lead_by_history(self, oldest_date: Optional[datetime]) -> str:
        """
        Categorize a lead based on the age of their oldest message.

        Returns:
            - "existing_customer" if oldest message > 30 days ago
            - "returning" if oldest message > 7 days ago
            - "new" if recent or no history
        """
        if not oldest_date:
            return "new"

        now = datetime.now(timezone.utc)
        days_old = (now - oldest_date).days

        if days_old > 30:
            return "existing_customer"
        elif days_old > 7:
            return "returning"
        else:
            return "new"

    async def _create_lead_with_history(
        self,
        sender_id: str,
        username: str,
        full_name: str,
        status: str,
        history: Optional[dict],
        profile_pic_url: str = "",
        profile_pending: bool = False,
    ) -> Optional[str]:
        """
        Create a COMPLETE lead with pre-loaded conversation history.

        Args:
            sender_id: Instagram user ID
            username: Instagram username
            full_name: Display name
            status: Lead status (new, returning, existing_customer)
            history: Dict with messages and metadata from _fetch_conversation_history
            profile_pic_url: Profile picture URL from Instagram API
            profile_pending: If True, profile fetch failed and will be retried

        Returns:
            Lead ID (string) if created successfully
        """
        # Prevent creating leads for creator's own IDs (prevents ghost leads)
        known_ids = getattr(self, "known_creator_ids", set())
        if not known_ids:
            known_ids = {self.page_id, self.ig_user_id, "17841400506734756"}
        if sender_id in known_ids:
            logger.warning(
                f"[LeadHistory] Skipping lead creation for known creator ID: {sender_id}"
            )
            return None

        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead, Message
            from core.link_preview import extract_link_preview, extract_urls

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=self.creator_id).first()
                if not creator:
                    logger.error(f"[LeadHistory] Creator {self.creator_id} not found")
                    return None

                # Build context with profile_pending flag if needed
                context = {}
                if profile_pending:
                    context["profile_pending"] = True
                    context["profile_retry_at"] = None

                # Create COMPLETE lead with all fields
                # Use raw sender_id (no ig_ prefix) for consistency
                # Handle race condition with unique constraint
                try:
                    lead = Lead(
                        creator_id=creator.id,
                        platform="instagram",
                        platform_user_id=sender_id,  # No prefix - prevents duplicates
                        username=username,
                        full_name=full_name,
                        profile_pic_url=profile_pic_url,
                        status=status,
                        context=context,
                        purchase_intent=(
                            0.1
                            if status == "returning"
                            else (0.2 if status == "existing_customer" else 0.0)
                        ),
                    )
                    session.add(lead)
                    session.commit()

                    logger.info(
                        f"[LeadHistory] Created COMPLETE lead {lead.id} for @{username} "
                        f"(name={full_name[:15] if full_name else 'N/A'}, "
                        f"pic={'Yes' if profile_pic_url else 'No'}, status={status}"
                        f"{', profile_pending=True' if profile_pending else ''})"
                    )
                except Exception as e:
                    # Race condition: another request created the lead
                    session.rollback()
                    if "uq_lead_creator_platform" in str(e) or "duplicate" in str(e).lower():
                        logger.info(
                            "[LeadHistory] Lead already exists (race condition), fetching..."
                        )
                        lead = (
                            session.query(Lead)
                            .filter(
                                Lead.creator_id == creator.id,
                                Lead.platform_user_id.in_([sender_id, f"ig_{sender_id}"]),
                            )
                            .first()
                        )
                        if not lead:
                            logger.error(
                                "[LeadHistory] Could not find lead after constraint error"
                            )
                            return None
                    else:
                        raise

                # Save historical messages with link previews
                if history and history.get("messages"):
                    messages_saved = 0
                    previews_generated = 0

                    for msg in history["messages"]:
                        msg_id = msg.get("id")
                        msg_text = msg.get("message", "")
                        msg_from = msg.get("from", {})
                        msg_time_str = msg.get("created_time")

                        if not msg_text:
                            continue

                        # Check if message already exists
                        existing = (
                            session.query(Message).filter_by(platform_message_id=msg_id).first()
                        )
                        if existing:
                            continue

                        # Determine role (is this from the creator or the follower?)
                        # Primary check: if sender matches the follower's ID, it's from the follower
                        # This is more reliable than checking against page_id/ig_user_id
                        # which may not match the ID format in the Conversations API
                        msg_sender_id = str(msg_from.get("id", ""))
                        is_from_follower = msg_sender_id == str(sender_id)
                        is_from_creator = (
                            not is_from_follower
                            and msg_sender_id in [self.page_id, self.ig_user_id]
                        ) if msg_sender_id else False

                        # If sender is follower → "user", if sender is creator → "assistant"
                        # If neither matched, use fallback: non-follower = creator
                        if is_from_follower:
                            role = "user"
                        elif is_from_creator or (msg_sender_id and not is_from_follower):
                            role = "assistant"
                        else:
                            role = "user"  # Default to user if no ID available

                        # Parse timestamp
                        created_at = None
                        if msg_time_str:
                            try:
                                created_at = datetime.fromisoformat(
                                    msg_time_str.replace("Z", "+00:00").replace("+0000", "+00:00")
                                )
                            except Exception as e:
                                logger.warning("Suppressed error in created_at = datetime.fromisoformat(: %s", e)

                        # Generate link preview if message has URLs
                        msg_metadata = None
                        urls = extract_urls(msg_text)
                        if urls:
                            try:
                                preview = await extract_link_preview(urls[0])
                                if preview:
                                    msg_metadata = {"link_preview": preview}
                                    previews_generated += 1
                            except Exception as e:
                                logger.warning("Suppressed error in preview = await extract_link_preview(urls[0]): %s", e)

                        new_msg = Message(
                            lead_id=lead.id,
                            role=role,
                            content=msg_text,
                            status="sent",
                            platform_message_id=msg_id,
                            approved_by="historical_sync",
                            msg_metadata=msg_metadata,
                        )
                        if created_at:
                            new_msg.created_at = created_at

                        session.add(new_msg)
                        messages_saved += 1

                    session.commit()
                    logger.info(
                        f"[LeadHistory] Saved {messages_saved} messages "
                        f"({previews_generated} link previews) for lead {lead.id}"
                    )

                return str(lead.id)

            finally:
                session.close()

        except Exception as e:
            logger.error(f"[LeadHistory] Error creating lead with history: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return None

    async def _enrich_new_lead(
        self, sender_id: str, username: str = "", full_name: str = ""
    ) -> Optional[str]:
        """
        Main method to enrich a new lead with conversation history.
        Called when we detect a message from an unknown sender.

        Creates a COMPLETE lead with:
        - username, full_name, profile_pic_url (from API)
        - categorized status based on history
        - historical messages with link_previews

        AUTOMATIC RETRY: If profile fetch fails with transient error,
        the lead is created with profile_pending=True in context,
        and a background task will retry the profile fetch later.

        Returns:
            Lead status ("new", "returning", "existing_customer") or None if failed
        """
        logger.info(f"[LeadHistory] Enriching new lead: {sender_id}")

        # Fetch user profile data with automatic retry
        profile_pic_url = ""
        profile_pending = False
        try:
            from core.instagram_profile import fetch_instagram_profile_with_retry

            result = await fetch_instagram_profile_with_retry(sender_id, self.access_token)
            if result.success and result.profile:
                profile = result.profile
                if not full_name and profile.get("name"):
                    full_name = profile["name"]
                if not username and profile.get("username"):
                    username = profile["username"]
                profile_pic_url = profile.get("profile_pic", "")

                # Upload profile pic to Cloudinary for permanent storage
                if profile_pic_url:
                    cloudinary_svc = get_cloudinary_service()
                    if cloudinary_svc.is_configured:
                        cloud_result = cloudinary_svc.upload_from_url(
                            url=profile_pic_url,
                            media_type="image",
                            folder=f"clonnect/{self.creator_id or 'unknown'}/profiles",
                            public_id=f"profile_{sender_id}",
                        )
                        if cloud_result.success and cloud_result.url:
                            logger.info(
                                f"[LeadHistory] Profile pic uploaded to Cloudinary: {sender_id}"
                            )
                            profile_pic_url = cloud_result.url
                        else:
                            logger.warning(
                                f"[LeadHistory] Cloudinary upload failed: {cloud_result.error}"
                            )

                logger.info(
                    f"[LeadHistory] Got profile for {sender_id}: "
                    f"name={full_name[:20] if full_name else 'N/A'}, "
                    f"pic={'Yes' if profile_pic_url else 'No'}"
                )
            else:
                # Profile fetch failed - mark for later retry if transient
                if result.is_transient:
                    profile_pending = True
                    logger.warning(
                        f"[LeadHistory] Profile fetch transient error for {sender_id}: {result.error_message}. "
                        "Will retry automatically."
                    )
                else:
                    logger.warning(
                        f"[LeadHistory] Profile fetch permanent error for {sender_id}: {result.error_message}"
                    )
        except Exception as e:
            profile_pending = True  # Assume transient on exception
            logger.warning(f"[LeadHistory] Failed to fetch profile for {sender_id}: {e}")

        # Fetch conversation history from Instagram API
        history = await self._fetch_conversation_history(sender_id)

        # Categorize based on history
        oldest_date = history.get("oldest_message_date") if history else None
        status = self._categorize_lead_by_history(oldest_date)

        logger.info(f"[LeadHistory] Categorized {sender_id} as '{status}' (oldest: {oldest_date})")

        # Create lead with history
        lead_id = await self._create_lead_with_history(
            sender_id=sender_id,
            username=username,
            full_name=full_name,
            profile_pic_url=profile_pic_url,
            status=status,
            history=history,
            profile_pending=profile_pending,
        )

        # Queue profile retry if needed
        if lead_id and profile_pending:
            await self._queue_profile_retry(sender_id, lead_id)

        if lead_id:
            return status
        return None

    async def _queue_profile_retry(self, sender_id: str, lead_id: str) -> None:
        """
        Queue a lead for profile retry.
        Uses the sync_queue table with a special task_type.
        """
        try:
            from api.database import SessionLocal
            from api.models import SyncQueue

            session = SessionLocal()
            try:
                # Check if already queued
                existing = (
                    session.query(SyncQueue)
                    .filter_by(
                        creator_id=self.creator_id,
                        conversation_id=f"profile_retry:{sender_id}",
                        status="pending",
                    )
                    .first()
                )
                if existing:
                    logger.debug(f"[ProfileRetry] Already queued for {sender_id}")
                    return

                # Queue for retry
                queue_item = SyncQueue(
                    creator_id=self.creator_id,
                    conversation_id=f"profile_retry:{sender_id}",
                    status="pending",
                    attempts=0,
                )
                session.add(queue_item)
                session.commit()
                logger.info(
                    f"[ProfileRetry] Queued profile retry for {sender_id} (lead: {lead_id})"
                )

            finally:
                session.close()

        except Exception as e:
            logger.error(f"[ProfileRetry] Failed to queue retry for {sender_id}: {e}")

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
                            attachments = message_data.get("attachments", [])

                            # Derive display text for attachment-only echoes
                            if not text and attachments:
                                att_type = attachments[0].get("type", "attachment")
                                text = {
                                    "image": "Sent a photo",
                                    "video": "Sent a video",
                                    "audio": "Sent a voice message",
                                    "share": "Shared content",
                                    "template": "Shared content",
                                    "fallback": "Shared content",
                                }.get(att_type, "Sent an attachment")

                            if text:  # Record text AND attachment echo messages
                                echo_messages.append(
                                    {
                                        "message_id": message_data.get("mid", ""),
                                        "sender_id": sender_id,  # This is the page/creator
                                        "recipient_id": recipient_id,  # This is the follower
                                        "text": text,
                                        "timestamp": messaging.get("timestamp", 0),
                                        "attachments": attachments,  # Pass raw attachments for media capture
                                    }
                                )
                                logger.info(
                                    f"[Echo] Detected creator response to {recipient_id}: {text[:50]}..."
                                )

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
                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, platform_user_id=follower_id)
                    .first()
                )

                if not lead:
                    # Also check with ig_ prefix
                    lead = (
                        session.query(Lead)
                        .filter_by(creator_id=creator.id, platform_user_id=f"ig_{follower_id}")
                        .first()
                    )

                if not lead:
                    logger.info(f"[Echo] Lead not found for {follower_id}, skipping record")
                    return False

                # Check if this exact message already exists (avoid duplicates)
                existing = (
                    session.query(Message)
                    .filter_by(lead_id=lead.id, platform_message_id=echo_msg["message_id"])
                    .first()
                )

                if existing:
                    logger.debug(f"[Echo] Message {echo_msg['message_id']} already recorded")
                    # Still update last_contact_at even if message exists
                    lead.last_contact_at = datetime.now(timezone.utc)
                    session.commit()
                    return True

                # Extract media info from echo attachments (if any)
                msg_meta: Dict[str, Any] = {"source": "instagram_echo", "is_manual": True}
                attachments = echo_msg.get("attachments", [])
                if attachments:
                    media_info = self._extract_media_info(attachments)
                    if media_info:
                        media_url = media_info.get("url")
                        media_type = media_info.get("type", "unknown")

                        # Capture CDN media permanently before it expires
                        if media_url:
                            try:
                                from services.media_capture_service import capture_media_from_url, is_cdn_url

                                uploaded = False
                                cloudinary_svc = get_cloudinary_service()
                                if cloudinary_svc.is_configured and is_cdn_url(media_url):
                                    folder = f"clonnect/{self.creator_id or 'unknown'}/media"
                                    result = cloudinary_svc.upload_from_url(
                                        url=media_url,
                                        media_type=media_type,
                                        folder=folder,
                                        tags=["instagram", "echo", f"creator_{self.creator_id}"],
                                    )
                                    if result.success:
                                        media_info["original_url"] = media_url
                                        media_info["url"] = result.url
                                        media_info["cloudinary_id"] = result.public_id
                                        uploaded = True
                                        logger.info(f"[Echo] Media uploaded to Cloudinary: {result.public_id}")

                                # Fallback: base64 or permanent_url
                                if not uploaded and is_cdn_url(media_url):
                                    captured = await capture_media_from_url(
                                        url=media_url,
                                        media_type=media_type,
                                        creator_id=self.creator_id,
                                        use_cloudinary=False,
                                    )
                                    if captured:
                                        if captured.startswith("data:"):
                                            media_info["thumbnail_base64"] = captured
                                        else:
                                            media_info["permanent_url"] = captured
                            except Exception as e:
                                logger.warning(f"[Echo] Media capture failed: {e}")

                        # Merge media fields into msg_metadata (outside media_url check
                        # so share attachments with only permalink/type also get merged)
                        for key in ("type", "url", "permanent_url", "thumbnail_base64",
                                    "original_url", "cloudinary_id", "permalink"):
                            if key in media_info:
                                msg_meta[key] = media_info[key]

                # Record the creator's manual response
                msg = Message(
                    lead_id=lead.id,
                    role="assistant",
                    content=echo_msg["text"],
                    status="sent",
                    approved_by="creator_manual",  # Mark as manually sent by creator
                    platform_message_id=echo_msg["message_id"],
                    msg_metadata=msg_meta,
                )
                session.add(msg)

                # Update lead last_contact
                lead.last_contact_at = datetime.now(timezone.utc)
                session.commit()

                # Invalidate cache and notify frontend
                try:
                    from api.cache import api_cache

                    api_cache.invalidate(f"conversations:{self.creator_id}")
                    api_cache.invalidate(
                        f"follower_detail:{self.creator_id}:{lead.platform_user_id}"
                    )
                except Exception:
                    pass

                try:
                    from api.routers.events import notify_creator

                    await notify_creator(
                        self.creator_id,
                        "new_message",
                        {
                            "follower_id": lead.platform_user_id,
                            "role": "assistant",
                        },
                    )
                except Exception:
                    pass

                logger.info(f"[Echo] Recorded creator manual response to {follower_id}")
                return True

            finally:
                session.close()

        except Exception as e:
            logger.error(f"[Echo] Error recording creator response: {e}")
            return False

    async def _process_reaction_events(self, payload: Dict[str, Any]) -> int:
        """
        Process message reaction events from webhook.

        Instagram sends reactions as:
        {
            "sender": {"id": "user_123"},
            "recipient": {"id": "page_123"},
            "timestamp": 1704067200000,
            "reaction": {
                "mid": "mid.abc123",       # message being reacted to
                "action": "react",          # "react" or "unreact"
                "reaction": "love",         # reaction type
                "emoji": "❤️"               # emoji (may not always be present)
            }
        }

        Reactions are saved as messages with metadata.type="reaction" so the
        frontend can render them as small emoji bubbles. They do NOT trigger
        the bot response pipeline.
        """
        recorded = 0

        try:
            for entry in payload.get("entry", []):
                for messaging in entry.get("messaging", []):
                    if "reaction" not in messaging:
                        continue

                    reaction_data = messaging["reaction"]
                    action = reaction_data.get("action", "")

                    # Only process "react" (ignore "unreact" — we don't delete messages)
                    if action != "react":
                        continue

                    sender_id = messaging.get("sender", {}).get("id", "")
                    recipient_id = messaging.get("recipient", {}).get("id", "")

                    # Determine emoji
                    emoji = reaction_data.get("emoji", "")
                    if not emoji:
                        # Map reaction type names to emojis
                        reaction_type = reaction_data.get("reaction", "love")
                        emoji_map = {
                            "love": "❤️",
                            "haha": "😂",
                            "wow": "😮",
                            "sad": "😢",
                            "angry": "😠",
                            "like": "👍",
                        }
                        emoji = emoji_map.get(reaction_type, "❤️")

                    # Ensure heart has variation selector
                    if emoji == "❤" or emoji == "\u2764":
                        emoji = "❤️"

                    reacted_to_mid = reaction_data.get("mid", "")

                    # Determine role: if sender is a known creator ID, it's from the creator
                    known_ids = getattr(self, "known_creator_ids", set())
                    if not known_ids:
                        known_ids = {self.page_id, self.ig_user_id}
                    role = "assistant" if sender_id in known_ids else "user"

                    # The follower_id is the other party
                    follower_id = recipient_id if role == "user" else sender_id
                    # Wait, if role=user (follower reacted), sender=follower, recipient=page
                    # If role=assistant (creator reacted), sender=page, recipient=follower
                    follower_id = sender_id if role == "user" else recipient_id

                    # Save to DB
                    try:
                        from api.database import SessionLocal
                        from api.models import Creator, Lead, Message

                        session = SessionLocal()
                        try:
                            creator = session.query(Creator).filter_by(name=self.creator_id).first()
                            if not creator:
                                continue

                            lead = (
                                session.query(Lead)
                                .filter_by(creator_id=creator.id, platform_user_id=follower_id)
                                .first()
                            )
                            if not lead:
                                lead = (
                                    session.query(Lead)
                                    .filter_by(creator_id=creator.id, platform_user_id=f"ig_{follower_id}")
                                    .first()
                                )
                            if not lead:
                                logger.debug(f"[Reaction] Lead not found for {follower_id}")
                                continue

                            # Check if we already recorded this exact reaction
                            # Use reacted_to_mid + emoji + sender as uniqueness key
                            # msg_metadata is JSON (not JSONB), so use text() for ->> operator
                            from sqlalchemy import text as sa_text
                            existing = (
                                session.query(Message)
                                .filter(
                                    Message.lead_id == lead.id,
                                    sa_text("msg_metadata->>'type' = 'reaction'"),
                                    sa_text("msg_metadata->>'reacted_to_mid' = :mid"),
                                    Message.role == role,
                                )
                                .params(mid=reacted_to_mid)
                                .first()
                            )
                            if existing:
                                logger.debug(f"[Reaction] Already recorded reaction on {reacted_to_mid}")
                                continue

                            msg = Message(
                                lead_id=lead.id,
                                role=role,
                                content=emoji,
                                status="sent",
                                msg_metadata={
                                    "type": "reaction",
                                    "emoji": emoji,
                                    "reacted_to_mid": reacted_to_mid,
                                },
                            )
                            session.add(msg)
                            session.commit()
                            recorded += 1
                            logger.info(
                                f"[Reaction] {role} reacted {emoji} to {reacted_to_mid} "
                                f"(lead={lead.username})"
                            )

                            # Invalidate cache and notify frontend
                            try:
                                from api.cache import api_cache

                                api_cache.invalidate(f"conversations:{self.creator_id}")
                                api_cache.invalidate(
                                    f"follower_detail:{self.creator_id}:{lead.platform_user_id}"
                                )
                            except Exception:
                                pass

                            try:
                                from api.routers.events import notify_creator

                                await notify_creator(
                                    self.creator_id,
                                    "new_message",
                                    {
                                        "follower_id": lead.platform_user_id,
                                        "role": role,
                                    },
                                )
                            except Exception:
                                pass
                        finally:
                            session.close()
                    except Exception as e:
                        logger.error(f"[Reaction] Error saving reaction: {e}")

        except Exception as e:
            logger.error(f"[Reaction] Error processing reaction events: {e}")

        return recorded

    async def _has_creator_responded_recently(
        self, follower_id: str, window_seconds: int = 300
    ) -> bool:
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
                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, platform_user_id=follower_id)
                    .first()
                )

                if not lead:
                    lead = (
                        session.query(Lead)
                        .filter_by(creator_id=creator.id, platform_user_id=f"ig_{follower_id}")
                        .first()
                    )

                if not lead:
                    return False

                # Check for recent creator messages
                from datetime import timedelta

                cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)

                recent_creator_msg = (
                    session.query(Message)
                    .filter(
                        Message.lead_id == lead.id,
                        Message.role == "assistant",
                        Message.created_at >= cutoff_time,
                    )
                    .order_by(Message.created_at.desc())
                    .first()
                )

                if recent_creator_msg:
                    # Check if it was a manual response or recent bot response
                    is_manual = (
                        recent_creator_msg.approved_by == "creator_manual"
                        or (recent_creator_msg.msg_metadata or {}).get("is_manual") == True
                    )

                    # Get the most recent user message
                    last_user_msg = (
                        session.query(Message)
                        .filter(Message.lead_id == lead.id, Message.role == "user")
                        .order_by(Message.created_at.desc())
                        .first()
                    )

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

    def _extract_media_info(self, attachments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Extract media URL and type from Instagram message attachments.

        FIX 2026-02-02: Support both Meta formats:
        - New format (Instagram Messaging API): payload.url
        - Legacy format: image_data.url, video_data.url, audio_data.url

        Args:
            attachments: List of attachment objects from webhook

        Returns:
            Dict with type, url, and captured_at if media found, None otherwise
        """
        if not attachments:
            return None

        for att in attachments:
            att_type = (att.get("type") or "").lower()

            # Handle share/reel attachments first — these have permalink, not CDN media
            # Instagram share webhook format: {"type": "share", "share": {"link": "https://instagram.com/p/..."}}
            if att_type in ("share", "reel"):
                share_data = att.get("share", {})
                share_link = share_data.get("link", "") if isinstance(share_data, dict) else ""
                if share_link and "reel" in share_link.lower():
                    media_type = "shared_reel"
                elif att_type == "reel":
                    media_type = "shared_reel"
                else:
                    media_type = "share"

                result = {
                    "type": media_type,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                }
                if share_link:
                    result["permalink"] = share_link
                return result

            # Try new payload format first (Instagram Messaging API)
            payload = att.get("payload", {})
            payload_url = payload.get("url") if isinstance(payload, dict) else None

            # Check for legacy structure-based formats
            has_video = att.get("video_data") is not None
            has_image = att.get("image_data") is not None
            has_audio = att.get("audio_data") is not None
            is_sticker = att.get("render_as_sticker", False)
            is_animated = att.get("animated_gif_url") is not None

            # Get URL: try payload.url first, then legacy formats, then fallbacks
            if payload_url:
                media_url = payload_url
            elif has_video:
                media_url = att.get("video_data", {}).get("url")
            elif has_image:
                media_url = att.get("image_data", {}).get("url")
            elif has_audio:
                media_url = att.get("audio_data", {}).get("url")
            else:
                # Try common URL fields as fallbacks
                media_url = (
                    att.get("url")
                    or att.get("file_url")
                    or att.get("preview_url")
                    or att.get("src")
                    or att.get("source")
                    or att.get("link")
                    # Try nested structures (share.link for shares that reach here)
                    or att.get("share", {}).get("link")
                    or att.get("target", {}).get("url")
                    or att.get("media", {}).get("url")
                    or att.get("media", {}).get("source")
                )

            # Determine media type
            if "video" in att_type or has_video:
                media_type = "video"
            elif "audio" in att_type or has_audio:
                media_type = "audio"
            elif is_sticker:
                media_type = "sticker"
            elif is_animated or "gif" in att_type:
                media_type = "gif"
                media_url = att.get("animated_gif_url") or media_url
            elif "image" in att_type or "photo" in att_type or has_image:
                media_type = "image"
            else:
                # Instagram sends "unsupported_type" for various media — treat as unknown renderable
                media_type = "unknown" if att_type == "unsupported_type" else (att_type or "file")

            if media_url:
                return {
                    "type": media_type,
                    "url": media_url,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                }

        # No URL found - try deep extraction as last resort
        if attachments:
            att = attachments[0]
            raw_keys = list(att.keys())
            logger.warning(
                f"[MediaExtract] No URL found via standard methods. Attachment keys: {raw_keys}"
            )

            # Deep search for any URL-like field in the attachment
            fallback_url = None
            for key, value in att.items():
                if isinstance(value, str) and (
                    value.startswith("http://") or value.startswith("https://")
                ):
                    fallback_url = value
                    logger.info(f"[MediaExtract] Found fallback URL in field '{key}'")
                    break
                elif isinstance(value, dict):
                    for subkey, subvalue in value.items():
                        if isinstance(subvalue, str) and (
                            subvalue.startswith("http://") or subvalue.startswith("https://")
                        ):
                            fallback_url = subvalue
                            logger.info(
                                f"[MediaExtract] Found fallback URL in nested field '{key}.{subkey}'"
                            )
                            break
                    if fallback_url:
                        break

            return {
                "type": "unknown",
                "url": fallback_url,  # May still be None, but we tried harder
                "raw_keys": raw_keys,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }

        return None

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
                            logger.info("Skipping echo message (sent by bot)")
                            continue

                        # Skip if sender is same as recipient (edge case)
                        sender_id = messaging.get("sender", {}).get("id", "")
                        recipient_id = messaging.get("recipient", {}).get("id", "")
                        if sender_id == recipient_id:
                            logger.info("Skipping message where sender==recipient")
                            continue

                        msg = InstagramMessage(
                            message_id=message_data.get("mid", ""),
                            sender_id=sender_id,
                            recipient_id=recipient_id,
                            text=message_data.get("text", ""),
                            timestamp=datetime.fromtimestamp(messaging.get("timestamp", 0) / 1000),
                            attachments=message_data.get("attachments", []),
                            story=message_data.get("story"),  # Story reply/mention data
                            reactions=message_data.get("reactions", {}).get("data", []),
                        )
                        # FIX 2026-02-02: Process text, media, AND story messages
                        if msg.text or msg.attachments or msg.story:
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

        # Get profile and update lead if needed (FIX 2026-02-02: update profile_pic when user responds)
        username, profile_pic_url = await self._get_profile_and_update_lead(message.sender_id)

        # FIX 2026-02-02: Handle media messages without text
        message_text = message.text
        media_info = None
        story_info = None

        # FIX 2026-02-02: Handle STORY messages (reply_to, mention)
        # Stories contain CDN URLs in attachments that expire in 24h - capture immediately!
        if message.story:
            story_data = message.story
            story_type = None
            story_link = None

            if story_data.get("reply_to"):
                story_type = "story_reply"
                story_link = story_data["reply_to"].get("link", "")
            elif story_data.get("mention"):
                story_type = "story_mention"
                story_link = story_data["mention"].get("link", "")

            if story_type:
                # Extract CDN URL from attachments (this is the actual video/image)
                cdn_url = None
                if message.attachments:
                    att = message.attachments[0]
                    cdn_url = (
                        att.get("video_data", {}).get("url")
                        or att.get("image_data", {}).get("url")
                        or (
                            att.get("payload", {}).get("url")
                            if isinstance(att.get("payload"), dict)
                            else None
                        )
                        or att.get("url")
                    )

                # Get reaction emoji if present
                reaction_emoji = None
                if message.reactions:
                    reaction_emoji = message.reactions[0].get("emoji", "❤️")
                    if reaction_emoji:
                        story_type = "story_reaction"

                # Build story info
                story_info = {
                    "type": story_type,
                    "url": cdn_url or "",  # CDN URL for video/image
                    "link": story_link,  # Permalink for opening in Instagram
                }
                if reaction_emoji:
                    story_info["emoji"] = reaction_emoji

                # Set message text based on story type
                if not message_text:
                    if story_type == "story_reaction":
                        message_text = f"Reacción {reaction_emoji} a story"
                    elif story_type == "story_reply":
                        message_text = "Respuesta a story"
                    elif story_type == "story_mention":
                        message_text = "Mención en story"

                logger.info(
                    f"[IG:{message.sender_id}] Story message: type={story_type}, "
                    f"cdn_url={'Yes' if cdn_url else 'No'}, link={'Yes' if story_link else 'No'}"
                )

                # Capture CDN media immediately before it expires!
                if cdn_url:
                    from services.media_capture_service import capture_media_from_url, is_cdn_url

                    if is_cdn_url(cdn_url):
                        cloudinary_svc = get_cloudinary_service()
                        if cloudinary_svc.is_configured:
                            folder = f"clonnect/{self.creator_id or 'unknown'}/stories"
                            result = cloudinary_svc.upload_from_url(
                                url=cdn_url,
                                media_type="video",  # Stories are usually video
                                folder=folder,
                                tags=["instagram", "story", f"sender_{message.sender_id}"],
                            )
                            if result.success:
                                story_info["original_url"] = cdn_url
                                story_info["permanent_url"] = result.url
                                story_info["cloudinary_id"] = result.public_id
                                logger.info(
                                    f"[IG:{message.sender_id}] Story media uploaded to Cloudinary"
                                )
                            else:
                                # Fallback to base64
                                captured = await capture_media_from_url(
                                    url=cdn_url,
                                    media_type="video",
                                    creator_id=self.creator_id,
                                    use_cloudinary=False,
                                )
                                if captured and captured.startswith("data:"):
                                    story_info["thumbnail_base64"] = captured
                                    logger.info(
                                        f"[IG:{message.sender_id}] Story captured as base64"
                                    )
                        else:
                            # No Cloudinary - capture as base64
                            captured = await capture_media_from_url(
                                url=cdn_url,
                                media_type="video",
                                creator_id=self.creator_id,
                                use_cloudinary=False,
                            )
                            if captured:
                                if captured.startswith("data:"):
                                    story_info["thumbnail_base64"] = captured
                                else:
                                    story_info["permanent_url"] = captured
                                logger.info(
                                    f"[IG:{message.sender_id}] Story media captured permanently"
                                )

        if not message_text and message.attachments and not story_info:
            # Extract media info and create descriptive text
            media_info = self._extract_media_info(message.attachments)
            if media_info:
                media_type = media_info.get("type", "media")
                media_type_display = {
                    "image": "Imagen",
                    "video": "Video",
                    "audio": "Audio",
                    "gif": "GIF",
                    "sticker": "Sticker",
                }.get(media_type, "Media")
                message_text = f"[{media_type_display}]"
                logger.info(
                    f"[IG:{message.sender_id}] Media message: type={media_type}, "
                    f"url={'Yes' if media_info.get('url') else 'No'}"
                )

                # Upload to Cloudinary for permanent storage (Instagram URLs expire)
                # Fallback to base64 if Cloudinary not configured
                if media_info.get("url"):
                    from services.media_capture_service import capture_media_from_url, is_cdn_url

                    cloudinary_svc = get_cloudinary_service()
                    if cloudinary_svc.is_configured:
                        folder = f"clonnect/{self.creator_id or 'unknown'}/media"
                        result = cloudinary_svc.upload_from_url(
                            url=media_info["url"],
                            media_type=media_type,
                            folder=folder,
                            tags=["instagram", f"sender_{message.sender_id}"],
                        )
                        if result.success:
                            logger.info(
                                f"[IG:{message.sender_id}] Media uploaded to Cloudinary: "
                                f"{result.public_id}"
                            )
                            media_info["original_url"] = media_info["url"]
                            media_info["url"] = result.url
                            media_info["cloudinary_id"] = result.public_id
                        else:
                            logger.warning(
                                f"[IG:{message.sender_id}] Cloudinary upload failed: "
                                f"{result.error}"
                            )
                            # Fallback to base64 if Cloudinary fails
                            if is_cdn_url(media_info["url"]):
                                captured = await capture_media_from_url(
                                    url=media_info["url"],
                                    media_type=media_type,
                                    creator_id=self.creator_id,
                                    use_cloudinary=False,  # Already tried Cloudinary
                                )
                                if captured and captured.startswith("data:"):
                                    media_info["thumbnail_base64"] = captured
                                    logger.info(
                                        f"[IG:{message.sender_id}] Captured media as base64"
                                    )
                    else:
                        # No Cloudinary - capture as base64
                        logger.debug("[IG] Cloudinary not configured, capturing as base64")
                        if is_cdn_url(media_info["url"]):
                            captured = await capture_media_from_url(
                                url=media_info["url"],
                                media_type=media_type,
                                creator_id=self.creator_id,
                                use_cloudinary=False,
                            )
                            if captured:
                                if captured.startswith("data:"):
                                    media_info["thumbnail_base64"] = captured
                                else:
                                    media_info["permanent_url"] = captured
                                logger.info(
                                    f"[IG:{message.sender_id}] Captured media for permanent storage"
                                )

        # Build metadata including media and story info if present
        dm_metadata = {
            "message_id": message.message_id,
            "username": username,
            "platform": "instagram",
        }
        if media_info:
            dm_metadata["media"] = media_info
        if story_info:
            # Story info becomes the msg_metadata directly (type, url, link, emoji)
            dm_metadata["story"] = story_info
            # Also set as msg_metadata for direct storage in message
            dm_metadata["msg_metadata"] = story_info

        # Process with DM agent (V2 signature: message, sender_id, metadata) - FIX 2026-01-29
        logger.info(f"[V2-FIX] Calling process_dm with V2 signature for {message.sender_id}")
        response = await self.dm_agent.process_dm(
            message=message_text or "[Media]",
            sender_id=f"ig_{message.sender_id}",
            metadata=dm_metadata,
        )

        # V2 compatibility for logging
        response_text = getattr(response, "content", None) or getattr(response, "response_text", "")
        intent_str = (
            response.intent.value if hasattr(response.intent, "value") else str(response.intent)
        )
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

    async def _get_profile_and_update_lead(self, sender_id: str) -> tuple:
        """
        Get user profile from Instagram API and update lead if profile_pic is missing.

        FIX 2026-02-02: When a user responds, we can now access their profile.
        This updates leads that previously couldn't get profile_pic due to
        "User consent is required" error (one-way conversations).

        Args:
            sender_id: Instagram user ID

        Returns:
            Tuple of (username, profile_pic_url)
        """
        username = "amigo"
        profile_pic_url = None

        if not self.connector:
            return username, profile_pic_url

        try:
            profile = await self.connector.get_user_profile(sender_id)
            if profile:
                username = profile.name or profile.username or "amigo"
                profile_pic_url = profile.profile_pic_url

                # Upload profile pic to Cloudinary for permanent storage
                if profile_pic_url:
                    cloudinary_svc = get_cloudinary_service()
                    if cloudinary_svc.is_configured:
                        result = cloudinary_svc.upload_from_url(
                            url=profile_pic_url,
                            media_type="image",
                            folder=f"clonnect/{self.creator_id or 'unknown'}/profiles",
                            public_id=f"profile_{sender_id}",
                        )
                        if result.success and result.url:
                            logger.info(f"[IG:{sender_id}] Profile pic uploaded to Cloudinary")
                            profile_pic_url = result.url

                # Update lead with profile info including is_verified
                if profile_pic_url or profile.is_verified:
                    await self._update_lead_profile(
                        sender_id,
                        profile.username,
                        profile.name,
                        profile_pic_url,
                        profile.is_verified,
                    )
        except Exception as e:
            logger.debug(f"Could not fetch user profile: {e}")

        return username, profile_pic_url

    async def _update_lead_profile(
        self,
        sender_id: str,
        username: str,
        full_name: str,
        profile_pic_url: str,
        is_verified: bool = False,
    ):
        """
        Update lead's profile info including profile_pic_url and is_verified.

        Uses get_or_create_lead which handles the update logic,
        then updates context with is_verified if applicable.
        """
        try:
            from api.models import Lead
            from api.services.db_service import get_or_create_lead, get_session

            result = get_or_create_lead(
                creator_name=self.creator_id,
                platform_user_id=f"ig_{sender_id}",
                platform="instagram",
                username=username,
                full_name=full_name,
                profile_pic_url=profile_pic_url,
            )

            # Update is_verified in lead's context if verified
            if result and is_verified:
                session = get_session()
                if session:
                    try:
                        lead = session.query(Lead).filter_by(id=result["id"]).first()
                        if lead:
                            context = lead.context or {}
                            context["is_verified"] = True
                            lead.context = context
                            session.commit()
                            logger.info(f"[IG:{sender_id}] Updated verified badge")
                    finally:
                        session.close()

            if result:
                logger.info(
                    f"[IG:{sender_id}] Updated lead profile: pic={'yes' if profile_pic_url else 'no'}, verified={is_verified}"
                )
                # Fire-and-forget identity resolution
                try:
                    import asyncio
                    from core.identity_resolver import resolve_identity
                    asyncio.create_task(resolve_identity(self.creator_id, result["id"], "instagram"))
                except Exception as ir_err:
                    logger.debug(f"[IG] Identity resolution skipped: {ir_err}")
        except Exception as e:
            logger.warning(f"Could not update lead profile: {e}")

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
            "timestamp": self.status.last_message_time,
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
        response_text = getattr(response, "content", None) or getattr(response, "response_text", "")
        intent_str = (
            response.intent.value if hasattr(response.intent, "value") else str(response.intent)
        )
        record = {
            "follower_id": f"ig_{msg.sender_id}",
            "sender_id": msg.sender_id,
            "input": msg.text,
            "response": response_text,
            "intent": intent_str,
            "confidence": response.confidence,
            "product": getattr(response, "product_mentioned", None),
            "escalate": getattr(response, "escalate_to_human", False),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.recent_responses.append(record)
        if len(self.recent_responses) > 10:
            self.recent_responses = self.recent_responses[-10:]

    async def _save_messages_to_db(
        self,
        msg: InstagramMessage,
        response: DMResponse,
        username: str = "",
        full_name: str = "",
    ) -> bool:
        """
        Save user message and bot response to database (AUTOPILOT mode).

        This is CRITICAL - without this, messages only exist in memory!

        Args:
            msg: Incoming Instagram message
            response: DM agent response
            username: User's Instagram username
            full_name: User's display name

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead, Message

            session = SessionLocal()
            try:
                # Get creator
                creator = session.query(Creator).filter_by(name=self.creator_id).first()
                if not creator:
                    logger.error(f"[SaveMsg] Creator {self.creator_id} not found")
                    return False

                # Find lead (check both with and without ig_ prefix)
                lead = (
                    session.query(Lead)
                    .filter(
                        Lead.creator_id == creator.id,
                        Lead.platform_user_id.in_([f"ig_{msg.sender_id}", msg.sender_id]),
                    )
                    .first()
                )

                if not lead:
                    # Prevent creating leads for creator's own IDs (prevents ghost leads)
                    known_ids = getattr(self, "known_creator_ids", set())
                    if not known_ids:
                        known_ids = {self.page_id, self.ig_user_id, "17841400506734756"}
                    if msg.sender_id in known_ids:
                        logger.warning(
                            f"[SaveMsg] Skipping lead creation for known creator ID: {msg.sender_id}"
                        )
                        return False

                    # Create lead if doesn't exist
                    # Use raw sender_id (no ig_ prefix) for consistency
                    try:
                        lead = Lead(
                            creator_id=creator.id,
                            platform="instagram",
                            platform_user_id=msg.sender_id,  # No prefix - prevents duplicates
                            username=username or None,
                            full_name=full_name or None,
                            status="nuevo",
                        )
                        session.add(lead)
                        session.commit()
                        logger.info(f"[SaveMsg] Created lead for {msg.sender_id}")
                    except Exception as e:
                        # Race condition: another request created the lead
                        session.rollback()
                        if "uq_lead_creator_platform" in str(e) or "duplicate" in str(e).lower():
                            logger.info(
                                "[SaveMsg] Lead already exists (race condition), fetching..."
                            )
                            lead = (
                                session.query(Lead)
                                .filter(
                                    Lead.creator_id == creator.id,
                                    Lead.platform_user_id.in_(
                                        [msg.sender_id, f"ig_{msg.sender_id}"]
                                    ),
                                )
                                .first()
                            )
                            if not lead:
                                logger.error(
                                    "[SaveMsg] Could not find lead after constraint error"
                                )
                                return False
                        else:
                            raise

                # Check if user message already exists (by platform_message_id)
                existing_user_msg = (
                    session.query(Message).filter_by(platform_message_id=msg.message_id).first()
                )

                if not existing_user_msg:
                    # Extract media/story info if present
                    media_info = None
                    msg_metadata = {}
                    content = msg.text

                    # Handle story messages first (story data is separate from attachments)
                    if msg.story:
                        story_data = msg.story
                        if story_data.get("reply_to"):
                            msg_metadata["type"] = "story_reply"
                            msg_metadata["link"] = story_data["reply_to"].get("link", "")
                        elif story_data.get("mention"):
                            msg_metadata["type"] = "story_mention"
                            msg_metadata["link"] = story_data["mention"].get("link", "")
                        # Extract CDN URL from attachments for stories
                        if msg.attachments:
                            att = msg.attachments[0]
                            cdn_url = (
                                att.get("video_data", {}).get("url")
                                or att.get("image_data", {}).get("url")
                                or (att.get("payload", {}).get("url") if isinstance(att.get("payload"), dict) else None)
                                or att.get("url")
                            )
                            if cdn_url:
                                msg_metadata["url"] = cdn_url
                        if not content:
                            content = {
                                "story_reply": "Respuesta a story",
                                "story_mention": "Mención en story",
                            }.get(msg_metadata.get("type", ""), "Story")
                    elif msg.attachments:
                        media_info = self._extract_media_info(msg.attachments)
                        if media_info:
                            msg_metadata["type"] = media_info.get("type", "unknown")
                            if media_info.get("url"):
                                msg_metadata["url"] = media_info["url"]
                            if media_info.get("permalink"):
                                msg_metadata["permalink"] = media_info["permalink"]
                            # Use descriptive content if no text
                            if not content:
                                media_type = media_info.get("type", "media")
                                content = {
                                    "image": "Sent a photo",
                                    "video": "Sent a video",
                                    "audio": "Sent a voice message",
                                    "gif": "Sent a GIF",
                                    "sticker": "Sent a sticker",
                                    "story_mention": "Mentioned you in their story",
                                    "share": "Shared a post",
                                    "shared_reel": "Shared a reel",
                                }.get(media_type, "Sent an attachment")

                    # MEDIA CAPTURE: Capture CDN URLs immediately before they expire
                    if msg_metadata.get("url"):
                        try:
                            from services.media_capture_service import (
                                capture_media_from_url,
                                is_cdn_url,
                            )

                            media_url = msg_metadata["url"]
                            if is_cdn_url(media_url):
                                media_type_for_capture = msg_metadata.get("type", "image")
                                if media_type_for_capture in (
                                    "video",
                                    "audio",
                                    "shared_video",
                                    "reel",
                                ):
                                    capture_type = "video"
                                else:
                                    capture_type = "image"

                                captured = await capture_media_from_url(
                                    url=media_url,
                                    media_type=capture_type,
                                    creator_id=self.creator_id,
                                )
                                if captured:
                                    if captured.startswith("data:"):
                                        msg_metadata["thumbnail_base64"] = captured
                                    else:
                                        msg_metadata["permanent_url"] = captured
                                    logger.info(f"[SaveMsg] Captured media for {msg.sender_id}")
                        except Exception as capture_err:
                            logger.warning(f"[SaveMsg] Media capture failed: {capture_err}")

                    # Save user message
                    user_msg = Message(
                        lead_id=lead.id,
                        role="user",
                        content=content or "[Media/Attachment]",
                        status="sent",
                        platform_message_id=msg.message_id,
                        msg_metadata=msg_metadata if msg_metadata else None,
                    )
                    session.add(user_msg)
                    logger.debug(f"[SaveMsg] Saved user message {msg.message_id}")

                # Get response text (V2 compatibility)
                response_text = getattr(response, "content", None) or getattr(
                    response, "response_text", ""
                )
                intent_str = (
                    response.intent.value
                    if hasattr(response.intent, "value")
                    else str(response.intent)
                )

                # Save bot response
                bot_msg = Message(
                    lead_id=lead.id,
                    role="assistant",
                    content=response_text,
                    status="sent",
                    intent=intent_str,
                    approved_by="autopilot",
                )
                session.add(bot_msg)

                # Update lead's last_contact and recalculate score
                lead.last_contact_at = datetime.now(timezone.utc)

                try:
                    from services.lead_scoring import recalculate_lead_score

                    recalculate_lead_score(session, str(lead.id))
                except Exception as score_err:
                    logger.warning(f"[SaveMsg] Scoring failed: {score_err}")

                session.commit()
                logger.info(f"[SaveMsg] Saved messages for {msg.sender_id} (lead_id={lead.id})")

                # Invalidate cache for this creator
                try:
                    from api.cache import api_cache

                    api_cache.invalidate(f"conversations:{self.creator_id}")
                    api_cache.invalidate(f"leads:{self.creator_id}")
                    api_cache.invalidate(
                        f"follower_detail:{self.creator_id}:{lead.platform_user_id}"
                    )
                except Exception as cache_err:
                    logger.debug(f"[SaveMsg] Cache invalidation failed: {cache_err}")

                # Notify frontend via SSE
                try:
                    from api.routers.events import notify_creator

                    await notify_creator(
                        self.creator_id,
                        "new_message",
                        {
                            "follower_id": lead.platform_user_id,
                            "role": "user",
                        },
                    )
                except Exception as sse_err:
                    logger.debug(f"[SaveMsg] SSE notification failed: {sse_err}")

                return True

            finally:
                session.close()

        except Exception as e:
            logger.error(f"[SaveMsg] Error saving messages: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return False

    async def _save_user_message_to_db(
        self,
        msg: InstagramMessage,
        username: str = "",
        full_name: str = "",
    ) -> bool:
        """
        Save only user message to database (when bot doesn't respond).

        Used when creator already responded manually.

        Args:
            msg: Incoming Instagram message
            username: User's Instagram username
            full_name: User's display name

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead, Message

            session = SessionLocal()
            try:
                # Get creator
                creator = session.query(Creator).filter_by(name=self.creator_id).first()
                if not creator:
                    logger.error(f"[SaveUserMsg] Creator {self.creator_id} not found")
                    return False

                # Find lead (check both with and without ig_ prefix)
                lead = (
                    session.query(Lead)
                    .filter(
                        Lead.creator_id == creator.id,
                        Lead.platform_user_id.in_([f"ig_{msg.sender_id}", msg.sender_id]),
                    )
                    .first()
                )

                if not lead:
                    # Prevent creating leads for creator's own IDs (prevents ghost leads)
                    known_ids = getattr(self, "known_creator_ids", set())
                    if not known_ids:
                        known_ids = {self.page_id, self.ig_user_id, "17841400506734756"}
                    if msg.sender_id in known_ids:
                        logger.warning(
                            f"[SaveUserMsg] Skipping lead creation for known creator ID: {msg.sender_id}"
                        )
                        return False

                    # Create lead if doesn't exist
                    # Use raw sender_id (no ig_ prefix) for consistency
                    try:
                        lead = Lead(
                            creator_id=creator.id,
                            platform="instagram",
                            platform_user_id=msg.sender_id,  # No prefix - prevents duplicates
                            username=username or None,
                            full_name=full_name or None,
                            status="nuevo",
                        )
                        session.add(lead)
                        session.commit()
                        logger.info(f"[SaveUserMsg] Created lead for {msg.sender_id}")
                    except Exception as e:
                        # Race condition: another request created the lead
                        session.rollback()
                        if "uq_lead_creator_platform" in str(e) or "duplicate" in str(e).lower():
                            logger.info(
                                "[SaveUserMsg] Lead already exists (race condition), fetching..."
                            )
                            lead = (
                                session.query(Lead)
                                .filter(
                                    Lead.creator_id == creator.id,
                                    Lead.platform_user_id.in_(
                                        [msg.sender_id, f"ig_{msg.sender_id}"]
                                    ),
                                )
                                .first()
                            )
                            if not lead:
                                logger.error(
                                    "[SaveUserMsg] Could not find lead after constraint error"
                                )
                                return False
                        else:
                            raise

                # Check if user message already exists
                existing_msg = (
                    session.query(Message).filter_by(platform_message_id=msg.message_id).first()
                )

                if existing_msg:
                    logger.debug(f"[SaveUserMsg] Message {msg.message_id} already exists")
                    # Still update last_contact_at even if message exists
                    lead.last_contact_at = datetime.now(timezone.utc)
                    session.commit()
                    return True

                # Extract media info if present
                media_info = None
                msg_metadata = {}
                content = msg.text
                if msg.attachments:
                    media_info = self._extract_media_info(msg.attachments)
                    if media_info:
                        msg_metadata["type"] = media_info.get("type", "unknown")
                        if media_info.get("url"):
                            msg_metadata["url"] = media_info["url"]
                        # Use descriptive content if no text
                        if not content:
                            media_type = media_info.get("type", "media")
                            content = {
                                "image": "Sent a photo",
                                "video": "Sent a video",
                                "audio": "Sent a voice message",
                                "gif": "Sent a GIF",
                                "sticker": "Sent a sticker",
                                "story_mention": "Mentioned you in their story",
                                "share": "Shared a post",
                                "shared_reel": "Shared a reel",
                            }.get(media_type, "Sent an attachment")

                # MEDIA CAPTURE: Capture CDN URLs immediately before they expire
                # Instagram CDN URLs expire after ~24 hours
                if msg_metadata.get("url"):
                    try:
                        from services.media_capture_service import (
                            capture_media_from_url,
                            is_cdn_url,
                        )

                        media_url = msg_metadata["url"]
                        if is_cdn_url(media_url):
                            media_type_for_capture = msg_metadata.get("type", "image")
                            if media_type_for_capture in ("video", "audio", "shared_video", "reel"):
                                capture_type = "video"
                            else:
                                capture_type = "image"

                            captured = await capture_media_from_url(
                                url=media_url,
                                media_type=capture_type,
                                creator_id=self.creator_id,
                            )
                            if captured:
                                if captured.startswith("data:"):
                                    msg_metadata["thumbnail_base64"] = captured
                                else:
                                    msg_metadata["permanent_url"] = captured
                                logger.info(f"[SaveUserMsg] Captured media for {msg.sender_id}")
                    except Exception as capture_err:
                        logger.warning(f"[SaveUserMsg] Media capture failed: {capture_err}")

                # Save user message
                user_msg = Message(
                    lead_id=lead.id,
                    role="user",
                    content=content or "[Media/Attachment]",
                    status="sent",
                    platform_message_id=msg.message_id,
                    msg_metadata=msg_metadata if msg_metadata else None,
                )
                session.add(user_msg)

                # Update lead's last_contact and recalculate score
                lead.last_contact_at = datetime.now(timezone.utc)

                try:
                    from services.lead_scoring import recalculate_lead_score

                    recalculate_lead_score(session, str(lead.id))
                except Exception as score_err:
                    logger.warning(f"[SaveUserMsg] Scoring failed: {score_err}")

                session.commit()
                logger.info(
                    f"[SaveUserMsg] Saved user message for {msg.sender_id} (lead_id={lead.id})"
                )

                # Invalidate cache for this creator
                try:
                    from api.cache import api_cache

                    api_cache.invalidate(f"conversations:{self.creator_id}")
                    api_cache.invalidate(f"leads:{self.creator_id}")
                    api_cache.invalidate(
                        f"follower_detail:{self.creator_id}:{lead.platform_user_id}"
                    )
                except Exception as cache_err:
                    logger.debug(f"[SaveUserMsg] Cache invalidation failed: {cache_err}")

                # Notify frontend via SSE
                try:
                    from api.routers.events import notify_creator

                    await notify_creator(
                        self.creator_id,
                        "new_message",
                        {
                            "follower_id": lead.platform_user_id,
                            "role": "user",
                        },
                    )
                except Exception as sse_err:
                    logger.debug(f"[SaveUserMsg] SSE notification failed: {sse_err}")

                return True

            finally:
                session.close()

        except Exception as e:
            logger.error(f"[SaveUserMsg] Error saving user message: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return False

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
            "interesa",
            "precio",
            "info",
            "información",
            "quiero",
            "cómo",
            "como",
            "comprar",
            "cuánto",
            "cuanto",
            "dónde",
            "donde",
            "interested",
            "price",
            "how",
            "want",
            "buy",
            "cost",
        ]
        has_interest = any(kw.lower() in comment_text.lower() for kw in interest_keywords)

        if not has_interest:
            logger.debug(f"Comment from {commenter_username} has no interest keywords")
            return None

        logger.info(
            f"Interest detected in comment from @{commenter_username}: {comment_text[:50]}..."
        )

        # Get DM template from config or use default
        dm_template = os.getenv(
            "COMMENT_DM_TEMPLATE",
            "¡Hola! Vi tu comentario y me encantó. 😊 ¿Te cuento más sobre lo que preguntabas?",
        )

        # Send DM
        success = await self.send_response(commenter_id, dm_template)

        if success:
            # Register as lead with source "comment"
            await self._register_comment_lead(
                commenter_id=commenter_id,
                commenter_username=commenter_username,
                comment_text=comment_text,
                media_id=media_id,
            )

            return {
                "action": "dm_sent",
                "commenter_id": commenter_id,
                "commenter_username": commenter_username,
                "comment_preview": comment_text[:50],
            }

        return {"action": "dm_failed", "commenter_id": commenter_id}

    async def _register_comment_lead(
        self, commenter_id: str, commenter_username: str, comment_text: str, media_id: str
    ):
        """Register a lead from a comment interaction"""
        try:
            # Import here to avoid circular imports
            from core.memory import FollowerMemory, MemoryStore

            memory_store = MemoryStore()
            follower_id = f"ig_{commenter_id}"

            # Try to load existing or create new
            follower = await memory_store.load(self.creator_id, follower_id)
            if not follower:
                follower = FollowerMemory(
                    follower_id=follower_id, creator_id=self.creator_id, platform="instagram"
                )

            follower.name = commenter_username
            follower.is_lead = True
            follower.source = "comment"

            # Store comment in notes
            if not hasattr(follower, "notes") or not follower.notes:
                follower.notes = []
            follower.notes.append(
                {
                    "type": "comment",
                    "text": comment_text,
                    "media_id": media_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

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
    page_id: Optional[str] = None,
) -> InstagramHandler:
    """Get or create Instagram handler. Credentials auto-loaded from DB if not provided."""
    global _handler
    if _handler is None:
        _handler = InstagramHandler(
            access_token=access_token, page_id=page_id, creator_id=creator_id
        )
    return _handler
