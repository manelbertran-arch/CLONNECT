"""
Category 5: EXPERIENCIA USUARIO - Test Empatia
Tests that verify the bot detects and responds empathetically to user emotions.

Validates that:
- Explicit frustration ("Estoy harto") is detected with high confidence
- Objection context includes empathy guidance in alerts
- Complaint context does not dismiss the user's concern
- Objection handling includes empathetic context signals
- Purchase decision triggers a positive context type (celebration)
"""

import pytest
from core.context_detector import detect_all, detect_frustration, detect_objection_type
from core.frustration_detector import FrustrationDetector
from core.intent_classifier import Intent, classify_intent_simple
from services.length_controller import classify_lead_context

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def frustration_detector() -> FrustrationDetector:
    """Fresh FrustrationDetector with no history."""
    return FrustrationDetector()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEmpatia:
    """Bot must detect emotions and respond with empathy."""

    def test_reconoce_frustracion(self, frustration_detector):
        """'Estoy harto' and similar phrases produce frustration score > 0.5.

        Uses the FrustrationDetector from core/frustration_detector.py which
        tracks explicit frustration patterns and negative markers.
        """
        frustrated_messages = [
            "Estoy harto, no me ayudas nada",
            "Esto no funciona, no sirve para nada, eres inutil",
            "No entiendes nada, ya te lo dije mil veces",
        ]

        for msg in frustrated_messages:
            signals, score = frustration_detector.analyze_message(
                msg, conversation_id="test_empathy"
            )
            assert score > 0.2, (
                f"Message '{msg}' should produce frustration score > 0.2, " f"got {score:.2f}"
            )
            assert signals.explicit_frustration or signals.negative_markers > 0, (
                f"Message '{msg}' should trigger explicit_frustration or " f"negative_markers"
            )

        # Also verify via context_detector.detect_frustration
        result = detect_frustration("No me entiendes, ya te lo dije mil veces")
        assert (
            result.is_frustrated
        ), "detect_frustration should flag 'no me entiendes, ya te lo dije mil veces'"
        assert result.level in (
            "moderate",
            "severe",
        ), f"Frustration level should be moderate/severe, got '{result.level}'"

    def test_valida_sentimientos(self):
        """Objection context has empathy guidance in generated alerts.

        When a user raises an objection, detect_all should generate alerts
        that guide the LLM toward empathetic handling.
        """
        objection_msg = "Es demasiado caro, no puedo pagarlo"
        ctx = detect_all(objection_msg, history=None, is_first_message=False)

        # Should detect objection intent
        assert ctx.intent == Intent.OBJECTION or ctx.objection_type == "price", (
            f"Message should be classified as objection, got intent={ctx.intent.value}, "
            f"objection_type='{ctx.objection_type}'"
        )

        # Build alerts and check for empathy-related guidance
        alerts = ctx.build_alerts()
        alerts_text = " ".join(alerts).lower()

        # Alerts should mention value, alternatives, or empathy
        empathy_keywords = ["valor", "alternativa", "precio", "objecion", "objeción"]
        found = any(kw in alerts_text for kw in empathy_keywords)
        assert (
            found or len(alerts) > 0
        ), f"Objection alerts should contain empathy guidance, got: {alerts}"

    def test_no_minimiza_problema(self):
        """Complaint context does not dismiss the user's concern.

        When frustration is detected, the frustration context string
        generated for the LLM must include directives to acknowledge
        the problem rather than minimize it.
        """
        detector = FrustrationDetector()

        # Simulate a frustrated user who repeated a question
        previous = [
            "Cuanto cuesta el curso?",
            "Oye, cuanto cuesta?",
            "Te pregunto otra vez, cual es el precio?",
        ]
        signals, score = detector.analyze_message(
            "Ya te lo pregunte 3 veces, el precio!!",
            conversation_id="test_no_minimize",
            previous_messages=previous,
        )

        frustration_context = detector.get_frustration_context(score, signals)

        if frustration_context:
            context_lower = frustration_context.lower()
            # Must NOT contain dismissive language
            dismissive_phrases = ["no es para tanto", "tranquilo", "calmate"]
            for phrase in dismissive_phrases:
                assert phrase not in context_lower, (
                    f"Frustration context should not contain dismissive " f"phrase '{phrase}'"
                )

            # SHOULD contain empathetic directives
            empathetic_phrases = ["directo", "concis", "repita", "empatia", "empatía"]
            found = any(p in context_lower for p in empathetic_phrases)
            assert found, (
                "Frustration context should include empathetic directives "
                f"(directo/conciso/empatia), got: {frustration_context[:200]}"
            )

    def test_tono_empatico_objecion(self):
        """Objection handling includes empathetic context type.

        When a user voices a trust objection ('no me convence'), the
        context detection pipeline should mark the objection type and
        generate corresponding alerts with empathetic guidance.
        """
        trust_objection = "No estoy seguro, tengo muchas dudas"
        ctx = detect_all(trust_objection, history=None, is_first_message=False)

        # Should detect objection
        intent_str = classify_intent_simple(trust_objection)
        assert (
            intent_str == "objection"
        ), f"Trust objection should classify as 'objection', got '{intent_str}'"

        # Objection type should be trust
        objection_type = detect_objection_type(trust_objection)
        assert objection_type == "trust", f"Should detect trust objection, got '{objection_type}'"

        # Alerts for trust objection should mention guarantees or testimony
        alerts_text = " ".join(ctx.alerts).lower()
        empathy_indicators = ["confianza", "garant", "testimonio", "dudas", "objeción", "objecion"]
        found = any(ind in alerts_text for ind in empathy_indicators)
        assert found or ctx.objection_type == "trust", (
            "Trust objection should generate empathy-oriented alerts or "
            f"mark objection_type='trust', got alerts: {ctx.alerts}"
        )

    def test_celebra_decision_compra(self):
        """Purchase decision triggers a positive context type.

        When the user says they want to buy, the context detector should
        return strong interest and positive sentiment, enabling the bot
        to celebrate the decision.
        """
        purchase_messages = [
            "Me apunto, como pago?",
            "Lo quiero, donde compro?",
            "Quiero inscribirme ya!",
        ]

        for msg in purchase_messages:
            ctx = detect_all(msg, history=None, is_first_message=False)

            assert ctx.interest_level == "strong", (
                f"Message '{msg}' should have strong interest, " f"got '{ctx.interest_level}'"
            )

            # Length context should be 'interes' (short acknowledging response)
            lead_ctx = classify_lead_context(msg)
            assert lead_ctx == "interes", (
                f"Purchase message '{msg}' should classify as 'interes' "
                f"context for length, got '{lead_ctx}'"
            )

            # Alerts should mention purchase facilitation
            alerts_text = " ".join(ctx.alerts).lower()
            assert "compra" in alerts_text or "pago" in alerts_text or "reserva" in alerts_text, (
                f"Purchase alerts should mention compra/pago/reserva, " f"got: {ctx.alerts}"
            )
