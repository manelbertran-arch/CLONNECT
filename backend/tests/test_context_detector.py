"""
Tests for core/context_detector (v2 — Universal/Multilingual).

Tests the context detection module that produces factual observations
for the Recalling block. Frustration is handled by FrustrationDetectorV2,
sarcasm by the LLM natively.
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
    """Tests for FrustrationResult backward-compat dataclass."""

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
    """Tests for SarcasmResult backward-compat dataclass."""

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
        assert ctx.context_notes == []

    def test_detected_context_to_dict(self):
        ctx = DetectedContext(sentiment="positive", is_b2b=True)
        d = ctx.to_dict()
        assert d["sentiment"] == "positive"
        assert d["is_b2b"] is True

    def test_build_context_notes_b2b(self):
        ctx = DetectedContext(is_b2b=True, company_context="Bamos")
        notes = ctx.build_context_notes()
        assert len(notes) >= 1
        assert any("company" in n.lower() or "brand" in n.lower() for n in notes)

    def test_build_context_notes_name(self):
        ctx = DetectedContext(user_name="María")
        notes = ctx.build_context_notes()
        assert any("María" in n for n in notes)

    def test_build_context_notes_objection(self):
        ctx = DetectedContext(objection_type="price")
        notes = ctx.build_context_notes()
        assert any("price" in n.lower() for n in notes)

    def test_build_context_notes_empty(self):
        ctx = DetectedContext()
        notes = ctx.build_context_notes()
        assert notes == []

    def test_backward_compat_alerts(self):
        """build_context_notes also populates alerts for backward compat."""
        ctx = DetectedContext(is_b2b=True, company_context="TestCo")
        ctx.build_context_notes()
        assert ctx.alerts == ctx.context_notes


class TestDetectFrustrationStub:
    """Tests that frustration detection stub returns empty results."""

    def test_stub_returns_empty(self):
        result = detect_frustration("Eres inútil, no me ayudas")
        assert result.is_frustrated is False

    def test_stub_empty_message(self):
        result = detect_frustration("")
        assert result.is_frustrated is False


class TestDetectSarcasmStub:
    """Tests that sarcasm detection stub returns empty results."""

    def test_stub_returns_empty(self):
        result = detect_sarcasm("Ajá, seguro que sí")
        assert result.is_sarcastic is False

    def test_stub_empty_message(self):
        result = detect_sarcasm("")
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
        name = extract_user_name("Les escribe Silvia de Bamos")
        assert name == "Silvia"

    def test_extract_mi_nombre_es(self):
        name = extract_user_name("Mi nombre es Pedro")
        assert name == "Pedro"

    def test_no_name_normal_message(self):
        name = extract_user_name("Quiero información sobre el curso")
        assert name is None

    def test_filter_common_words(self):
        name = extract_user_name("Soy el que te escribió ayer")
        assert name is None or name != "El"

    def test_catalan_with_article(self):
        name = extract_user_name("Sóc la Marta de YogaVida")
        assert name == "Marta"

    def test_english_name(self):
        name = extract_user_name("I'm John from NikeTraining")
        assert name == "John"


class TestDetectB2B:
    """Tests for detect_b2b function."""

    def test_silvia_case_full(self):
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
        result = detect_b2b("Soy Juan de TechCorp")
        assert result.is_b2b is True
        assert "TechCorp" in result.company_context

    def test_previous_collaboration(self):
        result = detect_b2b("Ya habíamos trabajado juntos el año pasado")
        assert result.is_b2b is True
        assert result.collaboration_type == "previous_work"

    def test_collaboration_keyword(self):
        result = detect_b2b("Buscamos una colaboración para nuestros clientes")
        assert result.is_b2b is True

    def test_no_b2b_normal_message(self):
        result = detect_b2b("Hola, me interesa el curso")
        assert result.is_b2b is False

    def test_english_b2b(self):
        result = detect_b2b("I'm John from NikeTraining, we'd like a partnership")
        assert result.is_b2b is True
        assert "NikeTraining" in result.company_context

    def test_catalan_b2b(self):
        result = detect_b2b("Sóc la Marta de YogaVida, volem una col·laboració")
        assert result.is_b2b is True


class TestDetectInterestLevel:
    """Tests for detect_interest_level function (delegates to intent)."""

    def test_no_interest_without_intent(self):
        """Without intent parameter, returns 'none' (delegates to classifier)."""
        level = detect_interest_level("Quiero comprar el curso")
        assert level == "none"

    def test_strong_via_detect_all(self):
        """Via detect_all, purchase intent → strong interest."""
        ctx = detect_all("Quiero comprar el FitPack, ¿cómo pago?")
        assert ctx.interest_level == "strong"

    def test_soft_via_detect_all(self):
        """Via detect_all, interest message → strong interest (canonical classifier)."""
        ctx = detect_all("Me interesa, cuéntame más")
        # Post fix/intent-dual-reconciliation: "cuéntame más" is classified as
        # INTEREST_STRONG by services.IntentClassifier (canonical), not interest_soft
        # as classify_intent_simple did previously. "cuéntame más" is in INTEREST_STRONG_PATTERNS.
        assert ctx.interest_level == "strong"

    def test_no_interest_greeting(self):
        ctx = detect_all("Hola, qué tal")
        assert ctx.interest_level == "none"


class TestDetectMetaMessage:
    """Tests for detect_meta_message function."""

    def test_ya_te_dije(self):
        assert detect_meta_message("Ya te dije que quiero el precio") is True

    def test_revisa_chat(self):
        assert detect_meta_message("Revisa el chat, está arriba") is True

    def test_catalan_meta(self):
        assert detect_meta_message("Ja t'ho he dit, mira el xat") is True

    def test_english_meta(self):
        assert detect_meta_message("I already told you, scroll up") is True

    def test_normal_message(self):
        assert detect_meta_message("Quiero información") is False


class TestDetectCorrection:
    """Tests for detect_correction function."""

    def test_no_he_dicho(self):
        assert detect_correction("No he dicho que quiero comprar") is True

    def test_malentendido(self):
        assert detect_correction("Creo que hay un malentendido") is True

    def test_english_correction(self):
        assert detect_correction("That's not what I said, you misunderstood") is True

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
    """Tests for detect_all main orchestration function."""

    def test_silvia_b2b(self):
        """Silvia's B2B message: should be B2B with name, not frustrated."""
        message = (
            "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes "
            "con grupos de estudiantes Erasmus."
        )
        ctx = detect_all(message, is_first_message=True)
        assert ctx.is_b2b is True
        assert ctx.user_name == "Silvia"
        # context_notes should mention B2B
        assert any("company" in n.lower() or "brand" in n.lower() for n in ctx.context_notes)
        # Should not have frustration in notes
        assert not any("frustrad" in n.lower() for n in ctx.context_notes)

    def test_purchase_intent(self):
        """Purchase message → strong interest."""
        ctx = detect_all("Quiero comprar el FitPack, ¿cómo pago?", is_first_message=False)
        assert ctx.interest_level == "strong"

    def test_first_message(self):
        ctx = detect_all("Hola! Me interesa el curso", is_first_message=True)
        assert ctx.is_first_message is True

    def test_objection_with_type(self):
        ctx = detect_all("Es muy caro para mí, no puedo pagarlo")
        assert ctx.objection_type == "price"
        assert any("price" in n.lower() for n in ctx.context_notes)

    def test_positive_sentiment(self):
        ctx = detect_all("Genial, me encanta, gracias!")
        assert ctx.sentiment == "positive"

    def test_meta_and_correction(self):
        ctx = detect_all("No he dicho eso, ya te lo dije antes")
        assert ctx.is_correction is True
        assert ctx.is_meta_message is True


