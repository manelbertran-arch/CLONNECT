"""
DM Processing - Core DM processing endpoints
(process_dm, send_manual_message, send_media_message)
"""

import logging
import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Database availability check
try:
    pass

    USE_DB = True
except Exception:
    USE_DB = False
    logger.warning("Database service not available in dm router")

import httpx

# Core imports
from core.dm_agent_v2 import DMResponderAgent
from core.instagram_handler import get_instagram_handler
from core.whatsapp import get_whatsapp_handler

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

router = APIRouter()


# ---------------------------------------------------------
# PYDANTIC MODELS
# ---------------------------------------------------------
class ProcessDMRequest(BaseModel):
    creator_id: str
    sender_id: str
    message: str
    message_id: str = ""


class SendMessageRequest(BaseModel):
    """Request to send a manual message to a follower"""

    follower_id: str
    message: str


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------
def get_dm_agent(creator_id: str) -> DMResponderAgent:
    """Factory para crear DM agent"""
    return DMResponderAgent(creator_id=creator_id)


# ---------------------------------------------------------
# DM ENDPOINTS
# ---------------------------------------------------------
@router.post("/process")
async def process_dm(payload: ProcessDMRequest):
    """Procesar un DM manualmente (para testing)"""
    try:
        agent = get_dm_agent(payload.creator_id)

        result = await agent.process_dm(
            message=payload.message,
            sender_id=payload.sender_id,
            metadata={"message_id": payload.message_id},
        )

        return {
            "status": "ok",
            "response": result.content,
            "intent": result.intent,
            "lead_stage": result.lead_stage,
            "confidence": result.confidence,
            "tokens_used": result.tokens_used,
        }

    except Exception as e:
        logger.error(f"Error processing DM: {e}")
        raise HTTPException(status_code=503, detail="LLM service unavailable")


