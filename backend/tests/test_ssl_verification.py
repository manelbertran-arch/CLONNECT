"""
Tests for SSL verification in DeterministicScraper.

Verifies that:
1. SSL verification is enabled by default
2. SCRAPER_VERIFY_SSL env var controls behavior
3. SSL errors are handled gracefully (log and skip, don't crash)

Run with: pytest tests/test_ssl_verification.py -v
"""

import os
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


class TestSSLConfiguration:
    """Tests for SSL configuration."""

    def test_verify_ssl_default_is_true(self):
        """Verify SSL verification is enabled by default."""
        # Remove env var if set
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SCRAPER_VERIFY_SSL", None)

            # Reload module to get fresh default
            import importlib
            import ingestion.deterministic_scraper as scraper_module
            importlib.reload(scraper_module)

            assert scraper_module.VERIFY_SSL is True

    def test_verify_ssl_can_be_disabled_via_env(self):
        """Verify SCRAPER_VERIFY_SSL=false disables verification."""
        import importlib
        import ingestion.deterministic_scraper as scraper_module

        with patch.dict(os.environ, {"SCRAPER_VERIFY_SSL": "false"}):
            importlib.reload(scraper_module)
            assert scraper_module.VERIFY_SSL is False

        # Restore default
        with patch.dict(os.environ, {"SCRAPER_VERIFY_SSL": "true"}):
            importlib.reload(scraper_module)

    def test_verify_ssl_accepts_various_true_values(self):
        """Verify various truthy values work."""
        import importlib
        import ingestion.deterministic_scraper as scraper_module

        for value in ["true", "True", "TRUE", "1", "yes", "YES"]:
            with patch.dict(os.environ, {"SCRAPER_VERIFY_SSL": value}):
                importlib.reload(scraper_module)
                assert scraper_module.VERIFY_SSL is True, f"Failed for value: {value}"

    def test_verify_ssl_accepts_various_false_values(self):
        """Verify various falsy values work."""
        import importlib
        import ingestion.deterministic_scraper as scraper_module

        for value in ["false", "False", "FALSE", "0", "no", "NO"]:
            with patch.dict(os.environ, {"SCRAPER_VERIFY_SSL": value}):
                importlib.reload(scraper_module)
                assert scraper_module.VERIFY_SSL is False, f"Failed for value: {value}"

        # Restore default
        with patch.dict(os.environ, {"SCRAPER_VERIFY_SSL": "true"}):
            importlib.reload(scraper_module)


class TestSSLErrorHandling:
    """Tests for SSL error handling."""

    @pytest.mark.asyncio
    async def test_ssl_error_logs_warning_and_returns_none(self):
        """Verify SSL errors are logged and URL is skipped (not crashed)."""
        from ingestion.deterministic_scraper import DeterministicScraper

        scraper = DeterministicScraper(max_pages=10)

        # Mock httpx to raise SSL error
        with patch("ingestion.deterministic_scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = ssl.SSLCertVerificationError(
                1, "certificate verify failed"
            )
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            # Should return None (skip URL), not raise exception
            result = await scraper.scrape_page("https://bad-ssl-site.com")

            assert result is None

    @pytest.mark.asyncio
    async def test_ssl_connect_error_handled_gracefully(self):
        """Verify SSL connection errors are handled."""
        from ingestion.deterministic_scraper import DeterministicScraper

        scraper = DeterministicScraper(max_pages=10)

        with patch("ingestion.deterministic_scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = httpx.ConnectError(
                "SSL: CERTIFICATE_VERIFY_FAILED"
            )
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            result = await scraper.scrape_page("https://bad-ssl-site.com")

            assert result is None

    @pytest.mark.asyncio
    async def test_non_ssl_errors_still_handled(self):
        """Verify non-SSL errors are also handled gracefully."""
        from ingestion.deterministic_scraper import DeterministicScraper

        scraper = DeterministicScraper(max_pages=10)

        with patch("ingestion.deterministic_scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = Exception("Some random error")
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            result = await scraper.scrape_page("https://error-site.com")

            assert result is None


class TestSSLClientConfiguration:
    """Tests to verify httpx client uses correct SSL settings."""

    @pytest.mark.asyncio
    async def test_httpx_client_uses_verify_ssl_setting(self):
        """Verify httpx client is configured with VERIFY_SSL."""
        from ingestion.deterministic_scraper import DeterministicScraper, VERIFY_SSL

        scraper = DeterministicScraper(max_pages=10)

        with patch("ingestion.deterministic_scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "text/html"}
            mock_response.text = "<html><head><title>Test</title></head><body>Content here for testing</body></html>"
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            await scraper.scrape_page("https://example.com")

            # Verify AsyncClient was called with verify=VERIFY_SSL
            mock_client.assert_called_once()
            call_kwargs = mock_client.call_args[1]
            assert "verify" in call_kwargs
            assert call_kwargs["verify"] == VERIFY_SSL


class TestSuccessfulScrapeWithSSL:
    """Tests for successful scraping with SSL enabled."""

    @pytest.mark.asyncio
    async def test_successful_scrape_with_valid_ssl(self):
        """Verify scraping works when SSL is valid."""
        from ingestion.deterministic_scraper import DeterministicScraper

        scraper = DeterministicScraper(max_pages=10)

        with patch("ingestion.deterministic_scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "text/html"}
            mock_response.text = """
            <html>
                <head><title>Test Page</title></head>
                <body>
                    <h1>Welcome</h1>
                    <p>This is a test page with enough content to pass the has_content check.</p>
                    <p>Adding more content to ensure we have at least 100 characters of meaningful text.</p>
                </body>
            </html>
            """
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            result = await scraper.scrape_page("https://valid-ssl-site.com")

            assert result is not None
            assert result.title == "Test Page"
            assert "Welcome" in result.main_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
