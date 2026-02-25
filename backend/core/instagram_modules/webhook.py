"""
Instagram webhook processing.

Main webhook handler that processes incoming Meta webhook payloads,
extracts messages, handles deduplication, rate limiting, and delegates
response handling to dispatch module.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from core.instagram import InstagramMessage
from core.rate_limiter import get_rate_limiter

logger = logging.getLogger("clonnect-instagram")


async def handle_webhook_impl(
    handler,
    payload: Dict[str, Any],
    signature: str = "",
    raw_body: bytes = None,
) -> Dict[str, Any]:
    """
    Handle incoming webhook from Meta (POST request).

    Args:
        handler: InstagramHandler instance
        payload: Webhook payload from Meta
        signature: X-Hub-Signature-256 header for verification
        raw_body: Original raw HTTP body bytes for accurate HMAC verification

    Returns:
        Processing result with status and responses
    """
    from core.instagram_modules.dispatch import dispatch_response
    from core.instagram_modules.echo import (
        has_creator_responded_recently,
        process_reaction_events,
        record_creator_manual_response,
    )

    # Verify signature if app_secret is configured
    if handler.connector and handler.app_secret and signature:
        if raw_body:
            payload_bytes = raw_body
        else:
            import json
            payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
        if not handler.connector.verify_webhook_signature(payload_bytes, signature):
            logger.warning("Invalid webhook signature")
            handler.status.errors += 1
            return {"status": "error", "reason": "invalid_signature"}

    # Extract and record echo messages (creator's manual responses)
    echo_messages = await _extract_echo_messages(handler, payload)
    echo_recorded = 0
    for echo_msg in echo_messages:
        if await record_creator_manual_response(handler, echo_msg):
            echo_recorded += 1

    # Record message reactions
    reactions_recorded = await process_reaction_events(handler, payload)

    # Extract messages from webhook
    messages = _extract_messages(handler, payload)

    if not messages:
        return {
            "status": "ok",
            "messages_processed": 0,
            "echo_messages_recorded": echo_recorded,
            "reactions_recorded": reactions_recorded,
            "results": [],
        }

    # Check if copilot mode is enabled
    copilot_enabled = await handler._is_copilot_enabled()

    results = []
    for message in messages:
        # Skip messages from any known creator ID
        known_ids = getattr(handler, "known_creator_ids", set())
        if not known_ids:
            known_ids = {handler.page_id, handler.ig_user_id, "17841400506734756"}

        if message.sender_id in known_ids:
            logger.info(f"Skipping message from known creator ID: {message.sender_id}")
            continue

        if message.recipient_id and message.sender_id == message.recipient_id:
            logger.info(f"Skipping self-message: {message.sender_id}")
            continue

        handler._record_received(message)
        input_preview = (
            message.text[:100]
            if message.text
            else f"[Media: {len(message.attachments)} attachment(s)]"
        )
        logger.info(f"[IG:{message.sender_id}] Input: {input_preview}")

        # Lead enrichment
        lead_exists = await handler._check_lead_exists(message.sender_id)
        lead_status = None

        if not lead_exists:
            logger.info(f"[IG:{message.sender_id}] New lead detected - loading history...")
            username = ""
            full_name = ""
            try:
                if handler.connector:
                    profile = await handler.connector.get_user_profile(message.sender_id)
                    if profile:
                        username = profile.username or ""
                        full_name = profile.name or ""
            except Exception as e:
                logger.warning(f"[IG:{message.sender_id}] Could not get profile: {e}")

            lead_status = await handler._enrich_new_lead(
                sender_id=message.sender_id, username=username, full_name=full_name
            )
            if lead_status:
                logger.info(f"[IG:{message.sender_id}] Lead enriched with status: {lead_status}")

        # Rate limit check
        rate_limiter = get_rate_limiter()
        allowed, reason = rate_limiter.check_limit(message.sender_id)
        if not allowed:
            logger.warning(f"[IG:{message.sender_id}] Rate limited: {reason}")
            await handler._save_user_message_to_db(msg=message, username="", full_name="")
            results.append({
                "message_id": message.message_id,
                "sender_id": message.sender_id,
                "status": "rate_limited",
                "reason": reason,
            })
            continue

        try:
            # DEDUPLICATION: In-memory check
            if not hasattr(handler, "_processed_message_ids"):
                handler._processed_message_ids = set()

            if message.message_id in handler._processed_message_ids:
                logger.warning(
                    f"[IG:{message.sender_id}] Skipping duplicate message_id: {message.message_id}"
                )
                results.append({
                    "message_id": message.message_id,
                    "sender_id": message.sender_id,
                    "status": "duplicate_skipped",
                })
                continue

            handler._processed_message_ids.add(message.message_id)
            if len(handler._processed_message_ids) > 1000:
                handler._processed_message_ids = set(list(handler._processed_message_ids)[-500:])

            # PERSISTENT DEDUP: DB check
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
                            logger.info(f"[DEDUP:DB] Message {message.message_id} already in DB — skipping")
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

            # Process with DM agent
            response = await handler.process_message(message)

            response_text = getattr(response, "content", None) or getattr(response, "response_text", "")
            intent_str = (
                response.intent.value if hasattr(response.intent, "value") else str(response.intent)
            )

            # Never send error messages to users
            error_patterns = ["[LLM not configured]", "[Error", "[error", "error:", "Error:"]
            is_error_response = any(pattern in response_text for pattern in error_patterns)

            if is_error_response:
                logger.error(
                    f"[IG:{message.sender_id}] LLM returned error, NOT sending: {response_text[:100]}"
                )
                await handler._save_user_message_to_db(msg=message, username="", full_name="")
                results.append({
                    "message_id": message.message_id,
                    "sender_id": message.sender_id,
                    "status": "llm_error",
                    "error": "LLM not available - response not sent",
                })
                continue

            # Get username and display name
            username = ""
            full_name = ""
            try:
                if handler.connector:
                    profile = await handler.connector.get_user_profile(message.sender_id)
                    if profile:
                        username = profile.username
                        full_name = profile.name or ""
            except Exception as e:
                logger.warning("Failed to get user profile for %s: %s", message.sender_id, e)

            # Dispatch to copilot or autopilot
            result = await dispatch_response(
                handler, message, response, response_text, intent_str,
                username, full_name, copilot_enabled,
            )
            results.append(result)

        except Exception as e:
            import traceback
            logger.error(
                f"Error processing message {message.message_id}: {e}\n{traceback.format_exc()}"
            )
            handler.status.errors += 1
            results.append({
                "message_id": message.message_id,
                "sender_id": message.sender_id,
                "error": str(e),
            })

    return {
        "status": "ok",
        "messages_processed": len(messages),
        "echo_messages_recorded": echo_recorded,
        "copilot_mode": copilot_enabled,
        "results": results,
    }


async def _extract_echo_messages(handler, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract echo messages (creator's manual responses) from webhook payload."""
    echo_messages = []

    try:
        for entry in payload.get("entry", []):
            for messaging in entry.get("messaging", []):
                if "message" in messaging:
                    message_data = messaging["message"]

                    if message_data.get("is_echo"):
                        sender_id = messaging.get("sender", {}).get("id", "")
                        recipient_id = messaging.get("recipient", {}).get("id", "")
                        text = message_data.get("text", "")
                        attachments = message_data.get("attachments", [])

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

                        if text:
                            echo_messages.append({
                                "message_id": message_data.get("mid", ""),
                                "sender_id": sender_id,
                                "recipient_id": recipient_id,
                                "text": text,
                                "timestamp": messaging.get("timestamp", 0),
                                "attachments": attachments,
                            })
                            logger.info(
                                f"[Echo] Detected creator response to {recipient_id}: {text[:50]}..."
                            )

    except Exception as e:
        logger.error(f"Error extracting echo messages: {e}")

    return echo_messages


def _extract_messages(handler, payload: Dict[str, Any]) -> List[InstagramMessage]:
    """Extract messages from webhook payload."""
    messages = []

    try:
        for entry in payload.get("entry", []):
            for messaging in entry.get("messaging", []):
                if "message" in messaging:
                    message_data = messaging["message"]

                    if message_data.get("is_echo"):
                        logger.info("Skipping echo message (sent by bot)")
                        continue

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
                        story=message_data.get("story"),
                        reactions=message_data.get("reactions", {}).get("data", []),
                    )
                    if msg.text or msg.attachments or msg.story:
                        messages.append(msg)
    except Exception as e:
        logger.error(f"Error extracting messages from webhook: {e}")

    return messages
