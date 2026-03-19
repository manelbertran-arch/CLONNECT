"""
Instagram media extraction and message processing.

Extracts media info from webhook attachments and processes
messages through the DM agent pipeline.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.cloudinary_service import get_cloudinary_service

logger = logging.getLogger("clonnect-instagram")


def extract_media_info(attachments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Extract media URL and type from Instagram message attachments.

    Supports both Meta formats:
    - New format (Instagram Messaging API): payload.url
    - Legacy format: image_data.url, video_data.url, audio_data.url
    """
    if not attachments:
        return None

    for att in attachments:
        att_type = (att.get("type") or "").lower()

        # Handle share/reel attachments
        if att_type in ("share", "reel"):
            share_data = att.get("share", {})
            share_link = share_data.get("link", "") if isinstance(share_data, dict) else ""
            if share_link and "reel" in share_link.lower():
                media_type = "shared_reel"
            elif att_type == "reel":
                media_type = "shared_reel"
            else:
                media_type = "share"

            result: Dict[str, Any] = {
                "type": media_type,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
            if share_link:
                result["permalink"] = share_link

            # Extract CDN thumbnail URL if present
            payload = att.get("payload", {})
            cdn_url = (
                (payload.get("url") if isinstance(payload, dict) else None)
                or att.get("image_data", {}).get("url")
                or att.get("video_data", {}).get("url")
                or att.get("url")
            )
            if cdn_url:
                result["url"] = cdn_url

            return result

        # Try new payload format first
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
            media_url = (
                att.get("url")
                or att.get("file_url")
                or att.get("preview_url")
                or att.get("src")
                or att.get("source")
                or att.get("link")
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
            "url": fallback_url,
            "raw_keys": raw_keys,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }

    return None


async def process_message_impl(handler, message) -> "DMResponse":
    """
    Process an Instagram message through DMResponderAgent.

    Handles media extraction, story processing, audio transcription,
    and delegates to the DM agent for response generation.
    """
    from core.dm_agent_v2 import DMResponse

    if not handler.dm_agent:
        handler._init_agent()

    if not handler.dm_agent:
        raise RuntimeError("DM Agent not initialized")

    # Get profile and update lead
    username, profile_pic_url = await handler._get_profile_and_update_lead(message.sender_id)

    message_text = message.text
    media_info = None
    story_info = None

    # Handle STORY messages (reply_to, mention)
    if message.story:
        story_info = await _process_story_message(handler, message)
        if story_info and not message_text:
            story_type = story_info.get("type", "")
            if story_type == "story_reaction":
                message_text = f"Reacción {story_info.get('emoji', '❤️')} a story"
            elif story_type == "story_reply":
                message_text = "Respuesta a story"
            elif story_type == "story_mention":
                message_text = "Mención en story"

    if not message_text and message.attachments and not story_info:
        media_info = extract_media_info(message.attachments)
        if media_info:
            media_info = await _capture_media_permanently(handler, message.sender_id, media_info)
            media_type = media_info.get("type", "media")
            media_type_display = {
                "image": "Imagen", "video": "Video", "audio": "Audio",
                "gif": "GIF", "sticker": "Sticker",
            }.get(media_type, "Media")
            message_text = f"[{media_type_display}]"
            logger.info(
                f"[IG:{message.sender_id}] Media message: type={media_type}, "
                f"url={'Yes' if media_info.get('url') else 'No'}"
            )

    # AUDIO TRANSCRIPTION
    if media_info and media_info.get("type") == "audio" and media_info.get("url"):
        message_text, media_info = await _transcribe_audio(
            handler, message.sender_id, message_text, media_info
        )

    # Build metadata
    dm_metadata = {
        "message_id": message.message_id,
        "username": username,
        "platform": "instagram",
    }
    if media_info:
        dm_metadata["media"] = media_info
        if media_info.get("audio_intel"):
            dm_metadata["audio_intel"] = media_info["audio_intel"]
    if story_info:
        dm_metadata["story"] = story_info
        dm_metadata["msg_metadata"] = story_info

    # Process with DM agent
    logger.info(f"[V2-FIX] Calling process_dm with V2 signature for {message.sender_id}")
    response = await handler.dm_agent.process_dm(
        message=message_text or "[Media]",
        sender_id=f"ig_{message.sender_id}",
        metadata=dm_metadata,
    )

    # Log response
    response_text = getattr(response, "content", None) or getattr(response, "response_text", "")
    intent_str = (
        response.intent.value if hasattr(response.intent, "value") else str(response.intent)
    )
    logger.info(f"[IG:{message.sender_id}] Intent: {intent_str} ({response.confidence:.0%})")
    logger.info(f"[IG:{message.sender_id}] Output: {response_text[:100]}...")

    return response


async def _process_story_message(handler, message) -> Optional[Dict[str, Any]]:
    """Process story reply/mention/reaction and capture media."""
    story_data = message.story
    story_type = None
    story_link = None

    if story_data.get("reply_to"):
        story_type = "story_reply"
        story_link = story_data["reply_to"].get("link", "")
    elif story_data.get("mention"):
        story_type = "story_mention"
        story_link = story_data["mention"].get("link", "")

    if not story_type:
        return None

    # Extract CDN URL from attachments
    cdn_url = None
    if message.attachments:
        att = message.attachments[0]
        cdn_url = (
            att.get("video_data", {}).get("url")
            or att.get("image_data", {}).get("url")
            or (att.get("payload", {}).get("url") if isinstance(att.get("payload"), dict) else None)
            or att.get("url")
        )

    # Get reaction emoji if present
    reaction_emoji = None
    if message.reactions:
        reaction_emoji = message.reactions[0].get("emoji", "❤️")
        if reaction_emoji:
            story_type = "story_reaction"

    story_info = {
        "type": story_type,
        "url": cdn_url or "",
        "link": story_link,
    }
    if reaction_emoji:
        story_info["emoji"] = reaction_emoji

    logger.info(
        f"[IG:{message.sender_id}] Story message: type={story_type}, "
        f"cdn_url={'Yes' if cdn_url else 'No'}, link={'Yes' if story_link else 'No'}"
    )

    # Capture CDN media immediately before it expires
    if cdn_url:
        from services.media_capture_service import capture_media_from_url, is_cdn_url

        if is_cdn_url(cdn_url):
            cloudinary_svc = get_cloudinary_service()
            if cloudinary_svc.is_configured:
                folder = f"clonnect/{handler.creator_id or 'unknown'}/stories"
                result = cloudinary_svc.upload_from_url(
                    url=cdn_url,
                    media_type="video",
                    folder=folder,
                    tags=["instagram", "story", f"sender_{message.sender_id}"],
                )
                if result.success:
                    story_info["original_url"] = cdn_url
                    story_info["permanent_url"] = result.url
                    story_info["cloudinary_id"] = result.public_id
                    logger.info(f"[IG:{message.sender_id}] Story media uploaded to Cloudinary")
                else:
                    captured = await capture_media_from_url(
                        url=cdn_url, media_type="video",
                        creator_id=handler.creator_id,
                    )
                    if captured:
                        story_info["permanent_url"] = captured
            else:
                captured = await capture_media_from_url(
                    url=cdn_url, media_type="video",
                    creator_id=handler.creator_id,
                )
                if captured:
                    story_info["permanent_url"] = captured
                    logger.info(f"[IG:{message.sender_id}] Story media captured permanently")

    return story_info


async def _capture_media_permanently(
    handler, sender_id: str, media_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Upload media to Cloudinary or capture as base64."""
    if not media_info.get("url"):
        return media_info

    from services.media_capture_service import capture_media_from_url, is_cdn_url

    media_type = media_info.get("type", "unknown")
    cloudinary_svc = get_cloudinary_service()

    if cloudinary_svc.is_configured:
        folder = f"clonnect/{handler.creator_id or 'unknown'}/media"
        result = cloudinary_svc.upload_from_url(
            url=media_info["url"],
            media_type=media_type,
            folder=folder,
            tags=["instagram", f"sender_{sender_id}"],
        )
        if result.success:
            logger.info(f"[IG:{sender_id}] Media uploaded to Cloudinary: {result.public_id}")
            media_info["original_url"] = media_info["url"]
            media_info["url"] = result.url
            media_info["cloudinary_id"] = result.public_id
        else:
            logger.warning(f"[IG:{sender_id}] Cloudinary upload failed: {result.error}")
            if is_cdn_url(media_info["url"]):
                captured = await capture_media_from_url(
                    url=media_info["url"], media_type=media_type,
                    creator_id=handler.creator_id,
                )
                if captured:
                    media_info["permanent_url"] = captured
                    logger.info(f"[IG:{sender_id}] Captured media to Cloudinary (fallback)")
    else:
        logger.debug("[IG] Cloudinary not configured, skipping media capture")
        # No base64 fallback — Cloudinary is required for media capture

    return media_info


async def _transcribe_audio(
    handler, sender_id: str, message_text: str, media_info: Dict[str, Any]
) -> tuple:
    """Transcribe audio messages with Whisper + audio intelligence."""
    try:
        from ingestion.transcriber import get_transcriber

        transcriber = get_transcriber()
        transcript = await transcriber.transcribe_url(media_info["url"])
        if transcript and transcript.full_text.strip():
            transcribed_text = transcript.full_text.strip()

            try:
                from services.audio_intelligence import get_audio_intelligence

                intel = get_audio_intelligence()
                detected_lang = getattr(transcript, "language", None) or "es"
                if detected_lang == "auto":
                    detected_lang = "es"
                ai_result = await intel.process(
                    raw_text=transcribed_text,
                    duration_seconds=int(media_info.get("duration", 0)),
                    language=detected_lang,
                    role="user",
                )
                legacy = ai_result.to_legacy_fields()
                media_info.update(legacy)
                media_info["audio_intel"] = ai_result.to_metadata()
                message_text = f"[\U0001f3a4 Audio]: {ai_result.clean_text or transcribed_text}"
            except Exception as pp_err:
                logger.warning(f"[IG] Audio intelligence failed: {pp_err}")
                message_text = f"[\U0001f3a4 Audio]: {transcribed_text}"
                media_info["transcription"] = transcribed_text

            logger.info(f"[IG:{sender_id}] Audio transcribed: {transcribed_text[:50]}...")
    except Exception as transcribe_err:
        logger.error(f"[IG:{sender_id}] Audio transcription failed: {transcribe_err}")

    return message_text, media_info
