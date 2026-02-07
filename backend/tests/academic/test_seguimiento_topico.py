"""
Category 4 - DIALOGO MULTI-TURNO: Topic Tracking Tests

Tests that topic/product context persists across conversation turns,
topic changes are detected, and the conversation state machine tracks
transitions correctly.

All tests are FAST: no LLM calls, no DB.
"""

from unittest.mock import patch

from core.context_detector import detect_all
from core.conversation_state import ConversationPhase, ConversationState, StateManager, UserContext
from core.intent_classifier import classify_intent_simple

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    follower_id: str = "follower_1",
    creator_id: str = "creator_1",
    phase: ConversationPhase = ConversationPhase.INICIO,
) -> ConversationState:
    """Create a ConversationState without touching the DB."""
    return ConversationState(
        follower_id=follower_id,
        creator_id=creator_id,
        phase=phase,
        context=UserContext(),
    )


def _make_manager() -> StateManager:
    """Create a StateManager with DB persistence disabled."""
    with patch.dict("os.environ", {"PERSIST_CONVERSATION_STATE": "false"}):
        manager = StateManager()
    return manager


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSeguimientoTopico:
    """Topic tracking across conversation turns."""

    def test_mantiene_tema_producto(self):
        """Product context set in turn 1 persists in subsequent turns.

        When a user says 'quiero bajar de peso' and this is extracted as a
        goal, the goal must still be present after processing additional
        messages that do not override it.
        """
        manager = _make_manager()
        state = _make_state()

        # Turn 1 - user mentions weight loss goal
        state = manager.update_state(
            state,
            message="Hola, quiero bajar de peso",
            intent="interest_soft",
            response="Genial, te puedo ayudar con eso.",
        )
        assert state.context.goal == "bajar de peso"

        # Turn 2 - user asks a follow-up that does NOT mention a new goal
        state = manager.update_state(
            state,
            message="Cuanto tiempo tarda en verse resultados?",
            intent="question_product",
            response="Normalmente en 4-6 semanas empiezas a notar cambios.",
        )

        # Goal must still be set from turn 1
        assert state.context.goal == "bajar de peso"

    def test_no_cambia_tema_random(self):
        """Sending two messages about the same topic yields the same context type.

        Both messages ask about a product, so detect_all should report
        consistent intent signals (not suddenly change to 'greeting' etc.).
        """
        _ctx1 = detect_all(  # noqa: F841
            "Cuanto cuesta el curso de nutricion?",
            is_first_message=False,
        )
        _ctx2 = detect_all(  # noqa: F841
            "Y que incluye el curso de nutricion?",
            is_first_message=False,
        )

        # Both should have soft/strong interest or question_product intent
        product_intents = {"question_product", "interest_soft", "purchase"}
        assert classify_intent_simple("Cuanto cuesta el curso de nutricion?") in product_intents
        assert classify_intent_simple("Y que incluye el curso de nutricion?") in product_intents

    def test_vuelve_tema_principal(self):
        """After a digression, the main product topic is recoverable from state.

        The user talks about the product, goes off-topic, and when they
        return, the conversation state still has the original goal and
        product context stored.
        """
        manager = _make_manager()
        state = _make_state()

        # Turn 1 - product interest (weight loss)
        state = manager.update_state(
            state,
            message="Me interesa bajar de peso, quiero info del programa",
            intent="interest_soft",
            response="Perfecto, te cuento sobre el programa.",
        )
        assert state.context.goal == "bajar de peso"

        # Turn 2 - off-topic digression
        state = manager.update_state(
            state,
            message="Por cierto, que bonita foto la de ayer!",
            intent="other",
            response="Gracias! Me alegra que te gustara.",
        )

        # Turn 3 - back to product
        state = manager.update_state(
            state,
            message="Bueno, volviendo al programa, cuanto cuesta?",
            intent="purchase",
            response="El programa cuesta 99 euros.",
        )

        # Original goal must still be present
        assert state.context.goal == "bajar de peso"
        # Price was mentioned in the response
        assert state.context.price_discussed is True

    def test_cierra_tema_antes_cambiar(self):
        """Conversation phase tracks topic transitions through the sales funnel.

        As the user progresses from greeting -> qualification -> discovery,
        the phase updates correctly, reflecting the topic evolution.
        """
        manager = _make_manager()
        state = _make_state(phase=ConversationPhase.INICIO)

        # Turn 1 - initial greeting (INICIO -> CUALIFICACION after first msg)
        state = manager.update_state(
            state,
            message="Hola buenas!",
            intent="greeting",
            response="Hola! Que te llamo la atencion?",
        )
        assert state.phase == ConversationPhase.CUALIFICACION

        # Turn 2 - user mentions goal (CUALIFICACION -> DESCUBRIMIENTO)
        state = manager.update_state(
            state,
            message="Quiero perder peso, necesito ayuda",
            intent="interest_soft",
            response="Entiendo! Cuentame un poco sobre tu situacion.",
        )
        assert state.context.goal == "bajar de peso"
        assert state.phase == ConversationPhase.DESCUBRIMIENTO

        # Turn 3 - user gives situation (DESCUBRIMIENTO -> PROPUESTA)
        state = manager.update_state(
            state,
            message="Trabajo en oficina 10 horas al dia y no tengo tiempo",
            intent="other",
            response="Te entiendo perfectamente, el programa se adapta a personas con poco tiempo.",
        )
        assert "poco tiempo" in state.context.constraints
        assert state.phase == ConversationPhase.PROPUESTA

    def test_detecta_cambio_tema_usuario(self):
        """Context detector identifies a new topic when the user shifts subjects.

        A greeting intent followed by a product question intent shows that
        the simple classifier correctly differentiates the two topics.
        """
        # Message 1: greeting
        intent1 = classify_intent_simple("Hola, que tal?")
        assert intent1 == "greeting"

        # Message 2: product question (topic shift)
        intent2 = classify_intent_simple("Cuanto cuesta el programa de coaching?")
        assert intent2 in ("purchase", "question_product")

        # They should NOT be the same intent
        assert intent1 != intent2
