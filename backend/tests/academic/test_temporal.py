"""
Tests for Category 3: RAZONAMIENTO - Temporal reasoning.

Validates that the DM bot correctly handles temporal signals: urgency
vs delay, time pressure, conversation sequence, multi-step processes,
and product timeline data.

All tests are FAST: no LLM calls, no DB access.
"""

from datetime import datetime, timedelta, timezone

from core.context_detector import detect_all, detect_objection_type
from core.intent_classifier import ConversationAnalyzer, IntentClassifier, classify_intent_simple
from core.lead_categorization import calcular_categoria
from core.lead_categorizer import LeadCategorizer, LeadCategory


class TestTemporal:
    """Test temporal reasoning capabilities."""

    def test_entiende_ahora_vs_despues(self):
        """
        'Ahora no' and 'Lo quiero ya' should be detected as fundamentally
        different temporal signals: delay/objection vs urgency/purchase.

        Validates:
        - 'Ahora no' -> objection (time)
        - 'Lo quiero ya' -> interest_strong (urgency)
        - detect_objection_type differentiates correctly
        """
        msg_delay = "Ahora no puedo"
        msg_urgent = "Lo quiero ya"

        intent_delay = classify_intent_simple(msg_delay)
        intent_urgent = classify_intent_simple(msg_urgent)

        # 'ahora no' is a time-based objection
        assert (
            intent_delay == "objection"
        ), f"'Ahora no' should be 'objection', got '{intent_delay}'"
        objection_delay = detect_objection_type(msg_delay)
        assert (
            objection_delay == "time"
        ), f"'Ahora no' should be a 'time' objection, got '{objection_delay}'"

        # 'lo quiero ya' / 'lo quiero' is strong purchase interest
        assert (
            intent_urgent == "interest_strong"
        ), f"'Lo quiero ya' should be 'interest_strong', got '{intent_urgent}'"
        ctx_urgent = detect_all(msg_urgent, is_first_message=False)
        assert (
            ctx_urgent.interest_level == "strong"
        ), f"'Lo quiero ya' interest should be 'strong', got '{ctx_urgent.interest_level}'"

    def test_maneja_urgencia_tiempo(self):
        """
        Time pressure signals with strong purchase keywords like
        'Lo necesito ya, quiero comprar' should be detected as strong interest
        and categorized as 'caliente' for prioritization.

        Validates:
        - classify_intent_simple detects 'interest_strong' (via 'lo necesito')
        - detect_all picks up the urgency signal as strong interest
        - Lead categorization marks as 'caliente' (via 'comprar'/'quiero')
        """
        message = "Lo necesito ya, quiero comprar"

        intent_simple = classify_intent_simple(message)
        ctx = detect_all(message, is_first_message=False)

        # 'lo necesito' maps to interest_strong in classify_intent_simple
        assert (
            intent_simple == "interest_strong"
        ), f"Urgent need should be 'interest_strong', got '{intent_simple}'"

        # The context should reflect high purchase intent
        assert ctx.interest_level == "strong", (
            "Urgent context should show strong interest, "
            f"ctx.interest_level={ctx.interest_level}"
        )

        # Lead categorization should mark as caliente via 'comprar' and 'quiero'
        messages = [{"role": "user", "content": message}]
        result = calcular_categoria(messages)
        assert (
            result.categoria == "caliente"
        ), f"Urgent purchase request should be 'caliente', got '{result.categoria}'"
        assert (
            len(result.keywords_detectados) > 0
        ), "Should detect purchase keywords in urgent message"

    def test_entiende_antes_despues(self):
        """
        Sequential conversation flow should be maintained. The system should
        track how intents evolve over time in a conversation, with
        the funnel stage advancing as the conversation progresses.

        Validates:
        - ConversationAnalyzer tracks intent distribution over time
        - The funnel_stage reflects the overall conversation trajectory
        """
        messages = [
            {"role": "user", "content": "Hola, que tal?"},
            {"role": "assistant", "content": "Hola! En que puedo ayudarte?"},
            {"role": "user", "content": "Quiero saber mas sobre el curso"},
            {"role": "assistant", "content": "Claro, el curso incluye..."},
            {"role": "user", "content": "Cuanto cuesta?"},
            {"role": "assistant", "content": "El precio es 297 euros"},
            {"role": "user", "content": "Me apunto, donde pago?"},
        ]

        classifier = IntentClassifier()
        analyzer = ConversationAnalyzer(classifier)

        import asyncio

        analysis = asyncio.get_event_loop().run_until_complete(
            analyzer.analyze_conversation(messages)
        )

        # The conversation progresses through the funnel
        assert (
            analysis["total_messages"] == 4
        ), f"Should count 4 user messages, got {analysis['total_messages']}"

        # Purchase intent score should be relatively high after this journey
        assert analysis["purchase_intent_score"] > 0.0, (
            "Conversation with purchase signals should have positive score, "
            f"got {analysis['purchase_intent_score']}"
        )

        # The conversation is engaged (3+ messages)
        assert analysis[
            "is_engaged"
        ], "Conversation with 4 user messages should be marked as engaged"

    def test_secuencia_pasos(self):
        """
        Multi-step conversation showing a progression of intents should
        be correctly tracked. Each step should be individually classifiable.

        Validates:
        - Step 1 (greeting) -> classified as greeting
        - Step 2 (question) -> classified as question
        - Step 3 (purchase) -> classified as strong interest
        - The sequence maintains correct individual classifications
        """
        steps = [
            ("Hola", "greeting"),
            ("Que cursos tienes?", "question_product"),
            ("Cuanto cuesta el de marketing?", "purchase"),
            ("Me apunto, como pago?", "interest_strong"),
        ]

        for message, expected_intent in steps:
            actual_intent = classify_intent_simple(message)
            assert actual_intent == expected_intent, (
                f"Step '{message}' should be '{expected_intent}', " f"got '{actual_intent}'"
            )

    def test_plazos_correctos(self):
        """
        The lead categorization system should correctly use temporal data
        (timestamps) to determine ghost status. A lead with no response
        for 7+ days where the last message was from the bot should be
        marked as 'fantasma'.

        Validates:
        - Lead with recent activity is NOT ghost
        - Lead with 8 days silence IS ghost
        - Lead with 3 days silence is NOT ghost (below threshold)
        """
        now = datetime.now(timezone.utc)
        categorizer = LeadCategorizer()

        # Case 1: Recent activity (1 day ago) - NOT ghost
        messages_recent = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola! Como estas?"},
        ]
        cat_recent, score_recent, reason_recent = categorizer.categorize(
            messages=messages_recent,
            last_user_message_time=now - timedelta(days=1),
            last_bot_message_time=now - timedelta(hours=23),
        )
        assert (
            cat_recent != LeadCategory.FANTASMA
        ), f"Lead with 1 day silence should NOT be ghost, got {cat_recent}"

        # Case 2: Long silence (8 days) with bot's last message after user's - IS ghost
        messages_ghost = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola! Como estas?"},
        ]
        cat_ghost, score_ghost, reason_ghost = categorizer.categorize(
            messages=messages_ghost,
            last_user_message_time=now - timedelta(days=8),
            last_bot_message_time=now - timedelta(days=7),
        )
        assert (
            cat_ghost == LeadCategory.FANTASMA
        ), f"Lead with 8 days silence should be ghost, got {cat_ghost}"

        # Case 3: Medium silence (3 days) - NOT ghost (below 7-day threshold)
        cat_medium, score_medium, reason_medium = categorizer.categorize(
            messages=messages_ghost,
            last_user_message_time=now - timedelta(days=3),
            last_bot_message_time=now - timedelta(days=2),
        )
        assert (
            cat_medium != LeadCategory.FANTASMA
        ), f"Lead with 3 days silence should NOT be ghost, got {cat_medium}"
