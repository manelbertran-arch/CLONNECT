#!/usr/bin/env python3
"""
Instagram API Rate Limiter - Prevención de rate limits de Meta.

3 Capas de protección:
1. RECUPERACIÓN: Backoff exponencial cuando Meta nos bloquea
2. PREVENCIÓN: Limitar llamadas ANTES de que Meta nos bloquee
3. OPTIMIZACIÓN: Tracking para sync incremental

Límites de Meta (conservadores):
- 200 llamadas/hora por token
- 4800 llamadas/día por token
"""

import time
import asyncio
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class APICallRecord:
    """Registro de una llamada a la API"""
    timestamp: float
    endpoint: str
    response_code: int = 200
    creator_id: str = ""


@dataclass
class RateLimitState:
    """Estado del rate limiter para un creator"""
    calls_minute: list = field(default_factory=list)
    calls_hour: list = field(default_factory=list)
    calls_day: list = field(default_factory=list)
    last_error_time: float = 0
    consecutive_errors: int = 0
    backoff_until: float = 0


class InstagramRateLimiter:
    """
    Rate limiter específico para Instagram/Meta API.

    Características:
    - Prevención: Bloquea ANTES de alcanzar límites de Meta
    - Backoff: Espera exponencial cuando hay errores
    - Tracking: Registra todas las llamadas para análisis
    """

    # Límites conservadores (Meta permite más, pero mejor prevenir)
    CALLS_PER_MINUTE = 10   # Muy conservador
    CALLS_PER_HOUR = 150    # Meta permite ~200
    CALLS_PER_DAY = 3000    # Meta permite ~4800

    # Backoff exponencial
    INITIAL_BACKOFF_SECONDS = 5
    MAX_BACKOFF_SECONDS = 300  # 5 minutos máximo
    BACKOFF_MULTIPLIER = 2

    # Errores que indican rate limit
    RATE_LIMIT_CODES = {429, 503, 190, 4, 17, 32, 613}

    def __init__(self):
        # Estado por creator_id
        self._states: Dict[str, RateLimitState] = defaultdict(RateLimitState)
        # Historial global de llamadas (últimas 24h)
        self._call_history: list = []
        # Lock para thread safety
        self._lock = asyncio.Lock()

    def _clean_old_calls(self, state: RateLimitState):
        """Limpiar llamadas antiguas de los contadores"""
        now = time.time()
        minute_ago = now - 60
        hour_ago = now - 3600
        day_ago = now - 86400

        state.calls_minute = [t for t in state.calls_minute if t > minute_ago]
        state.calls_hour = [t for t in state.calls_hour if t > hour_ago]
        state.calls_day = [t for t in state.calls_day if t > day_ago]

    def can_make_request(self, creator_id: str) -> Tuple[bool, str, int]:
        """
        Verificar si se puede hacer una llamada a la API.

        Returns:
            Tuple de (allowed, reason, wait_seconds)
        """
        state = self._states[creator_id]
        self._clean_old_calls(state)
        now = time.time()

        # 1. Verificar backoff activo
        if state.backoff_until > now:
            wait = int(state.backoff_until - now)
            return False, f"Backoff activo ({state.consecutive_errors} errores)", wait

        # 2. Verificar límite por minuto
        if len(state.calls_minute) >= self.CALLS_PER_MINUTE:
            return False, f"Límite/minuto alcanzado ({self.CALLS_PER_MINUTE})", 60

        # 3. Verificar límite por hora
        if len(state.calls_hour) >= self.CALLS_PER_HOUR:
            oldest_call = min(state.calls_hour) if state.calls_hour else now
            wait = int(3600 - (now - oldest_call))
            return False, f"Límite/hora alcanzado ({self.CALLS_PER_HOUR})", max(1, wait)

        # 4. Verificar límite por día
        if len(state.calls_day) >= self.CALLS_PER_DAY:
            oldest_call = min(state.calls_day) if state.calls_day else now
            wait = int(86400 - (now - oldest_call))
            return False, f"Límite/día alcanzado ({self.CALLS_PER_DAY})", max(1, wait)

        return True, "OK", 0

    async def wait_if_needed(self, creator_id: str) -> int:
        """
        Esperar si es necesario antes de hacer una llamada.

        Returns:
            Segundos que se esperó (0 si no fue necesario)
        """
        allowed, reason, wait = self.can_make_request(creator_id)

        if not allowed and wait > 0:
            logger.warning(f"[RateLimit] {creator_id}: {reason}. Esperando {wait}s...")
            await asyncio.sleep(min(wait, 60))  # Máximo 60s de espera por llamada
            return wait

        return 0

    def record_call(self, creator_id: str, endpoint: str, response_code: int = 200):
        """
        Registrar una llamada a la API.

        Args:
            creator_id: ID del creator
            endpoint: Endpoint llamado (ej: "/conversations")
            response_code: Código de respuesta HTTP
        """
        now = time.time()
        state = self._states[creator_id]

        # Registrar la llamada
        state.calls_minute.append(now)
        state.calls_hour.append(now)
        state.calls_day.append(now)

        # Guardar en historial global
        self._call_history.append(APICallRecord(
            timestamp=now,
            endpoint=endpoint,
            response_code=response_code,
            creator_id=creator_id
        ))

        # Limpiar historial viejo (>24h)
        day_ago = now - 86400
        self._call_history = [c for c in self._call_history if c.timestamp > day_ago]

        # Manejar errores
        if response_code in self.RATE_LIMIT_CODES or response_code >= 400:
            self._handle_error(state, response_code)
        else:
            # Reset errores consecutivos en éxito
            if state.consecutive_errors > 0:
                logger.info(f"[RateLimit] {creator_id}: Recuperado después de {state.consecutive_errors} errores")
            state.consecutive_errors = 0
            state.backoff_until = 0

    def _handle_error(self, state: RateLimitState, response_code: int):
        """Manejar error de API con backoff exponencial"""
        state.consecutive_errors += 1
        state.last_error_time = time.time()

        # Calcular backoff exponencial
        backoff = min(
            self.INITIAL_BACKOFF_SECONDS * (self.BACKOFF_MULTIPLIER ** (state.consecutive_errors - 1)),
            self.MAX_BACKOFF_SECONDS
        )

        state.backoff_until = time.time() + backoff

        logger.warning(
            f"[RateLimit] Error {response_code}. "
            f"Errores consecutivos: {state.consecutive_errors}. "
            f"Backoff: {backoff}s"
        )

    def get_stats(self, creator_id: str = None) -> Dict:
        """
        Obtener estadísticas de rate limiting.

        Args:
            creator_id: Si se especifica, stats de ese creator. Si no, globales.
        """
        if creator_id:
            state = self._states[creator_id]
            self._clean_old_calls(state)
            return {
                "creator_id": creator_id,
                "calls_last_minute": len(state.calls_minute),
                "calls_last_hour": len(state.calls_hour),
                "calls_last_day": len(state.calls_day),
                "remaining_minute": self.CALLS_PER_MINUTE - len(state.calls_minute),
                "remaining_hour": self.CALLS_PER_HOUR - len(state.calls_hour),
                "remaining_day": self.CALLS_PER_DAY - len(state.calls_day),
                "consecutive_errors": state.consecutive_errors,
                "backoff_active": state.backoff_until > time.time(),
                "backoff_remaining": max(0, int(state.backoff_until - time.time())),
            }
        else:
            # Stats globales
            now = time.time()
            minute_ago = now - 60
            hour_ago = now - 3600

            calls_minute = len([c for c in self._call_history if c.timestamp > minute_ago])
            calls_hour = len([c for c in self._call_history if c.timestamp > hour_ago])
            calls_day = len(self._call_history)

            return {
                "total_creators": len(self._states),
                "calls_last_minute": calls_minute,
                "calls_last_hour": calls_hour,
                "calls_last_day": calls_day,
                "limits": {
                    "per_minute": self.CALLS_PER_MINUTE,
                    "per_hour": self.CALLS_PER_HOUR,
                    "per_day": self.CALLS_PER_DAY,
                }
            }

    def get_call_history(self, creator_id: str = None, hours: int = 1) -> list:
        """
        Obtener historial de llamadas.

        Args:
            creator_id: Filtrar por creator (opcional)
            hours: Últimas N horas
        """
        cutoff = time.time() - (hours * 3600)
        calls = [c for c in self._call_history if c.timestamp > cutoff]

        if creator_id:
            calls = [c for c in calls if c.creator_id == creator_id]

        return [
            {
                "timestamp": datetime.fromtimestamp(c.timestamp, tz=timezone.utc).isoformat(),
                "endpoint": c.endpoint,
                "response_code": c.response_code,
                "creator_id": c.creator_id,
            }
            for c in calls
        ]


# Singleton global
_instagram_rate_limiter: Optional[InstagramRateLimiter] = None


def get_instagram_rate_limiter() -> InstagramRateLimiter:
    """Obtener instancia global del rate limiter de Instagram"""
    global _instagram_rate_limiter
    if _instagram_rate_limiter is None:
        _instagram_rate_limiter = InstagramRateLimiter()
    return _instagram_rate_limiter
