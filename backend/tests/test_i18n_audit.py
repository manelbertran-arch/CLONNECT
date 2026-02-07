"""Audit tests for core/i18n.py."""

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Test 1: Init / Import
# ---------------------------------------------------------------------------


class TestI18nImport:
    """Verify module imports and key classes/constants."""

    def test_import_module(self):
        from core.i18n import DEFAULT_LANGUAGE, LANGUAGE_PATTERNS, SYSTEM_MESSAGES, Language

        # Language enum
        assert Language.SPANISH.value == "es"
        assert Language.ENGLISH.value == "en"
        assert Language.PORTUGUESE.value == "pt"
        assert Language.CATALAN.value == "ca"

        # Default language is Spanish
        assert DEFAULT_LANGUAGE == "es"

        # All 4 languages should have patterns
        assert set(LANGUAGE_PATTERNS.keys()) == {"es", "en", "pt", "ca"}

        # System messages should have at least greeting and default
        assert "greeting" in SYSTEM_MESSAGES
        assert "default" in SYSTEM_MESSAGES

    def test_language_detector_init(self):
        from core.i18n import LanguageDetector

        detector = LanguageDetector()
        assert detector._llm_client is None

        mock_llm = MagicMock()
        detector_with_llm = LanguageDetector(llm_client=mock_llm)
        assert detector_with_llm._llm_client is mock_llm


# ---------------------------------------------------------------------------
# Test 2: Happy Path -- Spanish translation / detection
# ---------------------------------------------------------------------------


class TestSpanishDetection:
    """Verify Spanish text is correctly detected and messages retrieved."""

    def test_detect_spanish_text(self):
        from core.i18n import LanguageDetector

        detector = LanguageDetector()

        assert detector.detect("Hola, quiero comprar el curso") == "es"
        assert detector.detect("Buenos dias, como estas") == "es"
        assert detector.detect("Necesito ayuda por favor") == "es"

    def test_get_system_message_spanish(self):
        from core.i18n import get_system_message

        greeting = get_system_message("greeting", "es")
        assert "Hola" in greeting

        goodbye = get_system_message("goodbye", "es")
        assert "pronto" in goodbye.lower()

    def test_i18n_manager_get_message(self):
        from core.i18n import I18nManager

        mgr = I18nManager()
        msg = mgr.get_message("greeting", "es")
        assert "Hola" in msg


# ---------------------------------------------------------------------------
# Test 3: Happy Path -- English fallback
# ---------------------------------------------------------------------------


class TestEnglishFallback:
    """English detection and system message retrieval."""

    def test_detect_english_text(self):
        from core.i18n import LanguageDetector

        detector = LanguageDetector()

        assert detector.detect("Hello, how much does your course cost?") == "en"
        assert detector.detect("I want to buy this product please") == "en"
        assert detector.detect("Can you help me with the schedule?") == "en"

    def test_get_system_message_english(self):
        from core.i18n import get_system_message

        greeting = get_system_message("greeting", "en")
        assert "Hi" in greeting or "Hello" in greeting

        goodbye = get_system_message("goodbye", "en")
        assert "soon" in goodbye.lower() or "care" in goodbye.lower()


# ---------------------------------------------------------------------------
# Test 4: Edge Case -- Missing key and empty/non-string input
# ---------------------------------------------------------------------------


class TestI18nEdgeCases:
    """Missing keys, empty strings, and non-string inputs."""

    def test_missing_key_returns_default(self):
        from core.i18n import get_system_message

        # Unknown key should fall back to "default" message
        msg = get_system_message("nonexistent_key_xyz", "es")
        default_msg = get_system_message("default", "es")
        assert msg == default_msg

    def test_empty_text_returns_default_language(self):
        from core.i18n import DEFAULT_LANGUAGE, LanguageDetector

        detector = LanguageDetector()
        assert detector.detect("") == DEFAULT_LANGUAGE
        assert detector.detect("  ") == DEFAULT_LANGUAGE
        assert detector.detect("a") == DEFAULT_LANGUAGE  # too short (<2 meaningful chars)

    def test_non_string_input_handled(self):
        from core.i18n import DEFAULT_LANGUAGE, LanguageDetector

        detector = LanguageDetector()

        # Dict input
        result = detector.detect({"text": "hello"})
        assert isinstance(result, str)

        # None input
        result_none = detector.detect(None)
        assert result_none == DEFAULT_LANGUAGE

    def test_unsupported_language_returns_spanish_message(self):
        from core.i18n import get_system_message

        # Requesting a language code that doesn't exist falls back to Spanish
        msg = get_system_message("greeting", "zh")
        msg_es = get_system_message("greeting", "es")
        assert msg == msg_es


# ---------------------------------------------------------------------------
# Test 5: Integration Check -- I18nManager singleton and detect with translate
# ---------------------------------------------------------------------------


class TestI18nManagerIntegration:
    """Integration: I18nManager, singleton, and translate flow."""

    def test_get_i18n_manager_singleton(self):
        # Reset singleton for test isolation
        import core.i18n as i18n_mod
        from core.i18n import get_i18n_manager

        i18n_mod._i18n_manager = None

        mgr1 = get_i18n_manager()
        mgr2 = get_i18n_manager()
        assert mgr1 is mgr2

        # Cleanup
        i18n_mod._i18n_manager = None

    def test_detect_language_convenience_function(self):
        import core.i18n as i18n_mod
        from core.i18n import detect_language

        i18n_mod._i18n_manager = None

        result = detect_language("Hello, how are you doing today?")
        assert result == "en"

        i18n_mod._i18n_manager = None

    @pytest.mark.asyncio
    async def test_translate_response_same_language_noop(self):
        """If source and target language are the same, return text as-is."""
        from core.i18n import translate_response

        text = "Hola mundo"
        result = await translate_response(text, target_lang="es", source_lang="es")
        assert result == text

    @pytest.mark.asyncio
    async def test_translate_response_empty_text(self):
        from core.i18n import translate_response

        result = await translate_response("", target_lang="en", source_lang="es")
        assert result == ""

    @pytest.mark.asyncio
    async def test_respond_in_language_same_lang_noop(self):
        from core.i18n import I18nManager

        mgr = I18nManager()
        result = await mgr.respond_in_language("Hola!", "es", "es")
        assert result == "Hola!"
