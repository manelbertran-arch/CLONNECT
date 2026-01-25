"""
Tests for Playwright-based JavaScript scraper.

Tests cover:
- JS rendering capability
- Fallback mechanism from DeterministicScraper
- Timeout handling
- Environment variable configuration
- Circuit breaker integration
- Browser instance reuse
"""

import pytest
import asyncio
import os
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_env_playwright_enabled():
    """Enable Playwright via environment."""
    with patch.dict(os.environ, {"SCRAPER_USE_PLAYWRIGHT": "true"}):
        yield


@pytest.fixture
def mock_env_playwright_disabled():
    """Disable Playwright via environment."""
    with patch.dict(os.environ, {"SCRAPER_USE_PLAYWRIGHT": "false"}):
        yield


@pytest.fixture
def mock_playwright_available():
    """Mock Playwright as available."""
    with patch("ingestion.playwright_scraper._PLAYWRIGHT_AVAILABLE", True):
        with patch("ingestion.playwright_scraper.PLAYWRIGHT_ENABLED", True):
            yield


@pytest.fixture
def mock_playwright_unavailable():
    """Mock Playwright as unavailable."""
    with patch("ingestion.playwright_scraper._PLAYWRIGHT_AVAILABLE", False):
        yield


@pytest.fixture
def sample_html_with_js():
    """Sample HTML that would be rendered by JavaScript."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>SPA Test Page</title>
        <meta name="description" content="A JavaScript-rendered page">
    </head>
    <body>
        <main>
            <h1>Welcome to Our SPA</h1>
            <div id="app">
                <section>
                    <h2>Features</h2>
                    <p>This content was rendered by JavaScript. It includes all our amazing features
                    that make this product stand out from the competition.</p>
                    <ul>
                        <li>Feature one with detailed description</li>
                        <li>Feature two that users love</li>
                        <li>Feature three for power users</li>
                    </ul>
                </section>
                <section>
                    <h2>Pricing</h2>
                    <p>Our pricing is simple and transparent. We offer three tiers to match your needs.</p>
                </section>
            </div>
        </main>
    </body>
    </html>
    """


@pytest.fixture
def sample_empty_html():
    """Sample HTML with minimal content (needs JS rendering)."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Loading...</title></head>
    <body>
        <div id="root"></div>
        <script src="/app.js"></script>
    </body>
    </html>
    """


# =============================================================================
# TEST: PLAYWRIGHT AVAILABILITY CHECK
# =============================================================================

class TestPlaywrightAvailability:
    """Tests for Playwright availability detection."""

    def test_is_playwright_available_when_installed_and_enabled(self, mock_playwright_available):
        """Should return True when Playwright is installed and enabled."""
        from ingestion.playwright_scraper import is_playwright_available
        # Need to reload to pick up mocked values
        assert is_playwright_available() is True

    def test_is_playwright_available_when_disabled(self):
        """Should return False when Playwright is disabled via env."""
        with patch("ingestion.playwright_scraper._PLAYWRIGHT_AVAILABLE", True):
            with patch("ingestion.playwright_scraper.PLAYWRIGHT_ENABLED", False):
                from ingestion.playwright_scraper import is_playwright_available
                assert is_playwright_available() is False

    def test_is_playwright_available_when_not_installed(self, mock_playwright_unavailable):
        """Should return False when Playwright is not installed."""
        from ingestion.playwright_scraper import is_playwright_available
        assert is_playwright_available() is False


# =============================================================================
# TEST: PLAYWRIGHT SCRAPER CORE FUNCTIONALITY
# =============================================================================

