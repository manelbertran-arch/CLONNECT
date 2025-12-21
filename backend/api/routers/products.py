"""Products endpoints"""
from fastapi import APIRouter, HTTPException
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/creator", tags=["products"])

USE_DB = bool(os.getenv("DATABASE_URL"))
if USE_DB:
    try:
        from api.services import db_service
    except ImportError:
        from api import db_service

@router.get("/{creator_id}/products")
async def get_products(creator_id: str, active_only: bool = True):
    if USE_DB:
        try:
            products = db_service.get_products(creator_id)
            if products is not None:
                return {"status": "ok", "products": products, "count": len(products)}
        except Exception as e:
            logger.warning(f"DB get products failed for {creator_id}: {e}")
    return {"status": "ok", "products": [], "count": 0}
