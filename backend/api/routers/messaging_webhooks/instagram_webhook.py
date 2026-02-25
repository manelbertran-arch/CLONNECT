"""
Messaging webhooks router — Instagram platform.
Extracted from messaging_webhooks.py following TDD methodology.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["messaging-webhooks"])


@router.get("/webhook/instagram")
async def instagram_webhook_verify(request: Request):
    """
    Instagram webhook verification (GET).
    Meta sends GET request to verify the endpoint before activating webhooks.
    """
    from core.instagram_handler import get_instagram_handler

    params = dict(request.query_params)
    mode = params.get("hub.mode", "")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")

    handler = get_instagram_handler()
    result = handler.verify_webhook(mode, token, challenge)

    if result:
        logger.info("Instagram webhook verified successfully")
        return Response(content=result, media_type="text/plain")

    logger.warning("Instagram webhook verification failed")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook/instagram")
async def instagram_webhook_receive(request: Request):
    """
    Receive Instagram webhook events (POST).

    V9: Handles both messaging (DMs) and feed (new posts) events.
    - Messaging: Processed via DMResponderAgent (existing flow)
    - Feed: New post/reel detected → background task for real-time ingestion (SPEC-004B)

    Multi-creator routing with robust ID matching.
    """
    from api.routers.instagram import get_handler_for_creator
    from core.webhook_routing import (
        extract_all_instagram_ids,
        find_creator_for_webhook,
        save_unmatched_webhook,
        update_creator_webhook_stats,
    )

    logger.warning("=" * 60)
    logger.warning("========== INSTAGRAM WEBHOOK HIT V9 (MESSAGING + FEED) ==========")
    logger.warning("=" * 60)

    try:
        raw_body = await request.body()
        payload = await request.json()
        signature = request.headers.get("X-Hub-Signature-256", "")

        # Validate minimum webhook structure (Meta always sends 'object' + 'entry')
        if not payload.get("object") and not payload.get("entry"):
            logger.warning(f"Invalid webhook payload: missing 'object' and 'entry' fields")
            from fastapi.responses import JSONResponse
            return JSONResponse(
                content={"status": "error", "error": "Invalid webhook payload"},
                status_code=400,
            )

        # 1. Extract ALL possible Instagram IDs from payload
        instagram_ids = extract_all_instagram_ids(payload)

        if not instagram_ids:
            logger.warning("Could not extract any Instagram IDs from webhook payload")
            return {"status": "ok", "warning": "no_ids_found", "messages_processed": 0}

        logger.info(f"Extracted Instagram IDs: {instagram_ids}")

        # 2. Find creator using any of the extracted IDs
        creator_info, matched_id = find_creator_for_webhook(instagram_ids)

        # 3. If no creator found, save for debugging and return
        if not creator_info:
            logger.warning(f"No creator found for Instagram IDs: {instagram_ids}")
            unmatched_id = save_unmatched_webhook(instagram_ids, payload)
            return {
                "status": "ok",
                "warning": "unknown_creator",
                "instagram_ids": instagram_ids,
                "unmatched_webhook_id": unmatched_id,
                "messages_processed": 0,
            }

        creator_id = creator_info["creator_id"]
        logger.info(f"Found creator: {creator_id} (matched by ID: {matched_id})")

        # 4. Update webhook stats for this creator
        update_creator_webhook_stats(creator_id)

        # 5. Check for feed events (new posts/reels) — SPEC-004B
        #    Process in background so webhook returns 200 instantly
        feed_events_found = 0
        for entry in payload.get("entry", []):
            has_feed = any(
                c.get("field") == "feed"
                for c in entry.get("changes", [])
            )
            if has_feed:
                feed_events_found += 1
                asyncio.create_task(
                    _process_feed_event_safe(creator_info, entry)
                )

        if feed_events_found > 0:
            logger.info(
                f"[FEED-WEBHOOK] Dispatched {feed_events_found} feed event(s) "
                f"for {creator_id} to background processing"
            )

        # 6. Check if bot is active (for DM processing)
        has_messaging = any(
            "messaging" in entry
            for entry in payload.get("entry", [])
        )

        if not has_messaging:
            # Pure feed event — no DM to process
            return {
                "status": "ok",
                "creator_id": creator_id,
                "matched_id": matched_id,
                "messages_processed": 0,
                "feed_events_dispatched": feed_events_found,
            }

        if not creator_info.get("bot_active", False):
            logger.info(f"Bot not active for creator {creator_id}, skipping DM processing")
            return {
                "status": "ok",
                "info": "bot_paused",
                "creator_id": creator_id,
                "matched_id": matched_id,
                "messages_processed": 0,
                "feed_events_dispatched": feed_events_found,
            }

        # 7. Get handler for this creator and process DMs
        handler = get_handler_for_creator(creator_info)
        result = await handler.handle_webhook(payload, signature, raw_body=raw_body)

        logger.info(f"Instagram webhook processed: {result.get('messages_processed', 0)} messages")
        return {
            **result,
            "creator_id": creator_id,
            "matched_id": matched_id,
            "feed_events_dispatched": feed_events_found,
        }

    except Exception as e:
        logger.error(f"Error processing Instagram webhook: {e}")
        import traceback

        logger.error(traceback.format_exc())
        # Return 200 to acknowledge receipt (prevents infinite retries from Meta)
        return {"status": "error", "error": str(e)}


async def _process_feed_event_safe(creator_info: dict, entry: dict):
    """Wrapper to safely run feed webhook processing in background."""
    try:
        from services.feed_webhook_handler import process_feed_webhook

        await process_feed_webhook(creator_info, entry)
    except Exception as e:
        logger.error(
            "[FEED-WEBHOOK] Background processing failed for "
            f"{creator_info.get('creator_id', '?')}: {e}"
        )



@router.get("/instagram/status")
async def instagram_status():
    """Get Instagram handler status"""
    from core.instagram_handler import get_instagram_handler

    handler = get_instagram_handler()
    return {
        "status": "ok",
        "handler": handler.get_status(),
        "recent_messages": handler.get_recent_messages(5),
        "recent_responses": handler.get_recent_responses(5),
    }


@router.post("/webhook/instagram/comments")
async def instagram_comments_webhook(request: Request):
    """
    Webhook for Instagram comments.
    When someone comments on a post with interest keywords, auto-sends a DM.
    Enable with AUTO_DM_ON_COMMENTS=true environment variable.
    """
    from core.instagram_handler import get_instagram_handler

    try:
        payload = await request.json()
        handler = get_instagram_handler()

        results = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "comments":
                    comment_data = change.get("value", {})
                    result = await handler.handle_comment(comment_data)
                    if result:
                        results.append(result)

        return {"status": "ok", "comments_processed": len(results), "results": results}

    except Exception as e:
        logger.error(f"Error processing Instagram comments webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal error processing webhook")
