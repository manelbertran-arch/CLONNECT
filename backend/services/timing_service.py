"""
TimingService - Gestiona el timing de respuestas para parecer humano.

Features:
- Delay mínimo de 2 segundos
- Delay proporcional a longitud de respuesta
- Horarios de actividad (8am-11pm)
- Variación aleatoria para naturalidad
"""
import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import pytz


@dataclass
class TimingConfig:
    """Configuración de timing."""

    min_delay: float = 2.0  # Segundos mínimos antes de responder
    max_delay: float = 30.0  # Máximo delay
    chars_per_second: float = 50.0  # Velocidad de "escritura" simulada
    reading_speed: float = 200.0  # Chars por segundo de "lectura"
    variation_pct: float = 0.2  # ±20% variación aleatoria

    # Horarios activos (hora local)
    active_hours_start: int = 8  # 8am
    active_hours_end: int = 23  # 11pm
    timezone: str = "Europe/Madrid"

    # Probabilidad de responder fuera de horario
    off_hours_response_chance: float = 0.1  # 10% chance


class TimingService:
    """Servicio para gestionar el timing de respuestas."""

    def __init__(self, config: TimingConfig = None):
        self.config = config or TimingConfig()

    def calculate_delay(self, response_length: int, message_length: int = 0) -> float:
        """
        Calcula delay natural basado en longitud.

        Simula:
        - Tiempo de lectura del mensaje
        - Tiempo de "pensar"
        - Tiempo de escribir la respuesta
        """
        # Base: 1-3 segundos de "pensar"
        think_time = random.uniform(1.0, 3.0)

        # Tiempo de lectura (mensaje del usuario)
        reading_time = message_length / self.config.reading_speed

        # Tiempo de escritura (respuesta)
        typing_time = response_length / self.config.chars_per_second

        # Total
        total = think_time + reading_time + typing_time

        # Añadir variación aleatoria
        variation = random.uniform(
            1 - self.config.variation_pct, 1 + self.config.variation_pct
        )
        total *= variation

        # Aplicar límites
        total = max(self.config.min_delay, min(total, self.config.max_delay))

        return round(total, 1)

    def is_active_hours(self, timezone: str = None) -> bool:
        """Verifica si estamos en horario activo."""
        tz = pytz.timezone(timezone or self.config.timezone)
        now = datetime.now(tz)
        hour = now.hour

        return self.config.active_hours_start <= hour < self.config.active_hours_end

    def should_respond_off_hours(self) -> bool:
        """Decide si responder fuera de horario (10% chance)."""
        return random.random() < self.config.off_hours_response_chance

    def get_next_active_time(self, timezone: str = None) -> datetime:
        """Obtiene la próxima hora activa."""
        tz = pytz.timezone(timezone or self.config.timezone)
        now = datetime.now(tz)

        if now.hour < self.config.active_hours_start:
            # Hoy más tarde
            return now.replace(
                hour=self.config.active_hours_start, minute=0, second=0
            )
        else:
            # Mañana
            tomorrow = now + timedelta(days=1)
            return tomorrow.replace(
                hour=self.config.active_hours_start, minute=0, second=0
            )

    async def wait_before_response(
        self, response_length: int, message_length: int = 0
    ):
        """Espera el delay calculado antes de responder."""
        delay = self.calculate_delay(response_length, message_length)
        await asyncio.sleep(delay)
        return delay

    def get_delay_for_response(self, response: str, message: str = "") -> float:
        """Obtiene el delay para una respuesta específica."""
        return self.calculate_delay(len(response), len(message))

    def should_delay_response(self) -> bool:
        """
        Determina si debe aplicar delay.

        En producción, siempre True. Útil para tests.
        """
        return True

    def format_wait_message(self) -> Optional[str]:
        """
        Mensaje para cuando está fuera de horario.

        Returns:
            None si debe responder, mensaje si debe esperar.
        """
        if self.is_active_hours():
            return None

        if self.should_respond_off_hours():
            return None

        return "Ahora no estoy disponible. Te respondo mañana! 😊"


# Singleton
_timing_service: Optional[TimingService] = None


def get_timing_service() -> TimingService:
    """Obtiene la instancia global del servicio de timing."""
    global _timing_service
    if _timing_service is None:
        _timing_service = TimingService()
    return _timing_service
