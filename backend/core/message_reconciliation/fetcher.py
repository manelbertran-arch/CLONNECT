"""
Message retrieval functions for message reconciliation.

Functions for fetching Instagram conversations and getting DB message IDs.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("clonnect-reconciliation")


async def get_instagram_conversations(
    access_token: str,
    ig_user_id: str,
    since: Optional[datetime] = None,
    limit: int = 20,
    folders: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch conversations from Instagram API with messages.

    Args:
        access_token: Instagram access token
        ig_user_id: Instagram user ID (page_id for creator)
        since: Only fetch messages since this time
        limit: Max conversations to fetch per folder (default 20)
        folders: IG conversation folders to check (default: ["inbox", "other"])

    Returns:
        List of conversations with messages
    """
    if folders is None:
        folders = ["inbox", "other"]

    conversations = []

    # Determine API base and conversations URL.
    # IGAAT tokens (Instagram Business Login) must use /me/conversations because
    # the ASID returned by /me differs from the IGSID expected by /{id}/conversations.
    # EAA tokens (Facebook Login) use the explicit page/user ID path.
    api_base = "https://graph.instagram.com/v21.0"
    if access_token.startswith("EAA"):
        api_base = "https://graph.facebook.com/v21.0"
        conversations_url = f"{api_base}/{ig_user_id}/conversations"
    else:
        # IGAAT — always use /me/conversations
        conversations_url = f"{api_base}/me/conversations"

    seen_conv_ids = set()

    async with httpx.AsyncClient(timeout=30.0) as client:
        for folder in folders:
            try:
                # Fetch conversation IDs with pagination
                page_url = conversations_url
                page_params = {
                    "fields": "id,participants",
                    "access_token": access_token,
                    "limit": min(limit, 50),  # Meta API max per page is 50
                    "folder": folder,
                }
                conv_list = []
                page = 0
                max_pages = max(1, limit // 50 + 1)

                while page_url and page < max_pages and len(conv_list) < limit:
                    if page == 0:
                        resp = await client.get(page_url, params=page_params)
                    else:
                        resp = await client.get(page_url)

                    if resp.status_code != 200:
                        err_text = resp.text[:300]
                        if "(#3)" in err_text or "does not have the capability" in err_text:
                            logger.warning(
                                "[Reconciliation] Conversations API not available for %s "
                                "(app capability not approved or non-business account): %s",
                                ig_user_id,
                                err_text[:150],
                            )
                        else:
                            logger.error(
                                "[Reconciliation] API error for %s folder=%s: %s - %s",
                                ig_user_id,
                                folder,
                                resp.status_code,
                                err_text,
                            )
                        break

                    data = resp.json()
                    page_convs = data.get("data", [])
                    if not page_convs:
                        break
                    conv_list.extend(page_convs)
                    page_url = data.get("paging", {}).get("next")
                    page += 1

                logger.info(
                    f"[Reconciliation] Fetched {len(conv_list)} conversation IDs "
                    f"from {folder} ({page} pages)"
                )

                # Then fetch messages for each conversation separately
                for conv in conv_list:
                    conv_id = conv.get("id")
                    if not conv_id or conv_id in seen_conv_ids:
                        continue
                    seen_conv_ids.add(conv_id)

                    try:
                        # Fetch messages for this conversation using /messages endpoint
                        # This format returns more attachment data (story, share, etc.)
                        msg_url = f"{api_base}/{conv_id}/messages"
                        msg_params = {
                            "fields": "id,message,from,to,created_time,attachments,story,share,shares,sticker",
                            "access_token": access_token,
                            "limit": 25,
                        }

                        msg_resp = await client.get(msg_url, params=msg_params)

                        if msg_resp.status_code == 200:
                            msg_data = msg_resp.json()
                            # Format response to match expected structure
                            conv["messages"] = {"data": msg_data.get("data", [])}
                            conversations.append(conv)
                        else:
                            logger.debug(f"[Reconciliation] Could not fetch messages for {conv_id}")
                            # Still add conversation without messages
                            conversations.append(conv)

                        # Small delay to avoid rate limits
                        await asyncio.sleep(0.1)

                    except Exception as e:
                        logger.debug(f"[Reconciliation] Error fetching messages for {conv_id}: {e}")
                        conversations.append(conv)

            except Exception as e:
                logger.error(f"[Reconciliation] Error fetching conversations folder=%s: %s", folder, e)

    logger.debug(
        f"[Reconciliation] Fetched {len(conversations)} conversations with messages "
        f"(folders: {folders})"
    )

    return conversations


async def get_db_message_ids(
    creator_id: str,
    since: Optional[datetime] = None,
) -> set:
    """
    Get all platform_message_ids from database for a creator.

    Args:
        creator_id: Creator name/ID
        since: Only get messages since this time

    Returns:
        Set of platform_message_ids
    """
    def _query_message_ids():
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        message_ids = set()
        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                logger.warning(f"[Reconciliation] Creator {creator_id} not found")
                return message_ids

            leads = session.query(Lead).filter_by(creator_id=creator.id).all()
            lead_ids = [lead.id for lead in leads]
            if not lead_ids:
                return message_ids

            query = session.query(Message.platform_message_id).filter(
                Message.lead_id.in_(lead_ids),
                Message.platform_message_id.isnot(None),
            )
            if since:
                query = query.filter(Message.created_at >= since)

            results = query.all()
            message_ids = {r[0] for r in results if r[0]}
            logger.debug(f"[Reconciliation] Found {len(message_ids)} existing messages in DB")
            return message_ids
        finally:
            session.close()

    return await asyncio.to_thread(_query_message_ids)
