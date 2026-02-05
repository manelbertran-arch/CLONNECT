"""
Webhook Routing for Multi-Creator Support

This module provides robust routing of Instagram webhooks to the correct creator,
regardless of which ID format Meta sends in the payload.

Functions:
- extract_all_instagram_ids: Extract ALL possible IDs from webhook payload
- get_creator_by_any_instagram_id: Find creator by any type of Instagram ID
- find_creator_for_webhook: Try all IDs to find matching creator
- save_unmatched_webhook: Store unmatched webhooks for debugging
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("clonnect-webhook-routing")

# Cache for creator lookups (5-minute TTL)
_creator_cache: Dict[str, Tuple[Optional[Dict], float]] = {}
_CACHE_TTL_SECONDS = 300


def extract_all_instagram_ids(payload: Dict[str, Any]) -> List[str]:
    """
    Extract ALL possible Instagram IDs from a webhook payload.

    Meta can send different IDs in different contexts:
    - entry[].id - Usually the page/business account ID
    - entry[].messaging[].recipient.id - The creator's account receiving the message
    - entry[].messaging[].sender.id - The user sending the message
    - entry[].changes[].value.from.id - For comments/reactions

    Args:
        payload: Raw webhook payload from Meta

    Returns:
        List of unique Instagram IDs found in the payload
    """
    ids = set()

    try:
        for entry in payload.get("entry", []):
            # Entry ID (usually the page_id or business account ID)
            entry_id = entry.get("id")
            if entry_id:
                ids.add(str(entry_id))

            # Messaging events (DMs)
            for messaging in entry.get("messaging", []):
                # Recipient is the creator receiving the message
                recipient_id = messaging.get("recipient", {}).get("id")
                if recipient_id:
                    ids.add(str(recipient_id))

                # Sender is the user (we include it for completeness but filter later)
                sender_id = messaging.get("sender", {}).get("id")
                if sender_id:
                    ids.add(str(sender_id))

            # Changes (comments, reactions, etc.)
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # From ID (who made the action)
                from_id = value.get("from", {}).get("id")
                if from_id:
                    ids.add(str(from_id))

                # To ID (who received)
                to_id = value.get("to", {}).get("id")
                if to_id:
                    ids.add(str(to_id))

                # Page ID in value
                page_id = value.get("page_id")
                if page_id:
                    ids.add(str(page_id))

    except Exception as e:
        logger.error(f"Error extracting Instagram IDs from payload: {e}")

    return list(ids)


def get_creator_by_any_instagram_id(instagram_id: str) -> Optional[Dict[str, Any]]:
    """
    Find a creator by ANY type of Instagram ID.

    Search order (all indexed for performance):
    1. instagram_page_id (exact match)
    2. instagram_user_id (exact match)
    3. instagram_additional_ids (JSON array contains)

    Args:
        instagram_id: Any Instagram ID to search for

    Returns:
        Dict with creator info if found, None otherwise
    """
    current_time = time.time()

    # Check cache first
    cache_key = f"ig_any:{instagram_id}"
    if cache_key in _creator_cache:
        cached_info, cached_time = _creator_cache[cache_key]
        if current_time - cached_time < _CACHE_TTL_SECONDS:
            if cached_info:
                logger.debug(
                    f"[ROUTING-CACHE] HIT for {instagram_id}: {cached_info.get('creator_id')}"
                )
            return cached_info

    # Cache miss - query DB
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            # 1. Search by instagram_page_id (most common)
            creator = session.query(Creator).filter_by(instagram_page_id=instagram_id).first()

            # 2. Search by instagram_user_id
            if not creator:
                creator = session.query(Creator).filter_by(instagram_user_id=instagram_id).first()

            # 3. Search in instagram_additional_ids (JSON array)
            if not creator:
                # PostgreSQL JSONB contains operator
                creator = (
                    session.query(Creator)
                    .filter(Creator.instagram_additional_ids.contains([instagram_id]))
                    .first()
                )

            if not creator:
                _creator_cache[cache_key] = (None, current_time)
                return None

            # Build result dict
            result = {
                "creator_id": creator.name,
                "creator_uuid": str(creator.id),
                "instagram_token": creator.instagram_token,
                "instagram_page_id": creator.instagram_page_id,
                "instagram_user_id": creator.instagram_user_id,
                "instagram_additional_ids": creator.instagram_additional_ids or [],
                "bot_active": creator.bot_active,
                "copilot_mode": creator.copilot_mode,
            }

            logger.info(f"[ROUTING] Found creator '{creator.name}' for Instagram ID {instagram_id}")
            _creator_cache[cache_key] = (result, current_time)
            return result

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error looking up creator by Instagram ID {instagram_id}: {e}")
        return None


def find_creator_for_webhook(
    instagram_ids: List[str],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Try to find a creator using any of the provided Instagram IDs.

    Iterates through all IDs and returns the first match.
    This handles cases where Meta sends different IDs in different contexts.

    Args:
        instagram_ids: List of Instagram IDs extracted from webhook payload

    Returns:
        Tuple of (creator_info, matched_id) if found, (None, None) otherwise
    """
    for ig_id in instagram_ids:
        creator_info = get_creator_by_any_instagram_id(ig_id)
        if creator_info:
            return creator_info, ig_id

    return None, None


