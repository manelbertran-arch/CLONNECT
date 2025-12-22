"""Simple Telegram message sender wrapper"""
import os
import logging
import httpx

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


async def send_telegram_message(chat_id: str, text: str) -> bool:
    """
    Send a message to a Telegram chat.

    Args:
        chat_id: Telegram chat ID (as string)
        text: Message text to send

    Returns:
        True if sent successfully, False otherwise
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not configured")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML"
                },
                timeout=10.0
            )

            if response.status_code == 200:
                logger.info(f"Message sent to Telegram chat {chat_id}")
                return True
            else:
                logger.warning(f"Telegram API error: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False
