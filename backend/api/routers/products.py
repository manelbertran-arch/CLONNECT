"""Products endpoints with frontend compatibility"""
from fastapi import APIRouter, HTTPException, Body
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

try:
    from api.utils.response_adapter import adapt_products_response, adapt_product_response
except ImportError:
    def adapt_products_response(x): return x
    def adapt_product_response(x): return x

@router.get("/{creator_id}/products")
async def get_products(creator_id: str, active_only: bool = True):
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
async def create_product(creator_id: str, data: dict = Body(...)):
    if USE_DB:
        try:
            result = db_service.create_product(creator_id, data)
            if result:
                return {"status": "ok", "product": adapt_product_response(result)}
        except Exception as e:
            logger.warning(f"DB create product failed: {e}")
    raise HTTPException(status_code=500, detail="Failed to create product")

@router.put("/{creator_id}/products/{product_id}")
async def update_product(creator_id: str, product_id: str, data: dict = Body(...)):
    logger.info(f"=== ROUTER UPDATE PRODUCT ===")
    logger.info(f"Creator: {creator_id}, Product ID: {product_id}")
    logger.info(f"Data received: {data}")
    if USE_DB:
        try:
            success = db_service.update_product(creator_id, product_id, data)
            logger.info(f"DB update result: {success}")
            if success:
                return {"status": "ok", "message": "Product updated"}
        except Exception as e:
            logger.error(f"DB update product failed: {e}", exc_info=True)
    raise HTTPException(status_code=404, detail="Product not found")

@router.delete("/{creator_id}/products/{product_id}")
async def delete_product(creator_id: str, product_id: str):
    if USE_DB:
        try:
            success = db_service.delete_product(creator_id, product_id)
            if success:
                return {"status": "ok", "message": "Product deleted"}
        except Exception as e:
            logger.warning(f"DB delete product failed: {e}")
    raise HTTPException(status_code=404, detail="Product not found")
