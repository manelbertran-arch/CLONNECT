"""Audit tests for core/intent_classifier.py."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.intent_classifier import (
    ConversationAnalyzer,
    Intent,
    IntentClassifier,
    IntentResult,
    classify_intent_simple,
    get_lead_status_from_intent,
)

# =========================================================================
# TEST 1: Init / Import
# =========================================================================


class TestIntentClassifierInit:
    """Verify module imports and classifier initialization."""

    def test_classifier_initializes_without_llm(self):
        """IntentClassifier can be created with no LLM client."""
        classifier = IntentClassifier(llm_client=None)
        assert classifier.llm_client is None
        # All intents should have an action mapping
        for intent in Intent:
            assert intent in classifier.INTENT_ACTIONS

    def test_intent_enum_has_all_expected_values(self):
        """Intent enum contains all twelve documented intent types."""
        expected = {
            "greeting",
            "question_general",
            "question_product",
            "interest_soft",
            "interest_strong",
            "objection",
            "support",
            "feedback_positive",
            "feedback_negative",
            "escalation",
            "spam",
            "other",
        }
        actual = {i.value for i in Intent}
        assert actual == expected

    def test_intent_result_defaults(self):
        """IntentResult initializes entities to empty list via __post_init__."""
        result = IntentResult(intent=Intent.OTHER, confidence=0.5)
        assert result.entities == []
        assert result.sub_intent == ""
        assert result.suggested_action == ""

    def test_classifier_with_llm_stores_client(self):
        """IntentClassifier stores the provided LLM client."""
        mock_llm = MagicMock()
        classifier = IntentClassifier(llm_client=mock_llm)
        assert classifier.llm_client is mock_llm

    def test_quick_patterns_populated(self):
        """QUICK_PATTERNS dict is populated for known intents."""
        assert len(IntentClassifier.QUICK_PATTERNS) >= 6
        for intent, patterns in IntentClassifier.QUICK_PATTERNS.items():
            assert isinstance(patterns, list)
            assert len(patterns) > 0


# =========================================================================
# TEST 2: Happy Path - Intent Detection for Known Intents
# =========================================================================


class TestIntentDetectionHappyPath:
    """Quick-classify correctly identifies well-known messages."""

    def test_greeting_detected(self):
        classifier = IntentClassifier()
        result = classifier._quick_classify("hola buenas tardes")
        assert result is not None
        assert result.intent == Intent.GREETING
        assert result.confidence >= 0.8

    def test_strong_interest_detected(self):
        classifier = IntentClassifier()
        result = classifier._quick_classify("quiero comprar el curso")
        assert result is not None
        assert result.intent == Intent.INTEREST_STRONG

    def test_escalation_detected(self):
        classifier = IntentClassifier()
        result = classifier._quick_classify("quiero hablar con un humano")
        assert result is not None
        assert result.intent == Intent.ESCALATION

    def test_simple_classifier_returns_correct_intent(self):
        """classify_intent_simple returns 'interest_strong' for buy signals."""
        assert classify_intent_simple("quiero comprar ya") == "interest_strong"
        assert classify_intent_simple("cuánto cuesta el curso") == "purchase"

    def test_lead_status_mapping(self):
        """get_lead_status_from_intent maps intents to correct lead statuses."""
        assert get_lead_status_from_intent("interest_strong") == "hot"
        assert get_lead_status_from_intent("purchase") == "hot"
        assert get_lead_status_from_intent("interest_soft") == "active"
        assert get_lead_status_from_intent("question_product") == "active"
        assert get_lead_status_from_intent("greeting") == "new"
        assert get_lead_status_from_intent("other") == "new"


# =========================================================================
# TEST 3: Edge Case - Ambiguous Input
# =========================================================================


class TestIntentEdgeCases:
    """Edge cases: ambiguous, very short, or unusual inputs."""

    def test_ambiguous_message_returns_none(self):
        """A message that matches no pattern returns None from quick classify."""
        classifier = IntentClassifier()
        result = classifier._quick_classify("ayer vi una estrella fugaz roja")
        assert result is None

    def test_spam_detected_for_long_crypto_message(self):
        """Long message with crypto keywords triggers spam detection."""
        classifier = IntentClassifier()
        spam_msg = "gana dinero con bitcoin " * 30  # >500 chars + keyword
        result = classifier._quick_classify(spam_msg)
        assert result is not None
        assert result.intent == Intent.SPAM
        assert result.confidence >= 0.8

    def test_case_insensitive_matching(self):
        """Pattern matching is case-insensitive."""
        classifier = IntentClassifier()
        result = classifier._quick_classify("HOLA Buenas Tardes")
        assert result is not None
        assert result.intent == Intent.GREETING

    def test_whitespace_handling(self):
        """Leading/trailing whitespace does not break classification."""
        classifier = IntentClassifier()
        result = classifier._quick_classify("   hola   ")
        assert result is not None
        assert result.intent == Intent.GREETING

    def test_simple_classifier_other_for_random_text(self):
        """classify_intent_simple returns 'other' for unclassifiable text."""
        assert classify_intent_simple("las nubes son blancas") == "other"


# =========================================================================
# TEST 4: Error Handling - Empty Message and LLM Failures
# =========================================================================


class TestIntentErrorHandling:
    """Error scenarios: empty messages, LLM failures, bad JSON."""

    @pytest.mark.asyncio
    async def test_empty_message_without_llm(self):
        """Empty string with no LLM falls back to OTHER."""
        classifier = IntentClassifier(llm_client=None)
        result = await classifier.classify("", use_llm=False)
        assert result.intent == Intent.OTHER
        assert result.confidence <= 0.5

    @pytest.mark.asyncio
    async def test_llm_exception_falls_back_gracefully(self):
        """When LLM raises an exception, classifier returns fallback."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(side_effect=RuntimeError("LLM is down"))
        classifier = IntentClassifier(llm_client=mock_llm)
        result = await classifier.classify("esto es algo raro")
        assert result.intent == Intent.OTHER
        assert "classification_error" in result.sub_intent or result.confidence <= 0.5

    def test_parse_response_with_invalid_json(self):
        """_parse_response returns OTHER with low confidence for garbage."""
        classifier = IntentClassifier()
        result = classifier._parse_response("this is not json at all")
        assert result.intent == Intent.OTHER
        assert result.confidence <= 0.5

    def test_parse_response_with_unknown_intent(self):
        """_parse_response maps unknown intent string to OTHER."""
        classifier = IntentClassifier()
        payload = json.dumps({"intent": "FLYING_SPAGHETTI", "confidence": 0.8})
        result = classifier._parse_response(payload)
        assert result.intent == Intent.OTHER

    @pytest.mark.asyncio
    async def test_classify_no_llm_flag(self):
        """use_llm=False skips LLM even when client is present."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock()
        classifier = IntentClassifier(llm_client=mock_llm)
        result = await classifier.classify("algo extraño", use_llm=False)
        mock_llm.generate.assert_not_called()
        assert result.intent == Intent.OTHER


# =========================================================================
# TEST 5: Integration Check - Confidence Threshold and Actions
# =========================================================================


class TestIntentIntegration:
    """Integration: classifier + actions + conversation analyzer."""

    def test_get_action_returns_mapped_action(self):
        """get_action returns the correct action for each intent."""
        classifier = IntentClassifier()
        assert classifier.get_action(Intent.GREETING) == "greet_and_discover"
        assert classifier.get_action(Intent.SPAM) == "ignore"
        assert classifier.get_action(Intent.ESCALATION) == "escalate_to_human"

    def test_get_intent_description_all_intents(self):
        """get_intent_description returns a non-empty string for all intents."""
        for intent in Intent:
            desc = IntentClassifier.get_intent_description(intent)
            assert isinstance(desc, str)
            assert len(desc) > 0

    @pytest.mark.asyncio
    async def test_parse_response_with_valid_json(self):
        """_parse_response correctly parses well-formed LLM JSON."""
        classifier = IntentClassifier()
        payload = json.dumps(
            {
                "intent": "INTEREST_STRONG",
                "confidence": 0.92,
                "sub_intent": "wants_to_buy",
                "entities": ["curso"],
                "reasoning": "User wants to purchase",
            }
        )
        result = classifier._parse_response(payload)
        assert result.intent == Intent.INTEREST_STRONG
        assert result.confidence == pytest.approx(0.92)
        assert "curso" in result.entities
        assert result.suggested_action == "close_sale"

    @pytest.mark.asyncio
    async def test_conversation_analyzer_purchase_intent(self):
        """ConversationAnalyzer calculates purchase_intent_score correctly."""
        classifier = IntentClassifier(llm_client=None)
        analyzer = ConversationAnalyzer(classifier)
        messages = [
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "Hola!"},
            {"role": "user", "content": "quiero comprar el curso"},
            {"role": "assistant", "content": "Genial!"},
            {"role": "user", "content": "cómo pago"},
        ]
        result = await analyzer.analyze_conversation(messages)
        assert result["total_messages"] == 3
        assert result["purchase_intent_score"] > 0
        assert result["is_engaged"]

    @pytest.mark.asyncio
    async def test_parse_response_strips_markdown_fences(self):
        """_parse_response handles ```json ... ``` wrapper from LLM."""
        classifier = IntentClassifier()
        wrapped = '```json\n{"intent": "GREETING", "confidence": 0.9}\n```'
        result = classifier._parse_response(wrapped)
        assert result.intent == Intent.GREETING
        assert result.confidence == pytest.approx(0.9)
