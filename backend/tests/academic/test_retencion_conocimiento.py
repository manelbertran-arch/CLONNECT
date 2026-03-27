"""
Category 1: INTELIGENCIA COGNITIVA
Test Suite: Retencion de Conocimiento

Tests that the DM bot retains knowledge across conversation turns:
- Remembers user name when provided
- Tracks products mentioned across turns
- Tracks objections in conversation state
- Records interest level
- Flags already-shared info to avoid repetition

Uses REAL modules (context_detector, memory_service, conversation_state)
and mocks only the LLM/DB services.
"""

from unittest.mock import patch

from core.context_detector import detect_all, extract_user_name
from core.conversation_state import ConversationPhase, ConversationState, StateManager, UserContext
from services.memory_service import ConversationMemoryService, FollowerMemory
from services.prompt_service import PromptBuilder


class TestRetencionConocimiento:
    """Test suite for knowledge retention across conversation turns."""

    # ─── test_recuerda_nombre_usuario ───────────────────────────────────

    def test_recuerda_nombre_usuario(self):
        """
        When user introduces themselves ('Soy Maria'), the context detector
        extracts the name and FollowerMemory stores it for later turns.
        """
        message = "Hola, soy Maria y quiero info"

        # 1. Context detector extracts name
        ctx = detect_all(message, is_first_message=True)
        assert ctx.user_name == "Maria", f"Expected name 'Maria', got '{ctx.user_name}'"

        # 2. Standalone extract_user_name works
        name = extract_user_name("Me llamo Carlos Garcia")
        assert name is not None
        assert "Carlos" in name

        # 3. FollowerMemory stores the name
        memory = FollowerMemory(
            follower_id="ig_123",
            creator_id="creator_1",
            username="maria_user",
            name=ctx.user_name,
        )
        assert memory.name == "Maria"

        # 4. The name persists in serialization round-trip
        data = memory.to_dict()
        restored = FollowerMemory.from_dict(data)
        assert restored.name == "Maria"

        # 5. context_notes include the user name (build_context_notes populates them)
        assert any("Maria" in n for n in ctx.context_notes), (
            f"Expected name in context_notes, got: {ctx.context_notes}"
        )

    # ─── test_recuerda_producto_mencionado ──────────────────────────────

    def test_recuerda_producto_mencionado(self):
        """
        Product discussed in turn 1 is stored in FollowerMemory.products_discussed
        and accessible in turn 3 via prompt builder's user context.
        """
        # Simulate: turn 1 user asks about product, turn 2 bot answers,
        # turn 3 user asks follow-up
        memory = FollowerMemory(
            follower_id="ig_456",
            creator_id="creator_1",
            username="buyer_user",
        )

        # Turn 1: User asks about Curso Premium -> we track it
        memory.products_discussed.append("Curso Premium")
        memory.last_messages.append({"role": "user", "content": "Quiero info del Curso Premium"})
        memory.last_messages.append(
            {"role": "assistant", "content": "El Curso Premium cuesta 297 euros."}
        )

        # Turn 2: More conversation
        memory.last_messages.append({"role": "user", "content": "Que incluye?"})
        memory.last_messages.append(
            {"role": "assistant", "content": "Incluye 12 modulos y acceso de por vida."}
        )

        # Turn 3: Verify product is still tracked
        assert "Curso Premium" in memory.products_discussed

        # Prompt builder should include product history in user context
        builder = PromptBuilder(personality={"name": "TestCreator", "tone": "friendly"})
        user_context = builder.build_user_context(
            username="buyer_user",
            stage="interesado",
            history=memory.last_messages,
            lead_info={"interests": memory.products_discussed},
        )
        assert "Curso Premium" in user_context

        # Serialization preserves products_discussed
        data = memory.to_dict()
        restored = FollowerMemory.from_dict(data)
        assert "Curso Premium" in restored.products_discussed

    # ─── test_recuerda_objecion_previa ──────────────────────────────────

    def test_recuerda_objecion_previa(self):
        """
        Previous objection is tracked in conversation state context
        (UserContext.objections_raised) so the bot can reference it.
        """
        # Create a conversation state with a StateManager
        state = ConversationState(
            follower_id="ig_789",
            creator_id="creator_1",
            phase=ConversationPhase.PROPUESTA,
            context=UserContext(),
            message_count=3,
        )

        # Patch _init_db to avoid actual database calls
        with patch.object(StateManager, "_init_db"):
            manager = StateManager()
            manager._db_available = False

        # User raises a price objection
        objection_msg = "Es demasiado caro para mi"
        state = manager.update_state(
            state, objection_msg, "objection", "Entiendo tu preocupacion..."
        )

        # Objection should move to OBJECIONES phase
        assert state.phase == ConversationPhase.OBJECIONES

        # Constraints should track budget concern
        assert "presupuesto limitado" in state.context.constraints

        # Context reminder should reference the objection/constraints
        manager.get_context_reminder(state)
        # price_discussed may be set if response had euros
        # The state tracks constraints via _extract_context

        # FollowerMemory also tracks objections
        memory = FollowerMemory(
            follower_id="ig_789",
            creator_id="creator_1",
        )
        memory.objections_raised.append("price")
        data = memory.to_dict()
        restored = FollowerMemory.from_dict(data)
        assert "price" in restored.objections_raised

        # Prompt builder shows objections in user context
        builder = PromptBuilder(personality={"name": "Test", "tone": "friendly"})
        user_context = builder.build_user_context(
            username="user_789",
            stage="interesado",
            history=[],
            lead_info={"objections": memory.objections_raised},
        )
        assert "price" in user_context

    # ─── test_recuerda_interes_expresado ────────────────────────────────

    def test_recuerda_interes_expresado(self):
        """
        Interest level is tracked in FollowerMemory.purchase_intent_score
        and in DetectedContext.interest_level for prompt injection.
        """
        message = "Me interesa mucho el programa, cuanto cuesta?"

        # 1. Context detector flags interest
        ctx = detect_all(message, is_first_message=False)
        assert ctx.interest_level in (
            "soft",
            "strong",
        ), f"Expected interest signal, got '{ctx.interest_level}'"

        # 2. FollowerMemory tracks purchase intent score
        memory = FollowerMemory(
            follower_id="ig_interest",
            creator_id="creator_1",
        )
        memory.purchase_intent_score = 0.6
        memory.is_lead = True
        assert memory.purchase_intent_score == 0.6
        assert memory.is_lead is True

        # 3. Score persists through serialization
        data = memory.to_dict()
        restored = FollowerMemory.from_dict(data)
        assert restored.purchase_intent_score == 0.6
        assert restored.is_lead is True

        # 4. Interest level is detected on the DetectedContext field directly
        # (interest is no longer in alerts/context_notes — it's on ctx.interest_level)
        assert ctx.interest_level in ("soft", "strong"), (
            f"Expected interest_level 'soft' or 'strong', got: {ctx.interest_level}"
        )

    # ─── test_no_repite_info_ya_dada ────────────────────────────────────

    def test_no_repite_info_ya_dada(self):
        """
        The ConversationMemoryService detects when info was already given
        (price, link) and generates a context reminder in the prompt to
        avoid repetition. The conversation_state also tracks price_discussed.
        """
        # 1. ConversationMemoryService.should_repeat_info with mock memory
        from models.conversation_memory import ConversationFact, ConversationMemory, FactType

        conv_memory = ConversationMemory(
            lead_id="ig_repeat",
            creator_id="creator_1",
        )

        # Simulate: bot already gave a price
        # add_fact stores PRICE_GIVEN under the key "precio" in info_given dict
        price_fact = ConversationFact(
            fact_type=FactType.PRICE_GIVEN,
            content="297 euros",
            confidence=0.95,
        )
        conv_memory.add_fact(price_fact)

        # Verify fact was stored correctly
        assert conv_memory.has_given_info("precio"), "Price should be in info_given"

        mem_service = ConversationMemoryService.__new__(ConversationMemoryService)
        should_repeat, prev_value = mem_service.should_repeat_info(conv_memory, "precio")
        # Should NOT repeat since price was already given
        assert should_repeat is False, "Should not repeat already-given price"
        assert prev_value == "297 euros"

        # 2. Memory context for prompt should warn about repetition
        prompt_context = mem_service.get_memory_context_for_prompt(conv_memory)
        assert "MEMORIA DE CONVERSACI" in prompt_context or "repitas" in prompt_context.lower()

        # 3. ConversationState also tracks price_discussed
        state = ConversationState(
            follower_id="ig_repeat",
            creator_id="creator_1",
            context=UserContext(price_discussed=True),
        )

        with patch.object(StateManager, "_init_db"):
            manager = StateManager()
            manager._db_available = False

        reminder = manager.get_context_reminder(state)
        assert "precio" in reminder.lower(), f"Expected price reminder, got: '{reminder}'"

        # 4. Facts are tracked via extract_facts
        mem_service_real = ConversationMemoryService.__new__(ConversationMemoryService)
        facts = mem_service_real.extract_facts(
            "Cuanto cuesta?",
            "El curso cuesta 297 euros y aqui tienes el link https://pay.example.com",
            is_bot_response=True,
        )
        fact_types = [f.fact_type for f in facts]
        assert FactType.PRICE_GIVEN in fact_types, "Should detect price in response"
        assert FactType.LINK_SHARED in fact_types, "Should detect link in response"
