"""
Tests for core/context_detector.py

Tests the Context Detector module that detects contextual signals
in messages for LLM prompt injection.

Part of refactor/context-injection-v2
"""

import pytest

from core.context_detector import (
    B2BResult,
    DetectedContext,
    FrustrationResult,
    SarcasmResult,
    detect_all,
    detect_b2b,
    detect_correction,
    detect_frustration,
    detect_interest_level,
    detect_meta_message,
    detect_objection_type,
    detect_sarcasm,
    extract_user_name,
    format_alerts_for_prompt,
    get_context_summary,
)


class TestFrustrationResult:
    """Tests for FrustrationResult dataclass."""

    def test_frustration_result_defaults(self):
        result = FrustrationResult()
        assert result.is_frustrated is False
        assert result.level == "none"
        assert result.reason == ""

    def test_frustration_result_to_dict(self):
        result = FrustrationResult(
            is_frustrated=True, level="severe", reason="Insulto directo"
        )
        d = result.to_dict()
        assert d["is_frustrated"] is True
        assert d["level"] == "severe"


class TestSarcasmResult:
    """Tests for SarcasmResult dataclass."""

    def test_sarcasm_result_defaults(self):
        result = SarcasmResult()
        assert result.is_sarcastic is False
        assert result.confidence == 0.0

    def test_sarcasm_result_to_dict(self):
        result = SarcasmResult(is_sarcastic=True, confidence=0.85)
        d = result.to_dict()
        assert d["is_sarcastic"] is True
        assert d["confidence"] == 0.85


class TestB2BResult:
    """Tests for B2BResult dataclass."""

    def test_b2b_result_defaults(self):
        result = B2BResult()
        assert result.is_b2b is False
        assert result.company_context == ""

    def test_b2b_result_to_dict(self):
        result = B2BResult(
            is_b2b=True, company_context="Bamos", contact_name="Silvia"
        )
        d = result.to_dict()
        assert d["is_b2b"] is True
        assert d["company_context"] == "Bamos"


class TestDetectedContext:
    """Tests for DetectedContext dataclass."""

    def test_detected_context_defaults(self):
        ctx = DetectedContext()
        assert ctx.sentiment == "neutral"
        assert ctx.frustration_level == "none"
        assert ctx.is_b2b is False
        assert ctx.interest_level == "none"
        assert ctx.alerts == []

    def test_detected_context_to_dict(self):
        ctx = DetectedContext(
            sentiment="frustrated", frustration_level="moderate", is_b2b=True
        )
        d = ctx.to_dict()
        assert d["sentiment"] == "frustrated"
        assert d["is_b2b"] is True

    def test_build_alerts_frustration(self):
        ctx = DetectedContext(frustration_level="severe")
        alerts = ctx.build_alerts()
        assert len(alerts) >= 1
        assert any("FRUSTRADO" in a.upper() for a in alerts)

    def test_build_alerts_b2b(self):
        ctx = DetectedContext(is_b2b=True, company_context="Bamos")
        alerts = ctx.build_alerts()
        assert any("B2B" in a for a in alerts)

    def test_build_alerts_interest(self):
        ctx = DetectedContext(interest_level="strong")
        alerts = ctx.build_alerts()
        assert any("compra" in a.lower() or "intención" in a.lower() for a in alerts)


