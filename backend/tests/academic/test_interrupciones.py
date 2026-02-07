"""
Category 4 - DIALOGO MULTI-TURNO: Interruption Handling Tests

Tests that the conversation system handles abrupt topic changes,
off-topic questions, and interruptions gracefully without losing
the accumulated context or crashing.

All tests are FAST: no LLM calls, no DB.
"""

from unittest.mock import patch

from core.context_detector import DetectedContext, detect_all
from core.conversation_state import ConversationPhase, ConversationState, StateManager, UserContext
from core.intent_classifier import classify_intent_simple

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager() -> StateManager:
    with patch.dict("os.environ", {"PERSIST_CONVERSATION_STATE": "false"}):
        return StateManager()


def _make_state(**overrides) -> ConversationState:
    defaults = dict(
        follower_id="follower_1",
        creator_id="creator_1",
        phase=ConversationPhase.DESCUBRIMIENTO,
        context=UserContext(goal="bajar de peso", situation="trabaja mucho"),
        message_count=3,
    )
    defaults.update(overrides)
    return ConversationState(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInterrupciones:
    """Handling of conversation interruptions and topic changes."""

    def test_maneja_cambio_tema_abrupto(self):
        """A sudden topic change is detected as a different context.

        If the conversation was about a product and the user abruptly
        asks about something unrelated, the intent classifier should
        return a different intent than the product-related one.
        """
        # Product-related message
        intent_product = classify_intent_simple("Cuanto cuesta el programa de coaching?")
        # Completely unrelated message
        intent_random = classify_intent_simple("Oye, sabes que hora es en Mexico?")

        # Product message should be purchase/question related
        assert intent_product in ("purchase", "question_product", "interest_soft")
        # Random question should be classified as "other"
        assert intent_random == "other"

    def test_responde_y_vuelve(self):
        """After handling an off-topic message, original topic is recoverable.

        The ConversationState should still hold the original goal and
        context after processing an off-topic interruption, so the bot
        can return to the sales conversation.
        """
        manager = _make_manager()
        state = _make_state()

        original_goal = state.context.goal
        original_situation = state.context.situation

        # Off-topic interruption
        state = manager.update_state(
            state,
            message="Que bonita la foto de tu ultimo viaje!",
            intent="other",
            response="Gracias! Fue un viaje increible.",
        )

        # Context must be preserved
        assert state.context.goal == original_goal
        assert state.context.situation == original_situation

        # Continue with the original topic
        state = manager.update_state(
            state,
            message="Bueno, volvemos al tema. Que programa me recomiendas?",
            intent="question_product",
            response="Basado en lo que me contaste, te recomiendo el plan basico.",
        )

        # Goal still intact
        assert state.context.goal == original_goal

    def test_no_pierde_hilo(self):
        """State is preserved through multiple interruptions.

        Even with two consecutive off-topic messages, the accumulated
        context (goal, situation, constraints, phase) remains intact.
        """
        manager = _make_manager()
        ctx = UserContext(
            goal="ganar musculo",
            situation="tiene hijos",
            constraints=["poco tiempo", "presupuesto limitado"],
            product_interested="plan de fuerza",
        )
        state = _make_state(
            phase=ConversationPhase.PROPUESTA,
            context=ctx,
            message_count=5,
        )

        # Interruption 1
        state = manager.update_state(
            state,
            message="Jajaja me acuerdo de tu video del perro",
            intent="other",
            response="Si, fue muy gracioso!",
        )

        # Interruption 2
        state = manager.update_state(
            state,
            message="Oye, tienes cuenta de TikTok?",
            intent="other",
            response="Si, me puedes encontrar como @creator en TikTok.",
        )

        # All context must survive both interruptions
        assert state.context.goal == "ganar musculo"
        assert state.context.situation == "tiene hijos"
        assert "poco tiempo" in state.context.constraints
        assert "presupuesto limitado" in state.context.constraints
        assert state.context.product_interested == "plan de fuerza"

    def test_maneja_pregunta_off_topic(self):
        """A random off-topic question does not crash the context detector.

        detect_all should handle any arbitrary message without raising
        exceptions, even if the message is completely unrelated to sales.
        """
        random_messages = [
            "Que opinas del cambio climatico?",
            "Me puedes recomendar una pelicula?",
            "Cual es tu color favorito?",
            "12345!@#$%",
            "",
            "   ",
            "jajajajajaja",
        ]

        for msg in random_messages:
            # Must not raise any exception
            ctx = detect_all(msg, is_first_message=False)
            assert isinstance(ctx, DetectedContext)
            # For empty/whitespace messages, alerts list should still be valid
            assert isinstance(ctx.alerts, list)

    def test_redirige_educadamente(self):
        """Sales redirection intent is detected correctly.

        When the user asks something off-topic but the bot needs to
        redirect back to sales, the context detector should still
        function correctly and the escalation/interest detection should
        work for follow-up messages.
        """
        # Off-topic message
        ctx_offtopic = detect_all(
            "Que opinas del ultimo partido de futbol?",
            is_first_message=False,
        )
        # This is not a sales-related message
        assert ctx_offtopic.interest_level == "none"

        # Follow-up redirect back to product
        ctx_redirect = detect_all(
            "Bueno, me interesa saber mas sobre tu programa",
            is_first_message=False,
        )
        # This should show interest
        assert ctx_redirect.interest_level in ("soft", "strong")

        # Verify the intent classifier also picks up the redirect
        intent_redirect = classify_intent_simple("Bueno, me interesa saber mas sobre tu programa")
        assert intent_redirect == "interest_soft"
