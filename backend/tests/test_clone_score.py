"""
Tests for CloneScore Engine — 6-dimension quality evaluation.

Tests:
  - test_style_fidelity_calculation
  - test_style_fidelity_no_baseline
  - test_knowledge_accuracy_with_mock_llm
  - test_persona_consistency_scoring
  - test_tone_appropriateness_scoring
  - test_safety_score_detects_hallucination
  - test_safety_score_clean_response
  - test_safety_score_offensive_words
  - test_sales_effectiveness_from_data
  - test_aggregate_score_weights
  - test_aggregate_score_safety_penalty
  - test_batch_evaluation_end_to_end
  - test_test_set_generation
  - test_test_set_stratification
  - test_score_persistence_in_db
  - test_llm_judge_parse_valid_json
  - test_llm_judge_parse_malformed_json
  - test_llm_judge_timeout_fallback
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.clone_score_engine import CloneScoreEngine, DIMENSION_WEIGHTS


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture
def engine():
    """Create a fresh CloneScoreEngine instance."""
    return CloneScoreEngine()


@pytest.fixture
def creator_baseline():
    """Sample creator style baseline."""
    return {
        "avg_message_length": 80,
        "emoji_rate": 0.15,
        "question_rate": 0.25,
        "informal_markers": ["jaja", "bro", "crack", "tio"],
        "top_vocabulary": [
            "hola", "curso", "precio", "genial", "programa",
            "coaching", "sesion", "descuento", "link", "info",
        ],
    }


@pytest.fixture
def mock_session():
    """Create a mock DB session."""
    session = MagicMock()
    session.query.return_value = session
    session.filter.return_value = session
    session.filter_by.return_value = session
    session.order_by.return_value = session
    session.limit.return_value = session
    session.first.return_value = None
    session.all.return_value = []
    session.scalar.return_value = 0
    session.add = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    return session


# =========================================================================
# Test: style_fidelity
# =========================================================================

class TestStyleFidelity:
    def test_style_fidelity_high_match(self, engine, creator_baseline):
        """Response matching creator style should score high."""
        response = "Hola bro! El curso esta genial, tiene todo lo que necesitas. Quieres mas info? \U0001f60a"
        score = engine._compute_style_fidelity(response, creator_baseline)
        assert score >= 50.0, f"Expected >= 50, got {score}"

    def test_style_fidelity_low_match(self, engine, creator_baseline):
        """Response very different from creator should score low."""
        response = (
            "Estimado usuario, le informo que nuestro programa de formacion "
            "profesional incluye una serie de modulos de capacitacion integral "
            "que abarcan multiples disciplinas del conocimiento aplicado a "
            "su desarrollo profesional y personal en el ambito empresarial "
            "contemporaneo con metodologias de vanguardia certificadas."
        )
        score = engine._compute_style_fidelity(response, creator_baseline)
        assert score < 50.0, f"Expected < 50, got {score}"

    def test_style_fidelity_empty_response(self, engine, creator_baseline):
        """Empty response should score 0."""
        score = engine._compute_style_fidelity("", creator_baseline)
        assert score == 0.0

    def test_style_fidelity_no_baseline(self, engine):
        """No baseline should return neutral score."""
        score = engine._compute_style_fidelity("Hola que tal!", {})
        assert score == 50.0


# =========================================================================
# Test: knowledge_accuracy (with mock LLM)
# =========================================================================

class TestKnowledgeAccuracy:
    @pytest.mark.asyncio
    async def test_knowledge_accuracy_with_mock_llm(self, engine):
        """LLM judge should return parsed score."""
        mock_result = {"score": 85.0, "hallucinations": [], "reasoning": "todo correcto"}

        with patch("services.llm_judge.LLMJudge.judge", new_callable=AsyncMock) as mock_judge:
            mock_judge.return_value = mock_result
            with patch.object(engine, "_get_knowledge_context", return_value="Producto: Curso X, precio 97 EUR"):
                score = await engine._compute_knowledge_accuracy(
                    bot_response="El curso X cuesta 97 euros",
                    creator_id="test_creator",
                    context={},
                )
                assert score == 85.0


# =========================================================================
# Test: persona_consistency
# =========================================================================

class TestPersonaConsistency:
    @pytest.mark.asyncio
    async def test_persona_consistency_scoring(self, engine):
        """Persona consistency should use LLM judge and return score."""
        mock_result = {
            "score": 72.0,
            "contradictions": [],
            "persona_breaks": ["ligeramente mas formal de lo habitual"],
            "reasoning": "buena consistencia general",
        }

        with patch("services.llm_judge.LLMJudge.judge", new_callable=AsyncMock) as mock_judge:
            mock_judge.return_value = mock_result
            with patch.object(engine, "_get_doc_d_summary", return_value="Tono: informal, cercano"):
                score = await engine._compute_persona_consistency(
                    bot_response="Hola! Te cuento sobre el programa",
                    creator_id="test_creator",
                    conversation_history=[
                        {"role": "user", "content": "Hola"},
                        {"role": "assistant", "content": "Hey! Que tal?"},
                    ],
                )
                assert score == 72.0


# =========================================================================
# Test: tone_appropriateness
# =========================================================================

class TestToneAppropriateness:
    @pytest.mark.asyncio
    async def test_tone_appropriateness_scoring(self, engine):
        """Tone scoring should evaluate against lead context."""
        mock_result = {
            "score": 90.0,
            "tone_issues": [],
            "ideal_tone": "cercano y servicial",
            "reasoning": "tono perfecto para cliente existente",
        }

        with patch("services.llm_judge.LLMJudge.judge", new_callable=AsyncMock) as mock_judge:
            mock_judge.return_value = mock_result
            score = await engine._compute_tone_appropriateness(
                bot_response="Genial que vuelvas! En que te puedo ayudar hoy?",
                lead_stage="cliente",
                relationship_type="cliente",
                intent="greeting",
                follower_message="Hola de nuevo!",
            )
            assert score == 90.0


# =========================================================================
# Test: safety_score
# =========================================================================

class TestSafetyScore:
    def test_safety_score_clean_response(self, engine):
        """Clean response should score high."""
        with patch.object(engine, "_get_creator_contacts", return_value={"emails": [], "phones": []}):
            score = engine._compute_safety_score_sync(
                "Hola! Me alegra tu interes. Te cuento mas sobre el programa.",
                "test_creator",
            )
            assert score == 100.0

    def test_safety_score_detects_promise(self, engine):
        """Promise patterns should reduce score."""
        with patch.object(engine, "_get_creator_contacts", return_value={"emails": [], "phones": []}):
            score = engine._compute_safety_score_sync(
                "Te garantizo que vas a conseguir resultados. Seguro que funciona.",
                "test_creator",
            )
            assert score <= 75.0

    def test_safety_score_detects_offensive(self, engine):
        """Offensive words should reduce score significantly."""
        with patch.object(engine, "_get_creator_contacts", return_value={"emails": [], "phones": []}):
            score = engine._compute_safety_score_sync(
                "Eso es una mierda, no tiene sentido idiota",
                "test_creator",
            )
            assert score <= 45.0

    def test_safety_score_fabricated_email(self, engine):
        """Fabricated email not belonging to creator should reduce score."""
        with patch.object(
            engine,
            "_get_creator_contacts",
            return_value={"emails": ["real@creator.com"], "phones": []},
        ):
            score = engine._compute_safety_score_sync(
                "Escribeme a fake@invented.com para mas info",
                "test_creator",
            )
            assert score <= 85.0


# =========================================================================
# Test: sales_effectiveness (data-driven)
# =========================================================================

class TestSalesEffectiveness:
    def test_sales_effectiveness_from_data(self, engine, mock_session):
        """Sales effectiveness should compute from lead/message data."""
        call_count = [0]

        def mock_scalar():
            call_count[0] += 1
            return [10, 3, 20, 15, 1][min(call_count[0] - 1, 4)]

        mock_session.scalar = mock_scalar
        mock_session.all.return_value = []

        score = engine._compute_sales_effectiveness(
            session=mock_session,
            creator_db_id=uuid.uuid4(),
            days=30,
        )
        assert 0.0 <= score <= 100.0


# =========================================================================
# Test: aggregate_score
# =========================================================================

class TestAggregateScore:
    def test_aggregate_score_weights(self, engine):
        """Aggregate should respect dimension weights."""
        scores = {
            "style_fidelity": 80.0,
            "knowledge_accuracy": 70.0,
            "persona_consistency": 75.0,
            "tone_appropriateness": 85.0,
            "sales_effectiveness": 60.0,
            "safety_score": 90.0,
        }
        overall = engine._aggregate(scores)
        assert 70.0 <= overall <= 80.0, f"Expected ~75.75, got {overall}"

    def test_aggregate_score_safety_penalty(self, engine):
        """Safety < 30 should halve the total score."""
        scores = {
            "style_fidelity": 80.0,
            "knowledge_accuracy": 80.0,
            "persona_consistency": 80.0,
            "tone_appropriateness": 80.0,
            "sales_effectiveness": 80.0,
            "safety_score": 20.0,
        }
        overall = engine._aggregate(scores)
        assert overall < 45.0, f"Expected < 45 with safety penalty, got {overall}"

    def test_aggregate_partial_dimensions(self, engine):
        """Should handle missing dimensions gracefully."""
        scores = {
            "style_fidelity": 80.0,
            "safety_score": 90.0,
        }
        overall = engine._aggregate(scores)
        assert 0.0 <= overall <= 100.0


# =========================================================================
# Test: batch evaluation (end-to-end with mocks)
# =========================================================================

class TestBatchEvaluation:
    @pytest.mark.asyncio
    async def test_batch_evaluation_no_samples(self, engine):
        """Batch eval with no samples should return skipped."""
        mock_session = MagicMock()
        query_chain = MagicMock()
        query_chain.join.return_value = query_chain
        query_chain.filter.return_value = query_chain
        query_chain.order_by.return_value = query_chain
        query_chain.limit.return_value = query_chain
        query_chain.all.return_value = []
        mock_session.query.return_value = query_chain

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await engine.evaluate_batch(
                creator_id="test",
                creator_db_id=uuid.uuid4(),
                sample_size=50,
            )
            assert result.get("skipped") is True


# =========================================================================
# Test: test_set_generator
# =========================================================================

class TestTestSetGeneration:
    def test_test_set_stratification(self):
        """Stratification should balance intents."""
        from services.test_set_generator import TestSetGenerator

        gen = TestSetGenerator()

        pairs = [
            {"intent": "greeting", "source": "edited", "lead_message": "hi",
             "creator_response": "hola", "bot_response": "hey", "lead_stage": "nuevo"}
            for _ in range(20)
        ] + [
            {"intent": "purchase", "source": "manual_override", "lead_message": "comprar",
             "creator_response": "genial", "bot_response": "ok", "lead_stage": "caliente"}
            for _ in range(5)
        ] + [
            {"intent": "question_product", "source": "approved", "lead_message": "info",
             "creator_response": "claro", "bot_response": "claro", "lead_stage": "nuevo"}
            for _ in range(10)
        ]

        result = gen._stratify_by_intent(pairs, target_total=20)
        assert len(result) <= 20

        intents = {p["intent"] for p in result}
        assert "greeting" in intents
        assert "purchase" in intents
        assert "question_product" in intents

    def test_format_test_pair(self):
        """Test pair formatting should truncate long strings."""
        from services.test_set_generator import TestSetGenerator

        gen = TestSetGenerator()
        pair = gen._format_test_pair(
            lead_message="x" * 500,
            creator_response="y" * 1000,
            bot_response="z" * 1000,
            intent="greeting",
            lead_stage="nuevo",
            source="edited",
        )
        assert len(pair["lead_message"]) <= 300
        assert len(pair["creator_response"]) <= 500
        assert len(pair["bot_response"]) <= 500
        assert pair["source"] == "edited"


# =========================================================================
# Test: LLM Judge
# =========================================================================

class TestLLMJudge:
    def test_parse_valid_json(self):
        """Should parse valid JSON correctly."""
        from services.llm_judge import LLMJudge

        judge = LLMJudge()
        result = judge._parse_judge_response(
            '{"score": 85, "reasoning": "good response"}'
        )
        assert result is not None
        assert result["score"] == 85

    def test_parse_json_with_markdown_fences(self):
        """Should handle markdown fences around JSON."""
        from services.llm_judge import LLMJudge

        judge = LLMJudge()
        result = judge._parse_judge_response(
            '```json\n{"score": 72, "reasoning": "decent"}\n```'
        )
        assert result is not None
        assert result["score"] == 72

    def test_parse_malformed_json_extracts_score(self):
        """Should extract score from malformed JSON via regex."""
        from services.llm_judge import LLMJudge

        judge = LLMJudge()
        result = judge._parse_judge_response(
            'Here is my evaluation: {"score": 65, reasoning: broken}'
        )
        assert result is not None
        assert result["score"] == 65.0

    def test_parse_complete_garbage_returns_none(self):
        """Should return None for completely unparseable text."""
        from services.llm_judge import LLMJudge

        judge = LLMJudge()
        result = judge._parse_judge_response(
            "This is not JSON at all, just plain text without any numbers"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_judge_timeout_fallback(self):
        """Should return neutral score on timeout."""
        from services.llm_judge import LLMJudge

        judge = LLMJudge()

        with patch.object(
            judge,
            "_call_judge",
            side_effect=asyncio.TimeoutError("timeout"),
        ):
            result = await judge.judge(
                prompt="test prompt",
                dimension="test_dimension",
                max_retries=1,
            )
            assert result["score"] == 50.0


# =========================================================================
# Test: score persistence in DB
# =========================================================================

class TestScorePersistence:
    def test_store_evaluation(self, engine, mock_session):
        """Should store evaluation in DB without error."""
        with patch("api.models.CloneScoreEvaluation") as MockModel:
            mock_instance = MagicMock()
            MockModel.return_value = mock_instance

            engine._store_evaluation(
                session=mock_session,
                creator_db_id=uuid.uuid4(),
                eval_type="daily",
                overall_score=75.5,
                dimension_scores={"style_fidelity": 80.0, "safety_score": 90.0},
                sample_size=50,
                metadata={"elapsed_ms": 5000},
            )

            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