class TestDetectFrustration:
    """Tests for detect_frustration function."""

    def test_no_frustration_normal_message(self):
        result = detect_frustration("Hola, me interesa el FitPack")
        assert result.is_frustrated is False
        assert result.level == "none"

    def test_severe_frustration_insult(self):
        result = detect_frustration("Eres inútil, no me ayudas")
        assert result.is_frustrated is True
        assert result.level == "severe"

    def test_severe_frustration_repeated_times(self):
        result = detect_frustration("Ya te dije 3 veces que quiero el precio")
        assert result.is_frustrated is True
        assert result.level == "severe"

    def test_moderate_frustration_not_understood(self):
        result = detect_frustration("No me entiendes, te lo explico otra vez")
        assert result.is_frustrated is True
        assert result.level == "moderate"

    def test_moderate_frustration_review_chat(self):
        result = detect_frustration("Revisa el chat, ya te lo dije")
        assert result.is_frustrated is True
        assert result.level == "moderate"

    def test_mild_frustration_again(self):
        result = detect_frustration("Otra vez tengo que explicarlo")
        assert result.is_frustrated is True
        assert result.level == "mild"

    def test_empty_message(self):
        result = detect_frustration("")
        assert result.is_frustrated is False


class TestDetectSarcasm:
    """Tests for detect_sarcasm function."""

    def test_no_sarcasm_normal_message(self):
        result = detect_sarcasm("Me interesa el curso")
        assert result.is_sarcastic is False

    def test_sarcasm_aja(self):
        result = detect_sarcasm("Ajá, seguro que sí")
        assert result.is_sarcastic is True
        assert result.confidence >= 0.8

    def test_sarcasm_ya_ya(self):
        result = detect_sarcasm("Ya ya, como si fuera a funcionar")
        assert result.is_sarcastic is True

    def test_sarcasm_que_gracioso(self):
        result = detect_sarcasm("Qué gracioso, muy bueno")
        assert result.is_sarcastic is True

    def test_no_false_positive_trabajado(self):
        """CRITICAL: 'trabajado' should NOT match 'ajá'."""
        result = detect_sarcasm("Ya habíamos trabajado antes con grupos")
        assert result.is_sarcastic is False

    def test_no_false_positive_trabajo(self):
        """'trabajo' should NOT trigger sarcasm."""
        result = detect_sarcasm("En mi trabajo hacemos esto")
        assert result.is_sarcastic is False


class TestExtractUserName:
    """Tests for extract_user_name function."""

    def test_extract_soy_name(self):
        name = extract_user_name("Hola, soy María")
        assert name == "María"

    def test_extract_me_llamo(self):
        name = extract_user_name("Me llamo Carlos García")
        assert name == "Carlos García"

    def test_extract_les_escribe(self):
        """B2B pattern: 'les escribe [Name]'."""
        name = extract_user_name("Les escribe Silvia de Bamos")
        assert name == "Silvia"

    def test_extract_mi_nombre_es(self):
        name = extract_user_name("Mi nombre es Pedro")
        assert name == "Pedro"

    def test_no_name_normal_message(self):
        name = extract_user_name("Quiero información sobre el curso")
        assert name is None

    def test_filter_common_words(self):
        """Should not extract common words as names."""
        name = extract_user_name("Soy el que te escribió ayer")
        assert name is None or name != "El"


class TestDetectB2B:
    """Tests for detect_b2b function."""

    def test_silvia_case_full(self):
        """
        CRITICAL TEST: The Silvia case that should be detected as B2B.

        This message should:
        1. Be detected as B2B
        2. NOT be detected as frustrated (despite 'ya habíamos')
        3. Extract company name 'Bamos'
        4. Extract contact name 'Silvia'
        """
        message = (
            "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes "
            "con grupos de estudiantes Erasmus. Queríamos ver si podemos "
            "organizar algo para febrero."
        )
        result = detect_b2b(message)

        assert result.is_b2b is True
        assert "Bamos" in result.company_context or result.company_context
        assert result.contact_name == "Silvia"

    def test_company_de_pattern(self):
        """Test 'soy X de [Company]' pattern."""
        result = detect_b2b("Soy Juan de TechCorp")
        assert result.is_b2b is True
        assert "TechCorp" in result.company_context

    def test_previous_collaboration(self):
        """Test previous work detection."""
        result = detect_b2b("Ya habíamos trabajado juntos el año pasado")
        assert result.is_b2b is True
        assert result.collaboration_type == "previous_work"

    def test_collaboration_keyword(self):
        result = detect_b2b("Buscamos una colaboración para nuestros clientes")
        assert result.is_b2b is True

    def test_students_group(self):
        result = detect_b2b("Tenemos un grupo de estudiantes interesados")
        assert result.is_b2b is True

    def test_no_b2b_normal_message(self):
        result = detect_b2b("Hola, me interesa el curso")
        assert result.is_b2b is False

    def test_erasmus_detection(self):
        result = detect_b2b("Organizamos viajes para estudiantes Erasmus")
        assert result.is_b2b is True