class TestFormatAlertsForPrompt:
    """Tests for format_alerts_for_prompt function."""

    def test_format_with_context_notes(self):
        ctx = DetectedContext(is_b2b=True, company_context="Bamos")
        ctx.build_context_notes()
        text = format_alerts_for_prompt(ctx)
        assert "company" in text.lower() or "brand" in text.lower()

    def test_format_empty(self):
        ctx = DetectedContext()
        ctx.build_context_notes()
        text = format_alerts_for_prompt(ctx)
        assert text == ""


class TestGetContextSummary:
    """Tests for get_context_summary function."""

    def test_summary_b2b(self):
        ctx = DetectedContext(is_b2b=True, company_context="TestCorp")
        summary = get_context_summary(ctx)
        assert "B2B" in summary

    def test_summary_neutral(self):
        ctx = DetectedContext()
        summary = get_context_summary(ctx)
        assert summary == "neutral"

    def test_summary_multiple_signals(self):
        ctx = DetectedContext(is_b2b=True, user_name="Pedro", is_meta_message=True)
        summary = get_context_summary(ctx)
        assert "B2B" in summary
        assert "Name" in summary
        assert "Meta" in summary


class TestIntegration:
    """Integration tests for detect_all."""

    def test_full_flow_b2b_message(self):
        message = (
            "Buenos días, soy Pedro de InnovateTech. "
            "Buscamos una colaboración para formar a nuestro equipo."
        )
        ctx = detect_all(message, is_first_message=True)
        assert ctx.is_b2b is True
        assert ctx.user_name == "Pedro"
        assert len(ctx.context_notes) > 0

    def test_full_flow_meta_message(self):
        message = "Ya te dije, solo quiero saber el precio!"
        ctx = detect_all(message, history=[], is_first_message=False)
        assert ctx.is_meta_message is True

    def test_full_flow_price_question(self):
        message = "¿Cuánto cuesta el FitPack Challenge?"
        ctx = detect_all(message, is_first_message=False)
        assert ctx.interest_level in ("strong", "soft")

    def test_multilingual_detection(self):
        """Test that all supported languages produce results."""
        messages = {
            "es": "Soy María de FitnessPro, queríamos una colaboración",
            "en": "I'm John from NikeTraining, we'd like a partnership",
            "ca": "Sóc la Marta de YogaVida, volem una col·laboració",
        }
        for lang, msg in messages.items():
            ctx = detect_all(msg)
            assert ctx.is_b2b is True, f"B2B not detected for {lang}: {msg}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
