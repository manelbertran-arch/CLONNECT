#!/usr/bin/env python3
"""
Instagram Handler for Clonnect Creators DM System.

Provides Instagram webhook handling and DM processing using Meta Graph API.
Heavy logic is delegated to core.instagram_modules subpackage.
"""
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.dm_agent_v2 import DMResponderAgent, DMResponse
from core.instagram import InstagramConnector, InstagramMessage
from core.instagram_modules import CommentHandler, LeadManager, MessageSender, MessageStore

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
        creator_id: str = None,
    ):
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
            self.creator_id = os.getenv("DEFAULT_CREATOR_ID", "")

        # Status tracking
        self.status = InstagramHandlerStatus()
        self.recent_messages: List[Dict[str, Any]] = []
        self.recent_responses: List[Dict[str, Any]] = []

        # DM Agent
        self.dm_agent: Optional[DMResponderAgent] = None

        # Instagram connector
        self.connector: Optional[InstagramConnector] = None

        self._init_connector()
        self._init_agent()

        # Sub-modules (delegate extracted responsibilities)
        self._sender = MessageSender(self.connector, self.creator_id, self.status)
        self._lead_mgr = LeadManager(
            self.creator_id, self.page_id, self.ig_user_id, self.access_token, self.connector
        )
        self._lead_mgr._additional_ids = getattr(self, "_additional_ids", [])
        self._msg_store = MessageStore(
            self.creator_id, self.page_id, self.ig_user_id, self.status,
            self.recent_messages, self.recent_responses, self._extract_media_info,
            access_token=self.access_token,
        )
        self._comment = CommentHandler(self.creator_id, self._sender.send_response)

    def _load_credentials_from_db(self):
        """Load Instagram credentials from database if not in ENV vars."""
        try:
            from api.database import SessionLocal
            from api.models import Creator

            if SessionLocal is None:
                logger.warning("Database not configured, cannot load Instagram credentials from DB")
                return

            db = SessionLocal()
            try:
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
                    self.known_creator_ids = set()
                    if self.page_id:
                        self.known_creator_ids.add(self.page_id)
                    if self.ig_user_id:
                        self.known_creator_ids.add(self.ig_user_id)
                    self._additional_ids = creator.instagram_additional_ids or []
                    for extra_id in self._additional_ids:
                        self.known_creator_ids.add(str(extra_id))
                    self.known_creator_ids.add("17841400506734756")

                    logger.info(f"Loaded Instagram credentials from DB for creator: {creator.name}")
                    logger.info(f"  - page_id: {self.page_id or 'N/A'}")
                    logger.info(f"  - ig_user_id: {self.ig_user_id or 'N/A'}")
                    logger.info(f"  - token: {len(self.access_token)} chars")

                    if not self.page_id and self.access_token:
                        self._fetch_page_id_from_api(creator, db)
                else:
                    logger.warning("No creator with Instagram credentials found in database")

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error loading Instagram credentials from DB: {e}")

    def _fetch_page_id_from_api(self, creator, db):
        """Fetch the Facebook Page ID from Meta API using the access token."""
        import requests

        try:
            url = "https://graph.facebook.com/v18.0/me/accounts"
            params = {"access_token": self.access_token}
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                pages = data.get("data", [])
                if pages:
                    page = pages[0]
                    self.page_id = page.get("id", "")
                    logger.info(f"Fetched page_id from Meta API: {self.page_id}")
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
        """Initialize Instagram connector."""
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
        """Initialize DM agent."""
        try:
            self.dm_agent = DMResponderAgent(creator_id=self.creator_id)
            logger.info(f"DM Agent initialized for creator: {self.creator_id}")
        except Exception as e:
            logger.error(f"Failed to initialize DM agent: {e}")

    # =========================================================================
    # WEBHOOK & MESSAGE PROCESSING (delegated to modules)
    # =========================================================================

    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """Verify webhook subscription (GET request from Meta)."""
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
        """Handle incoming webhook from Meta (POST request)."""
        from core.instagram_modules.webhook import handle_webhook_impl
        return await handle_webhook_impl(self, payload, signature, raw_body)

    async def process_message(self, message: InstagramMessage) -> DMResponse:
        """Process an Instagram message through DMResponderAgent."""
        from core.instagram_modules.media import process_message_impl
        return await process_message_impl(self, message)

    async def _is_copilot_enabled(self) -> bool:
        """Check if copilot mode is enabled for this creator."""
        try:
            from core.copilot_service import get_copilot_service
            copilot = get_copilot_service()
            return copilot.is_copilot_enabled(self.creator_id)
        except Exception as e:
            logger.error(f"Error checking copilot mode: {e}")
            return True

    # =========================================================================
    # LEAD ENRICHMENT (delegated to LeadManager)
    # =========================================================================

    async def _check_lead_exists(self, sender_id: str) -> bool:
        return await self._lead_mgr.check_lead_exists(sender_id)

    async def _find_conversation_for_user(self, sender_id: str) -> Optional[str]:
        return await self._lead_mgr.find_conversation_for_user(sender_id)

    async def _fetch_conversation_history(self, sender_id: str) -> Optional[dict]:
        return await self._lead_mgr.fetch_conversation_history(sender_id)

    def _categorize_lead_by_history(self, oldest_date: Optional[datetime]) -> str:
        return self._lead_mgr.categorize_lead_by_history(oldest_date)

    async def _create_lead_with_history(
        self, sender_id: str, username: str, full_name: str, status: str,
        history: Optional[dict], profile_pic_url: str = "", profile_pending: bool = False,
    ) -> Optional[str]:
        return await self._lead_mgr.create_lead_with_history(
            sender_id, username, full_name, status, history, profile_pic_url, profile_pending
        )

    async def _enrich_new_lead(
        self, sender_id: str, username: str = "", full_name: str = ""
    ) -> Optional[str]:
        return await self._lead_mgr.enrich_new_lead(sender_id, username, full_name)

    async def _queue_profile_retry(self, sender_id: str, lead_id: str) -> None:
        await self._lead_mgr.queue_profile_retry(sender_id, lead_id)

    async def _get_username(self, sender_id: str) -> str:
        return await self._lead_mgr.get_username(sender_id)

    async def _get_profile_and_update_lead(self, sender_id: str) -> tuple:
        return await self._lead_mgr.get_profile_and_update_lead(sender_id)

    async def _update_lead_profile(
        self, sender_id: str, username: str, full_name: str,
        profile_pic_url: str, is_verified: bool = False,
    ):
        await self._lead_mgr.update_lead_profile(
            sender_id, username, full_name, profile_pic_url, is_verified
        )

    async def _update_lead_profile_if_missing(
        self, sender_id: str, username: str, full_name: str, profile_pic_url: str
    ):
        """Update lead profile only if current values are missing."""
        await self._lead_mgr.update_lead_profile_if_missing(
            sender_id, username, full_name, profile_pic_url
        )

    # =========================================================================
    # MESSAGING (delegated to MessageSender / MessageStore)
    # =========================================================================

    async def send_response(self, recipient_id: str, text: str, approved: bool = False) -> bool:
        return await self._sender.send_response(recipient_id, text, approved)

    async def send_message_with_buttons(
        self, recipient_id: str, text: str, buttons: List[Dict[str, str]]
    ) -> bool:
        return await self._sender.send_message_with_buttons(recipient_id, text, buttons)

    def _record_received(self, msg: InstagramMessage):
        self._msg_store.record_received(msg)

    def _record_sent(self):
        self._msg_store.record_sent()

    def _record_response(self, msg: InstagramMessage, response: DMResponse):
        self._msg_store.record_response(msg, response)

    async def _save_messages_to_db(
        self, msg: InstagramMessage, response: DMResponse,
        username: str = "", full_name: str = "",
    ) -> bool:
        return await self._msg_store.save_messages_to_db(msg, response, username, full_name)

    async def _save_user_message_to_db(
        self, msg: InstagramMessage, username: str = "", full_name: str = "",
    ) -> bool:
        return await self._msg_store.save_user_message_to_db(msg, username, full_name)

    def _extract_media_info(self, attachments):
        from core.instagram_modules.media import extract_media_info
        return extract_media_info(attachments)

    # =========================================================================
    # COMMENTS (delegated to CommentHandler)
    # =========================================================================

    async def handle_comment(self, comment_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self._comment.handle_comment(comment_data)

    async def _register_comment_lead(
        self, commenter_id: str, commenter_username: str, comment_text: str, media_id: str
    ):
        await self._comment._register_comment_lead(
            commenter_id, commenter_username, comment_text, media_id
        )

    # =========================================================================
    # STATUS & LIFECYCLE
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        return self.status.to_dict()

    def get_recent_messages(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.recent_messages[-limit:]

    def get_recent_responses(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.recent_responses[-limit:]

    async def close(self):
        if self.connector:
            await self.connector.close()
            self.status.connected = False
            logger.info("Instagram handler closed")


# Global handler instance
_handler: Optional[InstagramHandler] = None


def get_instagram_handler(
    creator_id: str = None,
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
