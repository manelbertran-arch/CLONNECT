"""Unit tests for ARC3 Phase 4 — core/generation/circuit_breaker.py."""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.generation.circuit_breaker import (
    BreakerState,
    CircuitBreaker,
    FailureType,
    FALLBACK_RESPONSES,
    MAX_CONSECUTIVE_FAILURES,
    TRIP_COOLDOWN_SECONDS,
    RESET_WINDOW_SECONDS,
    get_circuit_breaker,
)

CREATOR = "iris_bertran"
LEAD = "1234567890"


@pytest.fixture
def breaker():
    cb = CircuitBreaker()
    cb._reset_for_tests()
    return cb


# ---------------------------------------------------------------------------
# check() — no state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_returns_true_when_no_state(breaker):
    assert await breaker.check(CREATOR, LEAD) is True


# ---------------------------------------------------------------------------
# check() — below threshold
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_returns_true_under_threshold(breaker):
    await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_TIMEOUT)
    await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_TIMEOUT)
    # 2 failures < MAX_CONSECUTIVE_FAILURES (3)
    assert await breaker.check(CREATOR, LEAD) is True


# ---------------------------------------------------------------------------
# check() — tripped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_returns_false_when_tripped(breaker):
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_TIMEOUT)
    assert await breaker.check(CREATOR, LEAD) is False


# ---------------------------------------------------------------------------
# check() — cooldown expired allows probe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_allows_probe_after_cooldown(breaker):
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_TIMEOUT)

    # Backdate tripped_at to simulate cooldown expiry
    state = breaker._get_state(CREATOR, LEAD)
    state.tripped_at = datetime.now(timezone.utc) - timedelta(seconds=TRIP_COOLDOWN_SECONDS + 1)
    breaker._set_state(state)

    assert await breaker.check(CREATOR, LEAD) is True


# ---------------------------------------------------------------------------
# record_failure() — increments counter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_failure_increments_counter(breaker):
    await breaker.record_failure(CREATOR, LEAD, FailureType.EMPTY_RESPONSE)
    state = breaker._get_state(CREATOR, LEAD)
    assert state is not None
    assert state.consecutive_failures == 1
    assert state.last_failure_at is not None


# ---------------------------------------------------------------------------
# record_failure() — trips at threshold
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_failure_trips_at_threshold(breaker):
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_TIMEOUT)

    state = breaker._get_state(CREATOR, LEAD)
    assert state is not None
    assert state.tripped_at is not None
    assert state.consecutive_failures == MAX_CONSECUTIVE_FAILURES


# ---------------------------------------------------------------------------
# record_failure() — alert fired on trip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_failure_sends_alert_on_trip(breaker):
    with patch("core.generation.circuit_breaker.CircuitBreaker._dispatch_trip_alert") as mock_alert:
        for _ in range(MAX_CONSECUTIVE_FAILURES):
            await breaker.record_failure(CREATOR, LEAD, FailureType.CONTENT_FILTER)

        mock_alert.assert_called_once_with(CREATOR, LEAD, FailureType.CONTENT_FILTER)


# ---------------------------------------------------------------------------
# record_failure() — alert fires only once (no duplicate on 4th failure)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_failure_alert_fires_only_once(breaker):
    with patch("core.generation.circuit_breaker.CircuitBreaker._dispatch_trip_alert") as mock_alert:
        for _ in range(MAX_CONSECUTIVE_FAILURES + 2):
            await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_TIMEOUT)

        assert mock_alert.call_count == 1


# ---------------------------------------------------------------------------
# record_success() — resets state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_success_resets_state(breaker):
    await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_TIMEOUT)
    await breaker.record_success(CREATOR, LEAD)

    state = breaker._get_state(CREATOR, LEAD)
    assert state is None
    assert await breaker.check(CREATOR, LEAD) is True


# ---------------------------------------------------------------------------
# record_success() — resets even after trip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_success_resets_after_trip(breaker):
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_TIMEOUT)

    await breaker.record_success(CREATOR, LEAD)
    assert await breaker.check(CREATOR, LEAD) is True


