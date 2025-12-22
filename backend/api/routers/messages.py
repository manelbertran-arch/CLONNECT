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
    # Try PostgreSQL first
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
                            # Get messages from PostgreSQL
                            messages = session.query(Message).filter_by(lead_id=lead.id).order_by(Message.created_at.asc()).all()
                            last_messages = [
                                {
                                    "role": m.role,
                                    "content": m.content,
                                    "timestamp": m.created_at.isoformat() if m.created_at else None
                                }
                                for m in messages[-50:]  # Last 50 messages
                            ]

                            # If PostgreSQL has no messages, try JSON fallback
                            if not last_messages:
                                try:
                                    from api.services.data_sync import _load_json
                                    json_data = _load_json(creator_id, follower_id)
                                    if json_data:
                                        last_messages = json_data.get("last_messages", [])[-50:]
                                except:
                                    pass

                            return {
                                "status": "ok",
                                "follower_id": lead.platform_user_id or str(lead.id),
                                "username": lead.username,
                                "name": lead.full_name,
                                "platform": lead.platform or "instagram",
                                "total_messages": len(messages) if messages else len([m for m in last_messages if m.get("role") == "user"]),
                                "purchase_intent": lead.purchase_intent or 0,
                                "purchase_intent_score": lead.purchase_intent or 0,
                                "is_lead": True,
                                "is_customer": lead.context.get("is_customer", False) if lead.context else False,
                                "last_messages": last_messages,
                                "last_contact": lead.last_contact_at.isoformat() if lead.last_contact_at else None,
                            }
                finally:
                    session.close()
        except Exception as e:
            logger.warning(f"Get follower detail (PostgreSQL) failed: {e}")

    # Fallback to JSON files
    try:
        from api.services.data_sync import _load_json
        json_data = _load_json(creator_id, follower_id)
        if json_data:
            last_messages = json_data.get("last_messages", [])
            user_msgs = len([m for m in last_messages if m.get("role") == "user"])
            return {
                "status": "ok",
                "follower_id": json_data.get("follower_id", follower_id),
                "username": json_data.get("username"),
                "name": json_data.get("name"),
                "platform": "instagram" if follower_id.startswith("ig_") else "telegram" if follower_id.startswith("tg_") else "whatsapp" if follower_id.startswith("wa_") else "instagram",
                "total_messages": user_msgs,
                "purchase_intent": json_data.get("purchase_intent_score", 0),
                "purchase_intent_score": json_data.get("purchase_intent_score", 0),
                "is_lead": json_data.get("is_lead", False),
                "is_customer": json_data.get("is_customer", False),
                "last_messages": last_messages[-50:],
                "last_contact": json_data.get("last_contact"),
            }
    except Exception as e:
        logger.warning(f"Get follower detail (JSON) failed: {e}")

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
            # Send via Instagram handler
            from core.instagram_handler import get_instagram_handler
            handler = get_instagram_handler()
            if handler.connector:
                recipient_id = follower_id.replace("ig_", "")
                sent = await handler.send_response(recipient_id, message_text)
                if sent:
                    logger.info(f"Message sent to Instagram {recipient_id}")
        else:
            # Legacy Instagram ID without prefix
            platform = "instagram"
            from core.instagram_handler import get_instagram_handler
            handler = get_instagram_handler()
            if handler.connector:
                sent = await handler.send_response(follower_id, message_text)
                if sent:
                    logger.info(f"Message sent to Instagram {follower_id}")
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

    # Map API status to Lead.status column values
    # Frontend uses: cold, warm, hot, customer
    # Lead.status uses: new, active, hot, customer (matching Kanban columns)
    api_to_db_status = {
        "cold": "new",
        "warm": "active",
        "hot": "hot",
        "customer": "customer"
    }
    db_status = api_to_db_status.get(new_status, "new")

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
            import uuid
            session = get_session()
            if session:
                try:
                    creator = session.query(Creator).filter_by(name=creator_id).first()
                    if creator:
                        # Try to find lead by UUID first, then by platform_user_id
                        lead = None
                        try:
                            lead = session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(follower_id)).first()
                        except (ValueError, AttributeError):
                            pass  # Not a valid UUID, try platform_user_id

                        if not lead:
                            lead = session.query(Lead).filter_by(creator_id=creator.id, platform_user_id=follower_id).first()

                        if lead:
                            # Update both status column AND purchase_intent
                            lead.status = db_status
                            lead.purchase_intent = new_intent
                            if new_status == "customer":
                                if not lead.context:
                                    lead.context = {}
                                lead.context["is_customer"] = True
                            session.commit()
                            logger.info(f"Updated lead {follower_id} status to {db_status} (intent: {new_intent})")
                            return {
                                "status": "ok",
                                "follower_id": follower_id,
                                "new_status": new_status,
                                "db_status": db_status,
                                "purchase_intent": new_intent
                            }
                        else:
                            logger.warning(f"Lead not found for status update: {follower_id}")
                finally:
                    session.close()
        except Exception as e:
            logger.warning(f"Update follower status failed: {e}")

    # JSON fallback - update the JSON file directly
    try:
        from api.services.data_sync import _load_json, STORAGE_PATH
        import os
        import json

        json_data = _load_json(creator_id, follower_id)
        if json_data:
            # Update status and purchase_intent in JSON
            json_data["status"] = db_status
            json_data["purchase_intent_score"] = new_intent
            if new_status == "customer":
                json_data["is_customer"] = True

            # Save back to JSON file
            json_path = os.path.join(STORAGE_PATH, creator_id, f"{follower_id}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Updated lead {follower_id} status to {db_status} via JSON fallback")
            return {
                "status": "ok",
                "follower_id": follower_id,
                "new_status": new_status,
                "db_status": db_status,
                "purchase_intent": new_intent
            }
    except Exception as e:
        logger.warning(f"JSON fallback for status update failed: {e}")

    return {"status": "ok", "follower_id": follower_id, "new_status": new_status, "purchase_intent": new_intent}

