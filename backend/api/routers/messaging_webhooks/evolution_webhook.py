"""
Messaging webhooks router — Evolution API (WhatsApp via Baileys) platform.
Extracted from messaging_webhooks.py following TDD methodology.
"""

import asyncio
import logging
import os
from typing import Dict

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter(tags=["messaging-webhooks"])


# =============================================================================
# EVOLUTION API WEBHOOK (WhatsApp via Baileys)
# =============================================================================

# Instance name → creator_id mapping
# TODO: Move to DB once multi-creator is needed
EVOLUTION_INSTANCE_MAP: Dict[str, str] = {
    "stefano-fitpack": "stefano_bonanno",
    "iris-bertran": "iris_bertran",
}

# Guard: prevent duplicate WA onboarding pipeline launches
_wa_pipeline_running: set = set()

# Cooldown: prevent re-running pipeline on frequent reconnects
_wa_pipeline_last_run: Dict[str, float] = {}
_WA_PIPELINE_COOLDOWN = 3600  # 1 hour between pipeline runs per creator

# Dedup: Evolution/Baileys sends messages.upsert twice per message.
# Track processed message IDs with timestamps to skip duplicates.
_evo_processed_messages: Dict[str, float] = {}
_EVO_DEDUP_TTL = 60  # seconds

# Content-based dedup: Baileys sometimes sends the SAME message with
# different message_ids (up to 3x). Track sender+text hash to catch these.
_evo_content_dedup: Dict[str, float] = {}
_EVO_CONTENT_DEDUP_TTL = 60  # seconds


def _evo_is_duplicate(message_id: str) -> bool:
    """Return True if this message_id was already processed (dedup)."""
    import time

    now = time.time()

    # Purge expired entries every call (dict is small, O(n) is fine)
    expired = [k for k, t in _evo_processed_messages.items() if now - t > _EVO_DEDUP_TTL]
    for k in expired:
        del _evo_processed_messages[k]

    if message_id in _evo_processed_messages:
        return True

    _evo_processed_messages[message_id] = now
    return False


def _evo_is_content_duplicate(sender: str, text: str) -> bool:
    """Return True if same sender sent same text within TTL (content-based dedup).

    Baileys sometimes delivers 1 WhatsApp message as 2-3 webhook events
    with DIFFERENT message_ids. This catches those by hashing sender+text.
    """
    import hashlib
    import time

    now = time.time()

    # Purge expired
    expired = [k for k, t in _evo_content_dedup.items() if now - t > _EVO_CONTENT_DEDUP_TTL]
    for k in expired:
        del _evo_content_dedup[k]

    key = hashlib.md5(f"{sender}:{text}".encode()).hexdigest()
    if key in _evo_content_dedup:
        return True

    _evo_content_dedup[key] = now
    return False


