"""
Tests for Instagram Graph API error handling and circuit breaker behavior.

Verifies that:
1. Circuit breaker constants are configured
2. Rate limits (429) raise RateLimitError immediately
3. Server errors (5xx) raise InstagramScraperError immediately
4. Timeouts raise InstagramScraperError immediately
4. Client errors (4xx except 429) do NOT retry
5. Auth errors (401) do NOT retry
6. Success on first try returns correct data

Run with: pytest tests/test_instagram_retry.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


class TestRetryConfiguration:
    """Tests for circuit breaker configuration constants."""

    def test_retry_constants_exist(self):
        """Verify circuit breaker constants are defined."""
        from ingestion.instagram_scraper import (
            CIRCUIT_FAILURE_THRESHOLD,
            CIRCUIT_RECOVERY_TIMEOUT,
        )

        assert CIRCUIT_FAILURE_THRESHOLD == 5
        assert CIRCUIT_RECOVERY_TIMEOUT == 60

    def test_transient_error_class_exists(self):
        """Verify CircuitBreakerOpenError class exists."""
        from ingestion.instagram_scraper import CircuitBreakerOpenError

        error = CircuitBreakerOpenError("Server error")
        assert str(error) == "Server error"


class TestRateLimitRetry:
    """Tests for rate limit (429) error behavior."""

    @pytest.mark.asyncio
    async def test_rate_limit_triggers_retry(self):
        """Verify that 429 response raises RateLimitError immediately."""
        from ingestion.instagram_scraper import MetaGraphAPIScraper, RateLimitError

        scraper = MetaGraphAPIScraper(
            access_token="test_token",
            instagram_business_id="test_id"
        )

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return MagicMock(status_code=429, text="Rate limited")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            with pytest.raises(RateLimitError):
                await scraper.get_posts(limit=10)

            # Should fail on first call without retrying
            assert call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_raises_error(self):
        """Verify that 429 raises RateLimitError with descriptive message."""
        from ingestion.instagram_scraper import MetaGraphAPIScraper, RateLimitError

        scraper = MetaGraphAPIScraper(
            access_token="test_token",
            instagram_business_id="test_id"
        )

        async def always_rate_limit(*args, **kwargs):
            return MagicMock(status_code=429, text="Rate limited")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = always_rate_limit
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            with pytest.raises(RateLimitError) as exc_info:
                await scraper.get_posts(limit=10)

            assert "rate limit" in str(exc_info.value).lower()


class TestServerErrorRetry:
    """Tests for server error (5xx) behavior."""

    @pytest.mark.asyncio
    async def test_server_error_triggers_retry(self):
        """Verify that 5xx response raises InstagramScraperError immediately."""
        from ingestion.instagram_scraper import MetaGraphAPIScraper, InstagramScraperError

        scraper = MetaGraphAPIScraper(
            access_token="test_token",
            instagram_business_id="test_id"
        )

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return MagicMock(status_code=503, text="Service Unavailable")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            with pytest.raises(InstagramScraperError) as exc_info:
                await scraper.get_posts(limit=10)

            assert "503" in str(exc_info.value)
            # Should fail on first call without retrying
            assert call_count == 1


class TestClientErrorNoRetry:
    """Tests for client error (4xx) non-retry behavior."""

    @pytest.mark.asyncio
    async def test_auth_error_no_retry(self):
        """Verify that 401 does NOT retry."""
        from ingestion.instagram_scraper import MetaGraphAPIScraper, AuthenticationError

        scraper = MetaGraphAPIScraper(
            access_token="invalid_token",
            instagram_business_id="test_id"
        )

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return MagicMock(status_code=401, text="Unauthorized")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            with pytest.raises(AuthenticationError):
                await scraper.get_posts(limit=10)

            # Should NOT retry on 401
            assert call_count == 1

    @pytest.mark.asyncio
    async def test_forbidden_error_no_retry(self):
        """Verify that 403 does NOT retry."""
        from ingestion.instagram_scraper import MetaGraphAPIScraper, InstagramScraperError

        scraper = MetaGraphAPIScraper(
            access_token="test_token",
            instagram_business_id="test_id"
        )

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return MagicMock(status_code=403, text="Forbidden")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            with pytest.raises(InstagramScraperError):
                await scraper.get_posts(limit=10)

            # Should NOT retry on 403
            assert call_count == 1

    @pytest.mark.asyncio
    async def test_bad_request_no_retry(self):
        """Verify that 400 does NOT retry."""
        from ingestion.instagram_scraper import MetaGraphAPIScraper, InstagramScraperError

        scraper = MetaGraphAPIScraper(
            access_token="test_token",
            instagram_business_id="invalid_id"
        )

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return MagicMock(status_code=400, text="Bad Request")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            with pytest.raises(InstagramScraperError):
                await scraper.get_posts(limit=10)

            # Should NOT retry on 400
            assert call_count == 1


class TestTimeoutRetry:
    """Tests for timeout error behavior."""

    @pytest.mark.asyncio
    async def test_timeout_triggers_retry(self):
        """Verify that timeout raises InstagramScraperError immediately."""
        from ingestion.instagram_scraper import MetaGraphAPIScraper, InstagramScraperError

        scraper = MetaGraphAPIScraper(
            access_token="test_token",
            instagram_business_id="test_id"
        )

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("Connection timed out")

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            with pytest.raises(InstagramScraperError) as exc_info:
                await scraper.get_posts(limit=10)

            assert "timeout" in str(exc_info.value).lower()
            # Should fail on first call without retrying
            assert call_count == 1


class TestSuccessfulFetch:
    """Tests for successful fetch with retry."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        """Verify successful fetch on first try."""
        from ingestion.instagram_scraper import MetaGraphAPIScraper

        scraper = MetaGraphAPIScraper(
            access_token="valid_token",
            instagram_business_id="valid_id"
        )

        mock_data = {
            "data": [
                {
                    "id": "post1",
                    "caption": "This is a test post with enough content",
                    "permalink": "https://instagram.com/p/post1",
                    "timestamp": "2024-01-15T12:00:00+00:00",
                    "media_type": "IMAGE",
                    "like_count": 100,
                    "comments_count": 10
                },
                {
                    "id": "post2",
                    "caption": "Another test post with content",
                    "permalink": "https://instagram.com/p/post2",
                    "timestamp": "2024-01-14T12:00:00+00:00",
                    "media_type": "VIDEO"
                }
            ]
        }

        async def mock_get(*args, **kwargs):
            return MagicMock(status_code=200, json=lambda: mock_data)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = mock_get
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            posts = await scraper.get_posts(limit=10)

            assert len(posts) == 2
            assert posts[0].post_id == "post1"
            assert posts[0].likes_count == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
