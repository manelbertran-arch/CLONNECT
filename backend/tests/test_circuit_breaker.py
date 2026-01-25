"""
Tests for Circuit Breaker implementation in scrapers.

Verifies that:
1. Circuit breaker opens after FAILURE_THRESHOLD consecutive failures
2. Circuit breaker rejects requests when open
3. Circuit breaker transitions to half-open after RECOVERY_TIMEOUT
4. Circuit breaker closes on successful request in half-open state
5. Auth errors don't count toward circuit breaker failures

Run with: pytest tests/test_circuit_breaker.py -v
"""

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pybreaker
import pytest


class TestCircuitBreakerConfiguration:
    """Tests for circuit breaker configuration constants."""

    def test_instagram_circuit_failure_threshold_default(self):
        """Verify default failure threshold is 5."""
        import importlib
        import ingestion.instagram_scraper as ig_module

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CIRCUIT_FAILURE_THRESHOLD", None)
            importlib.reload(ig_module)

            assert ig_module.CIRCUIT_FAILURE_THRESHOLD == 5

    def test_instagram_circuit_recovery_timeout_default(self):
        """Verify default recovery timeout is 60 seconds."""
        import importlib
        import ingestion.instagram_scraper as ig_module

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CIRCUIT_RECOVERY_TIMEOUT", None)
            importlib.reload(ig_module)

            assert ig_module.CIRCUIT_RECOVERY_TIMEOUT == 60

    def test_scraper_circuit_failure_threshold_default(self):
        """Verify default scraper failure threshold is 5."""
        import importlib
        import ingestion.deterministic_scraper as scraper_module

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SCRAPER_CIRCUIT_FAILURE_THRESHOLD", None)
            importlib.reload(scraper_module)

            assert scraper_module.SCRAPER_CIRCUIT_FAILURE_THRESHOLD == 5

    def test_circuit_configurable_via_env(self):
        """Verify circuit breaker is configurable via environment variables."""
        import importlib
        import ingestion.instagram_scraper as ig_module

        with patch.dict(os.environ, {
            "CIRCUIT_FAILURE_THRESHOLD": "10",
            "CIRCUIT_RECOVERY_TIMEOUT": "120"
        }):
            importlib.reload(ig_module)

            assert ig_module.CIRCUIT_FAILURE_THRESHOLD == 10
            assert ig_module.CIRCUIT_RECOVERY_TIMEOUT == 120

        # Restore defaults
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CIRCUIT_FAILURE_THRESHOLD", None)
            os.environ.pop("CIRCUIT_RECOVERY_TIMEOUT", None)
            importlib.reload(ig_module)


class TestCircuitBreakerOpenError:
    """Tests for CircuitBreakerOpenError exception."""

    def test_circuit_breaker_open_error_exists(self):
        """Verify CircuitBreakerOpenError is defined."""
        from ingestion.instagram_scraper import CircuitBreakerOpenError, InstagramScraperError

        error = CircuitBreakerOpenError("Circuit is open")
        assert isinstance(error, InstagramScraperError)
        assert "Circuit is open" in str(error)

    def test_scraper_circuit_breaker_open_error_exists(self):
        """Verify ScraperCircuitBreakerOpenError is defined."""
        from ingestion.deterministic_scraper import ScraperCircuitBreakerOpenError

        error = ScraperCircuitBreakerOpenError("Scraper circuit is open")
        assert "Scraper circuit is open" in str(error)


