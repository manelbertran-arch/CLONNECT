"""Tests for PostContext auto-refresh scheduler.

TDD: Tests written FIRST before implementation.
Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPostContextScheduler:
    """Test suite for auto-refresh scheduler."""

    @pytest.mark.asyncio
    async def test_refresh_expired_contexts(self):
        """Should refresh all expired contexts."""
        from services.post_context_scheduler import refresh_expired_contexts

        expired_contexts = [
            {"creator_id": "stefan", "expires_at": datetime.now(timezone.utc) - timedelta(hours=1)},
            {"creator_id": "maria", "expires_at": datetime.now(timezone.utc) - timedelta(hours=2)},
        ]

        with patch("services.post_context_scheduler.get_expired_contexts") as mock_expired:
            mock_expired.return_value = expired_contexts
            with patch("services.post_context_scheduler.PostContextService") as MockService:
                mock_service = MagicMock()
                mock_service.force_refresh = AsyncMock(return_value={"active_promotion": None})
                MockService.return_value = mock_service

                result = await refresh_expired_contexts()

                assert result["refreshed"] == 2
                assert mock_service.force_refresh.call_count == 2

    @pytest.mark.asyncio
    async def test_refresh_handles_errors(self):
        """Should continue on errors and report them."""
        from services.post_context_scheduler import refresh_expired_contexts

        expired_contexts = [
            {"creator_id": "stefan"},
            {"creator_id": "failing_creator"},
        ]

        with patch("services.post_context_scheduler.get_expired_contexts") as mock_expired:
            mock_expired.return_value = expired_contexts
            with patch("services.post_context_scheduler.PostContextService") as MockService:
                mock_service = MagicMock()
                mock_service.force_refresh = AsyncMock(
                    side_effect=[{"success": True}, Exception("Refresh failed")]
                )
                MockService.return_value = mock_service

                result = await refresh_expired_contexts()

                # Should have tried both
                assert result["refreshed"] == 1
                assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_refresh_empty_list(self):
        """Should handle empty expired list."""
        from services.post_context_scheduler import refresh_expired_contexts

        with patch("services.post_context_scheduler.get_expired_contexts") as mock_expired:
            mock_expired.return_value = []

            result = await refresh_expired_contexts()

            assert result["refreshed"] == 0
            assert result["errors"] == 0
