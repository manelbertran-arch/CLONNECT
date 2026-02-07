"""
Category 4 - DIALOGO MULTI-TURNO: Conversation Phase Transition Tests

Tests that the ConversationState machine transitions correctly between
sales funnel phases (INICIO -> CUALIFICACION -> ... -> CIERRE) and that
transitions feel natural (related contexts flow smoothly).

All tests are FAST: no LLM calls, no DB.
"""

from unittest.mock import patch

from core.conversation_state import ConversationPhase, ConversationState, StateManager, UserContext
from core.intent_classifier import classify_intent_simple

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    phase: ConversationPhase = ConversationPhase.INICIO,
    message_count: int = 0,
    goal: str = None,
    situation: str = None,
) -> ConversationState:
    ctx = UserContext()
    if goal:
        ctx.goal = goal
    if situation:
        ctx.situation = situation
    return ConversationState(
        follower_id="follower_1",
        creator_id="creator_1",
        phase=phase,
        context=ctx,
        message_count=message_count,
    )


def _make_manager() -> StateManager:
    with patch.dict("os.environ", {"PERSIST_CONVERSATION_STATE": "false"}):
        return StateManager()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTransiciones:
    """Conversation phase transitions through the sales funnel."""

    def test_transicion_saludo_a_negocio(self):
        """Greeting -> product question is detected as a phase change.

        When the user starts with 'Hola' (INICIO) and then asks about a
        product, the state machine should advance to CUALIFICACION (at
        minimum), reflecting the shift from greeting to business.
        """
        manager = _make_manager()
        state = _make_state(phase=ConversationPhase.INICIO)

        # Turn 1: greeting
        state = manager.update_state(
            state,
            message="Hola buenas tardes!",
            intent="greeting",
            response="Hola! Que te llamo la atencion?",
        )
        # After first message in INICIO, should move to CUALIFICACION
        assert state.phase == ConversationPhase.CUALIFICACION

        # Verify that intent detection sees the product question differently
        intent_greeting = classify_intent_simple("Hola buenas tardes!")
        intent_product = classify_intent_simple("Me interesa el curso de nutricion")
        assert intent_greeting == "greeting"
        assert intent_product == "interest_soft"

    def test_transicion_info_a_cierre(self):
        """Information phase -> closing is detected when user shows strong interest.

        If the user is in PROPUESTA phase and says something like "lo quiero",
        the state should transition to CIERRE.
        """
        manager = _make_manager()
        state = _make_state(
            phase=ConversationPhase.PROPUESTA,
            message_count=4,
            goal="bajar de peso",
        )

        # User shows strong purchase intent
        state = manager.update_state(
            state,
            message="Me encanta, lo quiero! Pasame el link",
            intent="interest_strong",
            response="Genial! Aqui tienes el link: https://buy.example.com",
        )

        assert state.phase == ConversationPhase.CIERRE
        assert state.context.link_sent is True

    def test_transicion_objecion_a_valor(self):
        """Objection -> value proposition transition.

        When the user raises an objection from PROPUESTA, the state machine
        should transition to OBJECIONES. Then if the user shows renewed
        interest, it should transition to CIERRE.
        """
        manager = _make_manager()
        state = _make_state(
            phase=ConversationPhase.PROPUESTA,
            message_count=5,
            goal="ganar musculo",
        )

        # User raises price objection
        state = manager.update_state(
            state,
            message="Es muy caro, no se si puedo pagarlo",
            intent="objection",
            response="Entiendo tu preocupacion. Tenemos opcion de pago en cuotas.",
        )
        assert state.phase == ConversationPhase.OBJECIONES

        # User shows renewed interest after objection handling
        state = manager.update_state(
            state,
            message="Vale, si se puede en cuotas si me interesa",
            intent="interest_strong",
            response="Perfecto! Te paso el link para pagar en cuotas.",
        )
        assert state.phase == ConversationPhase.CIERRE

    def test_transicion_natural(self):
        """Transitions follow a natural progression and do not skip phases.

        Walking through the full funnel: INICIO -> CUALIFICACION ->
        DESCUBRIMIENTO -> PROPUESTA, each step transitions logically.
        """
        manager = _make_manager()
        state = _make_state(phase=ConversationPhase.INICIO)
        phases_visited = [state.phase]

        # Step 1: greeting
        state = manager.update_state(
            state,
            message="Hola!",
            intent="greeting",
            response="Hola! Que te interesa?",
        )
        phases_visited.append(state.phase)

        # Step 2: mentions goal
        state = manager.update_state(
            state,
            message="Quiero tener mas energia",
            intent="interest_soft",
            response="Que bien! Cuentame mas sobre tu dia a dia.",
        )
        phases_visited.append(state.phase)

        # Step 3: gives context about situation
        state = manager.update_state(
            state,
            message="Soy madre de 3 hijos y trabajo como enfermera",
            intent="other",
            response="Entiendo, con tu ritmo necesitas algo practico.",
        )
        phases_visited.append(state.phase)

        # Verify natural progression without skipping
        expected_progression = [
            ConversationPhase.INICIO,
            ConversationPhase.CUALIFICACION,
            ConversationPhase.DESCUBRIMIENTO,
            ConversationPhase.PROPUESTA,
        ]
        assert phases_visited == expected_progression

    def test_no_transicion_brusca(self):
        """Related contexts do not cause an abrupt phase skip.

        Staying in CUALIFICACION when the user asks follow-up questions
        without revealing their goal should NOT jump to PROPUESTA.
        """
        manager = _make_manager()
        state = _make_state(
            phase=ConversationPhase.CUALIFICACION,
            message_count=1,
        )

        # User asks a generic question (no goal revealed)
        state = manager.update_state(
            state,
            message="Que tipo de cosas ofreces?",
            intent="question_product",
            response="Tengo programas de nutricion, entrenamiento y coaching.",
        )

        # Should stay in CUALIFICACION or move to DESCUBRIMIENTO at most,
        # NOT jump to PROPUESTA or CIERRE
        assert state.phase in (
            ConversationPhase.CUALIFICACION,
            ConversationPhase.DESCUBRIMIENTO,
        )
        # Definitely should NOT be in closing phases
        assert state.phase not in (
            ConversationPhase.PROPUESTA,
            ConversationPhase.CIERRE,
            ConversationPhase.ESCALAR,
        )
