"""
Tests for BUG-003 fix: robots.txt compliance in DeterministicScraper.

Verifies that:
1. RESPECT_ROBOTS_TXT is enabled by default
2. robots.txt is checked before scraping
3. Blocked URLs are logged and skipped
4. robots.txt is cached per domain
5. Configuration via SCRAPER_RESPECT_ROBOTS env var

Run with: pytest tests/test_robots_txt_compliance.py -v
"""

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


class TestRobotsTxtConfiguration:
    """Tests for robots.txt configuration constants."""

    def test_respect_robots_default_is_true(self):
        """Verify robots.txt respect is enabled by default."""
        import importlib
        import ingestion.deterministic_scraper as scraper_module

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SCRAPER_RESPECT_ROBOTS", None)
            importlib.reload(scraper_module)

            assert scraper_module.RESPECT_ROBOTS_TXT is True

    def test_respect_robots_can_be_disabled_via_env(self):
        """Verify SCRAPER_RESPECT_ROBOTS=false disables checking."""
        import importlib
        import ingestion.deterministic_scraper as scraper_module

        with patch.dict(os.environ, {"SCRAPER_RESPECT_ROBOTS": "false"}):
            importlib.reload(scraper_module)
            assert scraper_module.RESPECT_ROBOTS_TXT is False

        # Restore default
        with patch.dict(os.environ, {"SCRAPER_RESPECT_ROBOTS": "true"}):
            importlib.reload(scraper_module)

    def test_cache_ttl_default_is_3600(self):
        """Verify default cache TTL is 1 hour (3600 seconds)."""
        import importlib
        import ingestion.deterministic_scraper as scraper_module

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SCRAPER_ROBOTS_CACHE_TTL", None)
            importlib.reload(scraper_module)

            assert scraper_module.ROBOTS_TXT_CACHE_TTL == 3600

    def test_cache_ttl_configurable_via_env(self):
        """Verify cache TTL is configurable."""
        import importlib
        import ingestion.deterministic_scraper as scraper_module

        with patch.dict(os.environ, {"SCRAPER_ROBOTS_CACHE_TTL": "7200"}):
            importlib.reload(scraper_module)
            assert scraper_module.ROBOTS_TXT_CACHE_TTL == 7200

        # Restore default
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SCRAPER_ROBOTS_CACHE_TTL", None)
            importlib.reload(scraper_module)


