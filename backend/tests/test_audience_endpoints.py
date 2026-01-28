#!/usr/bin/env python3
"""
Tests for Audience Endpoints (SPRINT1-T1.3)

TDD: Tests written BEFORE implementation.
Endpoints:
- GET /audience/{creator_id}/profile/{follower_id}
- GET /audience/{creator_id}/segments
- GET /audience/{creator_id}/segments/{segment_name}
- GET /audience/{creator_id}/aggregated
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


class TestAudienceRouterImport:
    """Test that the router can be imported."""

    def test_router_imports(self):
        """Audience router should be importable."""
        from api.routers.audience import router
        assert router is not None

    def test_router_has_correct_prefix(self):
        """Router should have /audience prefix."""
        from api.routers.audience import router
        assert router.prefix == "/audience"


class TestProfileEndpoint:
    """Tests for GET /audience/{creator_id}/profile/{follower_id}"""

    def test_profile_endpoint_exists(self):
        """Profile endpoint should exist."""
        from api.routers.audience import router

        routes = [r.path for r in router.routes]
        # Routes include the prefix, so check for partial match
        assert any("profile" in r and "follower_id" in r for r in routes)

    @pytest.mark.asyncio
    async def test_profile_returns_audience_profile(self):
        """Should return AudienceProfile with all intelligence fields."""
        from api.routers.audience import get_profile
        from core.audience_intelligence import AudienceProfile

        # Mock the builder
        mock_profile = AudienceProfile(
            follower_id="ig_123",
            username="testuser",
            name="Test User",
            narrative="Test. Quiere bajar peso.",
            segments=["warm_lead"],
            recommended_action="Continúa nurturing",
            action_priority="medium",
        )

        with patch("api.routers.audience.get_audience_profile_builder") as mock_builder:
            mock_instance = MagicMock()
            mock_instance.build_profile = AsyncMock(return_value=mock_profile)
            mock_builder.return_value = mock_instance

            result = await get_profile("test_creator", "ig_123")

            assert result["follower_id"] == "ig_123"
            assert "narrative" in result
            assert "segments" in result
            assert "recommended_action" in result

    @pytest.mark.asyncio
    async def test_profile_returns_404_when_not_found(self):
        """Should return 404 when follower not found."""
        from api.routers.audience import get_profile
        from fastapi import HTTPException

        with patch("api.routers.audience.get_audience_profile_builder") as mock_builder:
            mock_instance = MagicMock()
            mock_instance.build_profile = AsyncMock(return_value=None)
            mock_builder.return_value = mock_instance

            with pytest.raises(HTTPException) as exc_info:
                await get_profile("test_creator", "nonexistent")

            assert exc_info.value.status_code == 404


class TestSegmentsEndpoint:
    """Tests for GET /audience/{creator_id}/segments"""

    def test_segments_endpoint_exists(self):
        """Segments endpoint should exist."""
        from api.routers.audience import router

        routes = [r.path for r in router.routes]
        # Check for segments endpoint (not segment_name variant)
        assert any("/segments" in r and "segment_name" not in r for r in routes)

    @pytest.mark.asyncio
    async def test_segments_returns_list_with_counts(self):
        """Should return list of segments with counts."""
        from api.routers.audience import get_segments

        with patch("api.routers.audience.get_segment_counts") as mock_counts:
            mock_counts.return_value = [
                {"segment": "hot_lead", "count": 8},
                {"segment": "ghost", "count": 45},
                {"segment": "customer", "count": 12},
            ]

            result = await get_segments("test_creator")

            assert isinstance(result, list)
            assert len(result) >= 3
            assert all("segment" in s and "count" in s for s in result)


class TestSegmentUsersEndpoint:
    """Tests for GET /audience/{creator_id}/segments/{segment_name}"""

    def test_segment_users_endpoint_exists(self):
        """Segment users endpoint should exist."""
        from api.routers.audience import router

        routes = [r.path for r in router.routes]
        # Check for segment_name variant
        assert any("segment_name" in r for r in routes)

    @pytest.mark.asyncio
    async def test_segment_users_returns_profiles(self):
        """Should return list of profiles for segment."""
        from api.routers.audience import get_segment_users

        # Mock returns dicts (as the actual function returns)
        mock_profiles = [
            {"follower_id": "ig_1", "username": "user1", "segments": ["hot_lead"]},
            {"follower_id": "ig_2", "username": "user2", "segments": ["hot_lead"]},
        ]

        with patch("api.routers.audience.get_profiles_by_segment") as mock_get:
            mock_get.return_value = mock_profiles

            result = await get_segment_users("test_creator", "hot_lead", limit=20)

            assert isinstance(result, list)
            assert len(result) == 2
            assert all("follower_id" in p for p in result)

    @pytest.mark.asyncio
    async def test_segment_users_respects_limit(self):
        """Should respect the limit parameter."""
        from api.routers.audience import get_segment_users

        with patch("api.routers.audience.get_profiles_by_segment") as mock_get:
            # Return 5 profiles
            mock_get.return_value = [{"follower_id": f"ig_{i}"} for i in range(5)]

            result = await get_segment_users("test_creator", "ghost", limit=3)

            # The mock was called with limit
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[1].get("limit", call_args[0][2] if len(call_args[0]) > 2 else 20) == 3


class TestAggregatedEndpoint:
    """Tests for GET /audience/{creator_id}/aggregated"""

    def test_aggregated_endpoint_exists(self):
        """Aggregated endpoint should exist."""
        from api.routers.audience import router

        routes = [r.path for r in router.routes]
        assert any("aggregated" in r for r in routes)

    @pytest.mark.asyncio
    async def test_aggregated_returns_metrics(self):
        """Should return aggregated metrics."""
        from api.routers.audience import get_aggregated

        with patch("api.routers.audience.get_aggregated_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "total_followers": 487,
                "top_interests": [{"interest": "nutricion", "count": 156}],
                "top_objections": [{"objection": "precio", "count": 52}],
                "funnel_distribution": {"inicio": 45, "propuesta": 23},
            }

            result = await get_aggregated("test_creator")

            assert "total_followers" in result
            assert "top_interests" in result
            assert "top_objections" in result
            assert "funnel_distribution" in result

    @pytest.mark.asyncio
    async def test_aggregated_top_interests_sorted(self):
        """Top interests should be sorted by count descending."""
        from api.routers.audience import get_aggregated

        with patch("api.routers.audience.get_aggregated_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "total_followers": 100,
                "top_interests": [
                    {"interest": "fitness", "count": 80},
                    {"interest": "nutricion", "count": 50},
                    {"interest": "yoga", "count": 30},
                ],
                "top_objections": [],
                "funnel_distribution": {},
            }

            result = await get_aggregated("test_creator")

            interests = result["top_interests"]
            counts = [i["count"] for i in interests]
            assert counts == sorted(counts, reverse=True)


class TestRouterRegistration:
    """Tests for router registration in main app."""

    def test_router_can_be_included(self):
        """Router should be includable in FastAPI app."""
        from fastapi import FastAPI
        from api.routers.audience import router

        app = FastAPI()
        # Should not raise
        app.include_router(router)

        # Check routes are registered
        routes = [r.path for r in app.routes]
        assert any("/audience" in r for r in routes)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_segment_returns_empty_list(self):
        """Should return empty list for segment with no users."""
        from api.routers.audience import get_segment_users

        with patch("api.routers.audience.get_profiles_by_segment") as mock_get:
            mock_get.return_value = []

            result = await get_segment_users("test_creator", "nonexistent_segment", limit=20)

            assert result == []

    @pytest.mark.asyncio
    async def test_aggregated_handles_no_followers(self):
        """Should handle case with no followers gracefully."""
        from api.routers.audience import get_aggregated

        with patch("api.routers.audience.get_aggregated_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "total_followers": 0,
                "top_interests": [],
                "top_objections": [],
                "funnel_distribution": {},
            }

            result = await get_aggregated("new_creator")

            assert result["total_followers"] == 0
            assert result["top_interests"] == []
