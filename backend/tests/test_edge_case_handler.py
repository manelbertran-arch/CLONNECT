"""Tests for the EdgeCaseHandler service."""

import pytest

from services.edge_case_handler import (
    EdgeCaseConfig,
    EdgeCaseHandler,
    EdgeCaseType,
)


@pytest.fixture
def handler():
    """Create an EdgeCaseHandler with default config."""
    return EdgeCaseHandler()


@pytest.fixture
def deterministic_handler():
    """Create handler with deterministic config for testing."""
    config = EdgeCaseConfig(
        admit_unknown_chance=1.0,  # Always admit unknown
        dry_response_chance=1.0,  # Always dry
        confidence_threshold=0.7,
    )
    return EdgeCaseHandler(config=config)


class TestSarcasmDetection:
    """Tests for sarcasm detection."""

    def test_detect_claro_que_si(self, handler):
        """Detect 'claro que sí' as sarcasm."""
        result = handler.detect("Claro que sí, como no")
        assert result.edge_type == EdgeCaseType.SARCASM

    def test_detect_no_me_digas(self, handler):
        """Detect 'no me digas' as sarcasm."""
        result = handler.detect("No me digas! Qué sorpresa")
        assert result.edge_type == EdgeCaseType.SARCASM

    def test_detect_obvious(self, handler):
        """Detect 'obvio' as sarcasm."""
        result = handler.detect("Obvio, era de esperarse")
        assert result.edge_type == EdgeCaseType.SARCASM

    def test_sarcasm_has_response(self, handler):
        """Sarcasm should have suggested response."""
        result = handler.detect("Sí, claro, seguro")
        assert result.suggested_response is not None
        assert result.should_escalate is False


class TestIronyDetection:
    """Tests for irony detection."""

    def test_detect_multiple_crying_emoji(self, handler):
        """Multiple 😂 emoji as potential irony."""
        result = handler.detect("Qué gracioso 😂😂😂")
        assert result.edge_type == EdgeCaseType.IRONY

    def test_detect_excessive_question_marks(self, handler):
        """Excessive question marks as irony."""
        result = handler.detect("En serio???")
        assert result.edge_type == EdgeCaseType.IRONY

    def test_detect_long_jaja(self, handler):
        """Long 'jajaja' can be ironic."""
        result = handler.detect("Jajajajajajaja")
        assert result.edge_type == EdgeCaseType.IRONY


class TestUnknownQuestions:
    """Tests for questions the bot shouldn't answer."""

    def test_detect_opinion_question(self, deterministic_handler):
        """Detect personal opinion questions."""
        result = deterministic_handler.detect("Qué piensas de verdad?")
        assert result.edge_type == EdgeCaseType.UNKNOWN_QUESTION

    def test_detect_feeling_question(self, deterministic_handler):
        """Detect feeling questions."""
        result = deterministic_handler.detect("Cómo te sientes hoy?")
        assert result.edge_type == EdgeCaseType.UNKNOWN_QUESTION

    def test_detect_memory_question(self, deterministic_handler):
        """Detect memory questions."""
        result = deterministic_handler.detect("Te acuerdas cuando nos vimos?")
        assert result.edge_type == EdgeCaseType.UNKNOWN_QUESTION

    def test_unknown_has_no_se_response(self, deterministic_handler):
        """Unknown questions should get 'no sé' response."""
        result = deterministic_handler.detect("Qué harías tú en mi lugar?")
        if result.edge_type == EdgeCaseType.UNKNOWN_QUESTION:
            assert result.suggested_response is not None
            assert "no" in result.suggested_response.lower() or "sé" in result.suggested_response.lower() or "idea" in result.suggested_response.lower()


class TestPersonalQuestions:
    """Tests for personal questions."""

    def test_detect_relationship_question(self, handler):
        """Detect relationship questions."""
        result = handler.detect("Tienes novia?")
        assert result.edge_type == EdgeCaseType.PERSONAL_QUESTION

    def test_detect_phone_request(self, handler):
        """Detect phone number requests."""
        result = handler.detect("Dame tu whatsapp")
        assert result.edge_type == EdgeCaseType.PERSONAL_QUESTION

    def test_detect_age_question(self, handler):
        """Detect age questions."""
        result = handler.detect("Cuántos años tienes?")
        assert result.edge_type == EdgeCaseType.PERSONAL_QUESTION

    def test_personal_has_deflection(self, handler):
        """Personal questions should get deflection."""
        result = handler.detect("Dónde vives ahora?")
        assert result.suggested_response is not None
        assert result.should_escalate is False


class TestOffTopic:
    """Tests for off-topic detection."""

    def test_detect_politics(self, handler):
        """Detect political questions."""
        result = handler.detect("Qué opinas de política?")
        assert result.edge_type == EdgeCaseType.OFF_TOPIC

    def test_detect_voting(self, handler):
        """Detect voting questions."""
        result = handler.detect("Por quién votaste?")
        assert result.edge_type == EdgeCaseType.OFF_TOPIC

    def test_off_topic_has_deflection(self, handler):
        """Off-topic should get deflection."""
        result = handler.detect("Eres de derecha o izquierda?")
        assert result.suggested_response is not None


