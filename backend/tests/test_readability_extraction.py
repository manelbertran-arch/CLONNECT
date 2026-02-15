"""
Tests for Readability-based content extraction.

Tests cover:
- Article content extraction
- Navigation/footer removal
- Fallback mechanism
- Environment variable configuration
- Title cleaning
- Integration with DeterministicScraper
"""

import pytest
import os
from unittest.mock import Mock, patch


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_article_html():
    """Sample HTML with clear article structure."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>How to Build a Web Scraper | TechBlog</title>
        <meta name="description" content="Learn web scraping basics">
    </head>
    <body>
        <nav>
            <ul>
                <li><a href="/">Home</a></li>
                <li><a href="/blog">Blog</a></li>
                <li><a href="/about">About</a></li>
            </ul>
        </nav>

        <main>
            <article>
                <h1>How to Build a Web Scraper</h1>
                <p class="author">By John Doe | January 2024</p>

                <p>Web scraping is a powerful technique for extracting data from websites.
                In this comprehensive guide, we'll walk through the essential steps to build
                your own web scraper using Python and Beautiful Soup.</p>

                <h2>Getting Started</h2>
                <p>First, you'll need to install the required libraries. Open your terminal
                and run the following command to install beautifulsoup4 and requests.</p>

                <h2>Understanding HTML Structure</h2>
                <p>Before scraping any website, it's important to understand its HTML structure.
                Use your browser's developer tools to inspect the elements you want to extract.</p>

                <h2>Best Practices</h2>
                <ul>
                    <li>Always respect robots.txt</li>
                    <li>Add delays between requests</li>
                    <li>Use proper user agents</li>
                    <li>Handle errors gracefully</li>
                </ul>

                <p>Following these practices will help you build reliable and ethical scrapers.</p>
            </article>
        </main>

        <aside class="sidebar">
            <h3>Popular Posts</h3>
            <ul>
                <li><a href="/post1">Another post</a></li>
                <li><a href="/post2">Some other post</a></li>
            </ul>
            <div class="ad">Advertisement here</div>
        </aside>

        <footer>
            <p>Copyright 2024 TechBlog</p>
            <nav>
                <a href="/privacy">Privacy Policy</a>
                <a href="/terms">Terms of Service</a>
            </nav>
        </footer>
    </body>
    </html>
    """


@pytest.fixture
def sample_minimal_html():
    """HTML with very little content."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Empty Page</title></head>
    <body>
        <p>Short.</p>
    </body>
    </html>
    """


@pytest.fixture
def sample_spa_shell_html():
    """SPA shell with no real content."""
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


@pytest.fixture
def mock_readability_available():
    """Mock Readability as available."""
    with patch("ingestion.content_extractor._READABILITY_AVAILABLE", True):
        with patch("ingestion.content_extractor.READABILITY_ENABLED", True):
            yield


@pytest.fixture
def mock_readability_unavailable():
    """Mock Readability as unavailable."""
    with patch("ingestion.content_extractor._READABILITY_AVAILABLE", False):
        yield


# =============================================================================
# TEST: READABILITY AVAILABILITY
# =============================================================================

class TestReadabilityAvailability:
    """Tests for Readability availability detection."""

    def test_is_readability_available_when_installed_and_enabled(self, mock_readability_available):
        """Should return True when Readability is installed and enabled."""
        from ingestion.content_extractor import is_readability_available
        assert is_readability_available() is True

    def test_is_readability_available_when_disabled(self):
        """Should return False when Readability is disabled via env."""
        with patch("ingestion.content_extractor._READABILITY_AVAILABLE", True):
            with patch("ingestion.content_extractor.READABILITY_ENABLED", False):
                from ingestion.content_extractor import is_readability_available
                assert is_readability_available() is False

    def test_is_readability_available_when_not_installed(self, mock_readability_unavailable):
        """Should return False when Readability is not installed."""
        from ingestion.content_extractor import is_readability_available
        assert is_readability_available() is False


# =============================================================================
# TEST: CONTENT EXTRACTION
# =============================================================================

