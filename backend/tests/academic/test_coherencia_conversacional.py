"""
Category 1: INTELIGENCIA COGNITIVA
Test Suite: Coherencia Conversacional

Tests that the DM bot maintains logical conversational flow:
- Greeting triggers greeting-type response
- Price question triggers price/product response
- Objection is addressed, not ignored
- Responses are contextually relevant
- Multi-turn context is maintained

Uses REAL modules (intent_classifier, context_detector, length_controller)
and mocks only the LLM service.
"""

from core.context_detector import detect_all
from core.intent_classifier import Intent, IntentClassifier, classify_intent_simple
from services.intent_service import Intent as ServiceIntent
from services.intent_service import IntentClassifier as ServiceIntentClassifier
from services.length_controller import detect_message_type
from services.prompt_service import PromptBuilder


class TestCoherenciaConversacional:
    """Test suite for conversational coherence."""

    # ─── test_flujo_logico_saludo_respuesta ─────────────────────────────

    def test_flujo_logico_saludo_respuesta(self):
        """
        When user says 'Hola', the intent classifier should detect a greeting,
        context detector should flag it as first message, and the length
        controller should classify it as a 'saludo' context.
        """
        message = "Hola"

        # 1. Intent classification (core module - pattern-based)
        classifier = IntentClassifier()
        result = classifier._quick_classify(message)
        assert result is not None, "Greeting should be detected by quick classify"
        assert result.intent == Intent.GREETING
        assert result.confidence >= 0.85

        # 2. Simple intent classifier
        simple_intent = classify_intent_simple(message)
        assert simple_intent == "greeting"

        # 3. Service-level intent classifier
        service_classifier = ServiceIntentClassifier()
        service_intent = service_classifier.classify(message)
        assert service_intent == ServiceIntent.GREETING

        # 4. Context detector flags first message + greeting intent
        ctx = detect_all(message, history=None, is_first_message=True)
        assert ctx.intent == Intent.GREETING
        assert ctx.is_first_message is True
        # Greeting with no special context → empty context_notes (expected)
        # The is_first_message flag is the signal, not a context note

        # 5. Length controller should classify as saludo
        msg_type = detect_message_type(message)
        assert msg_type == "saludo"

    # ─── test_flujo_logico_pregunta_precio ──────────────────────────────

    def test_flujo_logico_pregunta_precio(self):
        """
        When user asks 'Cuanto cuesta?', intent should be purchase/price-related,
        and context should detect strong interest. The prompt builder should
        include product info in the system prompt.
        """
        message = "Cuanto cuesta?"

        # 1. Core intent classifier detects strong interest (price = purchase signal)
        simple_intent = classify_intent_simple(message)
        assert (
            simple_intent == "purchase"
        ), f"Price question should map to 'purchase' intent, got '{simple_intent}'"

        # 2. Service intent classifier detects product question
        service_classifier = ServiceIntentClassifier()
        service_intent = service_classifier.classify(message)
        assert service_intent in (
            ServiceIntent.PRODUCT_QUESTION, ServiceIntent.PRICING
        ), f"Expected PRODUCT_QUESTION or PRICING, got {service_intent}"

        # 3. Context detector should flag interest level
        ctx = detect_all(message, is_first_message=False)
        assert (
            ctx.interest_level == "strong"
        ), f"Price question should indicate strong interest, got '{ctx.interest_level}'"

        # 4. Prompt builder includes products in system prompt when provided
        products = [{"name": "Curso Premium", "price": 297, "description": "Curso completo"}]
        builder = PromptBuilder(personality={"name": "TestCreator", "tone": "friendly"})
        system_prompt = builder.build_system_prompt(products=products)
        assert "Curso Premium" in system_prompt
        assert "297" in system_prompt

        # 5. Length controller classifies as price question
        msg_type = detect_message_type(message)
        assert msg_type == "pregunta_precio"

    # ─── test_flujo_logico_objecion_handling ────────────────────────────

    def test_flujo_logico_objecion_handling(self):
        """
        When user says 'Es muy caro', the system should detect an objection
        and generate context alerts that instruct the LLM to address the
        objection (not ignore it).
        """
        message = "Es muy caro"

        # 1. Core intent classifier detects objection
        simple_intent = classify_intent_simple(message)
        assert simple_intent == "objection"

        # 2. Pattern-based classifier also detects objection
        classifier = IntentClassifier()
        result = classifier._quick_classify(message)
        assert result is not None
        assert result.intent == Intent.OBJECTION

        # 3. Context detector identifies objection type as "price"
        ctx = detect_all(message, is_first_message=False)
        assert ctx.intent == Intent.OBJECTION
        assert (
            ctx.objection_type == "price"
        ), f"Expected 'price' objection type, got '{ctx.objection_type}'"

        # 4. Alerts should include price objection handling instruction
        assert len(ctx.alerts) > 0, "Objection should generate at least one alert"
        alerts_text = " ".join(ctx.alerts)
        assert (
            "precio" in alerts_text.lower() or "price" in alerts_text.lower()
        ), f"Price objection alert expected, got: {ctx.alerts}"

        # 5. Length controller recognizes objection context (longer response needed)
        msg_type = detect_message_type(message)
        assert msg_type == "objecion"

    # ─── test_no_responde_random ────────────────────────────────────────

    def test_no_responde_random(self):
        """
        The prompt builder should include conversation history and user context
        so the LLM response is grounded in the conversation, not random.
        Verify the user context section references the correct stage and history.
        """
        history = [
            {"role": "user", "content": "Hola, me interesa el curso de cocina"},
            {"role": "assistant", "content": "Hola! El curso de cocina es genial."},
        ]

        builder = PromptBuilder(personality={"name": "Chef Maria", "tone": "friendly"})
        user_context = builder.build_user_context(
            username="test_user",
            stage="interesado",
            history=history,
        )

        # 1. User context should include the username
        assert "test_user" in user_context

        # 2. User context should include the lead stage
        assert "interesado" in user_context

        # 3. User context should include conversation history
        assert "curso de cocina" in user_context
        assert "genial" in user_context

        # 4. System prompt should include personality identity
        system_prompt = builder.build_system_prompt(
            products=[{"name": "Curso Cocina", "price": 150, "description": "Aprende a cocinar"}]
        )
        assert "Chef Maria" in system_prompt
        assert "Curso Cocina" in system_prompt

        # 5. Context detector should detect interest from the user message
        ctx = detect_all(
            "Hola, me interesa el curso de cocina",
            history=None,
            is_first_message=True,
        )
        assert ctx.interest_level in (
            "soft",
            "strong",
        ), f"'me interesa' should signal interest, got '{ctx.interest_level}'"

    # ─── test_mantiene_hilo_3_turnos ────────────────────────────────────

    def test_mantiene_hilo_3_turnos(self):
        """
        Simulate a 3-turn conversation and verify context detection
        adapts correctly at each turn. The conversation state and
        prompt builder should maintain continuity.
        """
        # Turn 1: Greeting
        turn1_msg = "Hola, buenas tardes"
        ctx1 = detect_all(turn1_msg, history=None, is_first_message=True)
        assert ctx1.intent == Intent.GREETING
        assert ctx1.is_first_message is True

        # Turn 2: Product question (with history)
        turn2_msg = "Me interesa saber sobre el programa de coaching"
        history_after_turn1 = [
            {"role": "user", "content": turn1_msg},
            {"role": "assistant", "content": "Hola! Que bueno que escribes."},
        ]
        ctx2 = detect_all(turn2_msg, history=history_after_turn1, is_first_message=False)
        assert ctx2.is_first_message is False
        assert ctx2.interest_level == "soft", f"Expected soft interest, got '{ctx2.interest_level}'"

        # Turn 3: Price objection (with full history)
        turn3_msg = "Es muy caro para mi presupuesto"
        history_after_turn2 = history_after_turn1 + [
            {"role": "user", "content": turn2_msg},
            {"role": "assistant", "content": "El programa de coaching cuesta 500 euros."},
        ]
        ctx3 = detect_all(turn3_msg, history=history_after_turn2, is_first_message=False)
        assert ctx3.intent == Intent.OBJECTION
        assert ctx3.objection_type == "price"

        # Verify the prompt builder can incorporate all of this context
        builder = PromptBuilder(personality={"name": "Coach Ana", "tone": "friendly"})
        user_context = builder.build_user_context(
            username="potential_buyer",
            stage="interesado",
            history=history_after_turn2
            + [
                {"role": "user", "content": turn3_msg},
            ],
        )

        # History should contain all turns
        assert "Hola" in user_context
        assert "coaching" in user_context
        assert "presupuesto" in user_context
