"""
Product CRUD operations.
"""

import logging

from api.utils.creator_resolver import resolve_creator_safe
from .session import get_session

logger = logging.getLogger(__name__)


# ============================================
# CRUD COMPLETO - Phase 11
# ============================================


def get_products(creator_name: str):
    session = get_session()
    if not session:
        logger.warning(f"get_products: no session for {creator_name}")
        return []
    try:
        from api.models import Creator, Product

        creator = resolve_creator_safe(session, creator_name)
        if not creator:
            logger.warning(f"get_products: creator '{creator_name}' not found")
            return []
        products = session.query(Product).filter_by(creator_id=creator.id).all()
        logger.info(f"get_products: found {len(products)} products for {creator_name}")
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "short_description": getattr(p, "short_description", "") or "",
                "category": getattr(p, "category", "product") or "product",
                "product_type": getattr(p, "product_type", "otro") or "otro",
                "is_free": getattr(p, "is_free", False) or False,
                "price": p.price,
                "currency": p.currency,
                "payment_link": getattr(p, "payment_link", "") or "",
                "source_url": getattr(p, "source_url", "") or "",
                "is_active": p.is_active,
            }
            for p in products
        ]
    finally:
        session.close()


# =============================================================================
# PROTECTED BLOCK: Product Creation with Taxonomy
# Modified: 2026-01-16
# Reason: Guarda todos los campos de taxonomía (category, product_type, is_free)
# Do not remove taxonomy fields - required for frontend forms and bot responses
# =============================================================================
def create_product(creator_name: str, data: dict):
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Product

        creator = resolve_creator_safe(session, creator_name)
        if not creator:
            return None
        product = Product(
            creator_id=creator.id,
            name=data.get("name", ""),
            description=data.get("description", ""),
            short_description=data.get("short_description", ""),
            # Taxonomy fields
            category=data.get("category", "product"),
            product_type=data.get("product_type", "otro"),
            is_free=data.get("is_free", False),
            # Pricing
            price=data.get("price", 0),
            currency=data.get("currency", "EUR"),
            # Links
            payment_link=data.get("payment_link", ""),
            # Status
            is_active=data.get("is_active", True),
        )
        session.add(product)
        session.commit()
        return {"id": str(product.id), "name": product.name, "status": "created"}
    except Exception as _e:
        session.rollback()
        return None
    finally:
        session.close()


def update_product(creator_name: str, product_id: str, data: dict):
    session = get_session()
    if not session:
        logger.error("update_product: No session available")
        return False
    try:
        import uuid

        from api.models import Creator, Product

        logger.info(f"update_product: creator={creator_name}, product_id={product_id}")
        logger.info(f"update_product: data received = {data}")

        creator = resolve_creator_safe(session, creator_name)
        if not creator:
            logger.error(f"update_product: Creator '{creator_name}' not found")
            return False

        product = (
            session.query(Product)
            .filter_by(creator_id=creator.id, id=uuid.UUID(product_id))
            .first()
        )
        if product:
            logger.info(
                f"update_product: Found product '{product.name}', current payment_link='{product.payment_link}'"
            )
            for key, value in data.items():
                if hasattr(product, key):
                    old_value = getattr(product, key, None)
                    setattr(product, key, value)
                    logger.info(f"update_product: Set {key}: '{old_value}' -> '{value}'")
                else:
                    logger.warning(f"update_product: Product has no attribute '{key}'")
            session.commit()
            logger.info(f"update_product: Committed. payment_link is now '{product.payment_link}'")
            return True
        else:
            logger.error(f"update_product: Product {product_id} not found for creator {creator.id}")
        return False
    except Exception as e:
        logger.error(f"update_product: Exception: {e}", exc_info=True)
        session.rollback()
        return False
    finally:
        session.close()


def delete_product(creator_name: str, product_id: str):
    session = get_session()
    if not session:
        return False
    try:
        import uuid

        from api.models import Creator, Product

        creator = resolve_creator_safe(session, creator_name)
        if not creator:
            return False
        product = (
            session.query(Product)
            .filter_by(creator_id=creator.id, id=uuid.UUID(product_id))
            .first()
        )
        if product:
            session.delete(product)
            session.commit()
            return True
        return False
    except Exception as _e:
        session.rollback()
        return False
    finally:
        session.close()
