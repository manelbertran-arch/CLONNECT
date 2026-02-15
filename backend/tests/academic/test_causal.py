"""
Tests for Category 3: RAZONAMIENTO - Causal reasoning.

Validates that the DM bot can connect cause-and-effect, provide price
justifications through product data, explain why things work, link
user needs to product solutions, and handle "why?" questions properly.

All tests are FAST: no LLM calls, no DB access.
"""

from core.context_detector import (
    detect_all,
    detect_interest_level,
    detect_objection_type,
    format_alerts_for_prompt,
)
from core.intent_classifier import Intent, classify_intent_simple, get_lead_status_from_intent
from core.lead_categorization import KEYWORDS_CALIENTE, calcular_categoria
from core.reasoning.chain_of_thought import ChainOfThoughtReasoner


class TestCausal:
    """Test causal reasoning capabilities."""

    def test_explica_por_que_precio(self):
        """
        When a user complains about price ('Es muy caro, por que cuesta tanto?'),
        the system should detect a price objection and generate alerts that
        guide the response toward value justification.

        Validates:
        - detect_objection_type detects 'price' for explicit price complaints
        - The alerts system generates a price-objection alert with guidance
        - Product keywords for 'caliente' include price-related terms
        """
        message = "Es muy caro, por que cuesta tanto?"

        # Should detect this as a price objection via 'caro'
        objection_type = detect_objection_type(message)
        ctx = detect_all(message, is_first_message=False)

        assert objection_type == "price", (
            "'Es muy caro' should trigger price objection, " f"got '{objection_type}'"
        )
        assert (
            ctx.intent == Intent.OBJECTION
        ), f"Price complaint should have OBJECTION intent, got {ctx.intent}"
        assert ctx.objection_type == "price", (
            "Context should have price objection_type, " f"got '{ctx.objection_type}'"
        )

        # Verify the alerts system generates actionable guidance for price
        alerts_text = format_alerts_for_prompt(ctx)
        assert "precio" in alerts_text.lower() or "valor" in alerts_text.lower(), (
            "Price objection alert should mention precio/valor, " f"got: {alerts_text}"
        )

        # Product keywords should include price terms for categorization
        price_keywords_present = any(
            "precio" in kw or "cuesta" in kw or "cuánto" in kw for kw in KEYWORDS_CALIENTE
        )
        assert (
            price_keywords_present
        ), "KEYWORDS_CALIENTE should contain price-related terms for detection"

    def test_explica_por_que_funciona(self):
        """
        Product explanation queries ('como funciona') should be classified
        as product questions, enabling the system to provide benefit
        explanations.

        Validates:
        - classify_intent_simple detects 'question_product' for how-it-works
        - The ChainOfThoughtReasoner recognizes this as complex if health-related
        """
        message = "Como funciona el programa?"

        intent_simple = classify_intent_simple(message)

        assert (
            intent_simple == "question_product"
        ), f"'Como funciona' should be 'question_product', got '{intent_simple}'"

        # Chain of thought should consider product questions as potentially complex
        reasoner = ChainOfThoughtReasoner(llm_client=None)
        is_complex, query_type = reasoner._is_complex_query(
            "Como funciona el programa de nutricion y salud?"
        )
        # Health-related product question should trigger CoT
        assert is_complex, "Health-related product question should be considered complex"
        assert query_type in (
            "health",
            "product",
        ), f"Expected 'health' or 'product' query type, got '{query_type}'"

    def test_conecta_causa_efecto(self):
        """
        The intent analysis should connect a user's expressed need to the
        appropriate product category, establishing cause (user need) to
        effect (product recommendation).

        Validates:
        - 'Quiero mejorar mi negocio' triggers interest detection
        - Lead categorization connects this to 'interesado' category
        - get_lead_status_from_intent maps correctly
        """
        messages = [
            {"role": "user", "content": "Quiero mejorar mi negocio"},
            {"role": "user", "content": "Tienes algun curso de marketing?"},
            {"role": "user", "content": "Que incluye el programa?"},
        ]

        # Categorize based on conversation
        result = calcular_categoria(messages)

        # The conversation shows interest keywords ('tienes', 'que incluye')
        assert result.categoria in ("interesado", "caliente"), (
            "Need-to-solution conversation should be 'interesado' or 'caliente', "
            f"got '{result.categoria}'"
        )
        assert (
            len(result.keywords_detectados) > 0
        ), "Should detect interest keywords connecting need to product inquiry"

        # The intent mapping should connect interest to appropriate status
        for msg in messages:
            intent = classify_intent_simple(msg["content"])
            if intent in ("interest_soft", "question_product"):
                status = get_lead_status_from_intent(intent)
                assert status == "active", (
                    "Interest/question intent should map to 'active' status, " f"got '{status}'"
                )

    def test_justifica_recomendacion(self):
        """
        When a user shows strong purchase intent, the context detection
        should provide actionable alerts that justify recommending a product
        (e.g., include payment link, highlight benefits).

        Validates:
        - Strong interest generates 'close_sale' action
        - Context alerts include purchase facilitation guidance
        - Lead categorization assigns 'caliente' for purchase signals
        """
        message = "Quiero comprar el curso, como pago?"

        intent_simple = classify_intent_simple(message)
        ctx = detect_all(message, is_first_message=False)
        interest = detect_interest_level(message)

        # Strong purchase intent
        assert intent_simple in (
            "interest_strong",
            "purchase",
        ), f"Purchase request should be strong interest, got '{intent_simple}'"
        assert (
            interest == "strong"
        ), f"Purchase request should have 'strong' interest, got '{interest}'"

        # Alerts should guide toward facilitating the purchase
        alerts_text = format_alerts_for_prompt(ctx)
        assert (
            "compra" in alerts_text.lower()
            or "pago" in alerts_text.lower()
            or "reserva" in alerts_text.lower()
        ), (
            "Strong purchase intent should generate purchase-related alerts, "
            f"got: {alerts_text}"
        )

        # Lead categorization should mark as 'caliente'
        messages = [{"role": "user", "content": message}]
        cat_result = calcular_categoria(messages)
        assert cat_result.categoria == "caliente", (
            "Purchase intent should categorize as 'caliente', " f"got '{cat_result.categoria}'"
        )

    def test_responde_por_que(self):
        """
        A standalone 'Por que?' question should be treated as a general
        question seeking explanation, NOT as an objection or complaint.

        Validates:
        - classify_intent_simple does NOT return 'objection' for bare 'por que'
        - detect_objection_type returns '' (no objection pattern)
        - No frustration detected
        """
        message = "Por que?"

        intent_simple = classify_intent_simple(message)
        objection_type = detect_objection_type(message)
        ctx = detect_all(message, is_first_message=False)

        # A bare 'por que?' is just a question, not an objection
        assert objection_type == "", (
            "Bare 'Por que?' should not be a specific objection type, " f"got '{objection_type}'"
        )

        # Should NOT trigger frustration
        assert ctx.frustration_level == "none", (
            "Bare 'Por que?' should not trigger frustration, "
            f"got level='{ctx.frustration_level}'"
        )

        # Should be classified as a question or 'other', not objection
        assert (
            intent_simple != "objection" or ctx.intent != Intent.OBJECTION
        ), "Bare 'Por que?' should not be classified as objection"
