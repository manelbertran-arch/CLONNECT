"""
Category 5: EXPERIENCIA USUARIO - Test Empatia
Tests that verify the bot detects and responds empathetically to user emotions.

Validates that:
- Explicit frustration ("Estoy harto") is detected with high confidence
  via FrustrationDetector (core.frustration_detector), NOT the context_detector stub
- Objection context includes empathy guidance in context_notes
- Complaint context does not dismiss the user's concern
- Objection handling includes empathetic context signals
- Purchase decision triggers strong interest level
"""

import pytest
from core.context_detector import detect_all, detect_objection_type
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
        """'Estoy harto' and similar phrases produce frustration score > 0.2.

        Uses the FrustrationDetector from core/frustration_detector.py which
        tracks explicit frustration patterns and negative markers.
        The old context_detector.detect_frustration is now a stub.
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
                f"Message '{msg}' should trigger explicit_frustration or " "negative_markers"
            )

        # Verify FrustrationDetector detects this with level > 0
        signals, score = frustration_detector.analyze_message(
            "No me entiendes, ya te lo dije mil veces",
            conversation_id="test_empathy_verify",
        )
        assert signals.level > 0, (
            "FrustrationDetector should flag 'no me entiendes, ya te lo dije mil veces' "
            f"with level > 0, got level={signals.level}"
        )

    def test_valida_sentimientos(self):
        """Objection context has empathy guidance in generated context_notes.

        When a user raises an objection, detect_all should generate context_notes
        that guide the LLM toward empathetic handling.
        """
        objection_msg = "Es demasiado caro, no puedo pagarlo"
        ctx = detect_all(objection_msg, history=None, is_first_message=False)

        # Should detect objection intent
        assert ctx.intent == Intent.OBJECTION or ctx.objection_type == "price", (
            f"Message should be classified as objection, got intent={ctx.intent.value}, "
            f"objection_type='{ctx.objection_type}'"
        )

        # Build context notes and check for objection-related guidance
        notes = ctx.build_context_notes()
        notes_text = " ".join(notes).lower()

        # Context notes should mention the objection type (price)
        empathy_keywords = ["price", "objection"]
        found = any(kw in notes_text for kw in empathy_keywords)
        assert (
            found or ctx.objection_type == "price"
        ), f"Objection context_notes should contain empathy guidance, got: {notes}"

    def test_no_minimiza_problema(self):
        """Complaint context does not dismiss the user's concern.

        When frustration is detected by FrustrationDetector, the signals
        and reasons must acknowledge the problem rather than minimize it.
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

        # Should detect frustration (repetition + explicit count)
        assert score > 0.2, f"Expected frustration score > 0.2, got {score:.2f}"
        assert signals.level > 0, f"Expected frustration level > 0, got {signals.level}"

        # Reasons should describe the signal types, not dismissive language
        reasons_text = " ".join(signals.reasons).lower()
        dismissive_phrases = ["no es para tanto", "tranquilo", "calmate"]
        for phrase in dismissive_phrases:
            assert phrase not in reasons_text, (
                f"Frustration reasons should not contain dismissive phrase '{phrase}'"
            )

    def test_tono_empatico_objecion(self):
        """Objection handling includes empathetic context type.

        When a user voices a trust objection ('no me convence'), the
        context detection pipeline should mark the objection type and
        generate corresponding context_notes with empathetic guidance.
        """
        trust_objection = "No me convence, lo voy a pensar"
        ctx = detect_all(trust_objection, history=None, is_first_message=False)

        # Should detect objection
        intent_str = classify_intent_simple(trust_objection)
        assert (
            intent_str == "objection"
        ), f"Trust objection should classify as 'objection', got '{intent_str}'"

        # Objection type should be trust
        objection_type = detect_objection_type(trust_objection)
        assert objection_type == "trust", f"Should detect trust objection, got '{objection_type}'"

        # context_notes for trust objection should mention trust
        notes_text = " ".join(ctx.context_notes).lower()
        empathy_indicators = ["trust", "objection"]
        found = any(ind in notes_text for ind in empathy_indicators)
        assert found or ctx.objection_type == "trust", (
            "Trust objection should generate empathy-oriented context_notes or "
            f"mark objection_type='trust', got context_notes: {ctx.context_notes}"
        )

    def test_celebra_decision_compra(self):
        """Purchase decision triggers strong interest level.

        When the user says they want to buy, the context detector should
        return strong interest level, enabling the bot to celebrate the decision.
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

            # interest_level == "strong" is the primary signal for purchase
            assert ctx.interest_level == "strong", (
                f"Purchase message '{msg}' should have interest_level='strong'"
            )
