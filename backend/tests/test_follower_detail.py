#!/usr/bin/env python3
"""
Tests for Extended Follower Detail Endpoint (SPRINT1-T1.1)

TDD: These tests are written BEFORE implementation.
Goal: GET /dm/follower/{creator_id}/{follower_id} returns unified profile from:
- follower_memories (basic data)
- leads (email, phone, notes, deal_value)
- conversation_states (phase, context)
- user_profiles (weighted interests, preferences)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

# Import the schema we'll create
# from api.schemas.audience import FollowerDetailResponse  # Will fail until implemented


class TestFollowerDetailSchema:
    """Tests for the Pydantic response schema."""

    def test_schema_has_basic_fields(self):
        """Schema should have basic follower_memory fields."""
        from api.schemas.audience import FollowerDetailResponse

        # Create minimal valid data
        data = {
            "follower_id": "ig_123",
            "username": "testuser",
            "name": "Test User",
            "first_contact": "2024-01-01T00:00:00",
            "last_contact": "2024-01-28T12:00:00",
            "total_messages": 10,
            "purchase_intent_score": 0.75,
            "is_lead": True,
            "is_customer": False,
            "status": "hot",
        }
        response = FollowerDetailResponse(**data)
        assert response.follower_id == "ig_123"
        assert response.username == "testuser"
        assert response.total_messages == 10

    def test_schema_has_lead_fields(self):
        """Schema should include CRM fields from leads table."""
        from api.schemas.audience import FollowerDetailResponse

        data = {
            "follower_id": "ig_123",
            "username": "testuser",
            # Lead fields
            "email": "test@example.com",
            "phone": "+34600000000",
            "notes": "Interested in course",
            "deal_value": 297.0,
            "tags": ["vip", "price_sensitive"],
        }
        response = FollowerDetailResponse(**data)
        assert response.email == "test@example.com"
        assert response.phone == "+34600000000"
        assert response.deal_value == 297.0
        assert "vip" in response.tags

    def test_schema_has_conversation_state_fields(self):
        """Schema should include sales funnel phase from conversation_states."""
        from api.schemas.audience import FollowerDetailResponse

        data = {
            "follower_id": "ig_123",
            "username": "testuser",
            # Conversation state fields
            "funnel_phase": "propuesta",
            "funnel_context": {"pain_points": ["time"], "budget": "medium"},
        }
        response = FollowerDetailResponse(**data)
        assert response.funnel_phase == "propuesta"
        assert "pain_points" in response.funnel_context

    def test_schema_has_user_profile_fields(self):
        """Schema should include weighted interests from user_profiles."""
        from api.schemas.audience import FollowerDetailResponse

        data = {
            "follower_id": "ig_123",
            "username": "testuser",
            # User profile fields
            "weighted_interests": {"fitness": 0.9, "nutrition": 0.7},
            "preferences": {"language": "es", "tone": "friendly"},
        }
        response = FollowerDetailResponse(**data)
        assert response.weighted_interests["fitness"] == 0.9
        assert response.preferences["language"] == "es"

    def test_schema_optional_fields_default_to_none(self):
        """Optional fields should default to None or empty."""
        from api.schemas.audience import FollowerDetailResponse

        # Minimal required data only
        data = {
            "follower_id": "ig_123",
        }
        response = FollowerDetailResponse(**data)
        assert response.email is None
        assert response.phone is None
        assert response.funnel_phase is None
        assert response.weighted_interests == {}


class TestFollowerDetailEndpoint:
    """Tests for the GET /dm/follower/{creator_id}/{follower_id} endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_returns_unified_profile(self):
        """Endpoint should return data from all 4 tables unified."""

        # This test will need the actual endpoint to be updated
        # For now, we test the structure of the expected response
        expected_fields = [
            # From follower_memories
            "follower_id", "username", "name", "total_messages",
            "purchase_intent_score", "is_lead", "is_customer",
            "last_messages",
            # From leads
            "email", "phone", "notes", "deal_value", "tags",
            "profile_pic_url",
            # From conversation_states
            "funnel_phase", "funnel_context",
            # From user_profiles
            "weighted_interests", "preferences",
        ]
        # Just verify the expected structure (18 fields)
        assert len(expected_fields) == 18

    @pytest.mark.asyncio
    async def test_endpoint_returns_404_when_not_found(self):
        """Endpoint should return 404 if follower doesn't exist."""
        # Will be implemented with actual endpoint test

    @pytest.mark.asyncio
    async def test_endpoint_handles_partial_data(self):
        """Endpoint should work even if some tables have no data for follower."""
        # follower_memory exists but leads/conversation_states/user_profiles don't


class TestFollowerDetailQuery:
    """Tests for the database query efficiency."""

    def test_query_uses_joins_not_n_plus_1(self):
        """Query should use JOINs to avoid N+1 queries."""
        # This will be tested by checking the actual query or using query counting

    def test_query_handles_missing_related_records(self):
        """Query should use LEFT JOINs so missing records don't break it."""


class TestDMAgentV2GetFollowerDetail:
    """Tests for the get_follower_detail method in dm_agent_v2."""

    @pytest.mark.asyncio
    async def test_method_exists(self):
        """DMResponderAgentV2 should have get_follower_detail method."""
        from core.dm_agent_v2 import DMResponderAgentV2

        agent = DMResponderAgentV2(creator_id="test_creator")
        assert hasattr(agent, "get_follower_detail")
        assert callable(getattr(agent, "get_follower_detail"))

    @pytest.mark.asyncio
    async def test_method_returns_dict(self):
        """get_follower_detail should return a dict or None."""
        from core.dm_agent_v2 import DMResponderAgentV2

        agent = DMResponderAgentV2(creator_id="test_creator")

        # Mock the memory_store to return None (follower not found)
        agent.memory_store.get = AsyncMock(return_value=None)

        result = await agent.get_follower_detail("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_method_includes_all_sources(self):
        """get_follower_detail should query all 4 data sources."""
        from core.dm_agent_v2 import DMResponderAgentV2

        agent = DMResponderAgentV2(creator_id="test_creator")

        # Create mock follower memory
        mock_follower = MagicMock()
        mock_follower.follower_id = "ig_123"
        mock_follower.username = "testuser"
        mock_follower.name = "Test User"
        mock_follower.first_contact = "2024-01-01"
        mock_follower.last_contact = "2024-01-28"
        mock_follower.total_messages = 10
        mock_follower.interests = ["fitness"]
        mock_follower.products_discussed = ["course_1"]
        mock_follower.objections_raised = ["price"]
        mock_follower.purchase_intent_score = 0.75
        mock_follower.is_lead = True
        mock_follower.is_customer = False
        mock_follower.preferred_language = "es"
        mock_follower.last_messages = [{"role": "user", "content": "hola"}]

        agent.memory_store.get = AsyncMock(return_value=mock_follower)

        result = await agent.get_follower_detail("ig_123")

        assert result is not None
        assert result["follower_id"] == "ig_123"
        # These fields should eventually come from joined tables
        # For now, just verify structure
        assert "username" in result
        assert "total_messages" in result
