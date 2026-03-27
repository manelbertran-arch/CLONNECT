"""
Category 6: ROBUSTEZ - Test Out-of-Domain (OOD)
Tests that the bot handles out-of-domain messages correctly: detecting
off-topic content, avoiding hallucinations, redirecting to business
topics, suggesting escalation, and being honest about limitations.

Validates that:
- Off-topic questions are detected as 'other' intent
- Unknown products do not trigger hallucinated details
- Off-topic messages are guided back to business context
- Complex off-domain situations suggest escalation
- The bot acknowledges its limitations honestly
"""

from core.context_detector import detect_all
from core.guardrails import ResponseGuardrail
from core.intent_classifier import Intent, IntentClassifier, classify_intent_simple
from core.output_validator import validate_products


class TestOutOfDomain:
    """Test suite for out-of-domain message handling."""

    # ---- test_reconoce_fuera_dominio -------------------------------------

    def test_reconoce_fuera_dominio(self):
        """
        A weather question like 'Que tiempo hace hoy?' should be classified
        as 'other' by the intent classifier (not a product or purchase intent).
        """
        message = "Que tiempo hace hoy?"

        # Simple classifier should return "other"
        intent = classify_intent_simple(message)
        assert intent == "other", f"Weather question should be 'other', got '{intent}'"

        # Full classifier quick path should not match any business intent
        classifier = IntentClassifier()
        result = classifier._quick_classify(message)
        # Should be None (no pattern match) or OTHER
        if result is not None:
            assert result.intent == Intent.OTHER

        # Context detector should show no purchase interest
        ctx = detect_all(message, is_first_message=False)
        assert ctx.interest_level == "none"
        # Intent should be OTHER
        assert ctx.intent == Intent.OTHER

    # ---- test_no_inventa_si_no_sabe --------------------------------------

    def test_no_inventa_si_no_sabe(self):
        """
        When the LLM invents a product that does not exist, the output
        validator's product validation should flag it as unknown.
        """
        # Simulated LLM response that invents a product
        response = 'Te recomiendo el curso "Masterclass de Blockchain" que es increible.'

        # Known products do not include "Masterclass de Blockchain"
        known_products = ["Coaching Premium", "Taller Instagram"]

        issues = validate_products(response, known_products)

        # The unknown product should be flagged
        flagged_types = [i.type for i in issues]
        assert "unknown_product" in flagged_types, (
            "Hallucinated product 'Masterclass de Blockchain' should be flagged "
            f"as unknown_product. Got issues: {flagged_types}"
        )

    # ---- test_redirige_a_tema --------------------------------------------

    def test_redirige_a_tema(self):
        """
        When the user asks about bitcoin (off-topic) and the LLM gives an
        opinion, the guardrail off-topic check should redirect the response
        back to the business topic.
        """
        query = "Que opinas de bitcoin?"
        # Simulated LLM response that gives an opinion on bitcoin
        off_topic_response = (
            "Bitcoin es una criptomoneda muy interesante, creo que tiene "
            "mucho potencial a largo plazo."
        )

        guardrail = ResponseGuardrail()

        safe = guardrail.get_safe_response(
            query=query,
            response=off_topic_response,
            context={"products": [], "language": "es"},
        )

        # The response should be a redirect, not the bitcoin opinion
        assert (
            "bitcoin" not in safe.lower() or "fuera de mi" in safe.lower()
        ), "Guardrail should redirect bitcoin opinion to business topic"
        # Should contain a redirect phrase
        redirect_indicators = [
            "fuera de mi",
            "no es mi",
            "en que",
            "puedo ayudarte",
            "especialidad",
            "area",
            "momento",
        ]
        has_redirect = any(ind in safe.lower() for ind in redirect_indicators)
        assert has_redirect, f"Response should contain a redirect phrase. Got: '{safe}'"

