"""
Creator CRUD operations.
"""

import logging

from api.utils.creator_resolver import resolve_creator_safe
from .session import get_session

logger = logging.getLogger(__name__)


def get_creator_by_name(name: str):
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator

        creator = resolve_creator_safe(session, name)
        if creator:
            return {
                "id": str(creator.id),
                "name": creator.name,
                "email": creator.email,
                "bot_active": creator.bot_active,
                "clone_tone": creator.clone_tone or "friendly",
                "clone_style": creator.clone_style or "",
                "clone_name": creator.clone_name or creator.name,
                "clone_vocabulary": creator.clone_vocabulary or "",
                "welcome_message": creator.welcome_message or "",
                "other_payment_methods": creator.other_payment_methods or {},
                "knowledge_about": creator.knowledge_about or {},
            }
        return None
    finally:
        session.close()


# =============================================================================
# PROTECTED BLOCK: Instagram Token Access
# Modified: 2026-01-16
# Reason: Centralized function for Instagram credentials to prevent lookup bugs
# Do not modify without considering all usages across the codebase
# =============================================================================
def get_instagram_credentials(creator_id: str):
    """
    Centralized function to get Instagram credentials for a creator.

    IMPORTANT: This is the ONLY function that should be used to get Instagram tokens.
    It handles:
    - Lookup by name or UUID
    - Clear error messages when token is missing
    - All Instagram fields in one place

    Args:
        creator_id: Creator name (e.g., 'fitpack_global') or UUID

    Returns:
        Dict with:
            - success: bool
            - token: str or None
            - page_id: str or None
            - user_id: str or None
            - expires_at: datetime or None
            - creator_name: str
            - creator_uuid: str
            - error: str (if success=False)
    """
    session = get_session()
    if not session:
        return {
            "success": False,
            "error": "Database not available",
            "token": None,
            "page_id": None,
            "user_id": None,
        }

    try:
        from api.models import Creator

        creator = resolve_creator_safe(session, creator_id)

        if not creator:
            return {
                "success": False,
                "error": f"Creator '{creator_id}' not found in database",
                "token": None,
                "page_id": None,
                "user_id": None,
            }

        # Creator found - check if token exists
        if not creator.instagram_token:
            return {
                "success": False,
                "error": f"Creator '{creator.name}' has no Instagram token configured. "
                "Please connect Instagram via OAuth at /connect/instagram",
                "creator_name": creator.name,
                "creator_uuid": str(creator.id),
                "token": None,
                "page_id": creator.instagram_page_id,
                "user_id": creator.instagram_user_id,
            }

        # Success - return all credentials
        # Use getattr for expires_at as it may not exist in all DB schemas
        expires_at = getattr(creator, "instagram_token_expires_at", None)

        return {
            "success": True,
            "token": creator.instagram_token,
            "page_id": creator.instagram_page_id,
            "user_id": creator.instagram_user_id,
            "expires_at": expires_at,
            "creator_name": creator.name,
            "creator_uuid": str(creator.id),
            "error": None,
        }

    except Exception as e:
        logger.error(f"get_instagram_credentials error for {creator_id}: {e}")
        return {"success": False, "error": str(e), "token": None, "page_id": None, "user_id": None}
    finally:
        session.close()


def get_or_create_creator(name: str):
    """Get creator by name, or create if doesn't exist"""
    session = get_session()
    if not session:
        logger.error("get_or_create_creator: no session available")
        return None
    try:
        from api.models import Creator

        logger.info(f"get_or_create_creator: looking for creator '{name}'")
        creator = resolve_creator_safe(session, name)
        if not creator:
            logger.info(f"Creator '{name}' not found, auto-creating...")
            creator = Creator(name=name, bot_active=True, clone_tone="friendly")
            session.add(creator)
            session.commit()
            logger.info(f"Created creator '{name}' with id {creator.id}")

        # Build response dict, handling potentially missing columns gracefully
        result = {
            "id": str(creator.id),
            "name": creator.name,
            "email": creator.email,
            "bot_active": creator.bot_active if creator.bot_active is not None else True,
            "clone_tone": creator.clone_tone or "friendly",
            "clone_style": creator.clone_style or "",
            "clone_name": creator.clone_name or creator.name,
            "clone_vocabulary": creator.clone_vocabulary or "",
            "welcome_message": creator.welcome_message or "",
        }

        # These columns might not exist in older DB schemas
        try:
            result["other_payment_methods"] = creator.other_payment_methods or {}
        except AttributeError:
            result["other_payment_methods"] = {}
        try:
            result["knowledge_about"] = getattr(creator, "knowledge_about", None) or {}
        except AttributeError:
            result["knowledge_about"] = {}

        logger.info(f"get_or_create_creator: returning config for '{name}'")
        return result
    except Exception as e:
        logger.error(f"get_or_create_creator error: {e}")
        import traceback

        logger.error(traceback.format_exc())
        session.rollback()
        return None
    finally:
        session.close()


def update_creator(name: str, data: dict):
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator

        logger.info("=== UPDATE_CREATOR DEBUG ===")
        logger.info(f"Creator: {name}, Data keys: {list(data.keys())}")
        if "other_payment_methods" in data:
            logger.info(f"other_payment_methods value: {data['other_payment_methods']}")

        creator = resolve_creator_safe(session, name)
        if creator:
            for key, value in data.items():
                if hasattr(creator, key):
                    old_value = getattr(creator, key, None)
                    setattr(creator, key, value)
                    logger.info(f"Set {key}: {old_value} -> {value}")
                else:
                    logger.warning(f"Creator has no attribute '{key}' - skipping")
            session.commit()
            logger.info(f"Committed changes for {name}")
            # Verify the save
            session.refresh(creator)
            logger.info(f"After save, other_payment_methods = {creator.other_payment_methods}")
            return True
        else:
            logger.warning(f"Creator '{name}' not found")
        return False
    except Exception as e:
        logger.error(f"Error updating creator: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def toggle_bot(name: str, active: bool = None):
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator

        creator = resolve_creator_safe(session, name)
        if creator:
            creator.bot_active = active if active is not None else not creator.bot_active
            session.commit()
            return creator.bot_active
        return None
    finally:
        session.close()