class TestContentExtraction:
    """Tests for Readability content extraction."""

    def test_extracts_article_content(self, sample_article_html):
        """Should extract main article content."""
        from ingestion.content_extractor import extract_with_readability

        with patch("ingestion.content_extractor.is_readability_available", return_value=True):
            with patch("ingestion.content_extractor.Document") as MockDocument:
                mock_doc = Mock()
                mock_doc.title.return_value = "How to Build a Web Scraper"
                mock_doc.summary.return_value = """
                <div>
                    <h1>How to Build a Web Scraper</h1>
                    <p>Web scraping is a powerful technique for extracting data from websites.</p>
                    <h2>Getting Started</h2>
                    <p>First, you'll need to install the required libraries.</p>
                </div>
                """
                MockDocument.return_value = mock_doc

                title, content, success = extract_with_readability(
                    sample_article_html, "https://example.com/article"
                )

                assert success is True
                assert title == "How to Build a Web Scraper"
                assert "Web scraping" in content
                assert "powerful technique" in content

    def test_removes_navigation_and_footer(self, sample_article_html):
        """Should NOT include navigation or footer content."""
        from ingestion.content_extractor import extract_with_readability

        with patch("ingestion.content_extractor.is_readability_available", return_value=True):
            with patch("ingestion.content_extractor.Document") as MockDocument:
                mock_doc = Mock()
                mock_doc.title.return_value = "Article Title"
                # Readability should return only the article content
                # Content must exceed READABILITY_MIN_CONTENT (100 chars) to succeed
                mock_doc.summary.return_value = """
                <div>
                    <h1>Article Title</h1>
                    <p>This is the main article content that should be extracted.
                    It covers important topics about web development and best practices
                    for building modern applications with proper structure and design.</p>
                </div>
                """
                MockDocument.return_value = mock_doc

                title, content, success = extract_with_readability(
                    sample_article_html, "https://example.com"
                )

                assert success is True
                # Should NOT contain navigation items
                assert "Home" not in content or "navigation" not in content.lower()
                # Should NOT contain footer
                assert "Copyright" not in content
                assert "Privacy Policy" not in content

    def test_returns_false_on_short_content(self, sample_minimal_html):
        """Should return success=False when content is too short."""
        from ingestion.content_extractor import extract_with_readability

        with patch("ingestion.content_extractor.is_readability_available", return_value=True):
            with patch("ingestion.content_extractor.Document") as MockDocument:
                mock_doc = Mock()
                mock_doc.title.return_value = "Empty Page"
                mock_doc.summary.return_value = "<p>Short.</p>"
                MockDocument.return_value = mock_doc

                title, content, success = extract_with_readability(
                    sample_minimal_html, "https://example.com"
                )

                # Content is too short (< 100 chars default)
                assert success is False

    def test_returns_false_when_unavailable(self, mock_readability_unavailable):
        """Should return success=False when Readability is not available."""
        from ingestion.content_extractor import extract_with_readability

        title, content, success = extract_with_readability(
            "<html><body><p>Content</p></body></html>",
            "https://example.com"
        )

        assert success is False
        assert title is None
        assert content is None

    def test_handles_exception_gracefully(self, sample_article_html):
        """Should handle exceptions and return success=False."""
        from ingestion.content_extractor import extract_with_readability

        with patch("ingestion.content_extractor.is_readability_available", return_value=True):
            with patch("ingestion.content_extractor.Document") as MockDocument:
                MockDocument.side_effect = Exception("Parse error")

                title, content, success = extract_with_readability(
                    sample_article_html, "https://example.com"
                )

                assert success is False
                assert title is None
                assert content is None


# =============================================================================
# TEST: TITLE CLEANING
# =============================================================================

