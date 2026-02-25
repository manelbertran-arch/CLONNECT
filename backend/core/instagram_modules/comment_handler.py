"""Comment handling sub-module extracted from InstagramHandler."""
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger("clonnect-instagram")


class CommentHandler:
    """Handles Instagram comment processing and auto-DM."""

    def __init__(self, creator_id: str, send_response_fn: Callable[..., Coroutine]):
        self.creator_id = creator_id
        self._send_response = send_response_fn

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
        success = await self._send_response(commenter_id, dm_template)

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
