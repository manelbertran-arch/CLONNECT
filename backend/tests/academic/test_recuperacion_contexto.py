"""
Category 4 - DIALOGO MULTI-TURNO: Context Recovery Tests

Tests that context (goals, constraints, situation) accumulated across
multiple conversation turns is preserved and accessible later. Verifies
that the ConversationState and MemoryStore retain information even
after gaps or many turns.

All tests are FAST: no LLM calls, no DB, no filesystem I/O.
"""

from unittest.mock import patch

from core.conversation_state import ConversationPhase, ConversationState, StateManager, UserContext
from services.memory_service import FollowerMemory

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
        phase=ConversationPhase.INICIO,
        context=UserContext(),
    )
    defaults.update(overrides)
    return ConversationState(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRecuperacionContexto:
    """Context recovery across multi-turn conversations."""

    def test_referencia_mensaje_anterior(self):
        """Previous message information is accessible in conversation history.

        FollowerMemory.last_messages stores conversation history so that
        earlier user messages can be referenced in later turns.
        """
        memory = FollowerMemory(
            follower_id="f1",
            creator_id="c1",
        )

        # Simulate appending messages over several turns
        memory.last_messages.append({"role": "user", "content": "Me interesa el coaching"})
        memory.last_messages.append({"role": "assistant", "content": "Genial! Te cuento..."})
        memory.last_messages.append({"role": "user", "content": "Cuanto cuesta?"})
        memory.last_messages.append({"role": "assistant", "content": "Son 150 euros."})

        # The first user message (turn 1) is still accessible
        user_messages = [m["content"] for m in memory.last_messages if m["role"] == "user"]
        assert len(user_messages) == 2
        assert "Me interesa el coaching" in user_messages[0]

    def test_usa_info_turno_1_en_turno_5(self):
        """Information from turn 1 is still available after 5 turns.

        The UserContext accumulates data (goal, situation, constraints)
        and none of it is lost even after multiple update_state calls.
        """
        manager = _make_manager()
        state = _make_state()

        # Turn 1 - user reveals goal
        state = manager.update_state(
            state,
            message="Quiero adelgazar, me sobran unos kilos",
            intent="interest_soft",
            response="Entiendo, te puedo ayudar.",
        )
        assert state.context.goal == "bajar de peso"

        # Turn 2 - user reveals situation
        state = manager.update_state(
            state,
            message="Trabajo en oficina todo el dia",
            intent="other",
            response="Con poco tiempo hay opciones.",
        )

        # Turn 3 - user reveals constraint
        state = manager.update_state(
            state,
            message="No tengo mucho dinero tampoco",
            intent="objection",
            response="Hay opciones accesibles.",
        )

        # Turn 4 - generic follow-up
        state = manager.update_state(
            state,
            message="Eso suena bien",
            intent="interest_soft",
            response="Te cuento los detalles.",
        )

        # Turn 5 - another follow-up
        state = manager.update_state(
            state,
            message="Ok cuentame",
            intent="other",
            response="El plan basico cuesta 49 euros.",
        )

        # All context from turns 1-3 must still be present
        assert state.context.goal == "bajar de peso"
        assert state.context.situation is not None
        assert "trabaja" in state.context.situation
        assert "presupuesto limitado" in state.context.constraints
        assert state.message_count == 5

    def test_no_pierde_contexto(self):
        """Conversation state preserves accumulated context through updates.

        After setting goal, situation, and constraints, calling update_state
        with a message that contains no extractable context should NOT
        clear the existing context.
        """
        manager = _make_manager()
        ctx = UserContext(
            goal="ganar musculo",
            situation="trabaja mucho",
            constraints=["poco tiempo"],
            product_interested="programa de fuerza",
        )
        state = _make_state(
            phase=ConversationPhase.PROPUESTA,
            context=ctx,
        )
        state.message_count = 4

        # Neutral message with no extractable context
        state = manager.update_state(
            state,
            message="Ok, me parece bien",
            intent="other",
            response="Perfecto!",
        )

        # All previously set context must be intact
        assert state.context.goal == "ganar musculo"
        assert state.context.situation == "trabaja mucho"
        assert "poco tiempo" in state.context.constraints
        assert state.context.product_interested == "programa de fuerza"

    def test_resume_conversacion(self):
        """After a gap, the conversation context is still available via StateManager.

        StateManager stores states in-memory keyed by creator:follower.
        Retrieving the state after the gap should return the same context.
        """
        manager = _make_manager()
        state = manager.get_state("follower_x", "creator_x")

        # Simulate a few turns
        state = manager.update_state(
            state,
            message="Me interesa perder peso",
            intent="interest_soft",
            response="Perfecto, cuentame mas.",
        )
        state = manager.update_state(
            state,
            message="Tengo 45 anos y trabajo mucho",
            intent="other",
            response="Entiendo tu situacion.",
        )

        # "Gap" - user comes back later. StateManager should still have the state.
        recovered_state = manager.get_state("follower_x", "creator_x")
        assert recovered_state.context.goal == "bajar de peso"
        assert recovered_state.context.situation is not None
        assert recovered_state.message_count == 2

    def test_continua_donde_quedo(self):
        """Last discussed topic is recoverable from the prompt context.

        The build_enhanced_prompt method should include the user context
        so the LLM knows what was discussed previously.
        """
        manager = _make_manager()
        ctx = UserContext(
            name="Maria",
            goal="mas energia",
            situation="tiene hijos, trabaja mucho",
            constraints=["poco tiempo"],
            product_interested="plan de nutricion",
            price_discussed=True,
        )
        state = _make_state(
            phase=ConversationPhase.OBJECIONES,
            context=ctx,
        )
        state.message_count = 6

        prompt = manager.build_enhanced_prompt(state)

        # The prompt must contain the accumulated context so the LLM
        # can continue where the conversation left off
        assert "mas energia" in prompt
        assert "tiene hijos" in prompt
        assert "poco tiempo" in prompt
        assert "OBJECIONES" in prompt
        # Price reminder should be present since price was discussed
        assert "precio" in prompt.lower()
