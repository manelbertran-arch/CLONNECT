"""Nurturing sequences endpoints"""
from fastapi import APIRouter, Body
from typing import Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nurturing", tags=["nurturing"])

DEFAULT_SEQUENCES = [
    {"type": "welcome", "name": "Bienvenida", "description": "Secuencia de bienvenida", "enabled": False, "steps": [{"day": 1, "message": "Hola"}, {"day": 3, "message": "Como vas"}, {"day": 7, "message": "Te puedo ayudar"}], "enrolled": 0},
    {"type": "abandoned_cart", "name": "Carrito Abandonado", "description": "Seguimiento interesados", "enabled": False, "steps": [{"day": 1, "message": "Vi que te intereso"}, {"day": 3, "message": "Ultima oportunidad"}], "enrolled": 0},
    {"type": "post_purchase", "name": "Post-Compra", "description": "Seguimiento post-compra", "enabled": False, "steps": [{"day": 1, "message": "Gracias por tu compra"}, {"day": 7, "message": "Que tal la experiencia"}], "enrolled": 0}
]

@router.get("/{creator_id}/sequences")
async def get_nurturing_sequences(creator_id: str):
    return {"status": "ok", "creator_id": creator_id, "sequences": DEFAULT_SEQUENCES}

@router.get("/{creator_id}/followups")
async def get_nurturing_followups(creator_id: str, status: Optional[str] = None, limit: int = 50):
    return {"status": "ok", "creator_id": creator_id, "followups": [], "count": 0}

@router.get("/{creator_id}/stats")
async def get_nurturing_stats(creator_id: str):
    return {"status": "ok", "creator_id": creator_id, "total_enrolled": 0, "active_sequences": 0, "messages_sent": 0, "conversion_rate": 0.0, "by_sequence": {}}

@router.post("/{creator_id}/sequences/{sequence_type}/toggle")
async def toggle_nurturing_sequence(creator_id: str, sequence_type: str, data: Optional[dict] = Body(default=None)):
    enabled = False
    if data and isinstance(data, dict):
        enabled = data.get("enabled", False)
    return {"status": "ok", "sequence_type": sequence_type, "enabled": enabled}

@router.put("/{creator_id}/sequences/{sequence_type}")
async def update_nurturing_sequence(creator_id: str, sequence_type: str, data: Optional[dict] = Body(default=None)):
    return {"status": "ok", "message": "Sequence updated"}

@router.get("/{creator_id}/sequences/{sequence_type}/enrolled")
async def get_enrolled_followers(creator_id: str, sequence_type: str):
    return {"status": "ok", "sequence_type": sequence_type, "enrolled": [], "count": 0}

@router.delete("/{creator_id}/followers/{follower_id}/nurturing")
async def cancel_nurturing(creator_id: str, follower_id: str):
    return {"status": "ok", "message": "Nurturing cancelled", "follower_id": follower_id}