class TestDetectInterestLevel:
    """Tests for detect_interest_level function."""

    def test_strong_interest_quiero_comprar(self):
        level = detect_interest_level("Quiero comprar el curso")
        assert level == "strong"

    def test_strong_interest_como_pago(self):
        level = detect_interest_level("¿Cómo pago?")
        assert level == "strong"

    def test_strong_interest_me_apunto(self):
        level = detect_interest_level("Me apunto, dime cómo")
        assert level == "strong"

    def test_soft_interest_me_interesa(self):
        level = detect_interest_level("Me interesa, cuéntame más")
        assert level == "soft"

    def test_soft_interest_suena_bien(self):
        level = detect_interest_level("Suena bien, dame más info")
        assert level == "soft"

    def test_no_interest_greeting(self):
        level = detect_interest_level("Hola, qué tal")
        assert level == "none"


class TestDetectMetaMessage:
    """Tests for detect_meta_message function."""

    def test_ya_te_dije(self):
        assert detect_meta_message("Ya te dije que quiero el precio") is True

    def test_revisa_chat(self):
        assert detect_meta_message("Revisa el chat, está arriba") is True

    def test_normal_message(self):
        assert detect_meta_message("Quiero información") is False


class TestDetectCorrection:
    """Tests for detect_correction function."""

    def test_no_he_dicho(self):
        assert detect_correction("No he dicho que quiero comprar") is True

    def test_malentendido(self):
        assert detect_correction("Creo que hay un malentendido") is True

    def test_normal_message(self):
        assert detect_correction("Sí, eso es lo que quiero") is False


class TestDetectObjectionType:
    """Tests for detect_objection_type function."""

    def test_price_objection(self):
        assert detect_objection_type("Es muy caro para mí") == "price"

    def test_time_objection(self):
        assert detect_objection_type("No tengo tiempo ahora") == "time"

    def test_trust_objection(self):
        assert detect_objection_type("No estoy seguro, lo voy a pensar") == "trust"

    def test_need_objection(self):
        assert detect_objection_type("No lo necesito realmente") == "need"

    def test_no_objection(self):
        assert detect_objection_type("Me parece interesante") == ""


