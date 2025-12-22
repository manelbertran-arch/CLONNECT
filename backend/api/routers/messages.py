"""Messages and follower endpoints"""
from fastapi import APIRouter, HTTPException, Body
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dm", tags=["messages"])

USE_DB = bool(os.getenv("DATABASE_URL"))
if USE_DB:
    try:
        from api.services import db_service
    except ImportError:
        from api import db_service

@router.get("/metrics/{creator_id}")
async def get_metrics(creator_id: str):
    if USE_DB:
        try:
            stats = db_service.get_creator_stats(creator_id)
            if stats:
                return {"status": "ok", "metrics": {"total_messages": stats.get("total_messages", 0), "total_followers": stats.get("total_leads", 0), "leads": stats.get("total_leads", 0), "customers": 0, "high_intent_followers": stats.get("hot_leads", 0), "conversion_rate": 0.0}}
        except Exception as e:
            logger.warning(f"Get metrics failed: {e}")
    return {"status": "ok", "metrics": {"total_messages": 0, "total_followers": 0, "leads": 0, "customers": 0, "high_intent_followers": 0, "conversion_rate": 0.0}}

@router.get("/follower/{creator_id}/{follower_id}")
async def get_follower_detail(creator_id: str, follower_id: str):
    if USE_DB:
        try:
            from api.models import Creator, Lead, Message
            from api.services.db_service import get_session
            session = get_session()
            if session:
                try:
                    creator = session.query(Creator).filter_by(name=creator_id).first()
                    if creator:
                        # Find lead by platform_user_id or id
                        lead = session.query(Lead).filter_by(creator_id=creator.id, platform_user_id=follower_id).first()
                        if not lead:
                            # Try finding by id
                            try:
                                lead = session.query(Lead).filter_by(creator_id=creator.id, id=follower_id).first()
                            except:
                                pass
                        if lead:
                            # Get messages
                            messages = session.query(Message).filter_by(lead_id=lead.id).order_by(Message.created_at.asc()).all()
                            last_messages = [
                                {
                                    "role": m.role,
                                    "content": m.content,
                                    "timestamp": m.created_at.isoformat() if m.created_at else None
                                }
                                for m in messages[-50:]  # Last 50 messages
                            ]
                            return {
                                "status": "ok",
                                "follower_id": lead.platform_user_id or str(lead.id),
                                "username": lead.username,
                                "name": lead.full_name,
                                "platform": lead.platform or "instagram",
                                "total_messages": len(messages),
                                "purchase_intent": lead.purchase_intent or 0,
                                "purchase_intent_score": lead.purchase_intent or 0,
                                "is_lead": True,
                                "is_customer": lead.context.get("is_customer", False) if lead.context else False,
                                "last_messages": last_messages,
                                "last_contact": lead.updated_at.isoformat() if lead.updated_at else None,
                            }
                finally:
                    session.close()
        except Exception as e:
            logger.warning(f"Get follower detail failed: {e}")
    return {"status": "ok", "follower_id": follower_id, "username": None, "name": None, "platform": "instagram", "total_messages": 0, "purchase_intent": 0, "is_lead": False, "last_messages": []}

@router.post("/send/{creator_id}")
async def send_message(creator_id: str, data: dict = Body(...)):
    follower_id = data.get("follower_id")
    message_text = data.get("message", "")
    if not follower_id or not message_text:
        raise HTTPException(status_code=400, detail="follower_id and message required")

    sent = False
    platform = "unknown"

    # Try to send via platform
    try:
        # Detect platform from follower_id
        if follower_id.startswith("tg_"):
            platform = "telegram"
            # Try to send via Telegram
            from core.telegram_sender import send_telegram_message
            chat_id = follower_id.replace("tg_", "")
            sent = await send_telegram_message(chat_id, message_text)
        elif follower_id.startswith("ig_"):
            platform = "instagram"
            # Instagram sending would go here
            sent = False
        else:
            platform = "instagram"
    except Exception as e:
        logger.warning(f"Failed to send message via platform: {e}")

    # Save message to database regardless of send status
    if USE_DB:
        try:
            from api.models import Creator, Lead, Message
            from api.services.db_service import get_session
            from datetime import datetime, timezone
            session = get_session()
            if session:
                try:
                    creator = session.query(Creator).filter_by(name=creator_id).first()
                    if creator:
                        lead = session.query(Lead).filter_by(creator_id=creator.id, platform_user_id=follower_id).first()
                        if lead:
                            # Save the message
                            msg = Message(
                                lead_id=lead.id,
                                role="assistant",
                                content=message_text,
                                created_at=datetime.now(timezone.utc)
                            )
                            session.add(msg)
                            session.commit()
                            logger.info(f"Saved manual message to {follower_id}")
                finally:
                    session.close()
        except Exception as e:
            logger.warning(f"Failed to save message to DB: {e}")

    return {
        "status": "ok",
        "sent": sent,
        "platform": platform,
        "follower_id": follower_id,
        "message": "Message sent" if sent else "Message saved (delivery pending)"
    }

@router.put("/follower/{creator_id}/{follower_id}/status")
async def update_follower_status(creator_id: str, follower_id: str, data: dict = Body(...)):
    new_status = data.get("status", "cold")

    # Map status to purchase_intent score
    status_to_intent = {
        "cold": 0.1,
        "warm": 0.35,
        "hot": 0.7,
        "customer": 1.0
    }
    new_intent = status_to_intent.get(new_status, 0.1)

    if USE_DB:
        try:
            from api.models import Creator, Lead
            from api.services.db_service import get_session
            session = get_session()
            if session:
                try:
                    creator = session.query(Creator).filter_by(name=creator_id).first()
                    if creator:
                        lead = session.query(Lead).filter_by(creator_id=creator.id, platform_user_id=follower_id).first()
                        if lead:
                            lead.purchase_intent = new_intent
                            if new_status == "customer":
                                if not lead.context:
                                    lead.context = {}
                                lead.context["is_customer"] = True
                            session.commit()
                            return {
                                "status": "ok",
                                "follower_id": follower_id,
                                "new_status": new_status,
                                "purchase_intent": new_intent
                            }
                finally:
                    session.close()
        except Exception as e:
            logger.warning(f"Update follower status failed: {e}")

    return {"status": "ok", "follower_id": follower_id, "new_status": new_status, "purchase_intent": new_intent}

@router.get("/conversations/{creator_id}")
async def get_conversations(creator_id: str, limit: int = 50):
    if USE_DB:
        try:
            leads = db_service.get_leads(creator_id)
            if leads:
                conversations = [{"follower_id": l.get("platform_user_id", l.get("id")), "username": l.get("username"), "name": l.get("full_name"), "platform": l.get("platform", "instagram"), "total_messages": 0, "purchase_intent": l.get("purchase_intent", 0)} for l in leads[:limit]]
                return {"status": "ok", "conversations": conversations, "count": len(conversations)}
        except Exception as e:
            logger.warning(f"Get conversations failed: {e}")
    return {"status": "ok", "conversations": [], "count": 0}