class TestPlaywrightScraperCore:
    """Tests for PlaywrightScraper core functionality."""

    @pytest.mark.asyncio
    async def test_scrape_page_returns_none_when_unavailable(self, mock_playwright_unavailable):
        """Should return None when Playwright is not available."""
        from ingestion.playwright_scraper import PlaywrightScraper

        scraper = PlaywrightScraper()
        result = await scraper.scrape_page("https://example.com", "creator_123")
        assert result is None

    @pytest.mark.asyncio
    async def test_scrape_page_respects_robots_txt(self, mock_playwright_available):
        """Should respect robots.txt and return None for blocked URLs."""
        from ingestion.playwright_scraper import PlaywrightScraper

        with patch("ingestion.playwright_scraper.get_robots_checker") as mock_robots:
            mock_checker = Mock()
            mock_checker.is_allowed.return_value = False
            mock_robots.return_value = mock_checker

            scraper = PlaywrightScraper()
            result = await scraper.scrape_page("https://example.com/blocked", "creator_123")

            assert result is None
            mock_checker.is_allowed.assert_called_once_with("https://example.com/blocked")

    @pytest.mark.asyncio
    async def test_scrape_page_extracts_content(self, sample_html_with_js, mock_playwright_available):
        """Should extract content from rendered HTML."""
        from ingestion.playwright_scraper import PlaywrightScraper

        # Mock all dependencies
        with patch("ingestion.playwright_scraper.get_robots_checker") as mock_robots:
            mock_checker = Mock()
            mock_checker.is_allowed.return_value = True
            mock_robots.return_value = mock_checker

            with patch("ingestion.playwright_scraper.scraper_circuit_breaker") as mock_cb:
                mock_cb.call_async = AsyncMock(return_value=(sample_html_with_js, "https://example.com"))

                # Mock metrics
                with patch("ingestion.playwright_scraper.record_page_scraped"):
                    with patch("ingestion.playwright_scraper.observe_scrape_duration"):
                        scraper = PlaywrightScraper()
                        scraper._browser = Mock()  # Pretend browser is initialized

                        result = await scraper.scrape_page("https://example.com", "creator_123")

                        assert result is not None
                        assert result.title == "Welcome to Our SPA"
                        assert "Features" in result.main_content
                        assert "Pricing" in result.main_content
                        assert result.metadata.get("rendered_by") == "playwright"

    @pytest.mark.asyncio
    async def test_scrape_page_handles_timeout(self, mock_playwright_available):
        """Should handle timeout gracefully."""
        from ingestion.playwright_scraper import PlaywrightScraper, PlaywrightTimeout

        with patch("ingestion.playwright_scraper.get_robots_checker") as mock_robots:
            mock_checker = Mock()
            mock_checker.is_allowed.return_value = True
            mock_robots.return_value = mock_checker

            with patch("ingestion.playwright_scraper.scraper_circuit_breaker") as mock_cb:
                mock_cb.call_async = AsyncMock(side_effect=PlaywrightTimeout("Timeout"))

                with patch("ingestion.playwright_scraper.record_page_failed") as mock_failed:
                    with patch("ingestion.playwright_scraper.record_ingestion_error"):
                        scraper = PlaywrightScraper()
                        result = await scraper.scrape_page("https://slow-site.com", "creator_123")

                        assert result is None
                        mock_failed.assert_called_once_with("creator_123", "playwright_timeout")

    @pytest.mark.asyncio
    async def test_scrape_page_handles_circuit_breaker_open(self, mock_playwright_available):
        """Should handle circuit breaker open state."""
        import pybreaker
        from ingestion.playwright_scraper import PlaywrightScraper

        with patch("ingestion.playwright_scraper.get_robots_checker") as mock_robots:
            mock_checker = Mock()
            mock_checker.is_allowed.return_value = True
            mock_robots.return_value = mock_checker

            with patch("ingestion.playwright_scraper.scraper_circuit_breaker") as mock_cb:
                mock_cb.call_async = AsyncMock(side_effect=pybreaker.CircuitBreakerError())

                with patch("ingestion.playwright_scraper.record_page_failed") as mock_failed:
                    scraper = PlaywrightScraper()
                    result = await scraper.scrape_page("https://failing-site.com", "creator_123")

                    assert result is None
                    mock_failed.assert_called_once_with("creator_123", "circuit_breaker_open")


# =============================================================================
# TEST: PLAYWRIGHT BROWSER MANAGEMENT
# =============================================================================

class TestPlaywrightBrowserManagement:
    """Tests for browser instance management."""

    @pytest.mark.asyncio
    async def test_browser_lazy_initialization(self, mock_playwright_available):
        """Browser should be lazily initialized on first use."""
        from ingestion.playwright_scraper import PlaywrightScraper

        scraper = PlaywrightScraper()
        assert scraper._browser is None
        assert scraper._playwright is None

    @pytest.mark.asyncio
    async def test_close_cleans_up_resources(self, mock_playwright_available):
        """Close should properly cleanup browser resources."""
        from ingestion.playwright_scraper import PlaywrightScraper

        scraper = PlaywrightScraper()

        # Mock browser and playwright
        mock_browser = AsyncMock()
        mock_pw = AsyncMock()
        scraper._browser = mock_browser
        scraper._playwright = mock_pw

        await scraper.close()

        mock_browser.close.assert_called_once()
        mock_pw.stop.assert_called_once()
        assert scraper._browser is None
        assert scraper._playwright is None


