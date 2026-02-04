"""Tests for Instagram Post Fetcher.

TDD: Tests written FIRST before implementation.
Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestInstagramPostFetcher:
    """Test suite for Instagram post fetching."""

    @pytest.mark.asyncio
    async def test_fetch_recent_posts_success(self):
        """Should fetch posts from Instagram API."""
        from services.instagram_post_fetcher import InstagramPostFetcher

        fetcher = InstagramPostFetcher()

        mock_response = {
            "data": [
                {
                    "id": "post1",
                    "caption": "🚀 Lanzamos curso de meditación!",
                    "timestamp": "2026-02-04T10:00:00+0000",
                    "media_type": "IMAGE",
                },
                {
                    "id": "post2",
                    "caption": "Preparando el retiro en Bali",
                    "timestamp": "2026-02-03T15:00:00+0000",
                    "media_type": "CAROUSEL_ALBUM",
                },
            ]
        }

        with patch.object(fetcher, "_get_creator_credentials") as mock_creds:
            mock_creds.return_value = ("token123", "user123")
            with patch.object(fetcher, "_call_instagram_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = mock_response

                posts = await fetcher.fetch_recent_posts("stefan", days=7, limit=10)

                assert len(posts) == 2
                assert posts[0]["id"] == "post1"
                assert "meditación" in posts[0]["caption"]

    @pytest.mark.asyncio
    async def test_fetch_recent_posts_empty(self):
        """Should return empty list when no posts."""
        from services.instagram_post_fetcher import InstagramPostFetcher

        fetcher = InstagramPostFetcher()

        with patch.object(fetcher, "_call_instagram_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = {"data": []}

            posts = await fetcher.fetch_recent_posts("stefan", days=7)

            assert posts == []

    @pytest.mark.asyncio
    async def test_fetch_recent_posts_api_error(self):
        """Should handle API errors gracefully."""
        from services.instagram_post_fetcher import InstagramPostFetcher

        fetcher = InstagramPostFetcher()

        with patch.object(fetcher, "_call_instagram_api", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = Exception("API Error")

            posts = await fetcher.fetch_recent_posts("stefan", days=7)

            assert posts == []

    @pytest.mark.asyncio
    async def test_fetch_formats_posts_correctly(self):
        """Should format posts with required fields."""
        from services.instagram_post_fetcher import InstagramPostFetcher

        fetcher = InstagramPostFetcher()

        mock_response = {
            "data": [
                {
                    "id": "123",
                    "caption": "Test post",
                    "timestamp": "2026-02-04T12:00:00+0000",
                    "media_type": "VIDEO",
                    "permalink": "https://instagram.com/p/123",
                }
            ]
        }

        with patch.object(fetcher, "_get_creator_credentials") as mock_creds:
            mock_creds.return_value = ("token123", "user123")
            with patch.object(fetcher, "_call_instagram_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = mock_response

                posts = await fetcher.fetch_recent_posts("stefan", days=7)

                assert "id" in posts[0]
                assert "caption" in posts[0]
                assert "timestamp" in posts[0]
                assert "media_type" in posts[0]

    @pytest.mark.asyncio
    async def test_get_creator_token(self):
        """Should retrieve Instagram token for creator."""
        from services.instagram_post_fetcher import InstagramPostFetcher

        fetcher = InstagramPostFetcher()

        with patch("services.instagram_post_fetcher.get_session") as mock_session:
            session = MagicMock()
            mock_session.return_value = session

            mock_creator = MagicMock()
            mock_creator.instagram_token = "test_token_123"
            mock_creator.instagram_user_id = "user_123"
            session.query.return_value.filter_by.return_value.first.return_value = mock_creator

            token, user_id = fetcher._get_creator_credentials("stefan")

            assert token == "test_token_123"
            assert user_id == "user_123"

    @pytest.mark.asyncio
    async def test_filters_old_posts(self):
        """Should filter posts older than specified days."""
        from services.instagram_post_fetcher import InstagramPostFetcher

        fetcher = InstagramPostFetcher()

        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
            "%Y-%m-%dT%H:%M:%S+0000"
        )
        recent_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%S+0000"
        )

        mock_response = {
            "data": [
                {"id": "old", "caption": "Old post", "timestamp": old_date, "media_type": "IMAGE"},
                {"id": "new", "caption": "New post", "timestamp": recent_date, "media_type": "IMAGE"},
            ]
        }

        with patch.object(fetcher, "_get_creator_credentials") as mock_creds:
            mock_creds.return_value = ("token123", "user123")
            with patch.object(fetcher, "_call_instagram_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = mock_response

                # Only fetch posts from last 7 days
                posts = await fetcher.fetch_recent_posts("stefan", days=7)

                # Should filter out the old post
                assert len(posts) == 1
                assert posts[0]["id"] == "new"
