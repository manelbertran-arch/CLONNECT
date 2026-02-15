"""
Tests for the Intelligence Engine and API endpoints.
"""
import pytest
from unittest.mock import MagicMock
from datetime import date, datetime, timedelta


class TestIntelligenceEngineModuleLoads:
    """Verify intelligence module loads correctly."""

    def test_intelligence_module_loads(self):
        """Intelligence module loads without errors."""
        from core.intelligence import IntelligenceEngine, ENABLE_INTELLIGENCE
        assert IntelligenceEngine is not None
        assert isinstance(ENABLE_INTELLIGENCE, bool)

    def test_intelligence_engine_factory(self):
        """get_intelligence_engine creates instance."""
        from core.intelligence.engine import get_intelligence_engine

        engine = get_intelligence_engine("test_creator")
        assert engine is not None
        assert engine.creator_id == "test_creator"


class TestIntelligenceEnginePatterns:
    """Tests for pattern analysis methods."""

    @pytest.mark.asyncio
    async def test_analyze_patterns_returns_structure(self):
        """analyze_patterns returns expected structure."""
        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine("test_creator")

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.fetchone.return_value = None

        patterns = await engine.analyze_patterns(mock_db, 30)

        assert "temporal" in patterns
        assert "conversation" in patterns
        assert "conversion" in patterns

    @pytest.mark.asyncio
    async def test_analyze_temporal_patterns_with_data(self):
        """_analyze_temporal_patterns returns hours and days."""
        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine("test_creator")

        mock_db = MagicMock()
        # Mock hour query results
        mock_db.execute.return_value.fetchall.side_effect = [
            [(14, 50, 30), (10, 40, 25)],  # Hour results
            [(1, 100, 50), (2, 80, 40)],   # Day results
        ]

        patterns = await engine._analyze_temporal_patterns(mock_db, 30)

        assert "best_hours" in patterns
        assert "best_days" in patterns
        assert patterns["peak_activity_hour"] == 14
        assert patterns["peak_activity_day"] == "Lunes"


class TestIntelligenceEnginePredictions:
    """Tests for prediction methods."""

    @pytest.mark.asyncio
    async def test_predict_conversions_returns_list(self):
        """predict_conversions returns list of predictions."""
        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine("test_creator")

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [
            (1, "lead123", "interesado", 0.7, "usuario1", 15, datetime.now() - timedelta(days=2)),
        ]

        predictions = await engine.predict_conversions(mock_db)

        assert isinstance(predictions, list)
        if predictions:
            assert "lead_id" in predictions[0]
            assert "conversion_probability" in predictions[0]
            assert "recommended_action" in predictions[0]

    @pytest.mark.asyncio
    async def test_predict_churn_risk_returns_list(self):
        """predict_churn_risk returns list of at-risk leads."""
        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine("test_creator")

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [
            ("lead123", "usuario1", "interesado", 0.5, datetime.now() - timedelta(days=10), 8),
        ]

        risks = await engine.predict_churn_risk(mock_db)

        assert isinstance(risks, list)
        if risks:
            assert "lead_id" in risks[0]
            assert "churn_risk" in risks[0]
            assert "recovery_action" in risks[0]

    @pytest.mark.asyncio
    async def test_forecast_revenue_with_history(self):
        """forecast_revenue generates forecasts from history."""
        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine("test_creator")

        mock_db = MagicMock()
        # 8 weeks of history - use timedelta to calculate dates
        base_date = date(2024, 1, 1)
        mock_db.execute.return_value.fetchall.return_value = [
            (base_date + timedelta(weeks=w), 1000 + w * 100, w) for w in range(8)
        ]

        forecast = await engine.forecast_revenue(mock_db, 4)

        assert "current_weekly_avg" in forecast
        assert "forecasts" in forecast
        assert len(forecast["forecasts"]) == 4

    @pytest.mark.asyncio
    async def test_forecast_revenue_insufficient_data(self):
        """forecast_revenue handles insufficient data."""
        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine("test_creator")

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        forecast = await engine.forecast_revenue(mock_db, 4)

        assert "error" in forecast


class TestIntelligenceEngineRecommendations:
    """Tests for recommendation generation."""

    @pytest.mark.asyncio
    async def test_generate_content_recommendations(self):
        """generate_content_recommendations returns list."""
        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine("test_creator")

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.side_effect = [
            [("mensaje repetido sobre coaching", 5)],  # Topics
            [(14, 50, 30)],  # Hours
            [(1, 100, 50)],  # Days
        ]

        recs = await engine.generate_content_recommendations(mock_db)

        assert isinstance(recs, list)
        for rec in recs:
            assert "category" in rec
            assert "priority" in rec
            assert "title" in rec

    @pytest.mark.asyncio
    async def test_generate_action_recommendations(self):
        """generate_action_recommendations includes leads to contact."""
        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine("test_creator")

        mock_db = MagicMock()
        # Mock for predict_conversions and predict_churn_risk
        mock_db.execute.return_value.fetchall.return_value = [
            (1, "lead123", "caliente", 0.8, "usuario1", 20, datetime.now() - timedelta(days=1)),
        ]

        recs = await engine.generate_action_recommendations(mock_db)

        assert isinstance(recs, list)