# =============================================================================
# TEST: DETERMINISTIC SCRAPER FALLBACK
# =============================================================================

class TestDeterministicScraperFallback:
    """Tests for Playwright fallback from DeterministicScraper."""

    @pytest.mark.asyncio
    async def test_fallback_triggered_on_empty_content(self, sample_empty_html, sample_html_with_js):
        """Should fallback to Playwright when BeautifulSoup returns empty content."""
        from ingestion.deterministic_scraper import DeterministicScraper, ScrapedPage

        scraper = DeterministicScraper()

        # Mock the initial HTTP fetch returning empty HTML
        with patch.object(scraper, "_fetch_page_with_circuit_breaker") as mock_fetch:
            mock_fetch.return_value = (sample_empty_html, "https://spa-site.com")

            # Mock Playwright fallback
            with patch("ingestion.playwright_scraper.is_playwright_available", return_value=True):
                with patch("ingestion.playwright_scraper.get_playwright_scraper") as mock_get_pw:
                    mock_pw_scraper = AsyncMock()
                    mock_pw_scraper.scrape_page.return_value = ScrapedPage(
                        url="https://spa-site.com",
                        title="SPA Site",
                        main_content="This is rich content rendered by JavaScript with more than 100 characters to pass the threshold check.",
                        sections=[],
                        links=[],
                        metadata={"rendered_by": "playwright"}
                    )
                    mock_get_pw.return_value = mock_pw_scraper

                    # Mock robots checker
                    with patch("ingestion.deterministic_scraper.get_robots_checker") as mock_robots:
                        mock_checker = Mock()
                        mock_checker.is_allowed.return_value = True
                        mock_robots.return_value = mock_checker

                        result = await scraper.scrape_page("https://spa-site.com", "creator_123")

                        # Should have used Playwright fallback
                        assert result is not None
                        assert result.metadata.get("rendered_by") == "playwright"
                        mock_pw_scraper.scrape_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_fallback_when_content_sufficient(self):
        """Should NOT fallback to Playwright when BeautifulSoup extracts enough content."""
        from ingestion.deterministic_scraper import DeterministicScraper

        sufficient_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Static Site</title></head>
        <body>
            <main>
                <h1>Welcome</h1>
                <p>This is a static site with plenty of content that doesn't need JavaScript
                rendering. The content is long enough to pass the minimum threshold of 100
                characters, so Playwright should not be called as a fallback.</p>
            </main>
        </body>
        </html>
        """

        scraper = DeterministicScraper()

        with patch.object(scraper, "_fetch_page_with_circuit_breaker") as mock_fetch:
            mock_fetch.return_value = (sufficient_html, "https://static-site.com")

            with patch("ingestion.playwright_scraper.get_playwright_scraper") as mock_get_pw:
                # Mock robots checker
                with patch("ingestion.deterministic_scraper.get_robots_checker") as mock_robots:
                    mock_checker = Mock()
                    mock_checker.is_allowed.return_value = True
                    mock_robots.return_value = mock_checker

                    # Mock metrics
                    with patch("ingestion.deterministic_scraper.record_page_scraped"):
                        with patch("ingestion.deterministic_scraper.observe_scrape_duration"):
                            result = await scraper.scrape_page("https://static-site.com", "creator_123")

                            assert result is not None
                            assert "rendered_by" not in result.metadata
                            # Playwright should NOT have been called
                            mock_get_pw.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_graceful_when_playwright_unavailable(self, sample_empty_html):
        """Should gracefully continue when Playwright is not available."""
        from ingestion.deterministic_scraper import DeterministicScraper

        scraper = DeterministicScraper()

        with patch.object(scraper, "_fetch_page_with_circuit_breaker") as mock_fetch:
            mock_fetch.return_value = (sample_empty_html, "https://spa-site.com")

            # Mock Playwright as unavailable
            with patch("ingestion.playwright_scraper.is_playwright_available", return_value=False):
                with patch("ingestion.deterministic_scraper.get_robots_checker") as mock_robots:
                    mock_checker = Mock()
                    mock_checker.is_allowed.return_value = True
                    mock_robots.return_value = mock_checker

                    with patch("ingestion.deterministic_scraper.record_page_scraped"):
                        with patch("ingestion.deterministic_scraper.observe_scrape_duration"):
                            result = await scraper.scrape_page("https://spa-site.com", "creator_123")

                            # Should still return (even with minimal content)
                            assert result is not None


# =============================================================================
# TEST: ENVIRONMENT CONFIGURATION
# =============================================================================

class TestEnvironmentConfiguration:
    """Tests for environment variable configuration."""

    def test_default_timeout_is_30_seconds(self):
        """Default timeout should be 30000ms (30 seconds)."""
        with patch.dict(os.environ, {}, clear=True):
            # Need to reload module to pick up defaults
            import importlib
            import ingestion.playwright_scraper as pw_module
            importlib.reload(pw_module)

            assert pw_module.PLAYWRIGHT_TIMEOUT == 30000

    def test_custom_timeout_from_env(self):
        """Should respect custom timeout from environment."""
        with patch.dict(os.environ, {"PLAYWRIGHT_TIMEOUT": "60000"}):
            import importlib
            import ingestion.playwright_scraper as pw_module
            importlib.reload(pw_module)

            assert pw_module.PLAYWRIGHT_TIMEOUT == 60000

    def test_headless_enabled_by_default(self):
        """Headless mode should be enabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import ingestion.playwright_scraper as pw_module
            importlib.reload(pw_module)

            assert pw_module.PLAYWRIGHT_HEADLESS is True

    def test_headless_can_be_disabled(self):
        """Should allow disabling headless mode for debugging."""
        with patch.dict(os.environ, {"PLAYWRIGHT_HEADLESS": "false"}):
            import importlib
            import ingestion.playwright_scraper as pw_module
            importlib.reload(pw_module)

            assert pw_module.PLAYWRIGHT_HEADLESS is False


