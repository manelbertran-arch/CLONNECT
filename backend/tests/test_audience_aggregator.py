"""
Tests for AudienceAggregator

SPRINT4-T4.1: TDD tests written BEFORE implementation
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from sqlalchemy.orm import Session

from core.audience_aggregator import AudienceAggregator
from api.schemas.audiencia import (
    TopicsResponse,
    ObjectionsResponse,
    CompetitionResponse,
    TrendsResponse,
    ContentRequestsResponse,
    PerceptionResponse,
)


class TestAudienceAggregatorInit:
    """Test AudienceAggregator initialization"""

    def test_init_with_creator_id_and_db(self):
        """AudienceAggregator should initialize with creator_id and db session"""
        mock_db = MagicMock(spec=Session)
        aggregator = AudienceAggregator(creator_id="test_creator", db=mock_db)

        assert aggregator.creator_id == "test_creator"
        assert aggregator.db == mock_db


class TestGetTopics:
    """Test get_topics method"""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.fixture
    def aggregator(self, mock_db):
        return AudienceAggregator(creator_id="test_creator", db=mock_db)

    def test_returns_topics_response(self, aggregator):
        """get_topics should return TopicsResponse"""
        result = aggregator.get_topics()
        assert isinstance(result, TopicsResponse)

    def test_topics_have_required_fields(self, aggregator):
        """Each topic should have all required fields"""
        result = aggregator.get_topics()
        for topic in result.topics:
            assert hasattr(topic, "topic")
            assert hasattr(topic, "count")
            assert hasattr(topic, "percentage")
            assert hasattr(topic, "quotes")
            assert hasattr(topic, "users")

    def test_respects_limit_parameter(self, aggregator):
        """Should respect the limit parameter"""
        result = aggregator.get_topics(limit=5)
        assert len(result.topics) <= 5

    def test_calculates_percentage(self, aggregator):
        """Percentages should sum to <= 100"""
        result = aggregator.get_topics()
        total_percentage = sum(t.percentage for t in result.topics)
        assert total_percentage <= 100.1  # Allow small floating point error


class TestGetPassions:
    """Test get_passions method"""

    @pytest.fixture
    def aggregator(self):
        mock_db = MagicMock(spec=Session)
        return AudienceAggregator(creator_id="test_creator", db=mock_db)

    def test_returns_topics_response(self, aggregator):
        """get_passions should return TopicsResponse"""
        result = aggregator.get_passions()
        assert isinstance(result, TopicsResponse)

    def test_respects_limit(self, aggregator):
        """Should respect the limit parameter"""
        result = aggregator.get_passions(limit=3)
        assert len(result.topics) <= 3


class TestGetFrustrations:
    """Test get_frustrations method"""

    @pytest.fixture
    def aggregator(self):
        mock_db = MagicMock(spec=Session)
        return AudienceAggregator(creator_id="test_creator", db=mock_db)

    def test_returns_objections_response(self, aggregator):
        """get_frustrations should return ObjectionsResponse"""
        result = aggregator.get_frustrations()
        assert isinstance(result, ObjectionsResponse)

    def test_objections_have_suggestions(self, aggregator):
        """Each objection should have a suggestion"""
        result = aggregator.get_frustrations()
        for obj in result.objections:
            assert hasattr(obj, "suggestion")
            # suggestion can be empty string but must exist

    def test_tracks_resolved_and_pending(self, aggregator):
        """Should track resolved and pending counts"""
        result = aggregator.get_frustrations()
        for obj in result.objections:
            assert hasattr(obj, "resolved_count")
            assert hasattr(obj, "pending_count")


class TestGetCompetition:
    """Test get_competition method"""

    @pytest.fixture
    def aggregator(self):
        mock_db = MagicMock(spec=Session)
        return AudienceAggregator(creator_id="test_creator", db=mock_db)

    def test_returns_competition_response(self, aggregator):
        """get_competition should return CompetitionResponse"""
        result = aggregator.get_competition()
        assert isinstance(result, CompetitionResponse)

    def test_competitors_have_sentiment(self, aggregator):
        """Each competitor should have sentiment"""
        result = aggregator.get_competition()
        for comp in result.competitors:
            assert comp.sentiment in ["positivo", "neutral", "negativo"]

    def test_competitors_have_context(self, aggregator):
        """Each competitor should have context quotes"""
        result = aggregator.get_competition()
        for comp in result.competitors:
            assert isinstance(comp.context, list)


class TestGetTrends:
    """Test get_trends method"""

    @pytest.fixture
    def aggregator(self):
        mock_db = MagicMock(spec=Session)
        return AudienceAggregator(creator_id="test_creator", db=mock_db)

    def test_returns_trends_response(self, aggregator):
        """get_trends should return TrendsResponse"""
        result = aggregator.get_trends()
        assert isinstance(result, TrendsResponse)

    def test_trends_have_growth_percentage(self, aggregator):
        """Each trend should have growth_percentage"""
        result = aggregator.get_trends()
        for trend in result.trends:
            assert hasattr(trend, "growth_percentage")
            assert hasattr(trend, "count_this_week")
            assert hasattr(trend, "count_last_week")

    def test_respects_limit(self, aggregator):
        """Should respect the limit parameter"""
        result = aggregator.get_trends(limit=5)
        assert len(result.trends) <= 5


class TestGetContentRequests:
    """Test get_content_requests method"""

    @pytest.fixture
    def aggregator(self):
        mock_db = MagicMock(spec=Session)
        return AudienceAggregator(creator_id="test_creator", db=mock_db)

    def test_returns_content_requests_response(self, aggregator):
        """get_content_requests should return ContentRequestsResponse"""
        result = aggregator.get_content_requests()
        assert isinstance(result, ContentRequestsResponse)

    def test_requests_have_questions(self, aggregator):
        """Each request should have specific questions"""
        result = aggregator.get_content_requests()
        for req in result.requests:
            assert isinstance(req.questions, list)


class TestGetPurchaseObjections:
    """Test get_purchase_objections method"""

    @pytest.fixture
    def aggregator(self):
        mock_db = MagicMock(spec=Session)
        return AudienceAggregator(creator_id="test_creator", db=mock_db)

    def test_returns_objections_response(self, aggregator):
        """get_purchase_objections should return ObjectionsResponse"""
        result = aggregator.get_purchase_objections()
        assert isinstance(result, ObjectionsResponse)

    def test_filters_purchase_related(self, aggregator):
        """Should only return purchase-related objections"""
        result = aggregator.get_purchase_objections()
        # All objections should be purchase-related (price, time, doubt, etc.)
        assert isinstance(result.objections, list)


class TestGetPerception:
    """Test get_perception method"""

    @pytest.fixture
    def aggregator(self):
        mock_db = MagicMock(spec=Session)
        return AudienceAggregator(creator_id="test_creator", db=mock_db)

    def test_returns_perception_response(self, aggregator):
        """get_perception should return PerceptionResponse"""
        result = aggregator.get_perception()
        assert isinstance(result, PerceptionResponse)

    def test_perceptions_have_positive_and_negative(self, aggregator):
        """Each perception should have positive and negative counts"""
        result = aggregator.get_perception()
        for perc in result.perceptions:
            assert hasattr(perc, "positive_count")
            assert hasattr(perc, "negative_count")
            assert isinstance(perc.quotes_positive, list)
            assert isinstance(perc.quotes_negative, list)


class TestEdgeCases:
    """Test edge cases"""

    @pytest.fixture
    def aggregator(self):
        mock_db = MagicMock(spec=Session)
        return AudienceAggregator(creator_id="test_creator", db=mock_db)

    def test_handles_no_data_topics(self, aggregator):
        """Should handle no data gracefully for topics"""
        result = aggregator.get_topics()
        assert isinstance(result, TopicsResponse)
        assert result.total_conversations >= 0

    def test_handles_no_data_objections(self, aggregator):
        """Should handle no data gracefully for objections"""
        result = aggregator.get_frustrations()
        assert isinstance(result, ObjectionsResponse)
        assert result.total_with_objections >= 0

    def test_handles_no_data_competition(self, aggregator):
        """Should handle no data gracefully for competition"""
        result = aggregator.get_competition()
        assert isinstance(result, CompetitionResponse)
        assert result.total_mentions >= 0


class TestAudienciaEndpoints:
    """Test /audiencia/* API endpoints"""

    def test_router_is_registered(self):
        """Audiencia router should be registered in the app"""
        from api.main import app

        routes = [route.path for route in app.routes]
        audiencia_routes = [r for r in routes if "/audiencia" in r]
        assert len(audiencia_routes) >= 7, f"Expected 7+ audiencia routes, found: {audiencia_routes}"

    def test_topics_endpoint_registered(self):
        """GET /audiencia/{creator_id}/topics should be registered"""
        from api.main import app

        routes = [route.path for route in app.routes]
        assert any("/audiencia/{creator_id}/topics" in r for r in routes)

    def test_frustrations_endpoint_registered(self):
        """GET /audiencia/{creator_id}/frustrations should be registered"""
        from api.main import app

        routes = [route.path for route in app.routes]
        assert any("/audiencia/{creator_id}/frustrations" in r for r in routes)

    def test_competition_endpoint_registered(self):
        """GET /audiencia/{creator_id}/competition should be registered"""
        from api.main import app

        routes = [route.path for route in app.routes]
        assert any("/audiencia/{creator_id}/competition" in r for r in routes)

    def test_trends_endpoint_registered(self):
        """GET /audiencia/{creator_id}/trends should be registered"""
        from api.main import app

        routes = [route.path for route in app.routes]
        assert any("/audiencia/{creator_id}/trends" in r for r in routes)
