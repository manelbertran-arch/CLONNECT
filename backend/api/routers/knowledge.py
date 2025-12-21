"""Knowledge base endpoints"""
from fastapi import APIRouter, Body
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/creator/config", tags=["knowledge"])

@router.get("/{creator_id}/knowledge")
async def get_knowledge(creator_id: str):
    return {"status": "ok", "creator_id": creator_id, "knowledge": [], "count": 0}

@router.post("/{creator_id}/knowledge")
async def add_knowledge(creator_id: str, data: dict = Body(...)):
    return {"status": "ok", "message": "Knowledge added"}

@router.delete("/{creator_id}/knowledge/{item_id}")
async def delete_knowledge(creator_id: str, item_id: str):
    return {"status": "ok", "message": "Knowledge deleted"}
