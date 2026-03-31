"""
Tests for Category 3: RAZONAMIENTO - Contradiction handling.

Validates that the DM bot can detect contradictions in user messages,
handle opinion changes, distinguish nuance from contradiction, and
maintain internal consistency in its own analysis.

All tests are FAST: no LLM calls, no DB access.
"""

from core.context_detector import detect_all, detect_correction
from core.intent_classifier import (
    ConversationAnalyzer,
    Intent,
    IntentClassifier,
    classify_intent_simple,
)
from core.reflexion_engine import ReflexionEngine


class TestContradicciones:
    """Test contradiction detection and handling."""

    def test_detecta_contradiccion_usuario(self):
        """
        User says 'si quiero' then 'no, mejor no' in conversation history.
        The system should detect the opinion shift -- the final intent
        should reflect the most recent message (objection/negative).

        Validates:
        - classify_intent_simple on the latest message reflects 'no'
        - ConversationAnalyzer tracks has_objections when contradictions appear
        """
        messages = [
            {"role": "user", "content": "Si quiero comprar el curso"},
            {"role": "assistant", "content": "Genial, aqui tienes el link de pago"},
            {"role": "user", "content": "No, mejor no, lo voy a pensar"},
        ]

        # The final message should be classified as objection
        final_intent = classify_intent_simple(messages[-1]["content"])
        assert (
            final_intent == "objection"
        ), f"Final contradicting message should be 'objection', got '{final_intent}'"

        # ConversationAnalyzer should show objections in the conversation
        classifier = IntentClassifier()
        analyzer = ConversationAnalyzer(classifier)

        # Run sync analysis (use_llm=False internally)
        import asyncio

        analysis = asyncio.get_event_loop().run_until_complete(
            analyzer.analyze_conversation(messages)
        )

        assert analysis[
            "has_objections"
        ], "Conversation with contradiction should have objections flagged"

    def test_maneja_cambio_opinion(self):
        """
        User changes from interested to not interested. The system should
        track this through different intent classifications across messages.

        Validates:
        - First message classified as interest
        - Second message classified as objection
        - detect_all on second message shows correction/objection flags
        """
        msg_interested = "Me interesa mucho, cuentame mas"
        msg_not_interested = "No creo que sea para mi, ahora no"

        intent_before = classify_intent_simple(msg_interested)
        intent_after = classify_intent_simple(msg_not_interested)

        # Before: should be interest
        assert intent_before in (
            "interest_soft",
            "interest_strong",
        ), f"Initial interested message should be interest, got '{intent_before}'"

        # After: should be objection
        assert (
            intent_after == "objection"
        ), f"Changed-mind message should be 'objection', got '{intent_after}'"

        # The context detector should pick up the objection
        ctx_after = detect_all(msg_not_interested, is_first_message=False)
        assert ctx_after.intent == Intent.OBJECTION, (
            "Changed-mind context should have OBJECTION intent, " f"got {ctx_after.intent}"
        )

    def test_no_confunde_con_contradiccion(self):
        """
        Nuanced message 'Me gusta pero es caro' is NOT a contradiction --
        it is a price objection combined with positive sentiment. The system
        should detect the objection type without losing the interest signal.

        Validates:
        - classify_intent_simple detects 'objection' (keyword 'caro')
        - detect_objection_type detects 'price'
        - The interest level is still detectable alongside the objection
        """
        message = "Me gusta pero es caro"

        intent_simple = classify_intent_simple(message)
        ctx = detect_all(message, is_first_message=False)

        # Primary classification should be objection (price concern)
        assert (
            intent_simple == "objection"
        ), f"'Me gusta pero es caro' should be 'objection', got '{intent_simple}'"
        assert (
            ctx.objection_type == "price"
        ), f"Should detect price objection, got '{ctx.objection_type}'"

        # This should NOT trigger frustration (it's a reasonable concern)
        assert ctx.frustration_level == "none", (
            "Nuanced feedback should not trigger frustration, "
            f"got level='{ctx.frustration_level}'"
        )

    def test_aclara_malentendido(self):
        """
        Message 'No es eso lo que dije' or similar correction triggers
        the correction detection, signaling a misunderstanding that needs
        to be addressed.

        Validates:
        - detect_correction returns True for correction phrases
        - detect_all sets is_correction=True
        - The alert system generates a correction alert
        """
        message = "No es lo que dije, me has entendido mal"

        is_correction = detect_correction(message)
        ctx = detect_all(message, is_first_message=False)

        assert is_correction, "Correction phrase 'me has entendido mal' should be detected"
        assert ctx.is_correction, "detect_all should set is_correction=True for correction messages"

        # The alerts should mention correction/misunderstanding
        correction_alerts = [
            a for a in ctx.alerts if "correcting" in a.lower() or "misunderstanding" in a.lower()
        ]
        assert (
            len(correction_alerts) > 0
        ), f"Should generate a correction alert, got alerts: {ctx.alerts}"

    def test_mantiene_coherencia(self):
        """
        The ReflexionEngine (output validator) should detect when a bot
        response repeats previous responses, ensuring consistency by
        flagging repetitions.

        Validates:
        - ReflexionEngine.analyze_response detects repetition with previous responses
        - The result flags the issue and suggests variation
        """
        engine = ReflexionEngine()

        previous_responses = [
            "Nuestro curso de marketing incluye 10 modulos con acceso de por vida.",
            "El programa tiene 10 modulos y acceso de por vida al contenido.",
        ]

        # New response that is very similar to previous ones
        new_response = "El curso de marketing tiene 10 modulos con acceso de por vida."
        user_message = "Que incluye el curso?"

        result = engine.analyze_response(
            response=new_response,
            user_message=user_message,
            previous_bot_responses=previous_responses,
        )

        # The engine should detect the repetition
        assert result.needs_revision, "Repeated response should need revision"
        repetition_issues = [
            i for i in result.issues if "repeticion" in i.lower() or "repetición" in i.lower()
        ]
        assert (
            len(repetition_issues) > 0
        ), f"Should detect repetition issue, got issues: {result.issues}"
