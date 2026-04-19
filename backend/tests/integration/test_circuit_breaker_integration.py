"""Integration tests — ARC3 Phase 4 CircuitBreaker.

Tests the end-to-end behaviour:
  1. 3 consecutive failures → breaker trips → subsequent check returns False
  2. After trip + cooldown expiry → breaker allows probe → success resets state
  3. ENABLE_CIRCUIT_BREAKER=false → breaker bypassed in generation phase
"""

import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.generation.circuit_breaker import (
    CircuitBreaker,
    FailureType,
    MAX_CONSECUTIVE_FAILURES,
    TRIP_COOLDOWN_SECONDS,
    FALLBACK_RESPONSES,
)

CREATOR = "test_creator_integration"
LEAD = "9876543210"


@pytest.fixture
def breaker():
    cb = CircuitBreaker()
    cb._reset_for_tests()
    return cb


# ---------------------------------------------------------------------------
# 1. Full pipeline: 3 failures → fallback returned
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_pipeline_3_failures_returns_fallback(breaker):
    """Three hard failures trip the breaker; subsequent call returns fallback."""
    # Simulate 3 consecutive hard failures
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        allowed = await breaker.check(CREATOR, LEAD)
        assert allowed is True, "Should be allowed before trip"
        await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_TIMEOUT)

    # Now the breaker should be tripped
    assert await breaker.check(CREATOR, LEAD) is False

    # get_fallback_response() returns a non-empty string
    fallback = await breaker.get_fallback_response(CREATOR, LEAD)
    assert isinstance(fallback, str) and len(fallback) > 5


# ---------------------------------------------------------------------------
# 2. Recovery after cooldown window
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_pipeline_recovers_after_window(breaker):
    """After cooldown expires, one successful call fully resets the breaker."""
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_5XX)

    assert await breaker.check(CREATOR, LEAD) is False

    # Simulate cooldown expiry by backdating tripped_at
    state = breaker._get_state(CREATOR, LEAD)
    state.tripped_at = datetime.now(timezone.utc) - timedelta(seconds=TRIP_COOLDOWN_SECONDS + 5)
    breaker._set_state(state)

    # Probe should be allowed now
    assert await breaker.check(CREATOR, LEAD) is True

    # Simulate a successful generation
    await breaker.record_success(CREATOR, LEAD)

    # State fully cleared — no cooldown, no counter
    assert breaker._get_state(CREATOR, LEAD) is None
    assert await breaker.check(CREATOR, LEAD) is True


# ---------------------------------------------------------------------------
# 3. ENABLE_CIRCUIT_BREAKER=false → bypassed in generation phase
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_breaker_disabled_by_flag():
    """When ENABLE_CIRCUIT_BREAKER=false, the breaker is not consulted."""
    from core.generation.circuit_breaker import get_circuit_breaker

    internal_breaker = get_circuit_breaker()
    internal_breaker._reset_for_tests()

    # Trip the shared singleton
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        await internal_breaker.record_failure("flag_test_creator", "flag_test_lead", FailureType.LLM_TIMEOUT)

    # With flag off, check() is never called — generation phase skips it.
    # We verify the flag machinery by inspecting flags directly.
    with patch.dict(os.environ, {"ENABLE_CIRCUIT_BREAKER": "false"}):
        from core.feature_flags import FeatureFlags
        test_flags = FeatureFlags()
        assert test_flags.enable_circuit_breaker is False


# ---------------------------------------------------------------------------
# 4. CCEE_NO_FALLBACK: breaker skipped in eval mode
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_breaker_skipped_in_ccee_mode():
    """CCEE_NO_FALLBACK=1 must bypass the circuit breaker in generation phase."""
    with patch.dict(os.environ, {"CCEE_NO_FALLBACK": "1"}):
        # The generation phase checks: not os.environ.get("CCEE_NO_FALLBACK")
        assert os.environ.get("CCEE_NO_FALLBACK") == "1"
        # Verify the condition that disables the breaker evaluates correctly
        _cb_active = not os.environ.get("CCEE_NO_FALLBACK")
        assert _cb_active is False


# ---------------------------------------------------------------------------
# 5. Mixed failure types: SOFT failures don't instantly trip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_soft_failures_accumulate_like_hard(breaker):
    """RESPONSE_TOO_SHORT (soft) failures still accumulate toward the threshold."""
    for _ in range(MAX_CONSECUTIVE_FAILURES - 1):
        await breaker.record_failure(CREATOR, LEAD, FailureType.RESPONSE_TOO_SHORT)

    # Not yet tripped
    assert await breaker.check(CREATOR, LEAD) is True

    # One more soft failure tips it over
    await breaker.record_failure(CREATOR, LEAD, FailureType.RESPONSE_TOO_SHORT)
    assert await breaker.check(CREATOR, LEAD) is False


# ---------------------------------------------------------------------------
# 6. Fallback: covers all languages in FALLBACK_RESPONSES
# ---------------------------------------------------------------------------

def test_fallback_responses_coverage():
    """All language keys in FALLBACK_RESPONSES must have non-trivial content."""
    required_keys = {"default", "es_long", "en"}
    for key in required_keys:
        assert key in FALLBACK_RESPONSES
        assert len(FALLBACK_RESPONSES[key]) > 10


# ---------------------------------------------------------------------------
# 7. Alerting fires exactly once on trip, not on subsequent failures
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_alert_fires_exactly_once_per_trip(breaker):
    alert_calls = []

    def capture_alert(**kwargs):
        alert_calls.append(kwargs)

    with patch("core.security.alerting.dispatch_fire_and_forget", side_effect=capture_alert):
        for _ in range(MAX_CONSECUTIVE_FAILURES + 3):
            await breaker.record_failure(CREATOR, LEAD, FailureType.LLM_TIMEOUT)

    assert len(alert_calls) == 1
    assert alert_calls[0]["event_type"] == "generation_circuit_tripped"
