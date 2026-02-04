"""Tests for PostContext Service.

TDD: Tests written FIRST before implementation.
Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.post_context import PostContext


class TestPostContextService:
    """Test suite for PostContext orchestration service."""

    @pytest.mark.asyncio
    async def test_get_or_refresh_returns_cached(self):
        """Should return cached context if fresh."""
        from services.post_context_service import PostContextService

        service = PostContextService()

        cached_context = {
            "creator_id": "stefan",
            "active_promotion": "Cached promo",
            "context_instructions": "Cached instructions",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=4),
        }

        with patch("services.post_context_service.get_post_context") as mock_get:
            mock_get.return_value = cached_context

            result = await service.get_or_refresh("stefan")

            assert result["active_promotion"] == "Cached promo"
            mock_get.assert_called_once_with("stefan")

    @pytest.mark.asyncio
    async def test_get_or_refresh_refreshes_expired(self):
        """Should refresh context if expired."""
        from services.post_context_service import PostContextService

        service = PostContextService()

        expired_context = {
            "creator_id": "stefan",
            "active_promotion": "Old promo",
            "context_instructions": "Old instructions",
            "expires_at": datetime.now(timezone.utc) - timedelta(hours=1),
        }

        fresh_analysis = {
            "active_promotion": "New promo",
            "context_instructions": "New instructions",
            "recent_topics": ["topic1"],
        }

        with patch("services.post_context_service.get_post_context") as mock_get:
            mock_get.return_value = expired_context
            with patch.object(service, "_refresh_context", new_callable=AsyncMock) as mock_refresh:
                mock_refresh.return_value = fresh_analysis

                result = await service.get_or_refresh("stefan")

                assert result["active_promotion"] == "New promo"
                mock_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_refresh_creates_new(self):
        """Should create new context if none exists."""
        from services.post_context_service import PostContextService

        service = PostContextService()

        fresh_analysis = {
            "active_promotion": "Fresh promo",
            "context_instructions": "Fresh instructions",
            "recent_topics": [],
        }

        with patch("services.post_context_service.get_post_context") as mock_get:
            mock_get.return_value = None
            with patch.object(service, "_refresh_context", new_callable=AsyncMock) as mock_refresh:
                mock_refresh.return_value = fresh_analysis

                result = await service.get_or_refresh("stefan")

                assert result["active_promotion"] == "Fresh promo"

    @pytest.mark.asyncio
    async def test_refresh_context_fetches_and_analyzes(self):
        """Should fetch posts and analyze them."""
        from services.post_context_service import PostContextService

        service = PostContextService()

        mock_posts = [
            {"id": "1", "caption": "Launch post!", "timestamp": "2026-02-04T10:00:00+0000"}
        ]

        mock_analysis = {
            "active_promotion": "Launch",
            "context_instructions": "Mention the launch",
            "recent_topics": ["launch"],
        }

        with patch("services.post_context_service.fetch_creator_posts", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_posts
            with patch("services.post_context_service.analyze_creator_posts", new_callable=AsyncMock) as mock_analyze:
                mock_analyze.return_value = mock_analysis
                with patch("services.post_context_service.create_post_context") as mock_create:
                    mock_create.return_value = True

                    result = await service._refresh_context("stefan")

                    mock_fetch.assert_called_once()
                    mock_analyze.assert_called_once_with(mock_posts)
                    assert result["active_promotion"] == "Launch"

    @pytest.mark.asyncio
    async def test_get_prompt_instructions(self):
        """Should return prompt instructions from context."""
        from services.post_context_service import PostContextService

        service = PostContextService()

        context = {
            "creator_id": "stefan",
            "active_promotion": "Curso 20% dto",
            "promotion_urgency": "48h",
            "recent_topics": ["meditación"],
            "context_instructions": "Menciona el curso",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=6),
        }

        with patch("services.post_context_service.get_post_context") as mock_get:
            mock_get.return_value = context

            instructions = await service.get_prompt_instructions("stefan")

            assert "Curso 20%" in instructions
            assert "meditación" in instructions.lower() or "Menciona" in instructions

    @pytest.mark.asyncio
    async def test_get_prompt_instructions_no_context(self):
        """Should return default when no context."""
        from services.post_context_service import PostContextService

        service = PostContextService()

        with patch("services.post_context_service.get_post_context") as mock_get:
            mock_get.return_value = None

            instructions = await service.get_prompt_instructions("stefan")

            assert instructions is not None
            assert "Sin contexto" in instructions or len(instructions) > 0
