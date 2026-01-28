"""
Tests for InsightsEngine

SPRINT3-T3.1: TDD tests written BEFORE implementation
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from core.insights_engine import InsightsEngine
from api.schemas.insights import (
    TodayMission,
    HotLeadAction,
    WeeklyInsights,
    WeeklyMetrics,
    ContentInsight,
)


class TestInsightsEngineInit:
    """Test InsightsEngine initialization"""

    def test_init_with_creator_id_and_db(self):
        """InsightsEngine should initialize with creator_id and db session"""
        mock_db = MagicMock(spec=Session)
        engine = InsightsEngine(creator_id="test_creator", db=mock_db)

        assert engine.creator_id == "test_creator"
        assert engine.db == mock_db


class TestTodayMission:
    """Test get_today_mission method"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session"""
        return MagicMock(spec=Session)

    @pytest.fixture
    def engine(self, mock_db):
        """Create InsightsEngine instance"""
        return InsightsEngine(creator_id="test_creator", db=mock_db)

    def test_returns_today_mission_structure(self, engine):
        """get_today_mission should return TodayMission with all fields"""
        result = engine.get_today_mission()

        assert isinstance(result, TodayMission)
        assert hasattr(result, "potential_revenue")
        assert hasattr(result, "hot_leads")
        assert hasattr(result, "pending_responses")
        assert hasattr(result, "today_bookings")

    def test_hot_leads_max_5(self, engine):
        """hot_leads should contain at most 5 leads"""
        result = engine.get_today_mission()

        assert len(result.hot_leads) <= 5

    def test_hot_leads_are_hot_lead_action_type(self, engine):
        """Each hot lead should be HotLeadAction type"""
        result = engine.get_today_mission()

        for lead in result.hot_leads:
            assert isinstance(lead, HotLeadAction)

    def test_calculates_potential_revenue_from_hot_leads(self, engine):
        """potential_revenue should be sum of hot_leads deal values"""
        result = engine.get_today_mission()

        expected_revenue = sum(lead.deal_value for lead in result.hot_leads)
        assert result.potential_revenue == expected_revenue

    def test_pending_responses_is_non_negative(self, engine):
        """pending_responses should be >= 0"""
        result = engine.get_today_mission()

        assert result.pending_responses >= 0

    def test_today_bookings_is_list(self, engine):
        """today_bookings should be a list"""
        result = engine.get_today_mission()

        assert isinstance(result.today_bookings, list)

    def test_handles_no_hot_leads_gracefully(self, engine):
        """Should return empty hot_leads list when no hot leads exist"""
        result = engine.get_today_mission()

        # Should not raise, hot_leads can be empty
        assert isinstance(result.hot_leads, list)
        assert result.potential_revenue >= 0


class TestHotLeadsQuery:
    """Test _get_hot_leads method"""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.fixture
    def engine(self, mock_db):
        return InsightsEngine(creator_id="test_creator", db=mock_db)

    def test_hot_leads_have_required_fields(self, engine):
        """Each hot lead should have all required fields"""
        hot_leads = engine._get_hot_leads(limit=5)

        for lead in hot_leads:
            assert hasattr(lead, "follower_id")
            assert hasattr(lead, "name")
            assert hasattr(lead, "username")
            assert hasattr(lead, "last_message")
            assert hasattr(lead, "hours_ago")
            assert hasattr(lead, "context")
            assert hasattr(lead, "action")

    def test_hot_leads_respect_limit(self, engine):
        """Should respect the limit parameter"""
        hot_leads = engine._get_hot_leads(limit=3)
        assert len(hot_leads) <= 3

        hot_leads = engine._get_hot_leads(limit=10)
        assert len(hot_leads) <= 10


class TestWeeklyInsights:
    """Test get_weekly_insights method"""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.fixture
    def engine(self, mock_db):
        return InsightsEngine(creator_id="test_creator", db=mock_db)

    def test_returns_weekly_insights_structure(self, engine):
        """get_weekly_insights should return WeeklyInsights"""
        result = engine.get_weekly_insights()

        assert isinstance(result, WeeklyInsights)
        assert hasattr(result, "content")
        assert hasattr(result, "trend")
        assert hasattr(result, "product")
        assert hasattr(result, "competition")

    def test_content_insight_has_suggestion(self, engine):
        """content insight should have a suggestion"""
        result = engine.get_weekly_insights()

        if result.content:
            assert isinstance(result.content, ContentInsight)
            assert result.content.suggestion is not None

    def test_handles_no_data_gracefully(self, engine):
        """Should return None for insights when no data"""
        result = engine.get_weekly_insights()

        # Should not raise, insights can be None
        assert isinstance(result, WeeklyInsights)


class TestWeeklyMetrics:
    """Test get_weekly_metrics method"""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.fixture
    def engine(self, mock_db):
        return InsightsEngine(creator_id="test_creator", db=mock_db)

    def test_returns_weekly_metrics_structure(self, engine):
        """get_weekly_metrics should return WeeklyMetrics"""
        result = engine.get_weekly_metrics()

        assert isinstance(result, WeeklyMetrics)
        assert hasattr(result, "revenue")
        assert hasattr(result, "revenue_delta")
        assert hasattr(result, "sales_count")
        assert hasattr(result, "response_rate")

    def test_revenue_is_non_negative(self, engine):
        """revenue should be >= 0"""
        result = engine.get_weekly_metrics()

        assert result.revenue >= 0

    def test_response_rate_is_between_0_and_1(self, engine):
        """response_rate should be between 0 and 1"""
        result = engine.get_weekly_metrics()

        assert 0 <= result.response_rate <= 1


class TestInsightsEndpoints:
    """Test /insights/* API endpoints"""

    def test_router_is_registered(self):
        """Insights router should be registered in the app"""
        from api.main import app

        # Check that insights routes exist
        routes = [route.path for route in app.routes]
        insights_routes = [r for r in routes if "/insights" in r]
        assert len(insights_routes) >= 3, f"Expected 3+ insights routes, found: {insights_routes}"

    def test_today_endpoint_path_registered(self):
        """GET /insights/{creator_id}/today should be registered"""
        from api.main import app

        routes = [route.path for route in app.routes]
        assert any("/insights/{creator_id}/today" in r for r in routes), \
            f"Today endpoint not found in routes: {routes}"

    def test_weekly_endpoint_path_registered(self):
        """GET /insights/{creator_id}/weekly should be registered"""
        from api.main import app

        routes = [route.path for route in app.routes]
        assert any("/insights/{creator_id}/weekly" in r for r in routes), \
            f"Weekly endpoint not found in routes: {routes}"

    def test_metrics_endpoint_path_registered(self):
        """GET /insights/{creator_id}/metrics should be registered"""
        from api.main import app

        routes = [route.path for route in app.routes]
        assert any("/insights/{creator_id}/metrics" in r for r in routes), \
            f"Metrics endpoint not found in routes: {routes}"

    def test_insights_router_has_correct_prefix(self):
        """Insights router should have /insights prefix"""
        from api.routers.insights import router

        assert router.prefix == "/insights"

    def test_insights_router_has_correct_tags(self):
        """Insights router should have insights tag"""
        from api.routers.insights import router

        assert "insights" in router.tags