def save_unmatched_webhook(instagram_ids: List[str], payload: Dict[str, Any]) -> Optional[str]:
    """
    Save an unmatched webhook for later debugging and resolution.

    Stores only non-sensitive summary data from the payload.

    Args:
        instagram_ids: All Instagram IDs extracted from the payload
        payload: Original webhook payload (will be summarized)

    Returns:
        UUID of the created record as string, or None on error
    """
    try:
        from api.database import SessionLocal
        from api.models import UnmatchedWebhook

        # Create a sanitized summary of the payload
        payload_summary = {
            "object": payload.get("object"),
            "entry_count": len(payload.get("entry", [])),
            "has_messaging": any("messaging" in entry for entry in payload.get("entry", [])),
            "has_changes": any("changes" in entry for entry in payload.get("entry", [])),
        }

        # Add entry IDs for reference
        entry_ids = [entry.get("id") for entry in payload.get("entry", []) if entry.get("id")]
        if entry_ids:
            payload_summary["entry_ids"] = entry_ids

        session = SessionLocal()
        try:
            unmatched = UnmatchedWebhook(
                instagram_ids=instagram_ids,
                payload_summary=payload_summary,
            )
            session.add(unmatched)
            session.commit()

            record_id = str(unmatched.id)
            logger.warning(
                f"[ROUTING] Saved unmatched webhook {record_id} with IDs: {instagram_ids}"
            )
            return record_id

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error saving unmatched webhook: {e}")
        return None


def update_creator_webhook_stats(creator_id: str) -> bool:
    """
    Update webhook tracking stats for a creator.

    Increments webhook_count and updates webhook_last_received.

    Args:
        creator_id: Creator name/ID

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator:
                creator.webhook_count = (creator.webhook_count or 0) + 1
                creator.webhook_last_received = datetime.now(timezone.utc)
                session.commit()
                return True
            return False
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error updating webhook stats for {creator_id}: {e}")
        return False


def clear_routing_cache():
    """Clear the creator routing cache. Useful for testing and after DB updates."""
    global _creator_cache
    _creator_cache.clear()
    logger.info("[ROUTING] Cache cleared")


def add_instagram_id_to_creator(creator_id: str, instagram_id: str) -> bool:
    """
    Add an Instagram ID to a creator's additional_ids list.

    Useful for manually resolving unmatched webhooks.

    Args:
        creator_id: Creator name/ID
        instagram_id: Instagram ID to add

    Returns:
        True if added successfully, False otherwise
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                logger.warning(f"Creator {creator_id} not found")
                return False

            # Initialize list if None
            current_ids = creator.instagram_additional_ids or []

            # Add if not already present
            if instagram_id not in current_ids:
                current_ids.append(instagram_id)
                creator.instagram_additional_ids = current_ids
                session.commit()
                logger.info(f"Added Instagram ID {instagram_id} to creator {creator_id}")

                # Clear cache for this ID
                cache_key = f"ig_any:{instagram_id}"
                if cache_key in _creator_cache:
                    del _creator_cache[cache_key]

            return True

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error adding Instagram ID to creator: {e}")
        return False
