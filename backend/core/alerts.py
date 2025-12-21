"""
Clonnect Creators - Alert System
Sistema de alertas via Telegram para errores criticos
"""

import os
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, asdict
import aiohttp

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Niveles de alerta"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Estructura de una alerta"""
    level: AlertLevel
    title: str
    message: str
    creator_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class AlertManager:
    """
    Gestor de alertas via Telegram.

    Configuracion via variables de entorno:
    - TELEGRAM_ALERTS_ENABLED: true/false
    - TELEGRAM_ALERTS_BOT_TOKEN: Token del bot de Telegram
    - TELEGRAM_ALERTS_CHAT_ID: ID del chat/grupo para alertas
    """

    # Emojis por nivel
    LEVEL_EMOJI = {
        AlertLevel.INFO: "ℹ️",
        AlertLevel.WARNING: "⚠️",
        AlertLevel.ERROR: "🔴",
        AlertLevel.CRITICAL: "🚨",
    }

    def __init__(self):
        self.enabled = os.getenv("TELEGRAM_ALERTS_ENABLED", "false").lower() == "true"
        self.bot_token = os.getenv("TELEGRAM_ALERTS_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_ALERTS_CHAT_ID", "")

        # Rate limiting para evitar spam
        self._last_alert_time: Dict[str, float] = {}
        self._rate_limit_seconds = 60  # Minimo 1 minuto entre alertas iguales

        if self.enabled:
            if not self.bot_token or not self.chat_id:
                logger.warning("Telegram alerts enabled but missing configuration")
                self.enabled = False
            else:
                logger.info("Telegram alerts initialized")

    def _should_send(self, alert_key: str) -> bool:
        """Verificar rate limiting"""
        now = datetime.now(timezone.utc).timestamp()
        last_time = self._last_alert_time.get(alert_key, 0)

        if now - last_time < self._rate_limit_seconds:
            return False

        self._last_alert_time[alert_key] = now
        return True

    def _format_message(self, alert: Alert) -> str:
        """Formatear alerta para Telegram"""
        emoji = self.LEVEL_EMOJI.get(alert.level, "📢")

        lines = [
            f"{emoji} *{alert.level.value.upper()}*: {alert.title}",
            "",
            alert.message,
        ]

        if alert.creator_id:
            lines.append(f"\n📋 Creator: `{alert.creator_id}`")

        if alert.metadata:
            lines.append("\n📊 Details:")
            for key, value in alert.metadata.items():
                lines.append(f"  • {key}: `{value}`")

        lines.append(f"\n🕐 {alert.timestamp[:19]}")

        return "\n".join(lines)

    async def send_telegram_alert(
        self,
        message: str,
        level: AlertLevel = AlertLevel.ERROR,
        title: str = "Alert",
        creator_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Enviar alerta via Telegram.

        Args:
            message: Mensaje de la alerta
            level: Nivel de alerta (info, warning, error, critical)
            title: Titulo corto
            creator_id: ID del creador afectado
            metadata: Datos adicionales

        Returns:
            True si se envio correctamente
        """
        if not self.enabled:
            logger.debug(f"Alert (disabled): [{level.value}] {title} - {message}")
            return False

        # Rate limiting
        alert_key = f"{level.value}:{title}"
        if not self._should_send(alert_key):
            logger.debug(f"Alert rate limited: {alert_key}")
            return False

        alert = Alert(
            level=level,
            title=title,
            message=message,
            creator_id=creator_id,
            metadata=metadata
        )

        formatted_message = self._format_message(alert)

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": formatted_message,
                "parse_mode": "Markdown",
                "disable_notification": level == AlertLevel.INFO
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Telegram alert sent: {title}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Telegram API error: {response.status} - {error_text}")
                        return False

        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
            return False

    # Metodos de conveniencia
    async def info(self, title: str, message: str, **kwargs):
        """Enviar alerta informativa"""
        return await self.send_telegram_alert(
            message=message,
            level=AlertLevel.INFO,
            title=title,
            **kwargs
        )

    async def warning(self, title: str, message: str, **kwargs):
        """Enviar alerta de advertencia"""
        return await self.send_telegram_alert(
            message=message,
            level=AlertLevel.WARNING,
            title=title,
            **kwargs
        )

    async def error(self, title: str, message: str, **kwargs):
        """Enviar alerta de error"""
        return await self.send_telegram_alert(
            message=message,
            level=AlertLevel.ERROR,
            title=title,
            **kwargs
        )

    async def critical(self, title: str, message: str, **kwargs):
        """Enviar alerta critica"""
        return await self.send_telegram_alert(
            message=message,
            level=AlertLevel.CRITICAL,
            title=title,
            **kwargs
        )

    # Alertas especificas del sistema
    async def alert_llm_error(
        self,
        error: str,
        creator_id: Optional[str] = None,
        provider: str = "unknown"
    ):
        """Alerta cuando falla el LLM"""
        await self.error(
            title="LLM Error",
            message=f"Error comunicando con {provider}:\n{error}",
            creator_id=creator_id,
            metadata={"provider": provider}
        )

    async def alert_rate_limit(
        self,
        creator_id: str,
        follower_id: str,
        reason: str
    ):
        """Alerta de rate limit alcanzado"""
        await self.warning(
            title="Rate Limit",
            message=f"Rate limit alcanzado para conversacion",
            creator_id=creator_id,
            metadata={
                "follower_id": follower_id,
                "reason": reason
            }
        )

    async def alert_escalation(
        self,
        creator_id: str,
        follower_id: str,
        follower_name: str,
        reason: str
    ):
        """Alerta de escalacion a humano"""
        await self.info(
            title="Escalation",
            message=f"Usuario {follower_name} requiere atencion humana:\n{reason}",
            creator_id=creator_id,
            metadata={
                "follower_id": follower_id,
                "follower_name": follower_name
            }
        )

    async def alert_health_check_failed(
        self,
        check_name: str,
        status: str,
        details: Optional[Dict] = None
    ):
        """Alerta cuando falla un health check"""
        await self.critical(
            title="Health Check Failed",
            message=f"El check '{check_name}' reporta: {status}",
            metadata=details
        )

    async def alert_exception(
        self,
        exception: Exception,
        context: str = "",
        creator_id: Optional[str] = None
    ):
        """Alerta de excepcion no manejada"""
        error_type = type(exception).__name__
        await self.error(
            title=f"Unhandled Exception: {error_type}",
            message=f"{context}\n\n{str(exception)}",
            creator_id=creator_id,
            metadata={"exception_type": error_type}
        )


# Singleton
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Obtener instancia singleton del AlertManager"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


# Funciones de conveniencia
async def send_alert(
    message: str,
    level: str = "error",
    title: str = "Alert",
    **kwargs
) -> bool:
    """Enviar alerta (funcion de conveniencia)"""
    manager = get_alert_manager()
    level_enum = AlertLevel(level) if isinstance(level, str) else level
    return await manager.send_telegram_alert(
        message=message,
        level=level_enum,
        title=title,
        **kwargs
    )


async def alert_llm_error(error: str, **kwargs):
    """Alerta de error LLM"""
    return await get_alert_manager().alert_llm_error(error, **kwargs)


async def alert_exception(exception: Exception, **kwargs):
    """Alerta de excepcion"""
    return await get_alert_manager().alert_exception(exception, **kwargs)
