"""ARC3 Phase 4 — Per-(creator, lead) CircuitBreaker.

Prevents infinite retry loops when generation fails repeatedly for the same
conversation. After MAX_CONSECUTIVE_FAILURES, the breaker trips and returns
a fallback response for TRIP_COOLDOWN_SECONDS.

Design:
  * Backend: cachetools.TTLCache (no Redis dependency). State expires after
    RESET_WINDOW_SECONDS; an idle conversation auto-resets for free.
  * Fail-silent: if the breaker itself raises, it logs at WARNING and allows
    generation to proceed — the circuit never blocks healthy requests.
  * Thread-safe: a threading.Lock guards the TTLCache compound read-modify-write.
  * Alerting: uses core.security.alerting.dispatch_fire_and_forget on trip.

Usage:
    breaker = get_circuit_breaker()
    if not await breaker.check(creator_id, lead_id):
        return await breaker.get_fallback_response(creator_id, lead_id)
    try:
        result = await generate_dm_response(...)
        if is_hard_failure(result):
            await breaker.record_failure(creator_id, lead_id, FailureType.EMPTY_RESPONSE)
            return await breaker.get_fallback_response(creator_id, lead_id)
        await breaker.record_success(creator_id, lead_id)
        return result
    except SomeError as e:
        await breaker.record_failure(creator_id, lead_id, FailureType.LLM_TIMEOUT)
        return await breaker.get_fallback_response(creator_id, lead_id)
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CONSECUTIVE_FAILURES = 3
RESET_WINDOW_SECONDS = 300   # auto-reset after 5 min of no activity
TRIP_COOLDOWN_SECONDS = 60   # after trip, block for 60s then allow one probe


# ---------------------------------------------------------------------------
# Failure taxonomy (§2.4.4)
# ---------------------------------------------------------------------------

class FailureType(Enum):
    LLM_TIMEOUT = "llm_timeout"
    LLM_5XX = "llm_5xx"
    CONTENT_FILTER = "content_filter"
    JSON_PARSE_ERROR = "json_parse_error"
    EMPTY_RESPONSE = "empty_response"
    RESPONSE_TOO_SHORT = "response_too_short"
    LOOP_DETECTED = "loop_detected"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class BreakerState:
    creator_id: str
    lead_id: str
    consecutive_failures: int = 0
    last_failure_at: Optional[datetime] = None
    tripped_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Fallback responses (§2.4.3)
# ---------------------------------------------------------------------------

FALLBACK_RESPONSES: dict[str, str] = {
    "default": "Ey, te respondo en un rato que ando liado/a 🙏",
    "es_long": "Mil perdones, se me está liando el día — te escribo ahorita con calma",
    "en": "hey! i'll get back to you in a bit, bear with me 🙏",
}


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Per-(creator_id, lead_id) generation circuit breaker."""

    def __init__(self) -> None:
        # TTLCache: states expire after RESET_WINDOW_SECONDS (graceful auto-reset).
        self._cache: TTLCache = TTLCache(maxsize=10_000, ttl=RESET_WINDOW_SECONDS)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, creator_id: str, lead_id: str) -> str:
        return f"{creator_id}:{lead_id}"

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _seconds_since(self, dt: datetime) -> float:
        return (self._now() - dt).total_seconds()

    def _get_state(self, creator_id: str, lead_id: str) -> Optional[BreakerState]:
        with self._lock:
            return self._cache.get(self._key(creator_id, lead_id))

    def _set_state(self, state: BreakerState) -> None:
        with self._lock:
            self._cache[self._key(state.creator_id, state.lead_id)] = state

    def _delete_state(self, creator_id: str, lead_id: str) -> None:
        with self._lock:
            self._cache.pop(self._key(creator_id, lead_id), None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check(self, creator_id: str, lead_id: str) -> bool:
        """Return True if generation is allowed, False if circuit is tripped.

        Always returns True on internal error (fail-open).
        """
        try:
            state = self._get_state(creator_id, lead_id)
            if state is None:
                return True

            if state.tripped_at is not None:
                if self._seconds_since(state.tripped_at) < TRIP_COOLDOWN_SECONDS:
                    logger.info(
                        "[CircuitBreaker] TRIPPED creator=%s lead=%s (%.0fs remaining)",
                        creator_id, lead_id,
                        TRIP_COOLDOWN_SECONDS - self._seconds_since(state.tripped_at),
                    )
                    return False
                # Cooldown expired — allow one probe (don't reset until success)
                return True

            return state.consecutive_failures < MAX_CONSECUTIVE_FAILURES

        except Exception:
            logger.warning("[CircuitBreaker] check() failed — allowing generation", exc_info=True)
            return True

    async def record_failure(
        self,
        creator_id: str,
        lead_id: str,
        failure_type: FailureType,
    ) -> None:
        """Increment failure counter; trip the breaker if threshold is reached."""
        try:
            state = self._get_state(creator_id, lead_id)
            if state is None:
                state = BreakerState(creator_id=creator_id, lead_id=lead_id)

            state.consecutive_failures += 1
            state.last_failure_at = self._now()

            if state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES and state.tripped_at is None:
                state.tripped_at = self._now()
                logger.warning(
                    "[CircuitBreaker] TRIP creator=%s lead=%s reason=%s failures=%d",
                    creator_id, lead_id, failure_type.value, state.consecutive_failures,
                )
                self._set_state(state)
                self._dispatch_trip_alert(creator_id, lead_id, failure_type)
            else:
                self._set_state(state)
                logger.info(
                    "[CircuitBreaker] failure recorded creator=%s lead=%s failures=%d/%d reason=%s",
                    creator_id, lead_id, state.consecutive_failures,
                    MAX_CONSECUTIVE_FAILURES, failure_type.value,
                )

        except Exception:
            logger.warning("[CircuitBreaker] record_failure() failed — swallowing", exc_info=True)

    async def record_success(self, creator_id: str, lead_id: str) -> None:
        """Reset the breaker for this (creator, lead) pair."""
        try:
            self._delete_state(creator_id, lead_id)
        except Exception:
            logger.warning("[CircuitBreaker] record_success() failed — swallowing", exc_info=True)

    async def get_fallback_response(self, creator_id: str, lead_id: str) -> str:
        """Return a human-sounding fallback response (no LLM needed).

        Language detection is best-effort; defaults to Spanish on any failure.
        """
        try:
            lang = await self._detect_language(creator_id, lead_id)
            return FALLBACK_RESPONSES.get(lang, FALLBACK_RESPONSES["default"])
        except Exception:
            return FALLBACK_RESPONSES["default"]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _detect_language(self, creator_id: str, lead_id: str) -> str:  # noqa: ARG002
        """Detect preferred language for fallback; defaults to 'default' (es)."""
        return "default"

    def _dispatch_trip_alert(
        self,
        creator_id: str,
        lead_id: str,
        failure_type: FailureType,
    ) -> None:
        """Fire-and-forget alerting — never raises."""
        try:
            from core.security.alerting import dispatch_fire_and_forget
            dispatch_fire_and_forget(
                creator_id=creator_id,
                sender_id=lead_id,
                event_type="generation_circuit_tripped",
                content=None,
                severity="WARNING",
                metadata={
                    "failure_type": failure_type.value,
                    "max_consecutive_failures": MAX_CONSECUTIVE_FAILURES,
                    "trip_cooldown_seconds": TRIP_COOLDOWN_SECONDS,
                },
            )
        except Exception:
            logger.debug("[CircuitBreaker] alert dispatch failed — swallowing", exc_info=True)

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def _reset_for_tests(self) -> None:
        """Clear all state. Test-only."""
        with self._lock:
            self._cache.clear()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_circuit_breaker: Optional[CircuitBreaker] = None
_singleton_lock = threading.Lock()


def get_circuit_breaker() -> CircuitBreaker:
    """Return the process-level CircuitBreaker singleton."""
    global _circuit_breaker
    if _circuit_breaker is None:
        with _singleton_lock:
            if _circuit_breaker is None:
                _circuit_breaker = CircuitBreaker()
    return _circuit_breaker
