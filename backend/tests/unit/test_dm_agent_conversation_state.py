"""Test conversation_state integration in dm_agent_v2 (Step 9)."""


class TestConversationStateIntegration:
    def test_module_importable(self):
        from core.conversation_state import get_state_manager

        mgr = get_state_manager()
        assert mgr is not None

    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_CONVERSATION_STATE

        assert isinstance(ENABLE_CONVERSATION_STATE, bool)

    def test_new_state_starts_inicio(self):
        from core.conversation_state import ConversationPhase, get_state_manager

        mgr = get_state_manager()
        state = mgr.get_state("test_follower", "test_creator")
        assert state.phase == ConversationPhase.INICIO

    def test_phase_instructions_exist(self):
        from core.conversation_state import ConversationPhase, get_state_manager

        mgr = get_state_manager()
        for phase in ConversationPhase:
            instructions = mgr.get_phase_instructions(phase)
            assert instructions, f"No instructions for {phase.value}"
