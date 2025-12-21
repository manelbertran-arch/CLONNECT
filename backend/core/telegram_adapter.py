#!/usr/bin/env python3
"""
Telegram Adapter for Clonnect Creators DM System.

Provides Telegram bot integration for testing the DM system without
depending on Instagram. Uses python-telegram-bot v20+ (async).

Usage:
    Polling (local): python core/telegram_adapter.py --mode polling
    Webhook (prod):  Used via FastAPI endpoints
"""
import os
import asyncio
import logging
import argparse
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("clonnect-telegram")

# Check for telegram library - handle cryptography/cffi issues gracefully
TELEGRAM_AVAILABLE = False
Update = None
Bot = None
Application = None
CommandHandler = None
MessageHandler = None
ContextTypes = None
filters = None

try:
    from telegram import Update as _Update, Bot as _Bot
    from telegram.ext import (
        Application as _Application,
        CommandHandler as _CommandHandler,
        MessageHandler as _MessageHandler,
        ContextTypes as _ContextTypes,
        filters as _filters
    )
    Update = _Update
    Bot = _Bot
    Application = _Application
    CommandHandler = _CommandHandler
    MessageHandler = _MessageHandler
    ContextTypes = _ContextTypes
    filters = _filters
    TELEGRAM_AVAILABLE = True
except (ImportError, Exception) as e:
    logger.warning(f"python-telegram-bot not available: {e}. Install with: pip install python-telegram-bot>=20.0")

# Import DM Agent components from clonnect-creators
from core.dm_agent import DMResponderAgent, DMResponse


@dataclass
class TelegramMessage:
    """Telegram message representation"""
    telegram_user_id: int
    chat_id: int
    message_id: int
    text: str
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    platform: str = "telegram"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @property
    def follower_id(self) -> str:
        """Generate follower_id for DMResponderAgent"""
        return f"tg_{self.telegram_user_id}"

    @property
    def display_name(self) -> str:
        """Get display name"""
        if self.username:
            return f"@{self.username}"
        if self.first_name:
            name = self.first_name
            if self.last_name:
                name += f" {self.last_name}"
            return name
        return f"User {self.telegram_user_id}"