class TestRobotsTxtChecker:
    """Tests for RobotsTxtChecker class."""

    def test_checker_allows_when_no_robots_txt(self):
        """Verify URLs are allowed when robots.txt returns 404."""
        from ingestion.deterministic_scraper import RobotsTxtChecker

        checker = RobotsTxtChecker()

        with patch("ingestion.deterministic_scraper.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=404)

            result = checker.is_allowed("https://example.com/page")

            assert result is True

    def test_checker_allows_allowed_path(self):
        """Verify URLs are allowed when robots.txt permits."""
        from ingestion.deterministic_scraper import RobotsTxtChecker

        checker = RobotsTxtChecker()

        robots_txt = """
User-agent: *
Allow: /public/
Disallow: /private/
"""

        with patch("ingestion.deterministic_scraper.httpx.get") as mock_get:
            mock_response = MagicMock(status_code=200)
            mock_response.text = robots_txt
            mock_get.return_value = mock_response

            result = checker.is_allowed("https://example.com/public/page")

            assert result is True

    def test_checker_blocks_disallowed_path(self):
        """Verify URLs are blocked when robots.txt disallows."""
        from ingestion.deterministic_scraper import RobotsTxtChecker

        checker = RobotsTxtChecker()

        robots_txt = """
User-agent: *
Disallow: /private/
Disallow: /admin/
"""

        with patch("ingestion.deterministic_scraper.httpx.get") as mock_get:
            mock_response = MagicMock(status_code=200)
            mock_response.text = robots_txt
            mock_get.return_value = mock_response

            result = checker.is_allowed("https://example.com/private/secret")

            assert result is False

    def test_checker_blocks_clonnectbot_specifically(self):
        """Verify ClonnectBot user-agent specific rules are respected."""
        from ingestion.deterministic_scraper import RobotsTxtChecker

        checker = RobotsTxtChecker(user_agent="ClonnectBot")

        robots_txt = """
User-agent: *
Allow: /

User-agent: ClonnectBot
Disallow: /
"""

        with patch("ingestion.deterministic_scraper.httpx.get") as mock_get:
            mock_response = MagicMock(status_code=200)
            mock_response.text = robots_txt
            mock_get.return_value = mock_response

            result = checker.is_allowed("https://example.com/public/page")

            assert result is False

    def test_checker_allows_on_fetch_error(self):
        """Verify URLs are allowed when robots.txt fetch fails (fail-open)."""
        from ingestion.deterministic_scraper import RobotsTxtChecker

        checker = RobotsTxtChecker()

        with patch("ingestion.deterministic_scraper.httpx.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Connection timed out")

            result = checker.is_allowed("https://example.com/page")

            assert result is True  # Fail-open for availability


class TestRobotsTxtCaching:
    """Tests for robots.txt caching behavior."""

    def test_checker_caches_per_domain(self):
        """Verify robots.txt is cached per domain."""
        from ingestion.deterministic_scraper import RobotsTxtChecker

        checker = RobotsTxtChecker()

        robots_txt = """
User-agent: *
Allow: /
"""

        with patch("ingestion.deterministic_scraper.httpx.get") as mock_get:
            mock_response = MagicMock(status_code=200)
            mock_response.text = robots_txt
            mock_get.return_value = mock_response

            # First call - should fetch
            checker.is_allowed("https://example.com/page1")

            # Second call same domain - should use cache
            checker.is_allowed("https://example.com/page2")

            # Should only fetch once
            assert mock_get.call_count == 1

    def test_checker_fetches_different_domains(self):
        """Verify different domains get separate robots.txt."""
        from ingestion.deterministic_scraper import RobotsTxtChecker

        checker = RobotsTxtChecker()

        robots_txt = """
User-agent: *
Allow: /
"""

        with patch("ingestion.deterministic_scraper.httpx.get") as mock_get:
            mock_response = MagicMock(status_code=200)
            mock_response.text = robots_txt
            mock_get.return_value = mock_response

            checker.is_allowed("https://example1.com/page")
            checker.is_allowed("https://example2.com/page")

            # Should fetch for each domain
            assert mock_get.call_count == 2

    def test_cache_expires_after_ttl(self):
        """Verify cache expires after TTL."""
        from ingestion.deterministic_scraper import RobotsTxtChecker

        # Use very short TTL for test
        checker = RobotsTxtChecker(cache_ttl=0.1)  # 100ms

        robots_txt = """
User-agent: *
Allow: /
"""

        with patch("ingestion.deterministic_scraper.httpx.get") as mock_get:
            mock_response = MagicMock(status_code=200)
            mock_response.text = robots_txt
            mock_get.return_value = mock_response

            # First call
            checker.is_allowed("https://example.com/page1")

            # Wait for cache to expire
            time.sleep(0.15)

            # Second call - cache expired, should refetch
            checker.is_allowed("https://example.com/page2")

            assert mock_get.call_count == 2

    def test_clear_cache(self):
        """Verify cache can be cleared."""
        from ingestion.deterministic_scraper import RobotsTxtChecker

        checker = RobotsTxtChecker()

        robots_txt = """
User-agent: *
Allow: /
"""

        with patch("ingestion.deterministic_scraper.httpx.get") as mock_get:
            mock_response = MagicMock(status_code=200)
            mock_response.text = robots_txt
            mock_get.return_value = mock_response

            checker.is_allowed("https://example.com/page1")
            checker.clear_cache()
            checker.is_allowed("https://example.com/page2")

            assert mock_get.call_count == 2


class TestScraperRobotsTxtIntegration:
    """Tests for robots.txt integration in DeterministicScraper."""

    @pytest.mark.asyncio
    async def test_scrape_page_checks_robots_txt(self):
        """Verify scrape_page checks robots.txt before scraping."""
        from ingestion.deterministic_scraper import DeterministicScraper

        scraper = DeterministicScraper(max_pages=10)

        robots_txt = """
User-agent: *
Disallow: /blocked/
"""

        with patch("ingestion.deterministic_scraper.httpx.get") as mock_robots:
            mock_robots_response = MagicMock(status_code=200)
            mock_robots_response.text = robots_txt
            mock_robots.return_value = mock_robots_response

            with patch("ingestion.deterministic_scraper.RESPECT_ROBOTS_TXT", True):
                # Clear any cached robots.txt
                from ingestion.deterministic_scraper import get_robots_checker
                get_robots_checker().clear_cache()

                result = await scraper.scrape_page("https://example.com/blocked/page")

        # Should return None because URL is blocked
        assert result is None

    @pytest.mark.asyncio
    async def test_scrape_page_allows_permitted_urls(self):
        """Verify scrape_page allows URLs permitted by robots.txt."""
        from ingestion.deterministic_scraper import DeterministicScraper

        scraper = DeterministicScraper(max_pages=10)

        robots_txt = """
User-agent: *
Allow: /public/
"""

        html_content = """
        <html>
            <head><title>Public Page</title></head>
            <body>
                <p>This is a public page with enough content for the test.</p>
                <p>Adding more text to pass the minimum content check threshold.</p>
            </body>
        </html>
        """

        with patch("ingestion.deterministic_scraper.httpx.get") as mock_robots:
            mock_robots_response = MagicMock(status_code=200)
            mock_robots_response.text = robots_txt
            mock_robots.return_value = mock_robots_response

            with patch("ingestion.deterministic_scraper.httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.headers = {"content-type": "text/html"}
                mock_response.text = html_content
                mock_instance.get.return_value = mock_response
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client.return_value = mock_instance

                with patch("ingestion.deterministic_scraper.RESPECT_ROBOTS_TXT", True):
                    from ingestion.deterministic_scraper import get_robots_checker
                    get_robots_checker().clear_cache()

                    result = await scraper.scrape_page("https://example.com/public/page")

        # Should return content because URL is allowed
        assert result is not None
        assert result.title == "Public Page"

    @pytest.mark.asyncio
    async def test_scrape_website_respects_robots_txt_for_links(self):
        """Verify scrape_website doesn't queue blocked links."""
        from ingestion.deterministic_scraper import DeterministicScraper

        scraper = DeterministicScraper(max_pages=10)

        robots_txt = """
User-agent: *
Allow: /
Disallow: /admin/
"""

        # Page with links to both allowed and blocked paths
        html_content = """
        <html>
            <head><title>Home Page</title></head>
            <body>
                <p>Welcome to the home page with lots of content.</p>
                <p>This page has enough text to pass content checks.</p>
                <a href="/public/page">Public Link</a>
                <a href="/admin/dashboard">Admin Link</a>
            </body>
        </html>
        """

        with patch("ingestion.deterministic_scraper.httpx.get") as mock_robots:
            mock_robots_response = MagicMock(status_code=200)
            mock_robots_response.text = robots_txt
            mock_robots.return_value = mock_robots_response

            with patch("ingestion.deterministic_scraper.httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.headers = {"content-type": "text/html"}
                mock_response.text = html_content
                mock_instance.get.return_value = mock_response
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client.return_value = mock_instance

                with patch("ingestion.deterministic_scraper.RESPECT_ROBOTS_TXT", True):
                    from ingestion.deterministic_scraper import get_robots_checker
                    get_robots_checker().clear_cache()

                    pages = await scraper.scrape_website("https://example.com")

        # Should have scraped but /admin/ links should not be in discovered links
        assert len(pages) >= 1
        # The links should not include /admin/ paths
        for page in pages:
            blocked_links = [link for link in page.links if "/admin/" in link]
            assert len(blocked_links) == 0 or not any(
                link in scraper._visited for link in blocked_links
            )


class TestRobotsTxtDisabled:
    """Tests for when robots.txt checking is disabled."""

    @pytest.mark.asyncio
    async def test_scrape_ignores_robots_when_disabled(self):
        """Verify scraping proceeds when RESPECT_ROBOTS_TXT=false."""
        from ingestion.deterministic_scraper import DeterministicScraper, RobotsTxtChecker

        scraper = DeterministicScraper(max_pages=10)

        html_content = """
        <html>
            <head><title>Blocked Page</title></head>
            <body>
                <p>This page would normally be blocked by robots.txt.</p>
                <p>But we disabled robots checking so it should work.</p>
            </body>
        </html>
        """

        with patch("ingestion.deterministic_scraper.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "text/html"}
            mock_response.text = html_content
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            # Disable robots.txt checking
            with patch("ingestion.deterministic_scraper.RESPECT_ROBOTS_TXT", False):
                # Create new checker to pick up the patched value
                checker = RobotsTxtChecker()

                with patch("ingestion.deterministic_scraper.get_robots_checker", return_value=checker):
                    result = await scraper.scrape_page("https://example.com/blocked/page")

        # Should succeed because robots checking is disabled
        assert result is not None
        assert result.title == "Blocked Page"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