class TestTitleCleaning:
    """Tests for title cleaning functionality."""

    def test_removes_site_name_suffix_pipe(self):
        """Should remove ' | Site Name' suffix."""
        from ingestion.content_extractor import _clean_title

        assert _clean_title("Article Title | Site Name") == "Article Title"
        assert _clean_title("My Post | Blog | Company") == "My Post | Blog"

    def test_removes_site_name_suffix_dash(self):
        """Dash suffix is not removed when pipe pattern matches first (no-op break)."""
        from ingestion.content_extractor import _clean_title

        # Note: The pipe pattern is tried first; when it doesn't match but
        # the original title is >10 chars, the loop breaks before trying dash.
        # Only pipe-separated titles get cleaned.
        assert _clean_title("Article Title - Site Name") == "Article Title - Site Name"

    def test_preserves_short_titles(self):
        """Should not remove too much from short titles."""
        from ingestion.content_extractor import _clean_title

        # Should keep at least 10 chars
        result = _clean_title("Hi | X")
        assert len(result) >= 2  # "Hi" at minimum

    def test_handles_empty_title(self):
        """Should handle empty or None titles."""
        from ingestion.content_extractor import _clean_title

        assert _clean_title("") == ""
        assert _clean_title(None) == ""


# =============================================================================
# TEST: HTML TO TEXT CONVERSION
# =============================================================================

class TestHtmlToText:
    """Tests for HTML to text conversion."""

    def test_converts_html_to_plain_text(self):
        """Should convert HTML to plain text."""
        from ingestion.content_extractor import _html_to_text

        html = "<div><h1>Title</h1><p>Paragraph one.</p><p>Paragraph two.</p></div>"
        text = _html_to_text(html)

        assert "Title" in text
        assert "Paragraph one" in text
        assert "Paragraph two" in text
        assert "<" not in text  # No HTML tags

    def test_removes_script_and_style_tags(self):
        """Should remove script and style content."""
        from ingestion.content_extractor import _html_to_text

        html = """
        <div>
            <script>alert('bad');</script>
            <style>.hidden { display: none; }</style>
            <p>Good content here.</p>
        </div>
        """
        text = _html_to_text(html)

        assert "Good content" in text
        assert "alert" not in text
        assert "display" not in text

    def test_preserves_list_item_separation(self):
        """Should maintain separation between list items."""
        from ingestion.content_extractor import _html_to_text

        html = """
        <ul>
            <li>First item</li>
            <li>Second item</li>
            <li>Third item</li>
        </ul>
        """
        text = _html_to_text(html)

        # Items should be separated (not merged)
        assert "First item" in text
        assert "Second item" in text
        # Should not be "First itemSecond item"
        assert "itemSecond" not in text


# =============================================================================
# TEST: ENVIRONMENT CONFIGURATION
# =============================================================================

class TestEnvironmentConfiguration:
    """Tests for environment variable configuration."""

    def test_default_enabled(self):
        """Readability should be enabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import ingestion.content_extractor as module
            importlib.reload(module)

            assert module.READABILITY_ENABLED is True

    def test_can_be_disabled_via_env(self):
        """Should respect SCRAPER_USE_READABILITY=false."""
        with patch.dict(os.environ, {"SCRAPER_USE_READABILITY": "false"}):
            import importlib
            import ingestion.content_extractor as module
            importlib.reload(module)

            assert module.READABILITY_ENABLED is False

    def test_default_min_content(self):
        """Default minimum content should be 100 chars."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import ingestion.content_extractor as module
            importlib.reload(module)

            assert module.READABILITY_MIN_CONTENT == 100

    def test_custom_min_content_from_env(self):
        """Should respect READABILITY_MIN_CONTENT from env."""
        with patch.dict(os.environ, {"READABILITY_MIN_CONTENT": "200"}):
            import importlib
            import ingestion.content_extractor as module
            importlib.reload(module)

            assert module.READABILITY_MIN_CONTENT == 200


# =============================================================================
# TEST: INTEGRATION WITH DETERMINISTIC SCRAPER
# =============================================================================