@router.post("/send/{creator_id}")
async def send_manual_message(creator_id: str, request: SendMessageRequest):
    """
    Send a manual message to a follower.

    The message will be sent via the appropriate platform (Telegram, Instagram, WhatsApp)
    based on the follower_id prefix:
    - tg_* -> Telegram
    - ig_* -> Instagram
    - wa_* -> WhatsApp

    The message is also saved in the conversation history.
    """
    try:
        follower_id = request.follower_id
        message_text = request.message

        if not message_text.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        # Detect platform from follower_id prefix
        if follower_id.startswith("tg_"):
            platform = "telegram"
            chat_id = follower_id.replace("tg_", "")
        elif follower_id.startswith("ig_"):
            platform = "instagram"
            recipient_id = follower_id.replace("ig_", "")
        elif follower_id.startswith("wa_"):
            platform = "whatsapp"
            phone = follower_id.replace("wa_", "")
        else:
            # Assume Instagram for legacy IDs without prefix
            platform = "instagram"
            recipient_id = follower_id

        sent = False

        # Send via appropriate platform
        if platform == "telegram" and TELEGRAM_BOT_TOKEN:
            try:
                telegram_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        telegram_api,
                        json={"chat_id": int(chat_id), "text": message_text, "parse_mode": "HTML"},
                    )
                    if resp.status_code == 200:
                        sent = True
                        logger.info(f"Manual message sent to Telegram chat {chat_id}")
            except Exception as e:
                logger.error(f"Error sending Telegram message: {e}")

        elif platform == "instagram":
            try:
                handler = get_instagram_handler()
                if handler.connector:
                    sent = await handler.send_response(recipient_id, message_text, approved=True)
                    if sent:
                        logger.info(f"Manual message sent to Instagram {recipient_id}")
            except Exception as e:
                logger.error(f"Error sending Instagram message: {e}")

        elif platform == "whatsapp":
            # Try Evolution API first (Baileys), fall back to Cloud API
            try:
                from services.evolution_api import send_evolution_message
                from api.routers.messaging_webhooks import EVOLUTION_INSTANCE_MAP

                # Find Evolution instance for this creator
                evo_instance = None
                for inst_name, cid in EVOLUTION_INSTANCE_MAP.items():
                    if cid == creator_id:
                        evo_instance = inst_name
                        break

                if evo_instance:
                    result = await send_evolution_message(evo_instance, phone, message_text, approved=True)
                    sent = "error" not in str(result).lower()
                    if sent:
                        logger.info(f"Manual message sent via Evolution [{evo_instance}] to {phone}")
                else:
                    # Fall back to official WhatsApp Cloud API
                    wa_handler = get_whatsapp_handler()
                    if wa_handler and wa_handler.connector:
                        result = await wa_handler.connector.send_message(phone, message_text)
                        sent = "error" not in result
                        if sent:
                            logger.info(f"Manual message sent to WhatsApp {phone}")
            except Exception as e:
                logger.error(f"Error sending WhatsApp message: {e}")

        # Save the message in conversation history
        agent = get_dm_agent(creator_id)
        await agent.save_manual_message(follower_id, message_text, sent)

        return {
            "status": "ok",
            "sent": sent,
            "platform": platform,
            "follower_id": follower_id,
            "message_preview": (
                message_text[:100] + "..." if len(message_text) > 100 else message_text
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending manual message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/send-media/{creator_id}")
async def send_media_message(
    creator_id: str,
    follower_id: str = Form(...),
    caption: str = Form(""),
    file: UploadFile = File(...),
):
    """
    Upload media to Cloudinary and send to a follower via their platform.

    Supports: images, videos, audio, documents. Max 16MB.
    The media is permanently stored in Cloudinary before sending.
    """
    import tempfile

    content_type = file.content_type or ""

    # Determine media type
    if "image" in content_type:
        media_type = "image"
    elif "video" in content_type:
        media_type = "video"
    elif "audio" in content_type:
        media_type = "audio"
    elif "pdf" in content_type or "document" in content_type or "msword" in content_type:
        media_type = "document"
    else:
        raise HTTPException(400, f"Unsupported file type: {content_type}")

    # Read and validate size
    content = await file.read()
    if len(content) > 16 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 16MB)")
    if len(content) < 100:
        raise HTTPException(400, "File too small or empty")

    # Save to temp file and upload to Cloudinary
    suffix = os.path.splitext(file.filename or ".bin")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from services.cloudinary_service import get_cloudinary_service

        cloud = get_cloudinary_service()
        if not cloud.is_configured:
            raise HTTPException(500, "Cloudinary not configured")

        cloud_media = media_type
        if media_type == "document":
            cloud_media = "raw"

        upload = cloud.upload_from_file(
            file_path=tmp_path,
            media_type=cloud_media,
            folder=f"clonnect/{creator_id}/sent",
            tags=[creator_id, "sent", media_type],
        )
        if not upload.success or not upload.url:
            raise HTTPException(500, f"Upload failed: {upload.error}")

        media_url = upload.url
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Send via platform
    follower_id_str = follower_id
    sent = False
    platform = "unknown"

    if follower_id_str.startswith("wa_"):
        platform = "whatsapp"
        phone = follower_id_str.replace("wa_", "")
        try:
            from api.routers.messaging_webhooks import EVOLUTION_INSTANCE_MAP
            from services.evolution_api import send_evolution_media

            evo_instance = None
            for inst_name, cid in EVOLUTION_INSTANCE_MAP.items():
                if cid == creator_id:
                    evo_instance = inst_name
                    break

            if evo_instance:
                result = await send_evolution_media(
                    evo_instance, phone, media_url, media_type, caption, approved=True
                )
                sent = "error" not in str(result).lower()
        except Exception as e:
            logger.error(f"Error sending WhatsApp media: {e}")

    elif follower_id_str.startswith("ig_"):
        platform = "instagram"
        # Instagram Send API doesn't support media from inbox -- save as text with URL
        if caption:
            message_text = f"{caption}\n{media_url}"
        else:
            message_text = media_url
        try:
            handler = get_instagram_handler()
            if handler.connector:
                sent = await handler.send_response(
                    follower_id_str.replace("ig_", ""), message_text, approved=True
                )
        except Exception as e:
            logger.error(f"Error sending Instagram media: {e}")

    # Save in conversation history
    display_text = caption or {
        "image": "[📷 Photo]",
        "video": "[🎬 Video]",
        "audio": "[🎤 Audio]",
        "document": "[📄 Document]",
    }.get(media_type, "[📎 Media]")

    agent = get_dm_agent(creator_id)
    await agent.save_manual_message(follower_id_str, display_text, sent)

    return {
        "status": "ok",
        "sent": sent,
        "platform": platform,
        "media_url": media_url,
        "media_type": media_type,
    }
