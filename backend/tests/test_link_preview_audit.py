"""Audit tests for core/link_preview.py."""

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Test 1: Init / Import
# ---------------------------------------------------------------------------


class TestLinkPreviewImport:
    """Verify module imports and constants."""

    def test_import_module(self):
        from core.link_preview import (
            INSTAGRAM_DOMAINS,
            TIKTOK_DOMAINS,
            URL_PATTERN,
            YOUTUBE_DOMAINS,
        )

        # Domain lists should be populated
        assert "instagram.com" in INSTAGRAM_DOMAINS
        assert "youtube.com" in YOUTUBE_DOMAINS
        assert "tiktok.com" in TIKTOK_DOMAINS

        # URL_PATTERN should be a compiled regex
        assert hasattr(URL_PATTERN, "findall")


# ---------------------------------------------------------------------------
# Test 2: Happy Path -- URL extraction and platform detection
# ---------------------------------------------------------------------------


class TestUrlExtractionHappyPath:
    """Test URL extraction from text and platform detection."""

    def test_extract_urls_from_text(self):
        from core.link_preview import extract_urls

        text = "Check out https://example.com and http://test.org/page for info"
        urls = extract_urls(text)
        assert len(urls) == 2
        assert "https://example.com" in urls
        assert "http://test.org/page" in urls

    def test_extract_urls_no_urls(self):
        from core.link_preview import extract_urls

        assert extract_urls("Just plain text") == []
        assert extract_urls("") == []
        assert extract_urls(None) == []

    def test_detect_platform_instagram(self):
        from core.link_preview import detect_platform

        assert detect_platform("https://www.instagram.com/p/abc123") == "instagram"
        assert detect_platform("https://instagr.am/p/abc") == "instagram"

    def test_detect_platform_youtube(self):
        from core.link_preview import detect_platform

        assert detect_platform("https://www.youtube.com/watch?v=abc") == "youtube"
        assert detect_platform("https://youtu.be/abc") == "youtube"

    def test_detect_platform_tiktok(self):
        from core.link_preview import detect_platform

        assert detect_platform("https://www.tiktok.com/@user/video/123") == "tiktok"
        assert detect_platform("https://vm.tiktok.com/abc") == "tiktok"

    def test_detect_platform_generic(self):
        from core.link_preview import detect_platform

        assert detect_platform("https://example.com") == "web"

    def test_get_domain(self):
        from core.link_preview import get_domain

        assert get_domain("https://www.example.com/path") == "www.example.com"
        assert get_domain("http://TEST.ORG") == "test.org"


# ---------------------------------------------------------------------------
# Test 3: Edge Case -- Invalid URL handling
# ---------------------------------------------------------------------------


class TestLinkPreviewEdgeCases:
    """Edge cases for URL handling."""

    def test_get_domain_empty_string(self):
        from core.link_preview import get_domain

        result = get_domain("")
        assert result == ""

    def test_has_link_preview_none_metadata(self):
        from core.link_preview import has_link_preview

        assert has_link_preview(None) is False
        assert has_link_preview({}) is False
        assert has_link_preview({"other_key": "value"}) is False

    def test_has_link_preview_with_data(self):
        from core.link_preview import has_link_preview

        assert has_link_preview({"link_preview": {"url": "https://x.com"}}) is True
        assert has_link_preview({"link_previews": [{"url": "https://x.com"}]}) is True

    def test_extract_urls_ignores_malformed(self):
        """Only properly formed URLs should be extracted."""
        from core.link_preview import extract_urls

        # Text with partial URL-like strings
        text = "Visit ftp://not-http.com or just example.com"
        urls = extract_urls(text)
        # ftp is not matched by the http/https pattern
        assert all(u.startswith("http") for u in urls)


# ---------------------------------------------------------------------------
# Test 4: Error Handling -- Timeout in extract_link_preview
# ---------------------------------------------------------------------------


class TestLinkPreviewTimeout:
    """Verify timeout and error handling in extract_link_preview."""

    @pytest.mark.asyncio
    async def test_timeout_returns_none_after_retries(self):
        pass

        import httpx
        from core.link_preview import extract_link_preview

        with patch(
            "core.link_preview._fetch_og_metadata",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("Timeout"),
        ), patch("asyncio.sleep", new_callable=AsyncMock):
            result = await extract_link_preview("https://slow-site.com", timeout=1.0, max_retries=2)

        assert result is None

    @pytest.mark.asyncio
    async def test_generic_exception_returns_none(self):
        from core.link_preview import extract_link_preview

        with patch(
            "core.link_preview._fetch_og_metadata",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Connection failed"),
        ):
            result = await extract_link_preview("https://broken.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_cdn_urls_skipped(self):
        """Instagram CDN URLs should return None immediately."""
        from core.link_preview import _fetch_og_metadata

        result = await _fetch_og_metadata(
            "https://scontent.cdninstagram.com/v/image.jpg", timeout=5.0
        )
        assert result is None

        result2 = await _fetch_og_metadata("https://scontent.fbcdn.net/v/image.jpg", timeout=5.0)
        assert result2 is None


# ---------------------------------------------------------------------------
# Test 5: Integration Check -- extract_previews_from_text with mocked fetch
# ---------------------------------------------------------------------------


class TestExtractPreviewsIntegration:
    """Integration: extract_previews_from_text processes multiple URLs."""

    @pytest.mark.asyncio
    async def test_extract_previews_limits_to_3(self):
        from core.link_preview import extract_previews_from_text

        text = "Links: https://a.com https://b.com https://c.com " "https://d.com https://e.com"

        mock_preview = {
            "url": "https://example.com",
            "title": "Example",
            "platform": "web",
        }

        with patch(
            "core.link_preview.extract_link_preview",
            new_callable=AsyncMock,
            return_value=mock_preview,
        ) as mock_fn:
            result = await extract_previews_from_text(text)

        # Should process at most 3 URLs
        assert mock_fn.call_count == 3
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_extract_previews_filters_none(self):
        from core.link_preview import extract_previews_from_text

        text = "Links: https://a.com https://b.com"

        # First URL returns preview, second returns None
        side_effects = [
            {"url": "https://a.com", "title": "A", "platform": "web"},
            None,
        ]

        with patch(
            "core.link_preview.extract_link_preview",
            new_callable=AsyncMock,
            side_effect=side_effects,
        ):
            result = await extract_previews_from_text(text)

        assert len(result) == 1
        assert result[0]["title"] == "A"

    @pytest.mark.asyncio
    async def test_extract_previews_empty_text(self):
        from core.link_preview import extract_previews_from_text

        result = await extract_previews_from_text("No links here")
        assert result == []
