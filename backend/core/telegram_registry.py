"""
Telegram Bot Registry - Manages multiple Telegram bots for different creators.
Each creator can have their own bot, and we route messages to the correct creator.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timezone
import httpx

logger = logging.getLogger(__name__)

# Path to bots config file
BOTS_CONFIG_PATH = Path("data/telegram/bots.json")


class TelegramBotRegistry:
    """
    Registry for managing multiple Telegram bots.
    Maps bot_id -> creator_id and stores bot tokens.
    """

    def __init__(self):
        self._bots: Dict[str, dict] = {}
        self._creator_to_bot: Dict[str, str] = {}  # Reverse lookup
        self._load_config()

    def _load_config(self):
        """Load bots configuration from file."""
        try:
            if BOTS_CONFIG_PATH.exists():
                with open(BOTS_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._bots = data.get("bots", {})
                # Build reverse lookup
                for bot_id, bot_data in self._bots.items():
                    creator_id = bot_data.get("creator_id")
                    if creator_id:
                        self._creator_to_bot[creator_id] = bot_id
                logger.info(f"Loaded {len(self._bots)} Telegram bots from config")
            else:
                logger.warning(f"Telegram bots config not found at {BOTS_CONFIG_PATH}")
                self._bots = {}
        except Exception as e:
            logger.error(f"Error loading Telegram bots config: {e}")
            self._bots = {}

    def _save_config(self):
        """Save bots configuration to file."""
        try:
            BOTS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "bots": self._bots,
                "default_bot_id": list(self._bots.keys())[0] if self._bots else None
            }
            with open(BOTS_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self._bots)} Telegram bots to config")
            return True
        except Exception as e:
            logger.error(f"Error saving Telegram bots config: {e}")
            return False

    def get_bot_by_id(self, bot_id: str) -> Optional[dict]:
        """Get bot configuration by bot_id (from Telegram message)."""
        return self._bots.get(bot_id)

    def get_bot_by_creator(self, creator_id: str) -> Optional[dict]:
        """Get bot configuration by creator_id."""
        bot_id = self._creator_to_bot.get(creator_id)
        if bot_id:
            return self._bots.get(bot_id)
        return None

    def get_creator_id(self, bot_id: str) -> Optional[str]:
        """Get creator_id for a bot_id."""
        bot = self._bots.get(bot_id)
        if bot:
            return bot.get("creator_id")
        return None

    def get_bot_token(self, bot_id: str) -> Optional[str]:
        """Get the full bot token for a bot_id."""
        bot = self._bots.get(bot_id)
        if bot:
            return bot.get("bot_token")
        return None

    def get_token_for_creator(self, creator_id: str) -> Optional[str]:
        """Get the bot token for a creator."""
        bot = self.get_bot_by_creator(creator_id)
        if bot:
            return bot.get("bot_token")
        return None

    def list_bots(self) -> list:
        """List all registered bots (without exposing full tokens)."""
        result = []
        for bot_id, bot_data in self._bots.items():
            token = bot_data.get("bot_token", "")
            result.append({
                "bot_id": bot_id,
                "creator_id": bot_data.get("creator_id"),
                "bot_username": bot_data.get("bot_username"),
                "bot_name": bot_data.get("bot_name"),
                "is_active": bot_data.get("is_active", True),
                "token_preview": f"{token[:10]}...{token[-5:]}" if len(token) > 15 else "***",
                "registered_at": bot_data.get("registered_at")
            })
        return result

    async def register_bot(
        self,
        creator_id: str,
        bot_token: str,
        bot_username: Optional[str] = None,
        set_webhook: bool = True,
        webhook_url: Optional[str] = None
    ) -> dict:
        """
        Register a new Telegram bot for a creator.

        Args:
            creator_id: The creator this bot belongs to
            bot_token: Full bot token from BotFather
            bot_username: Bot username (optional, will be fetched from Telegram)
            set_webhook: Whether to automatically set the webhook
            webhook_url: Custom webhook URL (uses Railway URL if not provided)

        Returns:
            dict with status and bot info
        """
        try:
            # Extract bot_id from token (format: "123456789:ABC...")
            bot_id = bot_token.split(":")[0]

            # Verify token by calling getMe
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"https://api.telegram.org/bot{bot_token}/getMe"
                )
                result = response.json()

                if not result.get("ok"):
                    return {
                        "status": "error",
                        "error": "Invalid bot token",
                        "telegram_error": result.get("description")
                    }

                bot_info = result.get("result", {})
                actual_username = bot_info.get("username", bot_username)
                bot_name = bot_info.get("first_name", "Unknown Bot")

            # Check if this creator already has a bot
            existing_bot_id = self._creator_to_bot.get(creator_id)
            if existing_bot_id and existing_bot_id != bot_id:
                logger.warning(f"Creator {creator_id} already has bot {existing_bot_id}, replacing with {bot_id}")
                # Remove old bot
                if existing_bot_id in self._bots:
                    del self._bots[existing_bot_id]

            # Register the bot
            self._bots[bot_id] = {
                "creator_id": creator_id,
                "bot_token": bot_token,
                "bot_username": actual_username,
                "bot_name": bot_name,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "is_active": True
            }
            self._creator_to_bot[creator_id] = bot_id

            # Save config
            self._save_config()

            # Set webhook if requested
            webhook_result = None
            if set_webhook:
                base_url = webhook_url or os.getenv("RAILWAY_PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL")
                if not base_url:
                    # Try to construct from known Railway URL
                    base_url = "https://web-production-9f69.up.railway.app"

                full_webhook_url = f"{base_url}/webhook/telegram"

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"https://api.telegram.org/bot{bot_token}/setWebhook",
                        json={"url": full_webhook_url}
                    )
                    webhook_result = response.json()

                    if webhook_result.get("ok"):
                        logger.info(f"Webhook set for bot {bot_id}: {full_webhook_url}")
                    else:
                        logger.error(f"Failed to set webhook: {webhook_result}")

            return {
                "status": "success",
                "bot_id": bot_id,
                "bot_username": actual_username,
                "bot_name": bot_name,
                "creator_id": creator_id,
                "webhook_set": webhook_result.get("ok") if webhook_result else False,
                "webhook_url": full_webhook_url if set_webhook else None
            }

        except Exception as e:
            logger.error(f"Error registering bot: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    def update_bot_creator(self, bot_id: str, new_creator_id: str) -> dict:
        """
        Update the creator_id for an existing bot.

        Args:
            bot_id: The bot ID to update
            new_creator_id: The new creator_id to assign

        Returns:
            dict with status and updated info
        """
        if bot_id not in self._bots:
            return {
                "status": "error",
                "error": f"Bot {bot_id} not found"
            }

        bot_data = self._bots[bot_id]
        old_creator_id = bot_data.get("creator_id")

        # Update reverse lookup
        if old_creator_id and old_creator_id in self._creator_to_bot:
            del self._creator_to_bot[old_creator_id]

        # Update bot data
        bot_data["creator_id"] = new_creator_id
        self._creator_to_bot[new_creator_id] = bot_id

        # Save config
        self._save_config()

        logger.info(f"Updated bot {bot_id} creator_id: {old_creator_id} -> {new_creator_id}")

        return {
            "status": "success",
            "bot_id": bot_id,
            "old_creator_id": old_creator_id,
            "new_creator_id": new_creator_id
        }

    async def unregister_bot(self, bot_id: str, delete_webhook: bool = True) -> dict:
        """
        Unregister a Telegram bot.

        Args:
            bot_id: The bot ID to unregister
            delete_webhook: Whether to delete the webhook from Telegram
        """
        try:
            if bot_id not in self._bots:
                return {"status": "error", "error": "Bot not found"}

            bot_data = self._bots[bot_id]
            creator_id = bot_data.get("creator_id")

            # Delete webhook if requested
            if delete_webhook and bot_data.get("bot_token"):
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        await client.post(
                            f"https://api.telegram.org/bot{bot_data['bot_token']}/deleteWebhook"
                        )
                except Exception as e:
                    logger.warning(f"Failed to delete webhook: {e}")

            # Remove from registry
            del self._bots[bot_id]
            if creator_id and creator_id in self._creator_to_bot:
                del self._creator_to_bot[creator_id]

            self._save_config()

            return {
                "status": "success",
                "bot_id": bot_id,
                "creator_id": creator_id,
                "message": "Bot unregistered successfully"
            }

        except Exception as e:
            logger.error(f"Error unregistering bot: {e}")
            return {"status": "error", "error": str(e)}

    def reload(self):
        """Reload configuration from file."""
        self._load_config()


# Global singleton instance
_registry: Optional[TelegramBotRegistry] = None


def get_telegram_registry() -> TelegramBotRegistry:
    """Get the global TelegramBotRegistry instance."""
    global _registry
    if _registry is None:
        _registry = TelegramBotRegistry()
    return _registry