@router.post("/webhook/whatsapp/evolution")
async def evolution_webhook(request: Request):
    """
    Receive webhook events from Evolution API (WhatsApp via Baileys).

    Events handled:
    - messages.upsert: New incoming message → generate suggestion → save as pending
      (COPILOT mode: does NOT auto-send. Creator approves from dashboard.)
    - connection.update: Instance connected/disconnected
    - qrcode.updated: New QR code generated

    All other events are acknowledged but ignored.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok", "ignored": "invalid_json"}

    event = payload.get("event", "")
    instance = payload.get("instance", "")

    # Log non-upsert events for debugging
    if event and event not in ("messages.upsert", "messages.update"):
        logger.info(f"[EVO:{instance}] Event: {event}")

    # Log non-message events briefly
    if event == "connection.update":
        state = payload.get("data", {}).get("state", "unknown")
        logger.info(f"[EVO:{instance}] Connection update: {state}")

        if state == "open":
            import time as _time
            creator_id = EVOLUTION_INSTANCE_MAP.get(instance)
            if creator_id and creator_id not in _wa_pipeline_running:
                # Cooldown: skip if pipeline ran recently (Evolution reconnects frequently)
                last_run = _wa_pipeline_last_run.get(creator_id, 0)
                if _time.time() - last_run < _WA_PIPELINE_COOLDOWN:
                    logger.info(f"[EVO:{instance}] Pipeline cooldown active for {creator_id}, skipping")
                    return {"status": "ok", "event": event, "state": state, "pipeline": "cooldown"}
                _wa_pipeline_running.add(creator_id)
                _wa_pipeline_last_run[creator_id] = _time.time()

                async def _run_wa_pipeline():
                    try:
                        from services.whatsapp_onboarding_pipeline import (
                            WhatsAppOnboardingPipeline,
                        )

                        pipeline = WhatsAppOnboardingPipeline(creator_id, instance)
                        result = await pipeline.run()
                        logger.info(
                            f"[WA-PIPELINE] Completed for {creator_id}: "
                            f"{result.get('status', 'unknown')}"
                        )
                    except Exception as e:
                        logger.error(f"[WA-PIPELINE] Failed for {creator_id}: {e}")
                    finally:
                        _wa_pipeline_running.discard(creator_id)

                asyncio.create_task(_run_wa_pipeline())
                logger.info(
                    f"[EVO:{instance}] WhatsApp onboarding pipeline started for {creator_id}"
                )

        return {"status": "ok", "event": event, "state": state}

    if event == "qrcode.updated":
        logger.info(f"[EVO:{instance}] QR code updated")
        return {"status": "ok", "event": event}

    # Handle message deletion ("Delete for everyone")
    # Evolution v2.3.7 sends: event="messages.edited" with data.type="REVOKE"
    # Older versions: event="messages.update" with messageStubType="REVOKE" or 1
    # Some forks: event="messages.delete"
    event_lower = event.lower().replace("_", ".")
    if event_lower in ("messages.update", "messages.delete", "messages.edited"):
        data_raw = payload.get("data", {})
        updates = data_raw if isinstance(data_raw, list) else [data_raw]
        handled = 0
        for update in updates:
            key = update.get("key", {})
            # ID location varies: key.id (messages.edited), root id (messages.delete)
            msg_id = key.get("id", "") or update.get("id", "")
            stub_type = update.get("messageStubType")
            update_type = update.get("type")  # Evolution v2.3.7: "REVOKE"
            update_status = update.get("status")
            # Detect deletion from any format:
            is_delete = (
                event_lower == "messages.delete"
                or stub_type in ("REVOKE", 1, "1")
                or update_type == "REVOKE"
                or update_status in (5, "DELETED")
            )
            if is_delete and msg_id:
                logger.info(
                    f"[EVO:{instance}] Delete detected: msg_id={msg_id} "
                    f"type={update_type} stub={stub_type} status={update_status} "
                    f"fromMe={key.get('fromMe')}"
                )
                asyncio.create_task(_handle_message_deleted(instance, msg_id, key))
                handled += 1
            else:
                logger.debug(
                    f"[EVO:{instance}] {event} (non-delete): "
                    f"msg_id={msg_id} status={update_status}"
                )
        if handled:
            logger.info(f"[EVO:{instance}] Message delete: {handled} message(s) processed")
        return {"status": "ok", "event": event, "handled": handled}

    # Only process incoming messages
    if event != "messages.upsert":
        return {"status": "ok", "ignored": event}

    data = payload.get("data", {})
    key = data.get("key", {})

    from_me = key.get("fromMe", False)

    # Extract message text (multiple possible locations in Baileys format)
    message_obj = data.get("message", {})
    text = (
        message_obj.get("conversation")
        or (message_obj.get("extendedTextMessage") or {}).get("text")
        or (message_obj.get("imageMessage") or {}).get("caption")
        or (message_obj.get("videoMessage") or {}).get("caption")
        or ""
    )

    # Detect ALL media types from Baileys message object
    audio_obj = message_obj.get("audioMessage") or message_obj.get("pttMessage")
    image_obj = message_obj.get("imageMessage")
    video_obj = message_obj.get("videoMessage")
    sticker_obj = message_obj.get("stickerMessage")
    document_obj = message_obj.get("documentMessage")

    # Determine the primary media type (priority: audio > video > image > sticker > document)
    detected_media_type = None
    if audio_obj:
        detected_media_type = "audio"
    elif video_obj:
        detected_media_type = "video"
    elif image_obj:
        detected_media_type = "image"
    elif sticker_obj:
        detected_media_type = "sticker"
    elif document_obj:
        detected_media_type = "document"

    # Process media: download from WhatsApp CDN → Cloudinary → (transcribe if audio)
    media_result = None
    audio_transcription = None
    if detected_media_type:
        try:
            media_result = await _download_evolution_media(instance, data, detected_media_type)
            if detected_media_type == "audio" and media_result.get("transcription"):
                audio_transcription = media_result["transcription"]
        except Exception as media_err:
            logger.error(f"[EVO:{instance}] Media processing failed ({detected_media_type}): {media_err}")

        # If no text yet, set a descriptive placeholder so the message isn't dropped
        if not text.strip():
            if detected_media_type == "audio":
                # Prefer clean_text from audio intelligence over raw transcription
                ai = media_result.get("audio_intel", {}) if media_result else {}
                display_text = ai.get("clean_text") or ai.get("summary") or audio_transcription
                text = f"[\U0001f3a4 Audio]: {display_text}" if display_text else "[\U0001f3a4 Audio message]"
            else:
                placeholder_map = {
                    "image": "[\U0001f4f7 Photo]",
                    "video": "[\U0001f3ac Video]",
                    "sticker": "[\U0001f3f7\ufe0f Sticker]",
                    "document": "[\U0001f4c4 Document]",
                }
                text = placeholder_map.get(detected_media_type, "[\U0001f4ce Media]")

    if not text.strip():
        return {"status": "ok", "ignored": "no_text"}

    # Extract sender info
    remote_jid = key.get("remoteJid", "")
    sender_number = remote_jid.replace("@s.whatsapp.net", "").replace("@g.us", "").replace("@lid", "")
    push_name = data.get("pushName", "")
    message_id = key.get("id", "")

    # Dedup: Baileys sends messages.upsert twice per message
    if not message_id or _evo_is_duplicate(message_id):
        return {"status": "ok", "ignored": "duplicate"}

    # Resolve creator from instance
    creator_id = EVOLUTION_INSTANCE_MAP.get(instance)
    if not creator_id:
        logger.warning(f"[EVO:{instance}] Unknown instance, no creator mapping")
        return {"status": "ok", "ignored": "unknown_instance"}

    # fromMe=true → Creator's own outgoing message. Save to DB but do NOT
    # generate a DM agent response (it's not an incoming lead message).
    if from_me:
        follower_id = f"wa_{sender_number}"
        logger.info(
            f"[EVO:{instance}] Outgoing (fromMe) to {sender_number}: {text[:80]}"
        )
        # Build outgoing msg_metadata from media_result
        outgoing_meta = None
        if detected_media_type:
            outgoing_meta = {
                "type": detected_media_type,
                "platform": "whatsapp",
                "source": "evolution_outgoing",
            }
            if media_result and media_result.get("url"):
                outgoing_meta["url"] = media_result["url"]
            if audio_transcription:
                outgoing_meta["transcription"] = audio_transcription
            if detected_media_type == "audio":
                if media_result and media_result.get("audio_intel"):
                    outgoing_meta["audio_intel"] = media_result["audio_intel"]
                    for k in ("transcript_raw", "transcript_full", "transcript_summary"):
                        if media_result.get(k):
                            outgoing_meta[k] = media_result[k]
                if isinstance(audio_obj, dict):
                    duration = audio_obj.get("seconds") or audio_obj.get("duration")
                    if duration:
                        outgoing_meta["duration"] = duration

        asyncio.create_task(
            _save_evolution_outgoing_message(
                instance=instance,
                creator_id=creator_id,
                follower_id=follower_id,
                text=text,
                message_id=message_id,
                push_name=push_name,
                msg_metadata=outgoing_meta,
            )
        )
        return {
            "status": "ok",
            "event": event,
            "instance": instance,
            "sender": sender_number,
            "saved_outgoing": True,
        }

    # Content-based dedup: Baileys sends 1 message as 2-3 events with different IDs
    if not from_me and _evo_is_content_duplicate(sender_number, text):
        logger.info(
            f"[EVO:{instance}] Content dedup: same text from {sender_number} within 60s, skipping"
        )
        return {"status": "ok", "ignored": "content_duplicate"}

    logger.info(
        f"[EVO:{instance}] Message from {push_name} ({sender_number}): {text[:80]}"
    )

    # Build metadata for media messages
    msg_metadata = None
    if detected_media_type:
        msg_metadata = {
            "type": detected_media_type,
            "platform": "whatsapp",
            "source": "evolution",
        }
        # Cloudinary permanent URL (preferred) or WhatsApp CDN URL (expires)
        if media_result and media_result.get("url"):
            msg_metadata["url"] = media_result["url"]
        # Audio-specific fields
        if detected_media_type == "audio":
            if audio_transcription:
                msg_metadata["transcription"] = audio_transcription
            # Audio Intelligence structured data (summary, entities, clean_text)
            if media_result and media_result.get("audio_intel"):
                msg_metadata["audio_intel"] = media_result["audio_intel"]
                # Legacy fields for backward compat
                for k in ("transcript_raw", "transcript_full", "transcript_summary"):
                    if media_result.get(k):
                        msg_metadata[k] = media_result[k]
            if isinstance(audio_obj, dict):
                duration = audio_obj.get("seconds") or audio_obj.get("duration")
                if duration:
                    msg_metadata["duration"] = duration
        # Video duration
        elif detected_media_type == "video" and isinstance(video_obj, dict):
            duration = video_obj.get("seconds") or video_obj.get("duration")
            if duration:
                msg_metadata["duration"] = duration
        # Sticker → render as sticker (smaller display)
        elif detected_media_type == "sticker":
            msg_metadata["render_as_sticker"] = True
        # Document filename
        elif detected_media_type == "document" and isinstance(document_obj, dict):
            filename = document_obj.get("fileName") or document_obj.get("title")
            if filename:
                msg_metadata["filename"] = filename

    # ── EARLY SAVE: Save user message in a thread (non-blocking) ──
    # Runs via asyncio.to_thread so DB operations don't block the event loop.
    # The SSE notification fires after the DB commit completes (~0.5-1s).
    _early_saved = False

    async def _do_early_save():
        nonlocal _early_saved
        from api.database import SessionLocal as _EarlySession
        from api.models import Creator as _ECreator, Lead as _ELead, Message as _EMsg
        from datetime import datetime, timezone as _tz

        follower_id_es = f"wa_{sender_number}"

        def _db_work():
            _es = _EarlySession()
            try:
                _ec = _es.query(_ECreator).filter_by(name=creator_id).first()
                if not _ec:
                    return False
                _el = _es.query(_ELead).filter(
                    _ELead.creator_id == _ec.id,
                    _ELead.platform_user_id == follower_id_es,
                ).first()
                if not _el:
                    return False
                _um = _EMsg(
                    lead_id=_el.id, role="user", content=text,
                    status="sent", platform_message_id=message_id,
                    msg_metadata=msg_metadata,
                )
                _es.add(_um)
                _el.last_contact_at = datetime.now(_tz.utc)
                _es.commit()
                return True
            finally:
                _es.close()

        try:
            saved = await asyncio.to_thread(_db_work)
            if saved:
                _early_saved = True
                # Invalidate follower cache (conversations cache kept intact to avoid
                # triggering 2.5s blocking query; SSE new_message handles client-side)
                try:
                    from api.cache import api_cache
                    api_cache.invalidate(f"follower_detail:{creator_id}:{follower_id_es}")
                except Exception:
                    pass
                try:
                    from api.routers.events import notify_creator
                    await notify_creator(
                        creator_id, "new_message",
                        {"follower_id": follower_id_es, "role": "user"},
                    )
                except Exception:
                    pass
                logger.info(
                    f"[EVO:{instance}] Early save: msg {message_id} "
                    f"for {sender_number} — frontend notified"
                )
        except Exception as early_err:
            logger.warning(f"[EVO:{instance}] Early save failed: {early_err}")

    follower_id = f"wa_{sender_number}"
    await _do_early_save()

    # Process with DM agent in background so webhook returns 200 fast
    asyncio.create_task(
        _process_evolution_message_safe(
            instance=instance,
            creator_id=creator_id,
            sender_number=sender_number,
            push_name=push_name,
            text=text,
            message_id=message_id,
            msg_metadata=msg_metadata,
        )
    )

    return {
        "status": "ok",
        "event": event,
        "instance": instance,
        "sender": sender_number,
        "processing": True,
    }


async def _download_evolution_media(instance: str, data: dict, media_type: str) -> dict:
    """
    Download any media type from Evolution API, upload to Cloudinary,
    and optionally transcribe (audio only).

    Uses Evolution's getBase64FromMediaMessage endpoint to fetch media bytes,
    uploads to Cloudinary for permanent storage, then transcribes audio via Whisper.

    Args:
        instance: Evolution API instance name
        data: Full webhook payload (contains message + key)
        media_type: "audio", "image", "video", "sticker", "document"

    Returns dict with keys: url (str|None), mimetype (str), transcription (str, audio only)
    """
    import base64
    import tempfile

    import httpx

    from services.evolution_api import EVOLUTION_API_KEY, EVOLUTION_API_URL

    result = {"transcription": "", "url": None, "mimetype": "application/octet-stream"}

    if not EVOLUTION_API_URL:
        logger.warning(f"[EVO:{instance}] Cannot fetch media: EVOLUTION_API_URL not set")
        return result

    message_obj = data.get("message", {})
    key = data.get("key", {})

    # Build the payload for getBase64FromMediaMessage
    media_payload = {"message": {"key": key, "message": message_obj}}

    url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{instance}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=media_payload, headers=headers)

            if resp.status_code >= 400:
                logger.error(
                    f"[EVO:{instance}] getBase64FromMediaMessage failed ({media_type}): "
                    f"HTTP {resp.status_code} {resp.text[:200]}"
                )
                return result

            resp_data = resp.json()
            b64_data = resp_data.get("base64", "")
            mimetype = resp_data.get("mimetype", "application/octet-stream")
            result["mimetype"] = mimetype

            if not b64_data:
                logger.warning(f"[EVO:{instance}] No base64 data in {media_type} response")
                return result

            # Determine file extension from mimetype
            ext_map = {
                # Audio
                "audio/ogg": ".ogg",
                "audio/ogg; codecs=opus": ".ogg",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "audio/wav": ".wav",
                "audio/webm": ".webm",
                # Image
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
                "image/gif": ".gif",
                # Video
                "video/mp4": ".mp4",
                "video/3gpp": ".3gp",
                "video/webm": ".webm",
                # Document
                "application/pdf": ".pdf",
                "application/msword": ".doc",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            }
            ext = ext_map.get(mimetype.split(";")[0].strip(), ".bin")

            # Decode base64 and write to temp file
            media_bytes = base64.b64decode(b64_data)

            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(media_bytes)
                tmp_path = tmp.name

            try:
                # Upload to Cloudinary for permanent storage
                try:
                    from services.cloudinary_service import get_cloudinary_service

                    cloud = get_cloudinary_service()
                    if cloud.is_configured:
                        sender = key.get("remoteJid", "unknown").replace("@s.whatsapp.net", "")
                        # Cloudinary maps: audio→video, sticker→image, document→raw
                        cloud_media_type = media_type
                        if media_type == "sticker":
                            cloud_media_type = "image"
                        elif media_type == "document":
                            cloud_media_type = "raw"

                        upload = cloud.upload_from_file(
                            file_path=tmp_path,
                            media_type=cloud_media_type,
                            folder=f"clonnect/{instance}/{media_type}",
                            tags=["whatsapp", media_type, sender],
                        )
                        if upload.success and upload.url:
                            result["url"] = upload.url
                            logger.info(
                                f"[EVO:{instance}] {media_type} uploaded to Cloudinary: {upload.url}"
                            )
                        else:
                            logger.warning(
                                f"[EVO:{instance}] Cloudinary upload failed ({media_type}): {upload.error}"
                            )
                except Exception as cloud_err:
                    logger.warning(f"[EVO:{instance}] Cloudinary upload skipped: {cloud_err}")

                # Transcribe audio with cascade (Groq → Gemini → OpenAI) + Audio Intelligence
                if media_type == "audio":
                    try:
                        from ingestion.transcriber import get_transcriber

                        transcriber = get_transcriber()
                        transcript = await transcriber.transcribe_file(tmp_path, language="es")
                        if transcript and transcript.full_text.strip():
                            raw_text = transcript.full_text.strip()
                            result["transcription"] = raw_text
                            # Audio Intelligence Pipeline (4-layer) — same as Instagram
                            try:
                                from services.audio_intelligence import get_audio_intelligence

                                intel = get_audio_intelligence()
                                ai_result = await intel.process(
                                    raw_text=raw_text,
                                    language="es",
                                    role="user",
                                )
                                result["audio_intel"] = ai_result.to_metadata()
                                legacy = ai_result.to_legacy_fields()
                                result.update(legacy)
                            except Exception as intel_err:
                                logger.warning(f"[EVO:{instance}] Audio intelligence failed: {intel_err}")
                    except Exception as whisper_err:
                        logger.error(f"[EVO:{instance}] Whisper transcription failed: {whisper_err}")

                return result
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    except Exception as e:
        logger.error(f"[EVO:{instance}] Media download error ({media_type}): {e}")
        return result


async def _handle_message_deleted(instance: str, message_id: str, key: dict):
    """Handle WhatsApp 'Delete for everyone' — soft-delete message in DB.

    - Marks the message with deleted_at timestamp
    - If the deleted message triggered a pending copilot suggestion, discards it
    - Removes the message from the in-memory follower cache
    """
    from datetime import datetime, timezone

    from api.database import SessionLocal
    from api.models import Message

    session = SessionLocal()
    try:
        msg = (
            session.query(Message)
            .filter(Message.platform_message_id == message_id)
            .first()
        )
        if not msg:
            logger.debug(f"[EVO:{instance}] Delete: message {message_id} not found in DB")
            return
        now = datetime.now(timezone.utc)
        msg.deleted_at = now
        lead_id = msg.lead_id

        # If there's a pending_approval suggestion triggered by this message, discard it
        pending = (
            session.query(Message)
            .filter(
                Message.lead_id == lead_id,
                Message.role == "assistant",
                Message.status == "pending_approval",
            )
            .first()
        )
        if pending:
            pending.status = "discarded"
            pending.copilot_action = "auto_discarded_deleted"
            pending.approved_at = now
            logger.info(
                f"[EVO:{instance}] Delete: discarded pending suggestion {pending.id} "
                f"(trigger message {message_id} was deleted)"
            )

        session.commit()
        logger.info(
            f"[EVO:{instance}] Delete: marked message {message_id} as deleted "
            f"(lead={lead_id}, pending_discarded={pending is not None})"
        )

        # Invalidate API caches + notify frontend
        creator_id = EVOLUTION_INSTANCE_MAP.get(instance)
        remote_jid = key.get("remoteJid", "")
        sender = remote_jid.replace("@s.whatsapp.net", "").replace("@g.us", "").replace("@lid", "")

        if creator_id:
            # Invalidate conversation & follower caches so frontend sees updated data
            try:
                from api.cache import api_cache
                follower_id = f"wa_{sender}" if sender else None
                api_cache.invalidate(f"conversations:{creator_id}")
                if follower_id:
                    api_cache.invalidate(f"follower_detail:{creator_id}:{follower_id}")
            except Exception:
                pass

            # Notify frontend via SSE so it refetches immediately
            try:
                from api.routers.events import notify_creator
                follower_id_sse = f"wa_{sender}" if sender else None
                await notify_creator(
                    creator_id,
                    "message_deleted",
                    {"follower_id": follower_id_sse, "lead_id": str(lead_id), "message_id": message_id},
                )
            except Exception:
                pass

        # Remove from in-memory follower cache
        try:
            if sender and creator_id:
                from services.memory_service import MemoryStore
                store = MemoryStore()
                follower_id = f"wa_{sender}"
                cache_key = f"{creator_id}:{follower_id}"
                if cache_key in store._cache:
                    follower = store._cache[cache_key]
                    original_len = len(follower.last_messages)
                    follower.last_messages = [
                        m for m in follower.last_messages
                        if not (isinstance(m, dict) and m.get("platform_message_id") == message_id)
                    ]
                    if len(follower.last_messages) < original_len:
                        logger.debug(f"[EVO:{instance}] Delete: removed from memory cache")
        except Exception as cache_err:
            logger.debug(f"[EVO:{instance}] Delete: cache cleanup skipped: {cache_err}")

    except Exception as e:
        logger.error(f"[EVO:{instance}] Delete handler error: {e}")
        session.rollback()
    finally:
        session.close()


async def _save_evolution_outgoing_message(
    instance: str,
    creator_id: str,
    follower_id: str,
    text: str,
    message_id: str,
    push_name: str,
    msg_metadata: dict = None,
):
    """
    Save a creator's outgoing WhatsApp message (fromMe=true) to the DB.

    This captures messages the creator sends directly from their phone so the
    dashboard shows the complete conversation (incoming + outgoing).
    No DM agent processing — this is not a lead message.
    """
    try:
        from datetime import datetime, timezone

        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        db = SessionLocal()
        try:
            # Find the creator (Creator.name stores the creator_id string)
            creator = db.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                logger.warning(f"[EVO:{instance}] Outgoing: creator {creator_id} not found")
                return

            # Find or create the lead for this remoteJid
            lead = db.query(Lead).filter(
                Lead.creator_id == creator.id,
                Lead.platform_user_id == follower_id,
            ).first()

            if not lead:
                import uuid

                sender_number = follower_id.removeprefix("wa_")
                # push_name here is the CREATOR's name (fromMe=true), not the contact's.
                # Use phone number as placeholder; inbound handler will set the real name.
                lead = Lead(
                    id=uuid.uuid4(),
                    creator_id=creator.id,
                    platform="whatsapp",
                    platform_user_id=follower_id,
                    username=f"+{sender_number}",
                    full_name=f"+{sender_number}",
                    phone=f"+{sender_number}" if sender_number else None,
                    source="whatsapp_dm",
                    status="nuevo",
                    purchase_intent=0.0,
                )
                db.add(lead)
                db.flush()
                logger.info(f"[EVO:{instance}] Outgoing: created lead {follower_id}")

            # DEDUP: skip if this outgoing message was already saved (e.g. Evolution replay on reconnect)
            if message_id:
                existing = (
                    db.query(Message.id)
                    .filter(
                        Message.lead_id == lead.id,
                        Message.platform_message_id == message_id,
                    )
                    .first()
                )
                if existing:
                    logger.info(
                        f"[EVO:{instance}] Outgoing msg {message_id} already in DB — skipping"
                    )
                    return

            # Audio Intelligence Pipeline (outgoing — creator's voice)
            if (
                msg_metadata
                and msg_metadata.get("type") == "audio"
                and msg_metadata.get("transcription")
            ):
                try:
                    from services.audio_intelligence import get_audio_intelligence

                    raw_text = msg_metadata["transcription"]
                    intel = get_audio_intelligence()
                    ai_result = await intel.process(
                        raw_text=raw_text,
                        duration_seconds=msg_metadata.get("duration", 0),
                        language="es",
                        role="assistant",
                    )
                    legacy = ai_result.to_legacy_fields()
                    msg_metadata.update(legacy)
                    msg_metadata["audio_intel"] = ai_result.to_metadata()
                    text = f"[\U0001f3a4 Audio]: {ai_result.clean_text or raw_text}"
                    logger.info(
                        f"[EVO:{instance}] Outgoing AudioIntel: "
                        f"{ai_result.summary[:60]}..."
                    )
                except Exception as e:
                    logger.warning(f"[EVO:{instance}] Outgoing audio intelligence failed: {e}")

            # Save the outgoing message (role=assistant, same as creator manual sends)
            import uuid

            msg_meta = {"source": "evolution_outgoing", "platform": "whatsapp"}
            if msg_metadata:
                msg_meta.update(msg_metadata)

            msg = Message(
                id=uuid.uuid4(),
                lead_id=lead.id,
                role="assistant",
                content=text,
                status="sent",
                approved_by="creator_manual",
                platform_message_id=message_id,
                msg_metadata=msg_meta,
            )
            db.add(msg)

            # Update last_contact_at so the lead appears fresh in the dashboard
            lead.last_contact_at = datetime.now(timezone.utc)

            # Auto-discard pending copilot suggestions for this lead
            # Pass creator_response so resolved_externally learning kicks in
            try:
                from core.copilot_service import get_copilot_service

                get_copilot_service().auto_discard_pending_for_lead(
                    lead.id, session=db,
                    creator_response=text,
                    creator_id=creator_id,
                )
            except Exception as e:
                logger.warning(f"[EVO:{instance}] Auto-discard failed: {e}")

            db.commit()
            logger.info(
                f"[EVO:{instance}] Saved outgoing msg {message_id} for {follower_id}: "
                f"{text[:60]}"
            )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"[EVO:{instance}] Error saving outgoing message: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def _process_evolution_message_safe(
    instance: str,
    creator_id: str,
    sender_number: str,
    push_name: str,
    text: str,
    message_id: str,
    msg_metadata: dict = None,
):
    """
    Process an incoming Evolution API message in COPILOT mode.

    User message is already saved to DB by the webhook handler (early save).
    This background task generates a suggested response via the DM agent.
    """
    import time as _time
    _t0 = _time.monotonic()

    try:
        from core.copilot_service import get_copilot_service
        from core.dm_agent_v2 import get_dm_agent

        follower_id = f"wa_{sender_number}"

        # Audio Intelligence already ran in _download_evolution_media() (Run 1).
        # Use existing audio_intel for display text if available.
        if (
            msg_metadata
            and msg_metadata.get("type") == "audio"
            and msg_metadata.get("audio_intel")
        ):
            ai = msg_metadata["audio_intel"]
            clean = ai.get("clean_text") or msg_metadata.get("transcription", "")
            text = f"[\U0001f3a4 Audio]: {clean}"

        # Generate suggestion via DM agent
        _t1 = _time.monotonic()
        agent = get_dm_agent(creator_id)
        _t_agent = int((_time.monotonic() - _t1) * 1000)
        dm_metadata = {
            "message_id": message_id,
            "username": push_name or "amigo",
            "platform": "whatsapp",
            "source": "evolution",
        }
        # Pass audio intelligence to DM agent for enriched context
        if msg_metadata and msg_metadata.get("audio_intel"):
            dm_metadata["audio_intel"] = msg_metadata["audio_intel"]
        _t2 = _time.monotonic()
        response = await agent.process_dm(
            message=text,
            sender_id=follower_id,
            metadata=dm_metadata,
        )
        _t_dm = int((_time.monotonic() - _t2) * 1000)

        # Extract text from response — response.content may be a string or a dict
        # like {'content': 'text', 'model': '...', 'provider': '...'}
        _raw_content = response.content if hasattr(response, "content") else response
        if isinstance(_raw_content, str):
            response_text = _raw_content
        elif isinstance(_raw_content, dict):
            response_text = _raw_content.get("content", "") or str(_raw_content)
        else:
            response_text = str(_raw_content)
        intent = str(response.intent) if hasattr(response, "intent") else "unknown"
        confidence = response.confidence if hasattr(response, "confidence") else 0.0

        # Save as pending response (copilot mode — no auto-send)
        copilot = get_copilot_service()

        # Merge Best-of-N candidates from DM response into existing metadata
        if not msg_metadata:
            msg_metadata = {}
        if hasattr(response, "metadata") and response.metadata and response.metadata.get("best_of_n"):
            msg_metadata["best_of_n"] = response.metadata["best_of_n"]

        _t3 = _time.monotonic()
        pending = await copilot.create_pending_response(
            creator_id=creator_id,
            lead_id="",
            follower_id=follower_id,
            platform="whatsapp",
            user_message=text,
            user_message_id=message_id,
            suggested_response=response_text,
            intent=intent,
            confidence=confidence,
            username=push_name or "",
            full_name=push_name or "",
            msg_metadata=msg_metadata if msg_metadata else None,
        )
        _t_copilot = int((_time.monotonic() - _t3) * 1000)
        _t_total = int((_time.monotonic() - _t0) * 1000)
        logger.info(
            f"[EVO:{instance}] [PIPELINE TIMING] total={_t_total}ms "
            f"(agent_init={_t_agent}ms process_dm={_t_dm}ms copilot_save={_t_copilot}ms)"
        )

        # Fetch and save WhatsApp profile picture + update pushName (fire-and-forget)
        try:
            from api.database import SessionLocal
            from api.models import Lead
            from services.evolution_api import fetch_profile_picture

            pic_url = await fetch_profile_picture(instance, sender_number)
            db = SessionLocal()
            try:
                lead = db.query(Lead).filter(
                    Lead.platform_user_id == follower_id
                ).first()
                if lead:
                    changed = False
                    if pic_url and not lead.profile_pic_url:
                        lead.profile_pic_url = pic_url
                        changed = True
                    if push_name and not lead.full_name:
                        lead.full_name = push_name
                        changed = True
                    if changed:
                        db.commit()
                        logger.info(f"[EVO:{instance}] Updated profile for {sender_number}")
            finally:
                db.close()
        except Exception as pic_err:
            logger.debug(f"[EVO:{instance}] Profile update skipped: {pic_err}")

        logger.info(
            f"[EVO:{instance}] Pending response {pending.id} for {sender_number}: "
            f"intent={intent} conf={confidence:.0%} text={response_text[:80]}"
        )

    except Exception as e:
        logger.error(
            f"[EVO:{instance}] Error processing message from {sender_number}: {e}"
        )
        import traceback
        logger.error(traceback.format_exc())
