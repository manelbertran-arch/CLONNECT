"""
Local validation tests for CloneScore Engine.

Runs CloneScoreEngine against synthetic test pairs using mocked LLM judge
and mocked DB. Validates all 6 dimensions return scores in [0, 100].
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from tests.echo.conftest import DIMENSION_WEIGHTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine():
    """Create a CloneScoreEngine with no DB dependency."""
    from services.clone_score_engine import CloneScoreEngine
    engine = CloneScoreEngine()
    return engine


def _mock_style_baseline():
    """Realistic Stefano-style baseline."""
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


SAMPLE_PAIRS = [
    {
        "id": "greeting",
        "message": "Hola! Vi tu video sobre nutricion",
        "response": "Ey que bien!! 💪 Me alegra que te haya gustado, de que video me hablas?",
    },
    {
        "id": "product_question",
        "message": "Cuanto cuesta el curso de nutricion?",
        "response": "El curso de Nutricion Consciente esta a 197€ bro 🔥 Incluye 12 modulos + comunidad privada. Te interesa saber mas?",
    },
    {
        "id": "purchase",
        "message": "Me encanto, como puedo pagar?",
        "response": "Vamoooos 🔥🔥 Te mando el link de pago por aqui! Dale que te va a encantar 💪",
    },
    {
        "id": "objection",
        "message": "197 es mucho para mi ahora",
        "response": "Te entiendo! 🙏 Mira, son menos de 7€ al dia. Ademas puedes pagar en 3 cuotas. Te paso la info?",
    },
    {
        "id": "support",
        "message": "No puedo acceder al modulo 3",
        "response": "Ok tranqui! Te lo soluciono yo. Dame 5 min que reviso tu cuenta. Disculpa las molestias 🙏",
    },
    {
        "id": "ghost_return",
        "message": "Ey Stefano, sigo aqui jaja",
        "response": "Buenaaas!! 😊 Que alegria verte por aqui de nuevo! Sigues con ganas de mejorar tu alimentacion?",
    },
]


# ===========================================================================
# DIMENSION 1: style_fidelity (no LLM, no DB needed)
# ===========================================================================

class TestStyleFidelityLocal:
    """Test style_fidelity dimension with mocked baseline."""

    def test_score_in_valid_range(self):
        engine = _make_engine()
        baseline = _mock_style_baseline()
        for pair in SAMPLE_PAIRS:
            score = engine._compute_style_fidelity(pair["response"], baseline)
            assert 0 <= score <= 100, f"style score {score} out of range for {pair['id']}"

    def test_empty_response_scores_zero(self):
        engine = _make_engine()
        score = engine._compute_style_fidelity("", _mock_style_baseline())
        assert score == 0.0

    def test_no_baseline_returns_neutral(self):
        engine = _make_engine()
        score = engine._compute_style_fidelity("Hola, que tal?", {})
        assert score == 50.0

    def test_on_brand_response_scores_higher(self):
        engine = _make_engine()
        baseline = _mock_style_baseline()
        on_brand = "Ey bro! 💪 Te cuento sobre el curso de nutricion, crack! Vamos dale 🔥"
        off_brand = (
            "Estimado usuario, le informamos que nuestro programa de nutricion "
            "avanzada esta disponible por 197 EUR. Quedamos a su disposicion."
        )
        on_score = engine._compute_style_fidelity(on_brand, baseline)
        off_score = engine._compute_style_fidelity(off_brand, baseline)
        assert on_score > off_score, f"On-brand ({on_score}) should beat off-brand ({off_score})"

    def test_all_sample_pairs_score_above_30(self):
        engine = _make_engine()
        baseline = _mock_style_baseline()
        for pair in SAMPLE_PAIRS:
            score = engine._compute_style_fidelity(pair["response"], baseline)
            assert score >= 30, f"{pair['id']} style score too low: {score}"


# ===========================================================================
# DIMENSION 6: safety_score (no LLM, no DB for basic tests)
# ===========================================================================

class TestSafetyScoreLocal:
    """Test safety_score dimension with mocked contacts."""

    def _mock_contacts(self):
        return {"emails": ["stefano@example.com"], "phones": []}

    def test_clean_response_scores_100(self):
        engine = _make_engine()
        with patch.object(engine, "_get_creator_contacts", return_value=self._mock_contacts()):
            score = engine._compute_safety_score_sync("Hola! Como estas? 😊", "stefano")
        assert score == 100.0

    def test_offensive_word_deducts(self):
        engine = _make_engine()
        with patch.object(engine, "_get_creator_contacts", return_value=self._mock_contacts()):
            score = engine._compute_safety_score_sync("Eres un idiota total", "stefano")
        assert score < 100.0

    def test_false_promise_deducts(self):
        engine = _make_engine()
        with patch.object(engine, "_get_creator_contacts", return_value=self._mock_contacts()):
            score = engine._compute_safety_score_sync(
                "Te garantizo resultados asegurados 100% garantizado", "stefano"
            )
        assert score < 100.0

    def test_leaked_email_deducts(self):
        engine = _make_engine()
        with patch.object(engine, "_get_creator_contacts", return_value=self._mock_contacts()):
            score = engine._compute_safety_score_sync(
                "Contactame en fake@evil.com", "stefano"
            )
        assert score < 100.0

    def test_creator_own_email_no_deduction(self):
        engine = _make_engine()
        with patch.object(engine, "_get_creator_contacts", return_value=self._mock_contacts()):
            score = engine._compute_safety_score_sync(
                "Escribeme a stefano@example.com", "stefano"
            )
        assert score == 100.0

    def test_safety_score_never_negative(self):
        engine = _make_engine()
        with patch.object(engine, "_get_creator_contacts", return_value=self._mock_contacts()):
            score = engine._compute_safety_score_sync(
                "idiota estupido imbecil te garantizo mierda fake@bad.com +1234567890",
                "stefano",
            )
        assert score >= 0.0

    def test_all_sample_pairs_pass_safety(self):
        engine = _make_engine()
        with patch.object(engine, "_get_creator_contacts", return_value=self._mock_contacts()):
            for pair in SAMPLE_PAIRS:
                score = engine._compute_safety_score_sync(pair["response"], "stefano")
                assert score >= 80, f"{pair['id']} safety score too low: {score}"


# ===========================================================================
# DIMENSION 2-4: LLM judge dimensions (mocked LLM)
# ===========================================================================

class TestKnowledgeAccuracyLocal:
    """Test knowledge_accuracy with mocked LLM judge."""

    @pytest.mark.asyncio
    async def test_returns_valid_score(self):
        engine = _make_engine()
        mock_judge_result = {"score": 78.0, "reasoning": "good", "hallucinations": [], "omissions": []}
        with patch("services.llm_judge.LLMJudge") as MockJudge:
            instance = MockJudge.return_value
            instance.judge = AsyncMock(return_value=mock_judge_result)
            with patch.object(engine, "_get_knowledge_context", return_value="Curso: 197€"):
                score = await engine._compute_knowledge_accuracy(
                    "El curso cuesta 197€ bro", "stefano", {}
                )
        assert 0 <= score <= 100

    @pytest.mark.asyncio
    async def test_fallback_on_error(self):
        engine = _make_engine()
        with patch("services.llm_judge.LLMJudge") as MockJudge:
            instance = MockJudge.return_value
            instance.judge = AsyncMock(return_value={"score": 50.0, "reasoning": "failed"})
            with patch.object(engine, "_get_knowledge_context", return_value=""):
                score = await engine._compute_knowledge_accuracy(
                    "response text", "stefano", {}
                )
        assert score == 50.0


class TestPersonaConsistencyLocal:
    """Test persona_consistency with mocked LLM judge."""

    @pytest.mark.asyncio
    async def test_returns_valid_score(self):
        engine = _make_engine()
        mock_result = {"score": 82.0, "reasoning": "consistent", "contradictions": [], "persona_breaks": []}
        with patch("services.llm_judge.LLMJudge") as MockJudge:
            instance = MockJudge.return_value
            instance.judge = AsyncMock(return_value=mock_result)
            with patch.object(engine, "_get_doc_d_summary", return_value="Stefano es cercano"):
                score = await engine._compute_persona_consistency(
                    "Ey bro! 💪", "stefano", []
                )
        assert 0 <= score <= 100


class TestToneAppropriatenessLocal:
    """Test tone_appropriateness with mocked LLM judge."""

    @pytest.mark.asyncio
    async def test_returns_valid_score(self):
        engine = _make_engine()
        mock_result = {"score": 75.0, "reasoning": "appropriate", "tone_issues": []}
        with patch("services.llm_judge.LLMJudge") as MockJudge:
            instance = MockJudge.return_value
            instance.judge = AsyncMock(return_value=mock_result)
            score = await engine._compute_tone_appropriateness(
                "Ey que bien!", "nuevo", "nuevo", "greeting", "Hola!"
            )
        assert 0 <= score <= 100


# ===========================================================================
# AGGREGATION
# ===========================================================================

class TestAggregation:
    """Test the weighted aggregation logic."""

    def test_all_dimensions_50_returns_50(self):
        engine = _make_engine()
        scores = {dim: 50.0 for dim in DIMENSION_WEIGHTS}
        result = engine._aggregate(scores)
        assert 49.0 <= result <= 51.0

    def test_all_dimensions_100_returns_100(self):
        engine = _make_engine()
        scores = {dim: 100.0 for dim in DIMENSION_WEIGHTS}
        result = engine._aggregate(scores)
        assert result == 100.0

    def test_all_dimensions_0_returns_0(self):
        engine = _make_engine()
        scores = {dim: 0.0 for dim in DIMENSION_WEIGHTS}
        result = engine._aggregate(scores)
        assert result == 0.0

    def test_safety_penalty_when_below_30(self):
        engine = _make_engine()
        scores = {dim: 80.0 for dim in DIMENSION_WEIGHTS}
        scores["safety_score"] = 20.0  # Below 30 -> 50% penalty
        result = engine._aggregate(scores)
        # Without penalty: ~76 (weighted). With penalty: ~38
        assert result < 50.0

    def test_partial_dimensions_still_works(self):
        engine = _make_engine()
        scores = {"style_fidelity": 80.0, "safety_score": 90.0}
        result = engine._aggregate(scores)
        assert 0 <= result <= 100

    def test_weights_sum_to_one(self):
        total = sum(DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01


# ===========================================================================
# evaluate_single (mocked dependencies)
# ===========================================================================

class TestEvaluateSingleLocal:
    """Test evaluate_single with all dependencies mocked."""

    @pytest.mark.asyncio
    async def test_lightweight_returns_style_only(self):
        engine = _make_engine()
        with patch.object(engine, "_get_style_baseline", return_value=_mock_style_baseline()):
            result = await engine.evaluate_single(
                "stefano", "Hola!", "Ey que bien! 💪", {}
            )
        assert "dimension_scores" in result
        assert "style_fidelity" in result["dimension_scores"]
        assert "overall_score" in result
        # Only style computed in lightweight mode
        assert len(result["dimension_scores"]) == 1

    @pytest.mark.asyncio
    async def test_full_eval_returns_all_dimensions(self):
        engine = _make_engine()
        mock_judge = {"score": 75.0, "reasoning": "ok"}
        with patch.object(engine, "_get_style_baseline", return_value=_mock_style_baseline()):
            with patch("services.llm_judge.LLMJudge") as MockJudge:
                instance = MockJudge.return_value
                instance.judge = AsyncMock(return_value=mock_judge)
                with patch.object(engine, "_get_knowledge_context", return_value=""):
                    with patch.object(engine, "_get_doc_d_summary", return_value=""):
                        with patch.object(engine, "_get_creator_contacts", return_value={"emails": [], "phones": []}):
                            result = await engine.evaluate_single(
                                "stefano", "Hola!", "Ey que bien! 💪",
                                {"full_eval": True},
                            )
        assert len(result["dimension_scores"]) >= 4
        for dim, score in result["dimension_scores"].items():
            assert 0 <= score <= 100, f"{dim}={score} out of range"

    @pytest.mark.asyncio
    async def test_error_returns_neutral_score(self):
        engine = _make_engine()
        with patch.object(engine, "_get_style_baseline", side_effect=Exception("boom")):
            result = await engine.evaluate_single(
                "stefano", "Hola!", "Ey!", {}
            )
        assert result["overall_score"] == 50.0
        assert "error" in result
