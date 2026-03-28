"""
Real-time content ingestion via Instagram feed webhooks (SPEC-004B).

When a creator publishes a new post/reel/video on Instagram, Meta sends a
webhook with field="feed". This module processes that event:
  1. Identifies the creator by page_id
  2. Checks for dedup (post already in DB)
  3. Fetches full post details via Graph API
  4. Saves to instagram_posts + content_chunks
  5. Generates contextual embeddings and hydrates RAG

Runs as a background task (asyncio.create_task) so the webhook returns 200
instantly (<2s) as required by Meta.

The 24h cron (SPEC-004) is kept as fallback for missed webhooks.
"""

import hashlib
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# Graph API version for media queries
GRAPH_API_VERSION = "v21.0"

# Map IG media_type → content_chunks source_type
_MEDIA_TYPE_MAP = {
    "VIDEO": "video",
    "CAROUSEL_ALBUM": "carousel",
    "IMAGE": "instagram_post",
    "REEL": "video",
}


async def process_feed_webhook(creator_info: Dict[str, Any], entry: dict):
    """
    Process a feed webhook entry for new content.

    Called via asyncio.create_task from the webhook handler.
    Iterates over changes in the entry looking for new posts/reels.

    Args:
        creator_info: Dict with creator_id, creator_uuid, instagram_token, etc.
        entry: The webhook entry dict containing "changes" array
    """
    creator_id = creator_info.get("creator_id", "unknown")

    for change in entry.get("changes", []):
        if change.get("field") != "feed":
            continue

        value = change.get("value", {})
        verb = value.get("verb", "")
        item = value.get("item", "")

        # Only process new content (not edits or deletes)
        if verb != "add":
            logger.debug(
                f"[FEED-WEBHOOK] Ignoring {verb} event for {item} ({creator_id})"
            )
            continue

        if item not in ("post", "photo", "video", "reel", "status"):
            logger.debug(
                f"[FEED-WEBHOOK] Ignoring item type '{item}' ({creator_id})"
            )
            continue

        post_id = value.get("post_id", "")
        logger.info(
            f"[FEED-WEBHOOK] New {item} detected: {post_id} for {creator_id}"
        )

        try:
            await _process_single_post(creator_info, value)
        except Exception as e:
            logger.error(
                f"[FEED-WEBHOOK] Error processing {item} {post_id} for {creator_id}: {e}"
            )


async def _process_single_post(creator_info: Dict[str, Any], webhook_value: dict):
    """
    Process a single new post from a feed webhook.

    Steps:
      1. Dedup check — skip if post already in DB
      2. Fetch full post details via Graph API
      3. Save to instagram_posts (upsert)
      4. Create content chunk + save to content_chunks (upsert)
      5. Generate embedding + store in pgvector
      6. Hydrate in-memory RAG
    """
    creator_id = creator_info["creator_id"]
    _creator_uuid = creator_info.get("creator_uuid", creator_id)
    access_token = creator_info.get("instagram_token", "")
    post_id = webhook_value.get("post_id", "")
    item_type = webhook_value.get("item", "post")

    if not post_id:
        logger.warning(f"[FEED-WEBHOOK] No post_id in webhook value for {creator_id}")
        return

    # Step 1: Dedup — check if post already exists in DB
    if await _post_exists_in_db(creator_id, post_id):
        logger.debug(
            f"[FEED-WEBHOOK] Post {post_id} already ingested for {creator_id}, skipping"
        )
        return

    # Step 2: Fetch full post details via Graph API
    post_data = await _fetch_post_details(access_token, post_id)
    if not post_data:
        logger.warning(f"[FEED-WEBHOOK] Could not fetch details for post {post_id}")
        return

    caption = post_data.get("caption", "") or ""
    permalink = post_data.get("permalink", "")
    media_type = post_data.get("media_type", item_type.upper())
    timestamp_str = post_data.get("timestamp", "")

    # Step 3: Save to instagram_posts via existing upsert
    try:
        from core.tone_profile_db import save_instagram_posts_db

        db_post = {
            "id": post_id,
            "post_id": post_id,
            "caption": caption,
            "permalink": permalink,
            "media_type": media_type,
            "media_url": post_data.get("media_url", ""),
            "thumbnail_url": post_data.get("thumbnail_url", ""),
            "timestamp": timestamp_str,
            "likes_count": 0,
            "comments_count": 0,
        }

        saved = await save_instagram_posts_db(creator_id, [db_post])
        logger.info(f"[FEED-WEBHOOK] Saved post {post_id} to instagram_posts ({saved} rows)")
    except Exception as e:
        logger.error(f"[FEED-WEBHOOK] Failed to save post {post_id}: {e}")

    # Step 4: Create content chunk + save (only if caption has useful content)
    source_type = _MEDIA_TYPE_MAP.get(media_type, "instagram_post")
    if caption and len(caption.strip()) > 50:
        try:
            from core.tone_profile_db import save_content_chunks_db

            chunk_id = hashlib.sha256(
                f"{creator_id}:{post_id}:0".encode()
            ).hexdigest()[:32]

            first_line = caption.split("\n")[0][:100]

            chunk = {
                "id": chunk_id,
                "chunk_id": chunk_id,
                "creator_id": creator_id,
                "content": caption,
                "source_type": source_type,
                "source_id": post_id,
                "source_url": permalink,
                "title": first_line,
                "chunk_index": 0,
                "total_chunks": 1,
                "metadata": {
                    "post_type": media_type,
                    "ingested_via": "feed_webhook",
                    "timestamp": timestamp_str,
                },
            }

            saved_chunks = await save_content_chunks_db(creator_id, [chunk])
            logger.info(
                f"[FEED-WEBHOOK] Saved {saved_chunks} {source_type} chunk(s) for post {post_id}"
            )
        except Exception as e:
            logger.error(f"[FEED-WEBHOOK] Failed to save chunk for {post_id}: {e}")

    # Step 5: Generate contextual embedding for the new chunk
    if caption and len(caption.strip()) > 50:
        try:
            await _embed_chunk(creator_id, chunk_id, caption)
        except Exception as e:
            logger.warning(f"[FEED-WEBHOOK] Embedding failed for {post_id}: {e}")

    # Step 6: Hydrate in-memory RAG
    try:
        from services.content_refresh import _hydrate_rag_for_creator

        _hydrate_rag_for_creator(creator_id)
    except Exception as e:
        logger.warning(f"[FEED-WEBHOOK] RAG hydration failed for {creator_id}: {e}")

    logger.info(
        f"[FEED-WEBHOOK] Real-time ingested: {item_type} {post_id} for {creator_id}"
    )


