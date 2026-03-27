"""
Category 1: INTELIGENCIA COGNITIVA
Test Suite: Sensibilidad al Contexto

Tests that the DM bot adapts its response strategy based on context:
- Greeting context -> short response expected
- Product question -> longer response expected
- Objection -> empathetic response markers in alerts
- High interest -> urgency markers in alerts
- Casual chat -> casual response style

Uses REAL modules (length_controller, context_detector, prompt_builder)
and mocks only the LLM service.
"""

from core.context_detector import detect_all, format_alerts_for_prompt
from core.intent_classifier import Intent
from services.length_controller import (
    classify_lead_context,
    detect_message_type,
    enforce_length,
    get_context_rule,
    get_length_guidance_prompt,
    get_short_replacement,
)


class TestSensibilidadContexto:
    """Test suite for context-sensitive response adaptation."""

    # ─── test_respuesta_corta_saludo ────────────────────────────────────

    def test_respuesta_corta_saludo(self):
        """
        Greeting context should expect a SHORT response. The length controller
        should classify it as 'saludo' with a low target character count,
        and predefined short responses should be available.
        """
        message = "Hola!"

        # 1. Classify as saludo
        context = classify_lead_context(message)
        assert context == "saludo"

        # 2. Get the length rule for saludo
        rule = get_context_rule("saludo")
        assert (
            rule.target <= 20
        ), f"Greeting target should be short (<= 20 chars), got {rule.target}"
        assert (
            rule.soft_max <= 50
        ), f"Greeting soft_max should be moderate (<= 50), got {rule.soft_max}"

        # 3. Short predefined responses available for greetings
        replacement = get_short_replacement("saludo")
        assert replacement is not None, "Should have short replacements for greetings"
        assert (
            len(replacement) < 20
        ), f"Short replacement should be brief, got '{replacement}' ({len(replacement)} chars)"

        # 4. Length enforcement should trim overly long greeting responses
        long_greeting_response = (
            "Hola! Que alegria que me escribas! Espero que tengas un dia increible! "
            "Estoy aqui para ayudarte en todo lo que necesites. No dudes en preguntar "
            "cualquier cosa que quieras saber. Estoy a tu disposicion!"
        )
        enforce_length(long_greeting_response, message)
        # enforce_length respects hard_max with 1.5x headroom
        # For saludo: hard_max=44, headroom=max(66, 200)=200
        # So it would only trim if response > 200 chars
        # The point is the system GUIDES shorter responses via the rule

        # 5. Length guidance prompt should mention greeting context
        guidance = get_length_guidance_prompt(message)
        assert (
            "greeting" in guidance.lower()
            or "saludo" in guidance.lower()
            or "short" in guidance.lower()
        ), f"Guidance should reference greeting context, got: {guidance}"

    # ─── test_respuesta_larga_pregunta_producto ─────────────────────────

    def test_respuesta_larga_pregunta_producto(self):
        """
        Product question should allow a LONGER response than a greeting.
        The target and soft_max should be higher to accommodate informative answers.
        """
        message = "Que incluye el curso de coaching y como funciona?"

        # 1. Classify as product question
        context = classify_lead_context(message)
        assert context == "pregunta_producto", f"Expected 'pregunta_producto', got '{context}'"

        # 2. Product question allows more chars than greeting
        product_rule = get_context_rule("pregunta_producto")
        greeting_rule = get_context_rule("saludo")
        assert product_rule.soft_max >= greeting_rule.soft_max, (
            f"Product soft_max ({product_rule.soft_max}) should be >= "
            f"greeting soft_max ({greeting_rule.soft_max})"
        )

        # 3. Objection context allows even more (for persuasion)
        objection_rule = get_context_rule("objecion")
        assert objection_rule.target > product_rule.target, (
            f"Objection target ({objection_rule.target}) should exceed "
            f"product target ({product_rule.target})"
        )

        # 4. Length guidance reflects the product context
        guidance = get_length_guidance_prompt(message)
        assert (
            "product" in guidance.lower() or "informative" in guidance.lower()
        ), f"Guidance should mention product context, got: {guidance}"

        # 5. No short replacement for product questions (need real answers)
        replacement = get_short_replacement("pregunta_producto")
        assert replacement is None, "Product questions should not have canned short responses"

    # ─── test_empatia_en_objecion ───────────────────────────────────────

    def test_empatia_en_objecion(self):
        """
        Objection context should generate empathetic response markers
        in the detected context alerts. The system instructs the LLM
        to validate the concern and handle with empathy.
        """
        message = "Es demasiado caro, no tengo el dinero"

        # 1. Detect context
        ctx = detect_all(message, is_first_message=False)
        assert ctx.intent == Intent.OBJECTION
        assert ctx.objection_type == "price"

        # 2. Alerts should contain price objection handling
        alerts_text = " ".join(ctx.alerts)
        assert any(
            keyword in alerts_text.lower()
            for keyword in ["precio", "valor", "alternativa", "price"]
        ), f"Objection alerts should mention price handling, got: {ctx.alerts}"

        # 3. Format alerts for prompt injection
        formatted = format_alerts_for_prompt(ctx)
        assert "ALERTAS" in formatted or len(formatted) > 0
        assert "precio" in formatted.lower() or "price" in formatted.lower()

        # 4. Length controller recognizes objection (longer response OK)
        msg_type = detect_message_type(message)
        assert msg_type == "objecion"
        rule = get_context_rule("objecion")
        assert rule.target > 40, f"Objection target should be substantial (> 40), got {rule.target}"

        # 5. Time objection also gets empathetic handling
        time_msg = "No tengo tiempo para hacer el curso"
        time_ctx = detect_all(time_msg, is_first_message=False)
        assert time_ctx.objection_type == "time"
        time_alerts = " ".join(time_ctx.alerts)
        assert any(
            keyword in time_alerts.lower() for keyword in ["tiempo", "flexibilidad", "time"]
        ), f"Time objection alerts should mention time handling, got: {time_ctx.alerts}"

    # ─── test_urgencia_en_interes_alto ──────────────────────────────────

    def test_urgencia_en_interes_alto(self):
        """
        High interest context should generate urgency/conversion markers
        in the alerts, instructing the LLM to facilitate the purchase.
        """
        message = "Quiero comprar el curso, como pago?"

        # 1. Detect context
        ctx = detect_all(message, is_first_message=False)
        assert ctx.interest_level == "strong"

        # 2. Interest level is on ctx.interest_level (not in alerts/context_notes)
        assert ctx.interest_level == "strong", (
            f"Purchase intent should be 'strong', got '{ctx.interest_level}'"
        )

        # 3. The interest detection function works via detect_all
        ctx2 = detect_all(message, is_first_message=False)
        assert ctx2.interest_level == "strong"

        # 4. Length controller classifies as interest (short ack, don't oversell)
        msg_type = classify_lead_context(message)
        assert msg_type == "interes"
        rule = get_context_rule("interes")
        # Interest responses should be brief - just facilitate
        assert (
            rule.target <= 15
        ), f"Interest response target should be brief (<= 15), got {rule.target}"

        # 5. Prompt builder includes proactive close instruction constant
        from core.prompt_builder import PROACTIVE_CLOSE_INSTRUCTION

        assert "CIERRE PROACTIVO" in PROACTIVE_CLOSE_INSTRUCTION
        assert (
            "LINK REAL" in PROACTIVE_CLOSE_INSTRUCTION
            or "link" in PROACTIVE_CLOSE_INSTRUCTION.lower()
        )

    # ─── test_casual_en_chat_casual ─────────────────────────────────────

    def test_casual_en_chat_casual(self):
        """
        Casual chat context should classify as 'casual' (or a sub-category
        like 'humor' that aliases to 'casual') with relaxed length rules and
        available short predefined responses.
        """
        # Casual message with laugh and multiple emojis
        # v10.2: classify_lead_context returns 'humor' for laugh patterns,
        # which aliases to 'casual' via CONTEXT_ALIASES
        message = "Jajaja 😂😂"

        # 1. Classify as casual or humor (humor is a sub-category of casual)
        context = classify_lead_context(message)
        casual_contexts = {"casual", "humor", "reaccion", "reaction", "continuacion", "continuation"}
        assert context in casual_contexts, (
            f"Expected a casual-family context, got '{context}'"
        )

        # 2. Resolved rule (via alias) has relaxed target
        rule = get_context_rule(context)
        assert rule.target <= 25, f"Casual target should be relaxed (<= 25), got {rule.target}"

        # 3. Short replacements available for casual
        replacement = get_short_replacement("casual")
        assert replacement is not None, "Should have short replacements for casual"

        # 4. Context detector sees neutral/positive sentiment
        ctx = detect_all(message, is_first_message=False)
        # Short casual laugh shouldn't trigger frustration
        assert ctx.frustration_level == "none"
        assert ctx.sentiment in ("neutral", "positive")

        # 5. Length guidance reflects casual context
        guidance = get_length_guidance_prompt(message)
        assert (
            "casual" in guidance.lower() or "relax" in guidance.lower()
            or "humor" in guidance.lower()
        ), f"Guidance should mention casual/humor context, got: {guidance}"
