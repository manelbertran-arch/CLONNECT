"""
Messaging webhooks router — WhatsApp platform.
Extracted from messaging_webhooks.py following TDD methodology.
"""

import asyncio
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .telegram_webhook import _get_copilot_mode_cached

logger = logging.getLogger(__name__)
router = APIRouter(tags=["messaging-webhooks"])


@router.get("/webhook/whatsapp")
async def whatsapp_webhook_verify(request: Request):
    """
    WhatsApp webhook verification (GET).
    Meta sends GET request to verify the endpoint before activating webhooks.
    """
    mode = request.query_params.get("hub.mode", "")
    token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge", "")

    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "clonnect_whatsapp_verify_2024")

    if mode == "subscribe" and token == verify_token:
        logger.info("WhatsApp webhook verified successfully")
        return PlainTextResponse(content=challenge)

    logger.warning(f"WhatsApp webhook verification failed: mode={mode}")
    return PlainTextResponse(content="Verification failed", status_code=403)


@router.post("/webhook/whatsapp")
async def whatsapp_webhook_receive(request: Request):
    """
    Receive WhatsApp webhook events (POST).
    Processes incoming messages with DMResponderAgent and sends automatic responses.
    Supports copilot mode (suggested responses) and autopilot mode (auto-send).
    """
    from core.dm_agent_v2 import get_dm_agent
    from core.whatsapp import WhatsAppConnector

    logger.warning("========== WHATSAPP WEBHOOK HIT ==========")

    try:
        body = await request.body()
        payload = json.loads(body)
        signature = request.headers.get("X-Hub-Signature-256", "")

        # Verify webhook signature
        connector = WhatsAppConnector()
        if not connector.verify_webhook_signature(body, signature):
            logger.warning("WhatsApp webhook signature verification failed")
            raise HTTPException(status_code=403, detail="Invalid signature")

        # Parse messages from webhook payload
        messages = await connector.handle_webhook_event(payload)

        if not messages:
            return {"status": "ok", "messages_processed": 0}

        # Multi-tenant: resolve creator from phone_number_id in webhook payload
        creator_id = os.getenv("WHATSAPP_CREATOR_ID", "stefano_bonanno")
        wa_token_db = ""
        wa_phone_id_db = ""
        try:
            # Extract phone_number_id from Meta webhook payload
            webhook_phone_id = ""
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    metadata = change.get("value", {}).get("metadata", {})
                    if metadata.get("phone_number_id"):
                        webhook_phone_id = metadata["phone_number_id"]
                        break
                if webhook_phone_id:
                    break

            if webhook_phone_id:
                from api.database import SessionLocal
                from api.models import Creator
                session = SessionLocal()
                try:
                    creator_row = session.query(Creator).filter(
                        Creator.whatsapp_phone_id == webhook_phone_id
                    ).first()
                    if creator_row:
                        creator_id = creator_row.name
                        wa_token_db = creator_row.whatsapp_token or ""
                        wa_phone_id_db = creator_row.whatsapp_phone_id or ""
                        logger.info(f"[WA] Multi-tenant: routed to creator '{creator_id}' via phone_number_id={webhook_phone_id}")
                    else:
                        logger.warning(f"[WA] No creator found for phone_number_id={webhook_phone_id}, fallback to env var creator '{creator_id}'")
                finally:
                    session.close()
        except Exception as mt_err:
            logger.warning(f"[WA] Multi-tenant lookup failed, using fallback: {mt_err}")

        # Per-creator credentials with env var fallback
        wa_token = wa_token_db or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        wa_phone_id = wa_phone_id_db or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

        results = []
        for message in messages:
            sender_id = f"wa_{message.sender_id}"
            display_name = message.sender_name or message.sender_id
            logger.info(f"[WA:{message.sender_id}] ({display_name}) Input: {message.text[:100]}")

            try:
                agent = get_dm_agent(creator_id)
                response = await agent.process_dm(
                    message=message.text,
                    sender_id=sender_id,
                    metadata={
                        "message_id": message.message_id,
                        "username": display_name,
                        "name": message.sender_name,
                        "platform": "whatsapp",
                    },
                )

                bot_reply = response.content if hasattr(response, "content") else str(response)
                intent = str(response.intent) if hasattr(response, "intent") else "unknown"
                confidence = response.confidence if hasattr(response, "confidence") else 0.0

                logger.info(f"[WA:{message.sender_id}] Intent: {intent} ({confidence:.0%})")

                # Fire-and-forget identity resolution
                try:
                    from core.identity_resolver import resolve_identity
                    from api.services.db_service import get_or_create_lead
                    lead_result = get_or_create_lead(
                        creator_id, sender_id, platform="whatsapp",
                        username=display_name, full_name=message.sender_name,
                    )
                    if lead_result:
                        asyncio.create_task(resolve_identity(creator_id, lead_result["id"], "whatsapp"))
                except Exception as ir_err:
                    logger.debug(f"[WA] Identity resolution skipped: {ir_err}")

                # Check copilot mode
                copilot_enabled = _get_copilot_mode_cached(creator_id)

                if copilot_enabled:
                    logger.info("[WA] COPILOT MODE - creating pending response")
                    try:
                        from core.copilot_service import get_copilot_service
                        copilot = get_copilot_service()
                        # Carry Best-of-N candidates from DM response metadata
                        _wa_msg_meta = {}
                        if hasattr(response, "metadata") and response.metadata and response.metadata.get("best_of_n"):
                            _wa_msg_meta["best_of_n"] = response.metadata["best_of_n"]

                        pending = await copilot.create_pending_response(
                            creator_id=creator_id,
                            lead_id="",
                            follower_id=sender_id,
                            platform="whatsapp",
                            user_message=message.text,
                            user_message_id=message.message_id,
                            suggested_response=bot_reply,
                            intent=intent,
                            confidence=confidence,
                            username=display_name,
                            full_name=message.sender_name or message.sender_id,
                            msg_metadata=_wa_msg_meta if _wa_msg_meta else None,
                        )
                        results.append({
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "intent": intent,
                            "copilot_mode": True,
                            "pending_response_id": pending.id,
                            "response_sent": False,
                        })
                    except Exception as copilot_err:
                        logger.error(f"[WA] Copilot error: {copilot_err}")
                        results.append({
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "error": f"copilot: {copilot_err}",
                        })
                else:
                    # AUTOPILOT MODE - send response via WhatsApp
                    logger.info("[WA] AUTOPILOT MODE - sending auto-reply")
                    sent = False

                    if bot_reply and wa_token and wa_phone_id:
                        try:
                            send_connector = WhatsAppConnector(
                                phone_number_id=wa_phone_id,
                                access_token=wa_token,
                            )
                            send_result = await send_connector.send_message(
                                message.sender_id, bot_reply
                            )
                            await send_connector.close()
                            if "error" not in send_result:
                                sent = True
                                logger.info(f"[WA] Response sent to {message.sender_id}")
                            else:
                                logger.error(f"[WA] Send error: {send_result['error']}")
                        except Exception as send_err:
                            logger.error(f"[WA] Send error: {send_err}")

                    # Mark as read
                    if wa_token and wa_phone_id:
                        try:
                            read_connector = WhatsAppConnector(
                                phone_number_id=wa_phone_id,
                                access_token=wa_token,
                            )
                            await read_connector.mark_as_read(message.message_id)
                            await read_connector.close()
                        except Exception as e:
                            logger.warning("Suppressed error in read_connector = WhatsAppConnector(: %s", e)

                    results.append({
                        "message_id": message.message_id,
                        "sender_id": message.sender_id,
                        "response": bot_reply[:100],
                        "intent": intent,
                        "confidence": confidence,
                        "copilot_mode": False,
                        "response_sent": sent,
                    })

            except Exception as e:
                logger.error(f"[WA] Error processing message {message.message_id}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                results.append({
                    "message_id": message.message_id,
                    "sender_id": message.sender_id,
                    "error": str(e),
                })

        logger.info(f"WhatsApp webhook processed: {len(messages)} messages")
        return {
            "status": "ok",
            "messages_processed": len(messages),
            "creator_id": creator_id,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Return 200 to acknowledge receipt (prevents infinite retries from Meta)
        return {"status": "error", "error": str(e)}


@router.get("/whatsapp/status")
async def whatsapp_status():
    """Get WhatsApp handler status"""
    from core.whatsapp import get_whatsapp_handler

    try:
        handler = get_whatsapp_handler()
        return {
            "status": "ok",
            "handler": handler.get_status(),
            "recent_messages": handler.get_recent_messages(5),
            "recent_responses": handler.get_recent_responses(5),
        }
    except Exception as e:
        return {
            "status": "error",
            "phone_number_id_configured": bool(os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")),
            "access_token_configured": bool(os.getenv("WHATSAPP_ACCESS_TOKEN", "")),
            "webhook_url": "/webhook/whatsapp",
            "error": str(e),
        }


# =============================================================================
# WHATSAPP TEST ENDPOINT
# =============================================================================


@router.post("/admin/whatsapp/test-message")
async def whatsapp_test_message(request: Request):
    """
    Simulate a WhatsApp message through the full DM pipeline.

    Use this to test the WhatsApp flow E2E without needing WhatsApp Business API.
    The message goes through DMResponderAgent just like a real webhook,
    but the response is returned in the API response instead of being
    sent to WhatsApp.

    Body: { "creator_id": "stefano_bonanno", "phone": "+34612345678", "text": "Hola" }
    """
    from core.dm_agent_v2 import get_dm_agent

    try:
        body = await request.json()
        creator_id = body.get("creator_id", "stefano_bonanno")
        phone = body.get("phone", "+34600000000")
        text = body.get("text", "Hola, me interesa tu servicio")

        # Strip + and spaces for consistent sender_id
        phone_clean = phone.replace("+", "").replace(" ", "")

        agent = get_dm_agent(creator_id)

        response = await agent.process_dm(
            message=text,
            sender_id=f"wa_{phone_clean}",
            metadata={
                "message_id": "test_wa_0",
                "username": phone,
                "name": phone,
                "platform": "whatsapp",
            },
        )

        response_text = response.content if hasattr(response, "content") else str(response)
        intent = str(response.intent) if hasattr(response, "intent") else "unknown"
        confidence = response.confidence if hasattr(response, "confidence") else None

        return {
            "status": "ok",
            "test_mode": True,
            "creator_id": creator_id,
            "input": {
                "phone": phone,
                "sender_id": f"wa_{phone_clean}",
                "text": text,
            },
            "pipeline_response": {
                "response_text": response_text,
                "intent": intent,
                "confidence": confidence,
            },
            "note": "Response NOT sent to WhatsApp - test mode only",
            "env_check": {
                "WHATSAPP_PHONE_NUMBER_ID": bool(os.getenv("WHATSAPP_PHONE_NUMBER_ID")),
                "WHATSAPP_ACCESS_TOKEN": bool(os.getenv("WHATSAPP_ACCESS_TOKEN")),
                "WHATSAPP_VERIFY_TOKEN": bool(os.getenv("WHATSAPP_VERIFY_TOKEN")),
            },
        }

    except Exception as e:
        logger.error(f"Error in WhatsApp test message: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal error processing WhatsApp message")
