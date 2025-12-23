#!/usr/bin/env python3
"""
Sistema de notificaciones para escalación a humano.
Soporta múltiples canales: webhook, email, Telegram.
"""
import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """Tipos de notificación"""
    ESCALATION = "escalation"           # Escalación a humano
    HOT_LEAD = "hot_lead"               # Lead con alta intención (>0.8)
    NEW_LEAD = "new_lead"               # Nuevo lead cualificado
    SUPPORT_REQUEST = "support"         # Solicitud de soporte
    DAILY_SUMMARY = "daily_summary"     # Resumen diario


@dataclass
class EscalationNotification:
    """Datos de notificación de escalación"""
    creator_id: str
    follower_id: str
    follower_username: str
    follower_name: str
    reason: str
    last_message: str
    conversation_summary: str
    purchase_intent_score: float
    total_messages: int
    products_discussed: List[str]
    timestamp: str = None
    notification_type: str = "escalation"

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    def to_slack_message(self) -> dict:
        """Formato para Slack webhook"""
        intent_emoji = "🔥" if self.purchase_intent_score > 0.7 else "⚡" if self.purchase_intent_score > 0.4 else "📩"
        products_text = ", ".join(self.products_discussed) if self.products_discussed else "Ninguno"

        return {
            "text": f"{intent_emoji} Escalación: @{self.follower_username}",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{intent_emoji} Escalación a Humano"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Usuario:*\n@{self.follower_username}"},
                        {"type": "mrkdwn", "text": f"*Nombre:*\n{self.follower_name or 'N/A'}"},
                        {"type": "mrkdwn", "text": f"*Intención compra:*\n{self.purchase_intent_score:.0%}"},
                        {"type": "mrkdwn", "text": f"*Mensajes:*\n{self.total_messages}"}
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Razón:*\n{self.reason}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Último mensaje:*\n>{self.last_message[:200]}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Productos discutidos:*\n{products_text}"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"📅 {self.timestamp[:16]}"}
                    ]
                }
            ]
        }

    def to_email_html(self) -> str:
        """Formato HTML para email"""
        intent_color = "#e74c3c" if self.purchase_intent_score > 0.7 else "#f39c12" if self.purchase_intent_score > 0.4 else "#3498db"
        products_text = ", ".join(self.products_discussed) if self.products_discussed else "Ninguno"

        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: {intent_color}; color: white; padding: 20px; text-align: center;">
                <h1 style="margin: 0;">🚨 Escalación a Humano</h1>
            </div>

            <div style="padding: 20px; background: #f9f9f9;">
                <h2 style="color: #333;">@{self.follower_username}</h2>
                <p><strong>Nombre:</strong> {self.follower_name or 'N/A'}</p>

                <div style="background: white; padding: 15px; border-radius: 8px; margin: 15px 0;">
                    <h3 style="margin-top: 0; color: {intent_color};">
                        Intención de compra: {self.purchase_intent_score:.0%}
                    </h3>
                    <p><strong>Total mensajes:</strong> {self.total_messages}</p>
                    <p><strong>Productos discutidos:</strong> {products_text}</p>
                </div>

                <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 15px 0;">
                    <h4 style="margin-top: 0;">Razón de escalación:</h4>
                    <p>{self.reason}</p>
                </div>

                <div style="background: white; padding: 15px; border-radius: 8px;">
                    <h4 style="margin-top: 0;">Último mensaje:</h4>
                    <p style="color: #666; font-style: italic;">"{self.last_message}"</p>
                </div>

                <p style="color: #999; font-size: 12px; margin-top: 20px;">
                    📅 {self.timestamp[:16]} | Creador: {self.creator_id}
                </p>
            </div>
        </body>
        </html>
        """

    def to_telegram_message(self) -> str:
        """Formato para Telegram"""
        intent_emoji = "🔥" if self.purchase_intent_score > 0.7 else "⚡" if self.purchase_intent_score > 0.4 else "📩"
        products_text = ", ".join(self.products_discussed) if self.products_discussed else "Ninguno"

        return f"""
{intent_emoji} *ESCALACIÓN A HUMANO*

👤 *Usuario:* @{self.follower_username}
📊 *Intención:* {self.purchase_intent_score:.0%}
💬 *Mensajes:* {self.total_messages}

*Razón:*
{self.reason}

*Último mensaje:*
_{self.last_message[:200]}_

*Productos:* {products_text}