class TestInstagramCircuitBreaker:
    """Tests for Instagram API circuit breaker behavior."""

    @pytest.fixture(autouse=True)
    def reset_circuit_breaker(self):
        """Reset circuit breaker before each test."""
        from ingestion.instagram_scraper import instagram_circuit_breaker
        instagram_circuit_breaker.close()
        yield
        instagram_circuit_breaker.close()

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold_failures(self):
        """Verify circuit opens after FAILURE_THRESHOLD consecutive failures."""
        from ingestion.instagram_scraper import (
            MetaGraphAPIScraper,
            instagram_circuit_breaker,
            CircuitBreakerOpenError,
            CIRCUIT_FAILURE_THRESHOLD
        )

        scraper = MetaGraphAPIScraper(
            access_token="test_token",
            instagram_business_id="test_id"
        )

        # Make the API always fail with server error
        async def always_fail(*args, **kwargs):
            return MagicMock(status_code=500, text="Server Error")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = always_fail
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            # Fail enough times to open the circuit
            for i in range(CIRCUIT_FAILURE_THRESHOLD):
                try:
                    await scraper.get_posts(limit=10)
                except Exception:
                    pass

            # Circuit should now be open
            assert instagram_circuit_breaker.current_state == pybreaker.STATE_OPEN

            # Next call should raise CircuitBreakerOpenError
            with pytest.raises(CircuitBreakerOpenError):
                await scraper.get_posts(limit=10)

    @pytest.mark.asyncio
    async def test_auth_errors_excluded_from_circuit(self):
        """Verify AuthenticationError doesn't count toward circuit failures."""
        from ingestion.instagram_scraper import (
            MetaGraphAPIScraper,
            instagram_circuit_breaker,
            AuthenticationError,
            CIRCUIT_FAILURE_THRESHOLD
        )

        scraper = MetaGraphAPIScraper(
            access_token="invalid_token",
            instagram_business_id="test_id"
        )

        # Make the API always fail with 401
        async def always_401(*args, **kwargs):
            return MagicMock(status_code=401, text="Unauthorized")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = always_401
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            # Fail many times with auth error
            for i in range(CIRCUIT_FAILURE_THRESHOLD + 5):
                try:
                    await scraper.get_posts(limit=10)
                except AuthenticationError:
                    pass

            # Circuit should still be CLOSED (auth errors excluded)
            assert instagram_circuit_breaker.current_state == pybreaker.STATE_CLOSED

    @pytest.mark.asyncio
    async def test_successful_request_resets_failure_count(self):
        """Verify successful request resets failure counter."""
        from ingestion.instagram_scraper import (
            MetaGraphAPIScraper,
            instagram_circuit_breaker,
            CIRCUIT_FAILURE_THRESHOLD
        )

        scraper = MetaGraphAPIScraper(
            access_token="test_token",
            instagram_business_id="test_id"
        )

        call_count = 0

        async def fail_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:  # Fail first 3 times
                return MagicMock(status_code=500, text="Server Error")
            return MagicMock(
                status_code=200,
                json=lambda: {"data": []}
            )

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = fail_then_succeed
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            # Fail 3 times
            for i in range(3):
                try:
                    await scraper.get_posts(limit=10)
                except Exception:
                    pass

            # Should have 3 failures but circuit still closed
            assert instagram_circuit_breaker.fail_counter <= 3
            assert instagram_circuit_breaker.current_state == pybreaker.STATE_CLOSED

            # Succeed once
            await scraper.get_posts(limit=10)

            # Failure counter should be reset
            assert instagram_circuit_breaker.fail_counter == 0


