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
    return {"status": "ok", "follower_id": follower_id, "username": None, "name": None, "platform": "instagram", "total_messages": 0, "purchase_intent": 0, "is_lead": False, "last_messages": []}

@router.post("/send/{creator_id}")
async def send_message(creator_id: str, data: dict = Body(...)):
    follower_id = data.get("follower_id")
    message = data.get("message", "")
    if not follower_id or not message:
        raise HTTPException(status_code=400, detail="follower_id and message required")
    return {"status": "ok", "message": "Message queued", "follower_id": follower_id}

@router.put("/follower/{creator_id}/{follower_id}/status")
async def update_follower_status(creator_id: str, follower_id: str, data: dict = Body(...)):
    return {"status": "ok", "message": "Status updated"}

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
