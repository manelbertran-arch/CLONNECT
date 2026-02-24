"""Products endpoints with frontend compatibility"""
from fastapi import APIRouter, Depends, HTTPException, Body
import logging
import os

from api.auth import require_creator_access
from api.schemas.products import ProductCreate, ProductUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/creator", tags=["products"])

USE_DB = bool(os.getenv("DATABASE_URL"))
if USE_DB:
    try:
        from api.services import db_service
    except ImportError:
        from api import db_service

try:
    from api.utils.response_adapter import adapt_products_response, adapt_product_response
except ImportError:
    def adapt_products_response(x): return x
    def adapt_product_response(x): return x


def _invalidate_bot_cache(creator_id: str):
    """Invalidar caché del bot cuando cambian productos."""
    try:
        from core.dm_agent_v2 import invalidate_dm_agent_cache
        invalidate_dm_agent_cache(creator_id)
        logger.info(f"[CACHE] Bot cache invalidated for {creator_id}")
    except Exception as e:
        logger.warning(f"[CACHE] Failed to invalidate bot cache: {e}")

@router.get("/{creator_id}/products")
async def get_products(creator_id: str, active_only: bool = True, _auth: str = Depends(require_creator_access)):
    if USE_DB:
        try:
            products = db_service.get_products(creator_id)
            if products is not None:
                if active_only:
                    products = [p for p in products if p.get("is_active", True)]
                adapted = adapt_products_response(products)
                return {"status": "ok", "products": adapted, "count": len(adapted)}
        except Exception as e:
            logger.warning(f"DB get products failed for {creator_id}: {e}")
    return {"status": "ok", "products": [], "count": 0}

@router.post("/{creator_id}/products")
async def create_product(creator_id: str, data: ProductCreate, _auth: str = Depends(require_creator_access)):
    if USE_DB:
        try:
            result = db_service.create_product(creator_id, data.model_dump(exclude_unset=True))
            if result:
                _invalidate_bot_cache(creator_id)
                return {"status": "ok", "product": adapt_product_response(result)}
        except Exception as e:
            logger.warning(f"DB create product failed: {e}")
    raise HTTPException(status_code=500, detail="Failed to create product")

@router.put("/{creator_id}/products/{product_id}")
async def update_product(creator_id: str, product_id: str, data: ProductUpdate, _auth: str = Depends(require_creator_access)):
    logger.info("=== ROUTER UPDATE PRODUCT ===")
    logger.info(f"Creator: {creator_id}, Product ID: {product_id}")
    logger.info(f"Data received: {data.model_dump(exclude_unset=True)}")
    if USE_DB:
        try:
            success = db_service.update_product(creator_id, product_id, data.model_dump(exclude_unset=True))
            logger.info(f"DB update result: {success}")
            if success:
                _invalidate_bot_cache(creator_id)
                return {"status": "ok", "message": "Product updated"}
        except Exception as e:
            logger.error(f"DB update product failed: {e}", exc_info=True)
    raise HTTPException(status_code=404, detail="Product not found")

@router.delete("/{creator_id}/products/{product_id}")
async def delete_product(creator_id: str, product_id: str, _auth: str = Depends(require_creator_access)):
    if USE_DB:
        try:
            success = db_service.delete_product(creator_id, product_id)
            if success:
                _invalidate_bot_cache(creator_id)
                return {"status": "ok", "message": "Product deleted"}
        except Exception as e:
            logger.warning(f"DB delete product failed: {e}")
    raise HTTPException(status_code=404, detail="Product not found")