# =============================================================================
# TEST: SSL CONFIGURATION
# =============================================================================

class TestSSLConfiguration:
    """Tests for SSL verification configuration."""

    def test_ssl_verification_enabled_by_default(self):
        """SSL verification should be enabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import ingestion.deterministic_scraper as ds_module
            importlib.reload(ds_module)

            assert ds_module.VERIFY_SSL is True

    def test_ssl_verification_used_in_fetch(self):
        """Should use VERIFY_SSL config in HTTP requests."""
        from ingestion.deterministic_scraper import DeterministicScraper
        import httpx

        # Check that the code uses VERIFY_SSL
        import inspect
        source = inspect.getsource(DeterministicScraper._fetch_page_html)
        assert "verify=VERIFY_SSL" in source


# =============================================================================
# TEST: TEXT EXTRACTION
# =============================================================================

class TestTextExtraction:
    """Tests for text extraction from rendered HTML."""

    def test_extract_text_removes_noise_elements(self, sample_html_with_js):
        """Should remove script, style, nav, footer, etc."""
        from ingestion.playwright_scraper import PlaywrightScraper
        from bs4 import BeautifulSoup

        html_with_noise = """
        <html>
        <body>
            <nav>Navigation menu</nav>
            <main>
                <h1>Main Content</h1>
                <p>This is the actual content that should be extracted and kept.</p>
            </main>
            <footer>Footer content</footer>
            <script>alert('bad')</script>
        </body>
        </html>
        """

        scraper = PlaywrightScraper()
        soup = BeautifulSoup(html_with_noise, 'html.parser')
        main_soup = soup.find('main') or soup.find('body')
        text = scraper._extract_text_from_soup(main_soup)

        assert "Main Content" in text
        assert "actual content" in text
        assert "Navigation menu" not in text
        assert "Footer content" not in text
        assert "alert" not in text

    def test_extract_sections_with_headings(self, sample_html_with_js):
        """Should extract sections with their headings."""
        from ingestion.playwright_scraper import PlaywrightScraper
        from bs4 import BeautifulSoup

        scraper = PlaywrightScraper()
        soup = BeautifulSoup(sample_html_with_js, 'html.parser')
        main_soup = soup.find('main')
        sections = scraper._extract_sections(main_soup)

        assert len(sections) >= 2
        headings = [s['heading'] for s in sections]
        assert "Features" in headings
        assert "Pricing" in headings


# =============================================================================
# TEST: INTEGRATION (REQUIRES ACTUAL PLAYWRIGHT - SKIP IN CI)
# =============================================================================

@pytest.mark.skip(reason="Integration test - requires Playwright browser installed")
class TestPlaywrightIntegration:
    """Integration tests that require actual Playwright installation."""

    @pytest.mark.asyncio
    async def test_real_page_scrape(self):
        """Test scraping a real page (requires network)."""
        from ingestion.playwright_scraper import PlaywrightScraper

        scraper = PlaywrightScraper(timeout=60000)
        try:
            result = await scraper.scrape_page("https://example.com", "test_creator")
            assert result is not None
            assert "Example Domain" in result.title
            assert len(result.main_content) > 50
        finally:
            await scraper.close()
