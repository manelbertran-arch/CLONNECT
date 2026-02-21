"""
End-to-end baseline measurement tests for CloneScore Engine.

Creates 10 synthetic pairs (greeting, product_question, purchase, objection,
support), runs evaluate_batch() with fully mocked dependencies, asserts
aggregate score computed correctly.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

from tests.echo.conftest import DIMENSION_WEIGHTS, SCORE_THRESHOLDS


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _mock_message_row(content, intent="general", lead_id="lead-001", idx=0):
    """Create a mock Message row matching the query shape in evaluate_batch."""
    row = MagicMock()
    row.id = f"msg-{idx:03d}"
    row.content = content
    row.intent = intent
    row.lead_id = lead_id
    row.suggested_response = None
    row.copilot_action = None
    row.created_at = datetime.now(timezone.utc) - timedelta(hours=idx)
    # Support tuple-like indexing used by some DB patterns
    row.__getitem__ = lambda self, i: getattr(self, ["id", "content", "intent", "lead_id", "suggested_response", "copilot_action", "created_at"][i])
    return row


SYNTHETIC_RESPONSES = [
    ("Ey que bien!! 💪 Me alegra que te haya gustado, de que video me hablas?", "greeting"),
    ("El curso de Nutricion Consciente esta a 197€ bro 🔥 Te interesa saber mas?", "product_inquiry"),
    ("Vamoooos 🔥🔥 Te mando el link de pago por aqui!", "purchase_intent"),
    ("Te entiendo! 🙏 Son menos de 7€ al dia. Puedes pagar en cuotas.", "objection"),
    ("Ok tranqui! Te lo soluciono. Dame 5 min 🙏", "support"),
    ("Buenaaas!! 😊 Que alegria verte! Como vas?", "greeting"),
    ("Te cuento! 📋 El curso tiene 12 modulos + soporte directo conmigo 💪", "product_inquiry"),
    ("Buena pregunta! 😊 Lo que diferencia mi curso es que es personalizado.", "comparison"),
    ("Buenisimo tio! 🔥 Fui a la playa. Tu que tal?", "casual"),
    ("Eyyy que bueno que me escribes! 💪 Te puedo ayudar.", "greeting"),
]


def _build_mock_samples():
    """Build 10 mock Message rows for evaluate_batch."""
    samples = []
    for idx, (content, intent) in enumerate(SYNTHETIC_RESPONSES):
        samples.append(_mock_message_row(content, intent, f"lead-{idx:03d}", idx))
    return samples


def _mock_style_baseline():
    return {
        "avg_message_length": 85,
        "emoji_rate": 0.15,
        "question_rate": 0.3,
        "informal_markers": ["jaja", "bro", "crack", "tio", "vamos", "dale"],
        "top_vocabulary": [
            "curso", "nutricion", "plan", "personalizado", "energia",
            "resultados", "salud", "entrenamiento", "comida", "cambio",
        ],
    }


# ===========================================================================
# Tests
# ===========================================================================

class TestBaselineMeasurement:
    """End-to-end baseline measurement with fully mocked dependencies."""

    @pytest.mark.asyncio
    async def test_evaluate_batch_returns_all_dimensions(self):
        """evaluate_batch returns scores for all 6 dimensions."""
        from services.clone_score_engine import CloneScoreEngine
        engine = CloneScoreEngine()

        samples = _build_mock_samples()
        mock_session = MagicMock()

        # Mock the DB query chain
        mock_query = MagicMock()
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = samples
        mock_session.query.return_value = mock_query

        # Mock LLM judge for knowledge, persona, tone
        mock_judge_result = {"score": 75.0, "reasoning": "mock judge"}

        with patch("api.database.SessionLocal", return_value=mock_session):
            with patch.object(engine, "_get_style_baseline", return_value=_mock_style_baseline()):
                with patch.object(engine, "_get_creator_contacts", return_value={"emails": [], "phones": []}):
                    with patch("services.llm_judge.LLMJudge") as MockJudge:
                        instance = MockJudge.return_value
                        instance.judge = AsyncMock(return_value=mock_judge_result)
                        with patch.object(engine, "_get_knowledge_context", return_value="Curso: 197€"):
                            with patch.object(engine, "_get_doc_d_summary", return_value="Stefano: cercano"):
                                with patch.object(engine, "_get_lead_context", return_value={"status": "nuevo"}):
                                    with patch.object(engine, "_get_conversation_snippet", return_value=[]):
                                        with patch.object(engine, "_compute_sales_effectiveness", return_value=65.0):
                                            with patch.object(engine, "_store_evaluation"):
                                                result = await engine.evaluate_batch(
                                                    creator_id="stefano",
                                                    creator_db_id="uuid-123",
                                                    sample_size=10,
                                                )

        assert "error" not in result
        assert "dimension_scores" in result
        assert "overall_score" in result

        dims = result["dimension_scores"]
        for dim_name in DIMENSION_WEIGHTS:
            assert dim_name in dims, f"Missing dimension: {dim_name}"
            assert 0 <= dims[dim_name] <= 100, f"{dim_name}={dims[dim_name]} out of range"

    @pytest.mark.asyncio
    async def test_overall_score_is_weighted_aggregate(self):
        """Overall score must match weighted aggregation formula."""
        from services.clone_score_engine import CloneScoreEngine
        engine = CloneScoreEngine()

        dimension_scores = {
            "style_fidelity": 80.0,
            "knowledge_accuracy": 75.0,
            "persona_consistency": 78.0,
            "tone_appropriateness": 76.0,
            "sales_effectiveness": 65.0,
            "safety_score": 90.0,
        }

        overall = engine._aggregate(dimension_scores)

        # Manually compute expected weighted average
        weighted_sum = sum(
            dimension_scores[dim] * weight
            for dim, weight in DIMENSION_WEIGHTS.items()
        )
        expected = round(weighted_sum, 1)

        # Safety >= 30, so no penalty
        assert abs(overall - expected) < 1.0, f"Got {overall}, expected ~{expected}"

    @pytest.mark.asyncio
    async def test_batch_skips_when_no_samples(self):
        """evaluate_batch returns skipped=True when no messages found."""
        from services.clone_score_engine import CloneScoreEngine
        engine = CloneScoreEngine()

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []  # No samples
        mock_session.query.return_value = mock_query

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await engine.evaluate_batch("stefano", "uuid-123", sample_size=10)

        assert result.get("skipped") is True
        assert result.get("reason") == "no_samples"

    @pytest.mark.asyncio
    async def test_batch_handles_llm_failures_gracefully(self):
        """When LLM judge fails, dimensions should fallback to 50.0."""
        from services.clone_score_engine import CloneScoreEngine
        engine = CloneScoreEngine()

        samples = _build_mock_samples()[:3]
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = samples
        mock_session.query.return_value = mock_query

        with patch("api.database.SessionLocal", return_value=mock_session):
            with patch.object(engine, "_get_style_baseline", return_value=_mock_style_baseline()):
                with patch.object(engine, "_get_creator_contacts", return_value={"emails": [], "phones": []}):
                    # LLM judge raises exception for all calls
                    with patch.object(engine, "_compute_knowledge_accuracy", side_effect=Exception("LLM down")):
                        with patch.object(engine, "_compute_persona_consistency", side_effect=Exception("LLM down")):
                            with patch.object(engine, "_compute_tone_appropriateness", side_effect=Exception("LLM down")):
                                with patch.object(engine, "_compute_sales_effectiveness", return_value=60.0):
                                    with patch.object(engine, "_get_lead_context", return_value={}):
                                        with patch.object(engine, "_get_conversation_snippet", return_value=[]):
                                            with patch.object(engine, "_store_evaluation"):
                                                result = await engine.evaluate_batch(
                                                    "stefano", "uuid-123", sample_size=3,
                                                )

        assert "error" not in result
        dims = result["dimension_scores"]
        # LLM dims should fallback to 50.0
        assert dims["knowledge_accuracy"] == 50.0
        assert dims["persona_consistency"] == 50.0
        assert dims["tone_appropriateness"] == 50.0
        # Non-LLM dims should have real scores
        assert dims["style_fidelity"] != 50.0
        assert dims["safety_score"] != 50.0

    def test_score_thresholds_ordering(self):
        """Verify SCORE_THRESHOLDS are ordered correctly."""
        vals = list(SCORE_THRESHOLDS.values())
        for i in range(len(vals) - 1):
            assert vals[i] > vals[i + 1], (
                f"Thresholds not in descending order: {SCORE_THRESHOLDS}"
            )

    def test_dimension_weights_sum_to_one(self):
        """All dimension weights must sum to 1.0."""
        total = sum(DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected 1.0"


class TestBaselineScoreClassification:
    """Test that scores are classified correctly by threshold."""

    @pytest.fixture
    def classify(self):
        def _classify(score: float) -> str:
            for label, threshold in SCORE_THRESHOLDS.items():
                if score >= threshold:
                    return label
            return "critical"
        return _classify

    def test_excellent_classification(self, classify):
        assert classify(95.0) == "excellent"

    def test_good_classification(self, classify):
        assert classify(80.0) == "good"

    def test_acceptable_classification(self, classify):
        assert classify(65.0) == "acceptable"

    def test_needs_improvement_classification(self, classify):
        assert classify(45.0) == "needs_improvement"

    def test_critical_classification(self, classify):
        assert classify(10.0) == "critical"

    def test_boundary_exact_threshold(self, classify):
        assert classify(90.0) == "excellent"
        assert classify(75.0) == "good"
        assert classify(60.0) == "acceptable"
        assert classify(40.0) == "needs_improvement"
        assert classify(0.0) == "critical"
