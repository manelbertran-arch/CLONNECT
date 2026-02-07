"""Audit tests for core/conversation_state.py"""

from core.conversation_state import ConversationPhase, ConversationState, StateManager, UserContext


class TestAuditConversationState:
    def test_import(self):
        from core.conversation_state import ConversationPhase, StateManager  # noqa: F811

        assert ConversationPhase is not None
        assert StateManager is not None

    def test_init(self):
        sm = StateManager()
        assert sm is not None

    def test_happy_path_phases(self):
        assert ConversationPhase.INICIO is not None
        assert ConversationPhase.CIERRE is not None
        phases = list(ConversationPhase)
        assert len(phases) >= 5

    def test_edge_case_user_context(self):
        ctx = UserContext()
        assert ctx is not None
        assert ctx.name is None or isinstance(ctx.name, str)

    def test_error_handling_state_creation(self):
        state = ConversationState(follower_id="test", creator_id="test")
        assert state.follower_id == "test"
        assert state.phase is not None
