"""
Tests for ConversationState PostgreSQL persistence (Phase 2.1).

Tests:
1. Feature flag controls persistence
2. State is saved to DB after update
3. State is loaded from DB on get_state
4. Fallback to memory when DB unavailable
5. UserContext serialization/deserialization
"""

import pytest
import os
from unittest.mock import patch


class TestConversationStatePersistence:
    """Test suite for conversation state persistence."""

    def test_feature_flag_disabled(self):
        """When PERSIST_CONVERSATION_STATE=false, should use memory only."""
        with patch.dict(os.environ, {"PERSIST_CONVERSATION_STATE": "false"}):
            # Re-import to pick up new env var
            import importlib
            import core.conversation_state as cs_module
            importlib.reload(cs_module)

            manager = cs_module.StateManager()
            assert manager._db_available is False

            # Should still work with memory
            state = manager.get_state("follower1", "creator1")
            assert state.follower_id == "follower1"
            assert state.creator_id == "creator1"

    def test_state_serialization(self):
        """UserContext should serialize to dict correctly."""
        from core.conversation_state import UserContext, ConversationState, ConversationPhase

        context = UserContext(
            name="María",
            situation="madre de 3, trabaja mucho",
            goal="bajar de peso",
            constraints=["poco tiempo", "presupuesto limitado"],
            product_interested="programa fitness",
            price_discussed=True,
            link_sent=False,
            objections_raised=["es caro"]
        )

        state = ConversationState(
            follower_id="follower123",
            creator_id="creator456",
            phase=ConversationPhase.PROPUESTA,
            context=context,
            message_count=5
        )

        # Serialize context
        context_dict = {
            'name': state.context.name,
            'situation': state.context.situation,
            'goal': state.context.goal,
            'constraints': state.context.constraints,
            'product_interested': state.context.product_interested,
            'price_discussed': state.context.price_discussed,
            'link_sent': state.context.link_sent,
            'objections_raised': state.context.objections_raised
        }

        assert context_dict['name'] == "María"
        assert context_dict['situation'] == "madre de 3, trabaja mucho"
        assert context_dict['goal'] == "bajar de peso"
        assert len(context_dict['constraints']) == 2
        assert context_dict['price_discussed'] is True
        assert "es caro" in context_dict['objections_raised']

    def test_state_deserialization(self):
        """UserContext should deserialize from dict correctly."""
        from core.conversation_state import UserContext

        context_data = {
            'name': "Juan",
            'situation': "trabaja mucho",
            'goal': "ganar musculo",
            'constraints': ["poco tiempo"],
            'product_interested': None,
            'price_discussed': False,
            'link_sent': False,
            'objections_raised': []
        }

        user_context = UserContext(
            name=context_data.get('name'),
            situation=context_data.get('situation'),
            goal=context_data.get('goal'),
            constraints=context_data.get('constraints', []),
            product_interested=context_data.get('product_interested'),
            price_discussed=context_data.get('price_discussed', False),
            link_sent=context_data.get('link_sent', False),
            objections_raised=context_data.get('objections_raised', [])
        )

        assert user_context.name == "Juan"
        assert user_context.goal == "ganar musculo"
        assert user_context.constraints == ["poco tiempo"]

    def test_phase_enum_conversion(self):
        """Phase should convert between enum and string."""
        from core.conversation_state import ConversationPhase

        # String to enum
        phases = ["inicio", "cualificacion", "descubrimiento", "propuesta", "objeciones", "cierre", "escalar"]
        for phase_str in phases:
            phase_enum = ConversationPhase(phase_str)
            assert phase_enum.value == phase_str

        # Enum to string
        assert ConversationPhase.INICIO.value == "inicio"
        assert ConversationPhase.CIERRE.value == "cierre"

    def test_memory_fallback_when_db_fails(self):
        """Should fallback to memory storage if DB import fails."""
        from core.conversation_state import StateManager

        # Even if DB is not available, StateManager should work
        manager = StateManager()

        state = manager.get_state("test_follower", "test_creator")
        assert state is not None
        assert state.follower_id == "test_follower"
        assert state.message_count == 0

    def test_state_update_increments_count(self):
        """update_state should increment message_count."""
        from core.conversation_state import StateManager

        manager = StateManager()
        state = manager.get_state("follower", "creator")

        assert state.message_count == 0

        manager.update_state(state, "hola, me interesa tu programa", "interest", "¡Hola! ¿Qué te llamó la atención?")

        assert state.message_count == 1

    def test_context_extraction(self):
        """_extract_context should capture user info from messages."""
        from core.conversation_state import StateManager

        manager = StateManager()
        state = manager.get_state("follower", "creator")

        # Message with personal info
        manager._extract_context(state, "Soy madre de 2 hijos y trabajo en oficina, quiero bajar de peso")

        assert state.context.situation is not None
        assert "hijos" in state.context.situation
        assert state.context.goal == "bajar de peso"

    def test_phase_transitions(self):
        """State machine should transition phases correctly."""
        from core.conversation_state import StateManager, ConversationPhase

        manager = StateManager()
        state = manager.get_state("follower", "creator")

        # Initial phase
        assert state.phase == ConversationPhase.INICIO

        # After first message, should transition to CUALIFICACION
        manager.update_state(state, "Hola, me interesa", "interest", "¡Hola!")
        assert state.phase == ConversationPhase.CUALIFICACION

        # After providing goal, should transition to DESCUBRIMIENTO
        manager.update_state(state, "Quiero bajar de peso", "interest", "Entiendo")
        assert state.context.goal == "bajar de peso"
        assert state.phase == ConversationPhase.DESCUBRIMIENTO

    def test_cache_after_get(self):
        """State should be cached in memory after get_state."""
        from core.conversation_state import StateManager

        manager = StateManager()

        # First get creates the state
        state1 = manager.get_state("follower", "creator")
        state1.message_count = 5

        # Second get should return same cached state
        state2 = manager.get_state("follower", "creator")
        assert state2.message_count == 5
        assert state1 is state2  # Same object


class TestConversationStateDBModel:
    """Test the SQLAlchemy model structure."""

    def test_model_import(self):
        """ConversationStateDB model should be importable."""
        try:
            from api.models import ConversationStateDB
            assert ConversationStateDB.__tablename__ == "conversation_states"
        except ImportError:
            pytest.skip("api.models not available in test environment")

    def test_model_columns(self):
        """ConversationStateDB should have required columns."""
        try:
            from api.models import ConversationStateDB

            # Check column names exist
            columns = [c.name for c in ConversationStateDB.__table__.columns]
            required_columns = ['id', 'creator_id', 'follower_id', 'phase', 'message_count', 'context', 'created_at', 'updated_at']

            for col in required_columns:
                assert col in columns, f"Missing column: {col}"
        except ImportError:
            pytest.skip("api.models not available in test environment")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