class TestIntelligenceEngineWeeklyReport:
    """Tests for weekly report generation."""

    @pytest.mark.asyncio
    async def test_get_weekly_metrics(self):
        """_get_weekly_metrics aggregates data correctly."""
        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine("test_creator")

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = (
            100,  # conversations
            500,  # messages
            50,   # new_leads
            10,   # conversions
            5000, # revenue
        )

        start = date(2024, 1, 1)
        end = date(2024, 1, 7)

        metrics = await engine._get_weekly_metrics(mock_db, start, end)

        assert metrics["conversations"] == 100
        assert metrics["messages"] == 500
        assert metrics["new_leads"] == 50
        assert metrics["conversions"] == 10
        assert metrics["revenue"] == 5000
        assert metrics["conversion_rate"] == 20.0

    @pytest.mark.asyncio
    async def test_get_comparison_calculates_changes(self):
        """_get_comparison calculates percentage changes."""
        from core.intelligence import IntelligenceEngine

        engine = IntelligenceEngine("test_creator")

        mock_db = MagicMock()
        # Current week: 120 conversations, Previous week: 100 conversations
        mock_db.execute.return_value.fetchone.side_effect = [
            (120, 600, 60, 12, 6000),  # Current
            (100, 500, 50, 10, 5000),  # Previous
        ]

        comparison = await engine._get_comparison(mock_db, date(2024, 1, 8), 7)

        assert comparison["conversations"] == 20.0  # 20% increase


class TestIntelligenceModels:
    """Tests for intelligence SQLAlchemy models."""

    def test_prediction_model_exists(self):
        """Prediction model is defined."""
        from api.models import Prediction
        assert Prediction is not None
        assert hasattr(Prediction, 'prediction_type')
        assert hasattr(Prediction, 'predicted_value')
        assert hasattr(Prediction, 'confidence')

    def test_recommendation_model_exists(self):
        """Recommendation model is defined."""
        from api.models import Recommendation
        assert Recommendation is not None
        assert hasattr(Recommendation, 'category')
        assert hasattr(Recommendation, 'priority')
        assert hasattr(Recommendation, 'title')

    def test_weekly_report_model_exists(self):
        """WeeklyReport model is defined."""
        from api.models import WeeklyReport
        assert WeeklyReport is not None
        assert hasattr(WeeklyReport, 'executive_summary')
        assert hasattr(WeeklyReport, 'metrics_summary')

    def test_creator_metrics_daily_model_exists(self):
        """CreatorMetricsDaily model is defined."""
        from api.models import CreatorMetricsDaily
        assert CreatorMetricsDaily is not None
        assert hasattr(CreatorMetricsDaily, 'total_conversations')
        assert hasattr(CreatorMetricsDaily, 'revenue')

    def test_lead_intelligence_model_exists(self):
        """LeadIntelligence model is defined."""
        from api.models import LeadIntelligence
        assert LeadIntelligence is not None
        assert hasattr(LeadIntelligence, 'conversion_probability')
        assert hasattr(LeadIntelligence, 'churn_risk')

    def test_content_performance_model_exists(self):
        """ContentPerformance model is defined."""
        from api.models import ContentPerformance
        assert ContentPerformance is not None
        assert hasattr(ContentPerformance, 'engagement_rate')
        assert hasattr(ContentPerformance, 'dms_generated_24h')


class TestIntelligenceAPIEndpoints:
    """Tests for intelligence API router."""

    def test_intelligence_router_loads(self):
        """Intelligence router loads without errors."""
        from api.routers.intelligence import router
        assert router is not None
        assert router.prefix == "/intelligence"

    def test_dashboard_endpoint_exists(self):
        """Dashboard endpoint is defined."""
        from api.routers.intelligence import get_intelligent_dashboard
        assert callable(get_intelligent_dashboard)

    def test_predictions_endpoint_exists(self):
        """Predictions endpoint is defined."""
        from api.routers.intelligence import get_predictions
        assert callable(get_predictions)

    def test_recommendations_endpoint_exists(self):
        """Recommendations endpoint is defined."""
        from api.routers.intelligence import get_recommendations
        assert callable(get_recommendations)

    def test_weekly_report_endpoint_exists(self):
        """Weekly report endpoint is defined."""
        from api.routers.intelligence import get_weekly_report
        assert callable(get_weekly_report)


class TestRecommendedActions:
    """Tests for recommended action logic."""

    def test_reactivation_for_inactive(self):
        """Recommends reactivation for inactive leads."""
        from core.intelligence.engine import IntelligenceEngine

        engine = IntelligenceEngine("test")
        action = engine._get_recommended_action(messages=5, days_inactive=10, score=0.5)
        assert "reactivacion" in action.lower()

    def test_direct_offer_for_high_score(self):
        """Recommends direct offer for high-score leads."""
        from core.intelligence.engine import IntelligenceEngine

        engine = IntelligenceEngine("test")
        action = engine._get_recommended_action(messages=5, days_inactive=2, score=0.8)
        assert "oferta" in action.lower()

    def test_closing_call_for_engaged(self):
        """Recommends closing call for highly engaged leads."""
        from core.intelligence.engine import IntelligenceEngine

        engine = IntelligenceEngine("test")
        action = engine._get_recommended_action(messages=15, days_inactive=2, score=0.5)
        assert "llamada" in action.lower()