# ---------------------------------------------------------------------------
# Cooldown respected — no probe during cooldown window
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cooldown_respected_after_trip(breaker):
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_5XX)

    # Immediately after trip — cooldown not expired
    assert await breaker.check(CREATOR, LEAD) is False

    # Partial cooldown — still blocked
    state = breaker._get_state(CREATOR, LEAD)
    state.tripped_at = datetime.now(timezone.utc) - timedelta(seconds=TRIP_COOLDOWN_SECONDS - 5)
    breaker._set_state(state)

    assert await breaker.check(CREATOR, LEAD) is False


# ---------------------------------------------------------------------------
# Fallback responses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_response_returns_default(breaker):
    text = await breaker.get_fallback_response(CREATOR, LEAD)
    assert text == FALLBACK_RESPONSES["default"]
    assert len(text) > 5


@pytest.mark.asyncio
async def test_fallback_response_non_empty_for_all_keys(breaker):
    for lang, response in FALLBACK_RESPONSES.items():
        assert len(response) > 5, f"fallback response for '{lang}' is too short"


# ---------------------------------------------------------------------------
# Fail-silent: internal errors never raise
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_fail_silent_on_cache_error(breaker):
    with patch.object(breaker, "_get_state", side_effect=RuntimeError("cache down")):
        # Should not raise — returns True (fail-open)
        result = await breaker.check(CREATOR, LEAD)
        assert result is True


@pytest.mark.asyncio
async def test_record_failure_fail_silent_on_cache_error(breaker):
    with patch.object(breaker, "_get_state", side_effect=RuntimeError("cache down")):
        # Should not raise
        await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_TIMEOUT)


@pytest.mark.asyncio
async def test_record_success_fail_silent_on_cache_error(breaker):
    with patch.object(breaker, "_delete_state", side_effect=RuntimeError("cache down")):
        # Should not raise
        await breaker.record_success(CREATOR, LEAD)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

def test_get_circuit_breaker_returns_singleton():
    cb1 = get_circuit_breaker()
    cb2 = get_circuit_breaker()
    assert cb1 is cb2


# ---------------------------------------------------------------------------
# Different (creator, lead) pairs are isolated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_different_leads_are_isolated(breaker):
    lead_a = "111"
    lead_b = "222"

    for _ in range(MAX_CONSECUTIVE_FAILURES):
        await breaker.record_failure(CREATOR, lead_a, FailureType.LLM_TIMEOUT)

    # lead_a should be blocked
    assert await breaker.check(CREATOR, lead_a) is False
    # lead_b should be unaffected
    assert await breaker.check(CREATOR, lead_b) is True


@pytest.mark.asyncio
async def test_different_creators_are_isolated(breaker):
    creator_a = "iris_bertran"
    creator_b = "stefano_xyz"

    for _ in range(MAX_CONSECUTIVE_FAILURES):
        await breaker.record_failure(creator_a, LEAD, FailureType.LLM_TIMEOUT)

    assert await breaker.check(creator_a, LEAD) is False
    assert await breaker.check(creator_b, LEAD) is True


# ---------------------------------------------------------------------------
# FailureType enum completeness
# ---------------------------------------------------------------------------

def test_failure_type_values():
    expected = {
        "LLM_TIMEOUT", "LLM_5XX", "CONTENT_FILTER",
        "JSON_PARSE_ERROR", "EMPTY_RESPONSE", "RESPONSE_TOO_SHORT", "LOOP_DETECTED",
    }
    actual = {f.name for f in FailureType}
    assert actual == expected


# ---------------------------------------------------------------------------
# _dispatch_trip_alert — uses alerting module
# ---------------------------------------------------------------------------

def test_dispatch_trip_alert_calls_alerting(breaker):
    with patch("core.security.alerting.dispatch_fire_and_forget") as mock_dispatch:
        breaker._dispatch_trip_alert(CREATOR, LEAD, FailureType.JSON_PARSE_ERROR)
        mock_dispatch.assert_called_once()
        call_kwargs = mock_dispatch.call_args.kwargs
        assert call_kwargs["creator_id"] == CREATOR
        assert call_kwargs["sender_id"] == LEAD
        assert call_kwargs["event_type"] == "generation_circuit_tripped"
        assert call_kwargs["severity"] == "WARNING"


def test_dispatch_trip_alert_fail_silent_on_import_error(breaker):
    with patch("core.security.alerting.dispatch_fire_and_forget", side_effect=Exception("boom")):
        # Should not raise
        breaker._dispatch_trip_alert(CREATOR, LEAD, FailureType.LLM_TIMEOUT)