📅 {self.timestamp[:16]}
"""


class NotificationService:
    """Servicio de notificaciones multi-canal"""

    def __init__(self):
        # Configuración desde variables de entorno
        self.webhook_url = os.getenv("ESCALATION_WEBHOOK_URL", "")
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.smtp_enabled = os.getenv("SMTP_ENABLED", "false").lower() == "true"

        # Historial de notificaciones (en memoria, para evitar duplicados)
        self._sent_notifications: Dict[str, datetime] = {}
        self._cooldown_seconds = 300  # 5 minutos entre notificaciones del mismo follower

    async def notify_escalation(
        self,
        notification: EscalationNotification,
        channels: List[str] = None
    ) -> Dict[str, bool]:
        """
        Enviar notificación de escalación por múltiples canales.

        Args:
            notification: Datos de la escalación
            channels: Lista de canales ['webhook', 'telegram', 'email', 'log']
                     Si es None, usa todos los configurados

        Returns:
            Dict con resultado por canal
        """
        # Cooldown para evitar spam
        cooldown_key = f"{notification.creator_id}:{notification.follower_id}"
        if cooldown_key in self._sent_notifications:
            last_sent = self._sent_notifications[cooldown_key]
            elapsed = (datetime.now() - last_sent).total_seconds()
            if elapsed < self._cooldown_seconds:
                logger.info(f"Notification skipped (cooldown): {cooldown_key}")
                return {"skipped": True, "reason": "cooldown"}

        # Determinar canales a usar
        if channels is None:
            channels = []
            if self.webhook_url:
                channels.append("webhook")
            if self.telegram_bot_token and self.telegram_chat_id:
                channels.append("telegram")
            if self.smtp_enabled:
                channels.append("email")
            channels.append("log")  # Siempre log

        results = {}

        # Enviar por cada canal
        for channel in channels:
            try:
                if channel == "webhook":
                    results["webhook"] = await self._send_webhook(notification)
                elif channel == "telegram":
                    results["telegram"] = await self._send_telegram(notification)
                elif channel == "email":
                    results["email"] = await self._send_email(notification)
                elif channel == "log":
                    results["log"] = self._log_notification(notification)
            except Exception as e:
                logger.error(f"Error sending notification via {channel}: {e}")
                results[channel] = False

        # Registrar envío
        self._sent_notifications[cooldown_key] = datetime.now()

        return results

    async def _send_webhook(self, notification: EscalationNotification) -> bool:
        """Enviar vía webhook (Slack, Discord, Zapier, etc.)"""
        if not self.webhook_url:
            return False

        try:
            import aiohttp

            # Detectar tipo de webhook por URL
            if "slack" in self.webhook_url.lower():
                payload = notification.to_slack_message()
            else:
                # Formato genérico JSON
                payload = notification.to_dict()

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    success = response.status in [200, 201, 204]
                    if success:
                        logger.info(f"Webhook notification sent: {notification.follower_username}")
                    else:
                        logger.error(f"Webhook failed: {response.status}")
                    return success

        except ImportError:
            logger.warning("aiohttp not installed, webhook disabled")
            return False
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return False

    async def _send_telegram(self, notification: EscalationNotification) -> bool:
        """Enviar vía Telegram Bot"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return False

        try:
            import aiohttp

            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": notification.to_telegram_message(),
                "parse_mode": "Markdown"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    success = response.status == 200
                    if success:
                        logger.info(f"Telegram notification sent: {notification.follower_username}")
                    return success

        except ImportError:
            logger.warning("aiohttp not installed, Telegram disabled")
            return False
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False

    async def _send_email(self, notification: EscalationNotification) -> bool:
        """Enviar vía email usando Resend API"""
        resend_api_key = os.getenv("RESEND_API_KEY", "")
        creator_email = os.getenv("CREATOR_EMAIL", "")

        if not resend_api_key or not creator_email:
            logger.debug("Email not configured (RESEND_API_KEY or CREATOR_EMAIL missing)")
            return False

        try:
            import aiohttp

            url = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "from": "Clonnect <notifications@clonnect.com>",
                "to": creator_email,
                "subject": f"🔥 Lead caliente: @{notification.follower_username}",
                "html": notification.to_email_html()
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    success = response.status in [200, 201]
                    if success:
                        logger.info(f"Email notification sent to {creator_email}")
                    else:
                        error_text = await response.text()
                        logger.error(f"Resend API error: {response.status} - {error_text}")
                    return success

        except ImportError:
            logger.warning("aiohttp not installed, email disabled")
            return False
        except Exception as e:
            logger.error(f"Email error: {e}")
            return False

    def _log_notification(self, notification: EscalationNotification) -> bool:
        """Guardar en log y archivo"""
        try:
            # Log
            logger.warning(
                f"🚨 ESCALACIÓN: @{notification.follower_username} | "
                f"Intent: {notification.purchase_intent_score:.0%} | "
                f"Razón: {notification.reason}"
            )

            # Guardar en archivo JSON
            log_dir = "data/escalations"
            os.makedirs(log_dir, exist_ok=True)

            log_file = os.path.join(log_dir, f"{notification.creator_id}_escalations.jsonl")
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(notification.to_dict(), ensure_ascii=False) + "\n")

            return True
        except Exception as e:
            logger.error(f"Log notification error: {e}")
            return False

    async def notify_hot_lead(
        self,
        creator_id: str,
        follower_id: str,
        follower_username: str,
        purchase_intent_score: float,
        products_discussed: List[str]
    ) -> Dict[str, bool]:
        """Notificar sobre lead con alta intención (>0.8)"""
        notification = EscalationNotification(
            creator_id=creator_id,
            follower_id=follower_id,
            follower_username=follower_username,
            follower_name="",
            reason=f"🔥 HOT LEAD - Intención de compra: {purchase_intent_score:.0%}",
            last_message="",
            conversation_summary="",
            purchase_intent_score=purchase_intent_score,
            total_messages=0,
            products_discussed=products_discussed,
            notification_type="hot_lead"
        )
        return await self.notify_escalation(notification)

    async def send_weekly_summary(
        self,
        creator_id: str,
        creator_email: str,
        stats: Dict[str, Any]
    ) -> bool:
        """
        Send weekly summary email to creator.

        Args:
            creator_id: Creator ID
            creator_email: Creator's email address
            stats: Dict with weekly statistics

        Returns:
            True if sent successfully
        """
        resend_api_key = os.getenv("RESEND_API_KEY", "")

        if not resend_api_key or not creator_email:
            logger.debug("Weekly summary not sent: missing RESEND_API_KEY or email")
            return False

        try:
            import aiohttp

            # Build email content
            total_messages = stats.get('total_messages', 0)
            new_leads = stats.get('new_leads', 0)
            hot_leads = stats.get('hot_leads', 0)
            sales = stats.get('sales', 0)
            revenue = stats.get('revenue', 0)

            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f5f5f5; padding: 20px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="margin: 0;">📊 Tu Semana en Clonnect</h1>
                </div>

                <div style="background: white; padding: 30px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #333;">¡Hola! Aquí está tu resumen semanal:</h2>

                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0;">
                        <div style="background: #e8f4fd; padding: 20px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 32px; font-weight: bold; color: #3498db;">📨 {total_messages}</div>
                            <div style="color: #666;">Mensajes recibidos</div>
                        </div>
                        <div style="background: #e8fdf4; padding: 20px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 32px; font-weight: bold; color: #2ecc71;">👥 {new_leads}</div>
                            <div style="color: #666;">Nuevos leads</div>
                        </div>
                        <div style="background: #fde8e8; padding: 20px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 32px; font-weight: bold; color: #e74c3c;">🔥 {hot_leads}</div>
                            <div style="color: #666;">Leads calientes</div>
                        </div>
                        <div style="background: #fdf8e8; padding: 20px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 32px; font-weight: bold; color: #f39c12;">💰 {revenue}€</div>
                            <div style="color: #666;">{sales} ventas</div>
                        </div>
                    </div>

                    <p style="color: #666; text-align: center; margin-top: 30px;">
                        ¡Sigue así! 🚀
                    </p>

                    <div style="text-align: center; margin-top: 20px;">
                        <a href="https://clonnect.vercel.app/dashboard"
                           style="background: #667eea; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Ver Dashboard
                        </a>
                    </div>
                </div>

                <p style="color: #999; font-size: 12px; text-align: center; margin-top: 20px;">
                    Clonnect - Tu clon de IA para responder DMs
                </p>
            </body>
            </html>
            """

            url = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "from": "Clonnect <weekly@clonnect.com>",
                "to": creator_email,
                "subject": f"📊 Tu semana en Clonnect - {new_leads} nuevos leads",
                "html": html_content
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    success = response.status in [200, 201]
                    if success:
                        logger.info(f"Weekly summary sent to {creator_email}")
                    else:
                        error_text = await response.text()
                        logger.error(f"Weekly summary failed: {response.status} - {error_text}")
                    return success

        except ImportError:
            logger.warning("aiohttp not installed, weekly summary disabled")
            return False
        except Exception as e:
            logger.error(f"Weekly summary error: {e}")
            return False


# Instancia global
_notification_service = None


def get_notification_service() -> NotificationService:
    """Get global notification service instance"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