class TestScraperCircuitBreaker:
    """Tests for website scraper circuit breaker behavior."""

    @pytest.fixture(autouse=True)
    def reset_circuit_breaker(self):
        """Reset circuit breaker before each test."""
        from ingestion.deterministic_scraper import scraper_circuit_breaker
        scraper_circuit_breaker.close()
        yield
        scraper_circuit_breaker.close()

    @pytest.mark.asyncio
    async def test_scraper_circuit_opens_after_failures(self):
        """Verify scraper circuit opens after consecutive failures."""
        from ingestion.deterministic_scraper import (
            DeterministicScraper,
            scraper_circuit_breaker,
            SCRAPER_CIRCUIT_FAILURE_THRESHOLD
        )

        scraper = DeterministicScraper(max_pages=10)

        # Make all requests fail with server error
        async def always_500(*args, **kwargs):
            return MagicMock(status_code=500)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = always_500
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            # Fail enough times to open the circuit
            for i in range(SCRAPER_CIRCUIT_FAILURE_THRESHOLD):
                await scraper.scrape_page(f"https://example.com/page{i}")

            # Circuit should now be open
            assert scraper_circuit_breaker.current_state == pybreaker.STATE_OPEN

    @pytest.mark.asyncio
    async def test_rate_limit_trips_circuit(self):
        """Verify 429 rate limit responses trip the circuit breaker."""
        from ingestion.deterministic_scraper import (
            DeterministicScraper,
            scraper_circuit_breaker,
            SCRAPER_CIRCUIT_FAILURE_THRESHOLD
        )

        scraper = DeterministicScraper(max_pages=10)

        # Make all requests return 429
        async def always_429(*args, **kwargs):
            return MagicMock(status_code=429)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = always_429
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            # Fail with rate limit
            for i in range(SCRAPER_CIRCUIT_FAILURE_THRESHOLD):
                await scraper.scrape_page(f"https://example.com/page{i}")

            # Circuit should be open
            assert scraper_circuit_breaker.current_state == pybreaker.STATE_OPEN

    @pytest.mark.asyncio
    async def test_scraper_returns_none_when_circuit_open(self):
        """Verify scraper returns None gracefully when circuit is open."""
        from ingestion.deterministic_scraper import (
            DeterministicScraper,
            scraper_circuit_breaker,
            SCRAPER_CIRCUIT_FAILURE_THRESHOLD
        )

        scraper = DeterministicScraper(max_pages=10)

        # Make all requests fail
        async def always_500(*args, **kwargs):
            return MagicMock(status_code=500)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = always_500
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            # Open the circuit
            for i in range(SCRAPER_CIRCUIT_FAILURE_THRESHOLD):
                await scraper.scrape_page(f"https://example.com/page{i}")

            # Next request should return None (not raise exception)
            result = await scraper.scrape_page("https://example.com/new-page")
            assert result is None


class TestCircuitBreakerStateTransitions:
    """Tests for circuit breaker state transitions."""

    def test_circuit_starts_closed(self):
        """Verify circuit breaker starts in closed state."""
        cb = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=10)
        assert cb.current_state == pybreaker.STATE_CLOSED

    def test_circuit_transitions_to_half_open(self):
        """Verify circuit transitions to half-open after recovery timeout."""
        cb = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=0.1)  # 100ms timeout

        # Open the circuit
        for _ in range(2):
            try:
                cb.call(lambda: 1/0)
            except ZeroDivisionError:
                pass

        assert cb.current_state == pybreaker.STATE_OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Circuit should be half-open now
        assert cb.current_state == pybreaker.STATE_HALF_OPEN

    def test_circuit_closes_on_success_in_half_open(self):
        """Verify circuit closes on successful call in half-open state."""
        cb = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=0.1)

        # Open the circuit
        for _ in range(2):
            try:
                cb.call(lambda: 1/0)
            except ZeroDivisionError:
                pass

        # Wait for half-open
        time.sleep(0.15)

        # Successful call should close the circuit
        result = cb.call(lambda: "success")
        assert result == "success"
        assert cb.current_state == pybreaker.STATE_CLOSED

    def test_circuit_reopens_on_failure_in_half_open(self):
        """Verify circuit reopens on failure in half-open state."""
        cb = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=0.1)

        # Open the circuit
        for _ in range(2):
            try:
                cb.call(lambda: 1/0)
            except ZeroDivisionError:
                pass

        # Wait for half-open
        time.sleep(0.15)

        # Fail again in half-open
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass

        # Should be back to open
        assert cb.current_state == pybreaker.STATE_OPEN


class TestCircuitBreakerListener:
    """Tests for circuit breaker listener logging."""

    def test_listener_logs_state_change(self):
        """Verify listener logs state changes."""
        from ingestion.instagram_scraper import CircuitBreakerListener

        listener = CircuitBreakerListener("test")
        cb = MagicMock()
        cb.reset_timeout = 60

        with patch("ingestion.instagram_scraper.logger") as mock_logger:
            listener.state_change(cb, pybreaker.STATE_CLOSED, pybreaker.STATE_OPEN)
            mock_logger.warning.assert_called()
            mock_logger.error.assert_called()

    def test_listener_logs_failures(self):
        """Verify listener logs failures."""
        from ingestion.instagram_scraper import CircuitBreakerListener

        listener = CircuitBreakerListener("test")
        cb = MagicMock()
        cb.fail_counter = 3
        cb.fail_max = 5

        with patch("ingestion.instagram_scraper.logger") as mock_logger:
            listener.failure(cb, Exception("test error"))
            mock_logger.debug.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