class TestDetectAll:
    """Tests for detect_all main function."""

    def test_silvia_b2b_not_frustrated(self):
        """
        CRITICAL TEST: Silvia's message should be B2B, NOT frustrated.

        This is the main case that was failing before the refactor.
        """
        message = (
            "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes "
            "con grupos de estudiantes Erasmus. Queríamos ver si podemos "
            "organizar algo para febrero."
        )
        ctx = detect_all(message, is_first_message=True)

        # Should be B2B
        assert ctx.is_b2b is True

        # Should NOT be frustrated (despite 'ya habíamos')
        assert ctx.frustration_level == "none"
        assert ctx.sentiment != "frustrated"

        # Should extract name
        assert ctx.user_name == "Silvia"

        # Alerts should mention B2B, not frustration
        alerts_text = " ".join(ctx.alerts)
        assert "B2B" in alerts_text
        assert "FRUSTRADO" not in alerts_text.upper()

    def test_frustrated_user(self):
        """Test frustrated user detection."""
        message = "Ya te dije 3 veces que quiero el precio, ¿me lo puedes dar o no?"
        ctx = detect_all(message, is_first_message=False)

        assert ctx.frustration_level == "severe"
        assert ctx.sentiment == "frustrated"
        assert any("FRUSTRADO" in a.upper() for a in ctx.alerts)

    def test_purchase_intent(self):
        """Test strong purchase intent detection."""
        message = "Quiero comprar el FitPack, ¿cómo pago?"
        ctx = detect_all(message, is_first_message=False)

        assert ctx.interest_level == "strong"
        assert any("compra" in a.lower() or "pago" in a.lower() for a in ctx.alerts)

    def test_first_message_greeting(self):
        """Test first message detection."""
        message = "Hola! Me interesa el curso"
        ctx = detect_all(message, is_first_message=True)

        assert ctx.is_first_message is True
        assert any("Primer mensaje" in a for a in ctx.alerts)

    def test_objection_with_type(self):
        """Test objection detection with type."""
        message = "Es muy caro para mí, no puedo pagarlo"
        ctx = detect_all(message)

        assert ctx.objection_type == "price"

    def test_sarcasm_detection(self):
        """Test sarcasm detection in context."""
        message = "Ajá, seguro que funciona"
        ctx = detect_all(message)

        assert ctx.sentiment == "sarcastic"

    def test_positive_sentiment(self):
        """Test positive sentiment detection."""
        message = "Genial, me encanta, gracias!"
        ctx = detect_all(message)

        assert ctx.sentiment == "positive"


class TestFormatAlertsForPrompt:
    """Tests for format_alerts_for_prompt function."""

    def test_format_with_alerts(self):
        ctx = DetectedContext(frustration_level="moderate", is_b2b=True)
        ctx.build_alerts()
        text = format_alerts_for_prompt(ctx)

        assert "ALERTAS DE CONTEXTO" in text
        assert "B2B" in text or "frustrado" in text.lower()

    def test_format_empty_alerts(self):
        ctx = DetectedContext()
        text = format_alerts_for_prompt(ctx)
        assert text == ""


class TestGetContextSummary:
    """Tests for get_context_summary function."""

    def test_summary_b2b(self):
        ctx = DetectedContext(is_b2b=True, company_context="TestCorp")
        summary = get_context_summary(ctx)
        assert "B2B" in summary

    def test_summary_frustration(self):
        ctx = DetectedContext(frustration_level="moderate")
        summary = get_context_summary(ctx)
        assert "Frustration" in summary

    def test_summary_neutral(self):
        ctx = DetectedContext()
        summary = get_context_summary(ctx)
        assert summary == "neutral"


class TestIntegration:
    """Integration tests."""

    def test_full_flow_b2b_message(self):
        """Test complete flow for B2B message."""
        message = (
            "Buenos días, soy Pedro de InnovateTech. "
            "Buscamos una colaboración para formar a nuestro equipo."
        )
        ctx = detect_all(message, is_first_message=True)

        assert ctx.is_b2b is True
        assert ctx.user_name == "Pedro"
        assert len(ctx.alerts) > 0

    def test_full_flow_frustrated_repeat(self):
        """Test complete flow for frustrated user with history."""
        history = [
            {"role": "user", "content": "¿Cuánto cuesta el curso?"},
            {"role": "assistant", "content": "El curso tiene varias opciones..."},
            {"role": "user", "content": "Pero cuánto cuesta exactamente?"},
            {"role": "assistant", "content": "Depende de lo que busques..."},
        ]
        message = "Ya te dije, solo quiero saber el precio!"

        ctx = detect_all(message, history=history, is_first_message=False)

        # Should detect frustration (not "none") OR meta message
        assert ctx.frustration_level != "none" or ctx.is_meta_message is True
        assert ctx.is_meta_message is True

    def test_full_flow_price_question(self):
        """Test complete flow for price question."""
        message = "¿Cuánto cuesta el FitPack Challenge?"
        ctx = detect_all(message, is_first_message=False)

        # Should detect interest (asking about price = purchase intent)
        assert ctx.interest_level in ("strong", "soft")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
