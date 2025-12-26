"""Onboarding checklist endpoints"""
import os
import logging
from fastapi import APIRouter

from core.products import ProductManager
from core.creator_config import CreatorConfigManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


async def check_instagram_connected(creator_id: str) -> bool:
    """Check if Instagram is connected"""
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    return bool(token and len(token) > 10)


async def check_telegram_connected(creator_id: str) -> bool:
    """Check if Telegram bot is configured"""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    return bool(token and len(token) > 10)


async def check_whatsapp_connected(creator_id: str) -> bool:
    """Check if WhatsApp is configured"""
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
    return bool(token and phone_id)


async def check_has_products(creator_id: str) -> bool:
    """Check if creator has at least 1 product"""
    try:
        product_manager = ProductManager()
        products = product_manager.get_products(creator_id)
        return len(products) > 0
    except Exception as e:
        logger.warning(f"Error checking products: {e}")
        return False


async def check_personality_configured(creator_id: str) -> bool:
    """Check if personality/config is set up"""
    try:
        config_manager = CreatorConfigManager()
        config = config_manager.get_config(creator_id)
        # Check for essential fields
        has_name = bool(config.get("name"))
        has_personality = bool(config.get("personality")) or bool(config.get("tone"))
        return has_name and has_personality
    except Exception:
        return False


async def check_bot_active(creator_id: str) -> bool:
    """Check if bot is activated"""
    try:
        config_manager = CreatorConfigManager()
        return config_manager.is_bot_active(creator_id)
    except Exception:
        return False  # Default to inactive (paused)


@router.get("/{creator_id}/status")
async def get_onboarding_status(creator_id: str):
    """Get onboarding checklist status"""

    # Check each step
    steps = {
        "connect_instagram": await check_instagram_connected(creator_id),
        "connect_telegram": await check_telegram_connected(creator_id),
        "connect_whatsapp": await check_whatsapp_connected(creator_id),
        "add_product": await check_has_products(creator_id),
        "configure_personality": await check_personality_configured(creator_id),
        "activate_bot": await check_bot_active(creator_id)
    }

    # At least one messaging channel connected
    has_channel = steps["connect_instagram"] or steps["connect_telegram"] or steps["connect_whatsapp"]

    # Core steps (required for basic functionality)
    core_steps = {
        "connect_channel": has_channel,
        "add_product": steps["add_product"],
        "configure_personality": steps["configure_personality"],
        "activate_bot": steps["activate_bot"]
    }

    completed = sum(1 for v in core_steps.values() if v)
    total = len(core_steps)

    return {
        "status": "ok",
        "steps": steps,
        "core_steps": core_steps,
        "completed": completed,
        "total": total,
        "percentage": int((completed / total) * 100),
        "is_complete": completed == total,
        "next_step": _get_next_step(core_steps)
    }


def _get_next_step(steps: dict) -> dict:
    """Get the next step to complete"""
    step_info = {
        "connect_channel": {
            "label": "Conectar un canal de mensajes",
            "description": "Conecta Instagram, Telegram o WhatsApp",
            "link": "/settings/connections"
        },
        "add_product": {
            "label": "Añadir un producto",
            "description": "Añade al menos un producto para vender",
            "link": "/settings/products"
        },
        "configure_personality": {
            "label": "Configurar personalidad",
            "description": "Define cómo habla tu clon de IA",
            "link": "/settings/personality"
        },
        "activate_bot": {
            "label": "Activar el bot",
            "description": "Activa las respuestas automáticas",
            "link": "/settings"
        }
    }

    for step_key, is_complete in steps.items():
        if not is_complete:
            return {
                "key": step_key,
                **step_info.get(step_key, {"label": step_key, "link": "/settings"})
            }

    return {"key": None, "label": "Completado", "link": "/dashboard"}


@router.post("/{creator_id}/skip")
async def skip_onboarding(creator_id: str):
    """Mark onboarding as skipped (user will configure later)"""
    # Could store in database/file that user skipped onboarding
    return {"status": "ok", "message": "Onboarding skipped"}