async def _post_exists_in_db(creator_id: str, post_id: str) -> bool:
    """Check if a post already exists in instagram_posts table."""
    try:
        from api.database import get_db_session
        from api.models import InstagramPost

        with get_db_session() as db:
            existing = (
                db.query(InstagramPost.id)
                .filter(
                    InstagramPost.creator_id == creator_id,
                    InstagramPost.post_id == post_id,
                )
                .first()
            )
            return existing is not None
    except Exception as e:
        logger.error(f"[FEED-WEBHOOK] Dedup check failed: {e}")
        return False  # If check fails, proceed with ingestion (idempotent anyway)


async def _fetch_post_details(access_token: str, post_id: str) -> Optional[dict]:
    """
    Fetch full post details from Instagram Graph API.

    Args:
        access_token: Creator's Instagram/Page access token
        post_id: Instagram post/media ID

    Returns:
        Dict with id, caption, timestamp, media_type, permalink, media_url, thumbnail_url
        or None on failure
    """
    if not access_token:
        logger.warning("[FEED-WEBHOOK] No access token available for Graph API call")
        return None

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{post_id}"
    params = {
        "fields": "id,caption,timestamp,media_type,permalink,media_url,thumbnail_url",
        "access_token": access_token,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)

            if resp.status_code == 200:
                data = resp.json()
                logger.info(
                    f"[FEED-WEBHOOK] Fetched post {post_id}: "
                    f"{data.get('media_type', '?')}, caption={len(data.get('caption', ''))} chars"
                )
                return data

            logger.error(
                f"[FEED-WEBHOOK] Graph API error for post {post_id}: "
                f"{resp.status_code} {resp.text[:200]}"
            )
            return None

    except Exception as e:
        logger.error(f"[FEED-WEBHOOK] HTTP error fetching post {post_id}: {e}")
        return None


async def _embed_chunk(creator_id: str, chunk_id: str, content: str):
    """Generate embedding for a new chunk and store in pgvector."""
    import asyncio

    from core.embeddings import generate_embedding, store_embedding

    embedding = await asyncio.to_thread(generate_embedding, content)
    if not embedding:
        logger.warning(f"[FEED-WEBHOOK] Failed to generate embedding for chunk {chunk_id}")
        return

    stored = await asyncio.to_thread(
        store_embedding, chunk_id, creator_id, content, embedding
    )
    if stored:
        logger.info(f"[FEED-WEBHOOK] Embedding stored for chunk {chunk_id}")
    else:
        logger.warning(f"[FEED-WEBHOOK] Failed to store embedding for chunk {chunk_id}")
