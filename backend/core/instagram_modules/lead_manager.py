"""Lead management sub-module extracted from InstagramHandler."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.cloudinary_service import get_cloudinary_service

logger = logging.getLogger("clonnect-instagram")


class LeadManager:
    """Handles lead creation, enrichment, and profile updates."""

    def __init__(self, creator_id: str, page_id: str, ig_user_id: str, access_token: str, connector):
        self.creator_id = creator_id
        self.page_id = page_id
        self.ig_user_id = ig_user_id
        self.access_token = access_token
        self.connector = connector

    async def check_lead_exists(self, sender_id: str) -> bool:
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

    async def find_conversation_for_user(self, sender_id: str) -> Optional[str]:
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

    async def fetch_conversation_history(self, sender_id: str) -> Optional[dict]:
        """
        Fetch conversation history from Instagram API for a new lead.
        Returns dict with messages and oldest_message_date if found.
        """
        if not self.connector:
            logger.warning("[LeadHistory] No connector available")
            return None

        try:
            # Find the conversation for this user
            conv_id = await self.find_conversation_for_user(sender_id)
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
                        logger.debug(f"[LeadManager] timestamp parse failed: {e}")

            return {
                "messages": messages,
                "oldest_message_date": oldest_date,
                "total_messages": len(messages),
            }

        except Exception as e:
            logger.error(f"[LeadHistory] Error fetching conversation history: {e}")
            return None

    def categorize_lead_by_history(self, oldest_date: Optional[datetime]) -> str:
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

    async def create_lead_with_history(
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
            history: Dict with messages and metadata from fetch_conversation_history
            profile_pic_url: Profile picture URL from Instagram API
            profile_pending: If True, profile fetch failed and will be retried

        Returns:
            Lead ID (string) if created successfully
        """
        # Prevent creating leads for creator's own IDs (prevents ghost leads)
        known_ids = {self.page_id, self.ig_user_id}
        for extra_id in (getattr(self, "_additional_ids", None) or []):
            known_ids.add(str(extra_id))
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
                        source="instagram_dm",
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
                        msg_sender_id = str(msg_from.get("id", ""))
                        is_from_follower = msg_sender_id == str(sender_id)
                        is_from_creator = (
                            not is_from_follower
                            and msg_sender_id in [self.page_id, self.ig_user_id]
                        ) if msg_sender_id else False

                        # If sender is follower → "user", if sender is creator → "assistant"
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

    async def enrich_new_lead(
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
        history = await self.fetch_conversation_history(sender_id)

        # Categorize based on history
        oldest_date = history.get("oldest_message_date") if history else None
        status = self.categorize_lead_by_history(oldest_date)

        logger.info(f"[LeadHistory] Categorized {sender_id} as '{status}' (oldest: {oldest_date})")

        # Create lead with history
        lead_id = await self.create_lead_with_history(
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
            await self.queue_profile_retry(sender_id, lead_id)

        if lead_id:
            return status
        return None

    async def queue_profile_retry(self, sender_id: str, lead_id: str) -> None:
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

    async def get_username(self, sender_id: str) -> str:
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

    async def get_profile_and_update_lead(self, sender_id: str) -> tuple:
        """
        Get user profile from Instagram API and update lead if profile_pic is missing.

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

                # Always update lead with profile info (username, name, pic, verified)
                await self.update_lead_profile(
                    sender_id,
                    profile.username,
                    profile.name,
                    profile_pic_url,
                    profile.is_verified,
                )
        except Exception as e:
            logger.debug(f"Could not fetch user profile: {e}")

        return username, profile_pic_url

    async def update_lead_profile(
        self,
        sender_id: str,
        username: str,
        full_name: str,
        profile_pic_url: str,
        is_verified: bool = False,
    ):
        """
        Update lead's profile info including profile_pic_url and is_verified.
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

    async def update_lead_profile_if_missing(
        self,
        sender_id: str,
        username: str,
        full_name: str,
        profile_pic_url: str,
    ):
        """
        Update lead profile ONLY if current values are missing.
        Called on every webhook to opportunistically backfill profile info
        for leads that were created without it (e.g., expired token at creation time).
        """
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=self.creator_id).first()
                if not creator:
                    return

                lead = (
                    session.query(Lead)
                    .filter(
                        Lead.creator_id == creator.id,
                        Lead.platform_user_id.in_([sender_id, f"ig_{sender_id}"]),
                    )
                    .first()
                )
                if not lead:
                    return

                updated = False
                if not lead.username and username:
                    lead.username = username
                    updated = True
                if not lead.full_name and full_name:
                    lead.full_name = full_name
                    updated = True
                if not lead.profile_pic_url and profile_pic_url:
                    lead.profile_pic_url = profile_pic_url
                    updated = True

                if updated:
                    # Clear profile_pending flag
                    if lead.context and lead.context.get("profile_pending"):
                        context = dict(lead.context)
                        context.pop("profile_pending", None)
                        context.pop("profile_retry_at", None)
                        lead.context = context

                    session.commit()
                    logger.info(
                        f"[IG:{sender_id}] Backfilled missing profile: "
                        f"username={username[:20] if username else 'N/A'}, "
                        f"pic={'Yes' if profile_pic_url else 'No'}"
                    )
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"Could not backfill lead profile for {sender_id}: {e}")

    async def copy_profile_from_sibling_lead(self, sender_id: str) -> bool:
        """
        Cross-creator profile fallback: if the IG API can't return this user's
        profile (permission error), copy username + profile_pic_url from another
        creator's lead with the same platform_user_id.

        Only copies username, full_name, and profile_pic_url. Does NOT create
        leads or modify messages.

        Returns True if profile was copied, False otherwise.
        """
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=self.creator_id).first()
                if not creator:
                    return False

                # Find our lead (the one missing profile data)
                our_lead = (
                    session.query(Lead)
                    .filter(
                        Lead.creator_id == creator.id,
                        Lead.platform_user_id.in_([sender_id, f"ig_{sender_id}"]),
                    )
                    .first()
                )
                if not our_lead:
                    return False

                # Already has profile — nothing to do
                if our_lead.username and our_lead.profile_pic_url:
                    return False

                # Find a sibling lead (different creator, same platform_user_id) that has profile data
                sibling = (
                    session.query(Lead)
                    .filter(
                        Lead.platform_user_id == our_lead.platform_user_id,
                        Lead.creator_id != creator.id,
                        Lead.username.isnot(None),
                        Lead.username != "",
                    )
                    .first()
                )
                if not sibling:
                    return False

                updated = False
                if not our_lead.username and sibling.username:
                    our_lead.username = sibling.username
                    updated = True
                if not our_lead.full_name and sibling.full_name:
                    our_lead.full_name = sibling.full_name
                    updated = True
                if not our_lead.profile_pic_url and sibling.profile_pic_url:
                    our_lead.profile_pic_url = sibling.profile_pic_url
                    updated = True

                if updated:
                    # Clear profile_pending flag
                    if our_lead.context and our_lead.context.get("profile_pending"):
                        context = dict(our_lead.context)
                        context.pop("profile_pending", None)
                        context.pop("profile_retry_at", None)
                        our_lead.context = context

                    session.commit()
                    logger.info(
                        f"[IG:{sender_id}] Copied profile from sibling lead: "
                        f"@{sibling.username} (creator={sibling.creator_id})"
                    )
                    return True

                return False
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"Could not copy sibling profile for {sender_id}: {e}")
            return False
