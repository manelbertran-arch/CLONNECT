#!/usr/bin/env python3
"""
Rate limiting para prevenir ban de Instagram y controlar costes.
Migrado de clonnect-memory-engine y adaptado para Clonnect Creators.
"""
from typing import Dict, Tuple
import time
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter.

    Límites por defecto (conservadores para Instagram):
    - 20 requests/minuto (Instagram recomienda max 200/hora)
    - 200 requests/hora
    - 1000 requests/día

    Beneficios:
    - Previene ban de Instagram
    - Control de costes LLM
    - Fair use entre creadores
    """

    def __init__(
        self,
        requests_per_minute: int = 20,
        requests_per_hour: int = 200,
        requests_per_day: int = 1000
    ):
        self.rpm = requests_per_minute
        self.rph = requests_per_hour
        self.rpd = requests_per_day

        # Storage: key -> (tokens_minute, tokens_hour, tokens_day, last_refill)
        self.buckets: Dict[str, Tuple[float, float, float, float]] = {}

    def _get_or_create_bucket(self, key: str) -> Tuple[float, float, float, float]:
        """Get or create token bucket for key"""
        if key not in self.buckets:
            now = time.time()
            self.buckets[key] = (
                float(self.rpm),
                float(self.rph),
                float(self.rpd),
                now
            )
        return self.buckets[key]

    def _refill_tokens(self, key: str):
        """Refill tokens based on elapsed time"""
        tokens_min, tokens_hour, tokens_day, last_refill = self._get_or_create_bucket(key)
        now = time.time()
        elapsed = now - last_refill

        # Refill rates (tokens per second)
        refill_rate_min = self.rpm / 60
        refill_rate_hour = self.rph / 3600
        refill_rate_day = self.rpd / 86400

        # Add refilled tokens (capped at max)
        tokens_min = min(self.rpm, tokens_min + refill_rate_min * elapsed)
        tokens_hour = min(self.rph, tokens_hour + refill_rate_hour * elapsed)
        tokens_day = min(self.rpd, tokens_day + refill_rate_day * elapsed)

        self.buckets[key] = (tokens_min, tokens_hour, tokens_day, now)

    def check_limit(self, key: str, cost: float = 1.0) -> Tuple[bool, str]:
        """
        Check if request is allowed.

        Args:
            key: Creator ID or follower ID
            cost: Cost of this request (default: 1.0)

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        self._refill_tokens(key)
        tokens_min, tokens_hour, tokens_day, last_refill = self.buckets[key]

        if tokens_min < cost:
            logger.warning(f"Rate limit (minute) exceeded for {key[:8]}...")
            return False, f"Límite: {self.rpm} mensajes/minuto. Espera un momento."

        if tokens_hour < cost:
            logger.warning(f"Rate limit (hour) exceeded for {key[:8]}...")
            return False, f"Límite: {self.rph} mensajes/hora."

        if tokens_day < cost:
            logger.warning(f"Rate limit (day) exceeded for {key[:8]}...")
            return False, f"Límite diario alcanzado: {self.rpd} mensajes/día."

        # Consume tokens
        self.buckets[key] = (
            tokens_min - cost,
            tokens_hour - cost,
            tokens_day - cost,
            last_refill
        )

        return True, "OK"

    def get_remaining(self, key: str) -> Dict[str, float]:
        """Get remaining tokens for key"""
        self._refill_tokens(key)
        tokens_min, tokens_hour, tokens_day, _ = self.buckets[key]

        return {
            "minute": int(tokens_min),
            "hour": int(tokens_hour),
            "day": int(tokens_day)
        }

    def reset(self, key: str):
        """Reset limits for key"""
        if key in self.buckets:
            del self.buckets[key]
            logger.info(f"Rate limit reset for {key[:8]}...")

    def stats(self) -> Dict[str, any]:
        """Get rate limiter statistics"""
        return {
            "tracked_keys": len(self.buckets),
            "limits": {
                "per_minute": self.rpm,
                "per_hour": self.rph,
                "per_day": self.rpd
            }
        }


# Instancia global para usar en toda la aplicación
_rate_limiter = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