class TestComplaints:
    """Tests for complaint detection."""

    def test_detect_not_working(self, handler):
        """Detect 'not working' complaints."""
        result = handler.detect("Esto no me sirve para nada")
        assert result.edge_type == EdgeCaseType.COMPLAINT

    def test_detect_refund_request(self, handler):
        """Detect refund requests."""
        result = handler.detect("Quiero mi devolución")
        assert result.edge_type == EdgeCaseType.COMPLAINT

    def test_detect_scam_accusation(self, handler):
        """Detect scam accusations."""
        result = handler.detect("Me siento estafado")
        assert result.edge_type == EdgeCaseType.COMPLAINT

    def test_complaint_escalates(self, handler):
        """Complaints should escalate."""
        result = handler.detect("Esto es una mierda total")
        assert result.should_escalate is True

    def test_complaint_has_empathy(self, handler):
        """Complaints should get empathy response."""
        result = handler.detect("Perdí mi dinero con esto")
        assert result.suggested_response is not None
        # Response should be empathetic
        empathy_words = ["entiendo", "lamento", "normal"]
        has_empathy = any(w in result.suggested_response.lower() for w in empathy_words)
        assert has_empathy


class TestAggressive:
    """Tests for aggressive detection."""

    def test_detect_insult(self, handler):
        """Detect insults."""
        result = handler.detect("Eres idiota")
        assert result.edge_type == EdgeCaseType.AGGRESSIVE

    def test_detect_profanity(self, handler):
        """Detect profanity."""
        result = handler.detect("Vete a la mierda")
        assert result.edge_type == EdgeCaseType.AGGRESSIVE

    def test_aggressive_escalates(self, handler):
        """Aggressive should always escalate."""
        result = handler.detect("Eres estúpido")
        assert result.should_escalate is True

    def test_aggressive_no_auto_response(self, handler):
        """Aggressive should not have auto response."""
        result = handler.detect("Hijo de puta")
        assert result.suggested_response is None


class TestNoEdgeCase:
    """Tests for normal messages (no edge case)."""

    def test_normal_greeting(self, handler):
        """Normal greeting is not edge case."""
        result = handler.detect("Hola! Cómo estás?")
        assert result.edge_type == EdgeCaseType.NONE

    def test_normal_question(self, handler):
        """Normal question is not edge case."""
        result = handler.detect("Cuánto cuesta el coaching?")
        assert result.edge_type == EdgeCaseType.NONE

    def test_normal_thanks(self, handler):
        """Normal thanks is not edge case."""
        result = handler.detect("Muchas gracias por la info!")
        assert result.edge_type == EdgeCaseType.NONE


class TestAdmitUnknown:
    """Tests for 'admit unknown' functionality."""

    def test_low_confidence_admits(self, deterministic_handler):
        """Low confidence should admit unknown."""
        should_admit, response = deterministic_handler.should_admit_unknown(0.5)
        assert should_admit is True
        assert response is not None

    def test_high_confidence_not_admits(self, handler):
        """High confidence should not admit unknown."""
        should_admit, response = handler.should_admit_unknown(0.9)
        assert should_admit is False
        assert response is None


class TestDryResponses:
    """Tests for dry response functionality."""

    def test_dry_for_confirmation(self, deterministic_handler):
        """Confirmations can get dry response."""
        response = deterministic_handler.get_dry_response_if_appropriate("confirmation")
        assert response is not None
        assert response in ["Ok", "Vale", "👍", "Sí", "Claro"]

    def test_no_dry_for_greeting(self, handler):
        """Greetings should not get dry response."""
        # Run multiple times - should rarely/never get dry
        dry_count = sum(
            1 for _ in range(20)
            if handler.get_dry_response_if_appropriate("greeting") is not None
        )
        assert dry_count == 0


class TestProcessWithContext:
    """Tests for full processing flow."""

    def test_edge_case_overrides_llm(self, handler):
        """Edge case response should override LLM."""
        response, escalate = handler.process_with_context(
            message="Tienes novia?",
            llm_response="Sí, tengo una novia muy guapa",
            llm_confidence=0.9,
        )
        # Should use deflection, not LLM response
        assert "guapa" not in response

    def test_aggressive_returns_llm_but_escalates(self, handler):
        """Aggressive should escalate but no auto-response."""
        response, escalate = handler.process_with_context(
            message="Eres idiota",
            llm_response="Lo siento si te frustré",
            llm_confidence=0.8,
        )
        assert escalate is True
        # No auto-response, so uses LLM
        assert response == "Lo siento si te frustré"

    def test_normal_uses_llm(self, handler):
        """Normal message should use LLM response."""
        response, escalate = handler.process_with_context(
            message="Cuánto cuesta?",
            llm_response="El precio es 150€",
            llm_confidence=0.9,
        )
        assert response == "El precio es 150€"
        assert escalate is False


class TestEdgeCasePriority:
    """Tests for edge case priority ordering."""

    def test_aggressive_over_sarcasm(self, handler):
        """Aggressive should take priority over sarcasm."""
        # Message with both aggressive and sarcasm patterns
        result = handler.detect("Eres idiota, claro que sí")
        assert result.edge_type == EdgeCaseType.AGGRESSIVE

    def test_complaint_over_off_topic(self, handler):
        """Complaint should take priority over off-topic."""
        result = handler.detect("Esto no me sirve, qué opinas de política?")
        assert result.edge_type == EdgeCaseType.COMPLAINT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