@dataclass
class TelegramBotStatus:
    """Status of the Telegram bot"""
    connected: bool = False
    bot_username: str = ""
    bot_id: int = 0
    mode: str = "unknown"  # polling or webhook
    messages_received: int = 0
    messages_sent: int = 0
    last_message_time: Optional[str] = None
    errors: int = 0
    started_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class TelegramAdapter:
    """
    Telegram adapter for Clonnect DM system.

    Bridges Telegram messages to DMResponderAgent and sends responses back.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        creator_id: str = "manel",
        webhook_url: Optional[str] = None
    ):
        """
        Initialize Telegram adapter.

        Args:
            token: Telegram bot token (from BotFather)
            creator_id: Creator ID to use for DMResponderAgent
            webhook_url: Webhook URL for production mode
        """
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.creator_id = creator_id
        self.webhook_url = webhook_url or os.getenv("TELEGRAM_WEBHOOK_URL")

        # Status tracking
        self.status = TelegramBotStatus()
        self.recent_messages: List[Dict[str, Any]] = []  # Last 10 messages
        self.recent_responses: List[Dict[str, Any]] = []  # Last 10 responses

        # DM Agent
        self.dm_agent: Optional[DMResponderAgent] = None

        # Telegram application
        self.application: Optional[Application] = None
        self.bot: Optional[Bot] = None

        if not TELEGRAM_AVAILABLE:
            logger.error("python-telegram-bot not installed")
            return

        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN not set")
            return

        self._init_agent()

    def _init_agent(self):
        """Initialize DM agent"""
        try:
            self.dm_agent = DMResponderAgent(creator_id=self.creator_id)
            logger.info(f"DM Agent initialized for creator: {self.creator_id}")
        except Exception as e:
            logger.error(f"Failed to initialize DM agent: {e}")

    async def start(self, mode: str = "polling") -> None:
        """
        Start the Telegram bot.

        Args:
            mode: 'polling' for local testing, 'webhook' for production
        """
        if not TELEGRAM_AVAILABLE:
            raise RuntimeError("python-telegram-bot not installed")

        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

        # Build application
        self.application = Application.builder().token(self.token).build()

        # Add handlers
        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(CommandHandler("help", self._handle_help))
        self.application.add_handler(CommandHandler("status", self._handle_status))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        # Get bot info
        self.bot = self.application.bot
        bot_info = await self.bot.get_me()
        self.status.bot_username = bot_info.username
        self.status.bot_id = bot_info.id
        self.status.connected = True
        self.status.mode = mode
        self.status.started_at = datetime.now(timezone.utc).isoformat()

        logger.info(f"Bot @{self.status.bot_username} starting in {mode} mode")

        if mode == "polling":
            # Start polling
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
            logger.info(f"Bot @{self.status.bot_username} is running (polling)")
        elif mode == "webhook":
            # Webhook mode - application is used by FastAPI
            await self.application.initialize()
            logger.info(f"Bot @{self.status.bot_username} ready for webhook")

    async def stop(self) -> None:
        """Stop the Telegram bot"""
        if self.application:
            if self.application.updater and self.application.updater.running:
                await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            self.status.connected = False
            logger.info("Bot stopped")

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        user = update.effective_user
        welcome_message = (
            f"¡Hola {user.first_name}! 👋\n\n"
            "Soy el asistente virtual de Clonnect. Puedo ayudarte con:\n"
            "• Información sobre productos y servicios\n"
            "• Responder tus preguntas\n"
            "• Conectarte con el creador si es necesario\n\n"
            "¡Escríbeme lo que necesites!"
        )
        await update.message.reply_text(welcome_message)
        self._record_sent()

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command"""
        help_message = (
            "📋 *Comandos disponibles:*\n\n"
            "/start - Iniciar conversación\n"
            "/help - Ver esta ayuda\n"
            "/status - Ver estado del bot\n\n"
            "💬 *También puedes:*\n"
            "• Preguntarme sobre productos\n"
            "• Pedir información\n"
            "• Hacer consultas generales\n"
        )
        await update.message.reply_text(help_message, parse_mode="Markdown")
        self._record_sent()

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command"""
        status_message = (
            f"🤖 *Estado del Bot*\n\n"
            f"• Bot: @{self.status.bot_username}\n"
            f"• Modo: {self.status.mode}\n"
            f"• Mensajes recibidos: {self.status.messages_received}\n"
            f"• Mensajes enviados: {self.status.messages_sent}\n"
            f"• Errores: {self.status.errors}\n"
        )
        await update.message.reply_text(status_message, parse_mode="Markdown")
        self._record_sent()

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming text messages"""
        try:
            # Parse message
            telegram_msg = self._parse_update(update)
            if not telegram_msg:
                return

            # Record message
            self._record_received(telegram_msg)

            # Process with DM agent
            response = await self.process_message(telegram_msg)

            # Send response
            await update.message.reply_text(response.response_text)
            self._record_sent()

            # Record response
            self._record_response(telegram_msg, response)

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            self.status.errors += 1
            await update.message.reply_text(
                "Lo siento, hubo un error procesando tu mensaje. Por favor, intenta de nuevo."
            )

    def _parse_update(self, update: Update) -> Optional[TelegramMessage]:
        """Parse Telegram update to TelegramMessage"""
        if not update.message or not update.message.text:
            return None

        user = update.effective_user
        return TelegramMessage(
            telegram_user_id=user.id,
            chat_id=update.message.chat_id,
            message_id=update.message.message_id,
            text=update.message.text,
            username=user.username or "",
            first_name=user.first_name or "",
            last_name=user.last_name or ""
        )

    async def process_message(self, telegram_msg: TelegramMessage) -> DMResponse:
        """
        Process a Telegram message through DMResponderAgent.

        Args:
            telegram_msg: Parsed Telegram message

        Returns:
            DMResponse from the agent
        """
        if not self.dm_agent:
            self._init_agent()

        if not self.dm_agent:
            raise RuntimeError("DM Agent not initialized")

        logger.info(f"[{telegram_msg.display_name}] Input: {telegram_msg.text}")

        # Get name for personalization and storage
        display_name = telegram_msg.first_name or telegram_msg.username or "amigo"
        full_name = telegram_msg.first_name or ""
        if telegram_msg.last_name:
            full_name += f" {telegram_msg.last_name}"

        # Process with DM agent (async) - passing name for storage
        response = await self.dm_agent.process_dm(
            sender_id=telegram_msg.follower_id,
            message_text=telegram_msg.text,
            message_id=str(telegram_msg.message_id),
            username=display_name,
            name=full_name.strip()
        )

        # Update follower name/username in memory if available and not set
        try:
            follower = await self.dm_agent.memory_store.get(
                self.creator_id, telegram_msg.follower_id
            )
            if follower:
                updated = False
                # Always update name if we have it from Telegram and not already set
                if telegram_msg.first_name and not follower.name:
                    follower.name = telegram_msg.first_name
                    if telegram_msg.last_name:
                        follower.name += f" {telegram_msg.last_name}"
                    updated = True
                # Update username if available and not set
                if telegram_msg.username and not follower.username:
                    follower.username = telegram_msg.username
                    updated = True
                if updated:
                    await self.dm_agent.memory_store.save(follower)
                    logger.info(f"Updated follower profile: name={follower.name}, username={follower.username}")
        except Exception as e:
            logger.debug(f"Could not update follower profile: {e}")

        logger.info(f"[{telegram_msg.display_name}] Intent: {response.intent.value} ({response.confidence:.0%})")
        logger.info(f"[{telegram_msg.display_name}] Output: {response.response_text[:100]}...")

        return response

    async def process_webhook_update(self, update_data: Dict[str, Any]) -> Optional[DMResponse]:
        """
        Process a webhook update from Telegram.

        Args:
            update_data: Raw update data from Telegram webhook

        Returns:
            DMResponse if message was processed, None otherwise
        """
        if not TELEGRAM_AVAILABLE:
            raise RuntimeError("python-telegram-bot not installed")

        try:
            update = Update.de_json(update_data, self.bot)
            if not update or not update.message or not update.message.text:
                return None

            telegram_msg = self._parse_update(update)
            if not telegram_msg:
                return None

            self._record_received(telegram_msg)

            # Process message
            response = await self.process_message(telegram_msg)

            # Send response via bot
            await self.bot.send_message(
                chat_id=telegram_msg.chat_id,
                text=response.response_text
            )
            self._record_sent()
            self._record_response(telegram_msg, response)

            return response

        except Exception as e:
            logger.error(f"Error processing webhook update: {e}")
            self.status.errors += 1
            return None

    async def send_message(self, chat_id: int, text: str) -> bool:
        """
        Send a message to a chat.

        Args:
            chat_id: Telegram chat ID
            text: Message text

        Returns:
            True if sent successfully
        """
        if not self.bot:
            logger.error("Bot not initialized")
            return False

        try:
            await self.bot.send_message(chat_id=chat_id, text=text)
            self._record_sent()
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.status.errors += 1
            return False

    def _record_received(self, msg: TelegramMessage):
        """Record received message"""
        self.status.messages_received += 1
        self.status.last_message_time = msg.timestamp

        record = {
            "type": "received",
            "follower_id": msg.follower_id,
            "username": msg.display_name,
            "text": msg.text,
            "timestamp": msg.timestamp
        }
        self.recent_messages.append(record)
        if len(self.recent_messages) > 10:
            self.recent_messages = self.recent_messages[-10:]

    def _record_sent(self):
        """Record sent message"""
        self.status.messages_sent += 1

    def _record_response(self, msg: TelegramMessage, response: DMResponse):
        """Record response"""
        record = {
            "follower_id": msg.follower_id,
            "username": msg.display_name,
            "input": msg.text,
            "response": response.response_text,
            "intent": response.intent.value if hasattr(response.intent, 'value') else str(response.intent),
            "confidence": response.confidence,
            "product": response.product_mentioned,
            "escalate": response.escalate_to_human,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.recent_responses.append(record)
        if len(self.recent_responses) > 10:
            self.recent_responses = self.recent_responses[-10:]

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        return self.status.to_dict()

    def get_recent_messages(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent messages"""
        return self.recent_messages[-limit:]

    def get_recent_responses(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent responses"""
        return self.recent_responses[-limit:]


# Global adapter instance
_adapter: Optional[TelegramAdapter] = None


def get_telegram_adapter(
    creator_id: str = "manel",
    token: Optional[str] = None
) -> TelegramAdapter:
    """Get or create Telegram adapter"""
    global _adapter
    if _adapter is None:
        _adapter = TelegramAdapter(token=token, creator_id=creator_id)
    return _adapter


async def run_polling(creator_id: str = "manel"):
    """Run bot in polling mode (for local testing)"""
    adapter = get_telegram_adapter(creator_id)
    await adapter.start(mode="polling")

    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping bot...")
    finally:
        await adapter.stop()


def main():
    """Main entry point for CLI"""
    parser = argparse.ArgumentParser(description="Clonnect Telegram Bot")
    parser.add_argument(
        "--mode",
        choices=["polling", "webhook"],
        default="polling",
        help="Bot mode: polling (local) or webhook (production)"
    )
    parser.add_argument(
        "--creator-id",
        default="manel",
        help="Creator ID to use"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if args.mode == "polling":
        print(f"Starting Telegram bot in polling mode (creator: {args.creator_id})")
        print("Press Ctrl+C to stop")
        asyncio.run(run_polling(args.creator_id))
    else:
        print("Webhook mode: Use FastAPI endpoints to receive updates")
        print("Start the API with: uvicorn api.main:app --host 0.0.0.0 --port 8000")


if __name__ == "__main__":
    main()