@router.get("/conversations/{creator_id}")
async def get_conversations(creator_id: str, limit: int = 50):
    # Try PostgreSQL first
    if USE_DB:
        try:
            leads = db_service.get_leads(creator_id)
            if leads:
                conversations = []
                for l in leads[:limit]:
                    follower_id = l.get("platform_user_id", l.get("id"))
                    # Get message count from JSON as fallback
                    msg_count = 0
                    last_messages = []
                    try:
                        from api.services.data_sync import _load_json
                        json_data = _load_json(creator_id, follower_id)
                        if json_data:
                            msgs = json_data.get("last_messages", [])
                            msg_count = len([m for m in msgs if m.get("role") == "user"])
                            last_messages = msgs[-5:]
                    except:
                        pass
                    # Extract email/phone/notes from context (stored as JSON in PostgreSQL)
                    ctx = l.get("context") or {}
                    conversations.append({
                        "follower_id": follower_id,
                        "id": l.get("id"),  # UUID for reliable updates
                        "username": l.get("username"),
                        "name": l.get("full_name"),
                        "platform": l.get("platform", "instagram"),
                        "total_messages": msg_count,
                        "purchase_intent": l.get("purchase_intent", 0),
                        "lead_status": l.get("status", "new"),  # Pipeline status: new, active, hot, customer
                        "last_messages": last_messages,
                        "last_contact": l.get("last_contact_at"),
                        "email": ctx.get("email") or l.get("email") or "",
                        "phone": ctx.get("phone") or l.get("phone") or "",
                        "notes": ctx.get("notes") or l.get("notes") or "",
                    })
                return {"status": "ok", "conversations": conversations, "count": len(conversations)}
        except Exception as e:
            logger.warning(f"Get conversations (PostgreSQL) failed: {e}")

    # Fallback to JSON files
    try:
        from api.services.data_sync import _load_json, STORAGE_PATH
        import os
        creator_dir = os.path.join(STORAGE_PATH, creator_id)
        conversations = []
        if os.path.exists(creator_dir):
            for filename in sorted(os.listdir(creator_dir), key=lambda x: os.path.getmtime(os.path.join(creator_dir, x)), reverse=True)[:limit]:
                if filename.endswith('.json'):
                    follower_id = filename[:-5]
                    json_data = _load_json(creator_id, follower_id)
                    if json_data:
                        msgs = json_data.get("last_messages", [])
                        user_msgs = len([m for m in msgs if m.get("role") == "user"])
                        conversations.append({
                            "follower_id": follower_id,
                            "username": json_data.get("username"),
                            "name": json_data.get("name"),
                            "platform": "instagram" if follower_id.startswith("ig_") else "telegram" if follower_id.startswith("tg_") else "instagram",
                            "total_messages": user_msgs,
                            "purchase_intent": json_data.get("purchase_intent_score", 0),
                            "lead_status": json_data.get("status", "new"),  # Pipeline status
                            "last_messages": msgs[-5:],
                            "last_contact": json_data.get("last_contact"),
                            "email": json_data.get("email") or "",
                            "phone": json_data.get("phone") or "",
                            "notes": json_data.get("notes") or "",
                        })
        return {"status": "ok", "conversations": conversations, "count": len(conversations)}
    except Exception as e:
        logger.warning(f"Get conversations (JSON) failed: {e}")

    return {"status": "ok", "conversations": [], "count": 0}