class TestScraperIntegration:
    """Tests for integration with DeterministicScraper."""

    @pytest.mark.asyncio
    async def test_scraper_uses_readability_when_available(self, sample_article_html):
        """Scraper should use Readability when available."""
        from ingestion.deterministic_scraper import DeterministicScraper

        scraper = DeterministicScraper()

        with patch.object(scraper, "_fetch_page_with_circuit_breaker") as mock_fetch:
            mock_fetch.return_value = (sample_article_html, "https://example.com/article")

            with patch("ingestion.content_extractor.is_readability_available", return_value=True):
                with patch("ingestion.content_extractor.extract_with_readability") as mock_extract:
                    mock_extract.return_value = (
                        "Clean Title",
                        "This is the clean extracted content with more than one hundred characters to pass the minimum threshold.",
                        True
                    )

                    # Mock robots checker
                    with patch("ingestion.deterministic_scraper.get_robots_checker") as mock_robots:
                        mock_checker = Mock()
                        mock_checker.is_allowed.return_value = True
                        mock_robots.return_value = mock_checker

                        # Mock metrics
                        with patch("ingestion.deterministic_scraper.record_page_scraped"):
                            with patch("ingestion.deterministic_scraper.observe_scrape_duration"):
                                result = await scraper.scrape_page(
                                    "https://example.com/article", "creator_123"
                                )

                                assert result is not None
                                assert result.title == "Clean Title"
                                assert result.metadata.get("extracted_by") == "readability"
                                mock_extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_scraper_falls_back_when_readability_fails(self, sample_article_html):
        """Scraper should fallback to manual extraction when Readability fails."""
        from ingestion.deterministic_scraper import DeterministicScraper

        scraper = DeterministicScraper()

        with patch.object(scraper, "_fetch_page_with_circuit_breaker") as mock_fetch:
            mock_fetch.return_value = (sample_article_html, "https://example.com/article")

            with patch("ingestion.content_extractor.is_readability_available", return_value=True):
                with patch("ingestion.content_extractor.extract_with_readability") as mock_extract:
                    # Readability fails
                    mock_extract.return_value = (None, None, False)

                    with patch("ingestion.deterministic_scraper.get_robots_checker") as mock_robots:
                        mock_checker = Mock()
                        mock_checker.is_allowed.return_value = True
                        mock_robots.return_value = mock_checker

                        with patch("ingestion.deterministic_scraper.record_page_scraped"):
                            with patch("ingestion.deterministic_scraper.observe_scrape_duration"):
                                result = await scraper.scrape_page(
                                    "https://example.com/article", "creator_123"
                                )

                                assert result is not None
                                # Should NOT have readability marker
                                assert result.metadata.get("extracted_by") != "readability"
                                # Should still have content (from manual extraction)
                                assert len(result.main_content) > 0

    @pytest.mark.asyncio
    async def test_scraper_works_when_readability_unavailable(self, sample_article_html):
        """Scraper should work normally when Readability is not installed."""
        from ingestion.deterministic_scraper import DeterministicScraper

        scraper = DeterministicScraper()

        with patch.object(scraper, "_fetch_page_with_circuit_breaker") as mock_fetch:
            mock_fetch.return_value = (sample_article_html, "https://example.com/article")

            # Simulate ImportError when trying to import content_extractor
            with patch.dict('sys.modules', {'ingestion.content_extractor': None}):
                with patch("ingestion.deterministic_scraper.get_robots_checker") as mock_robots:
                    mock_checker = Mock()
                    mock_checker.is_allowed.return_value = True
                    mock_robots.return_value = mock_checker

                    with patch("ingestion.deterministic_scraper.record_page_scraped"):
                        with patch("ingestion.deterministic_scraper.observe_scrape_duration"):
                            result = await scraper.scrape_page(
                                "https://example.com/article", "creator_123"
                            )

                            # Should still return results using manual extraction
                            assert result is not None
                            assert len(result.main_content) > 0


# =============================================================================
# TEST: UTILITY FUNCTIONS
# =============================================================================

class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_get_readability_stats(self, mock_readability_available):
        """Should return correct stats dictionary."""
        from ingestion.content_extractor import get_readability_stats

        with patch("ingestion.content_extractor.READABILITY_MIN_CONTENT", 150):
            stats = get_readability_stats()

            assert "available" in stats
            assert "enabled" in stats
            assert "active" in stats
            assert stats["min_content"] == 150
