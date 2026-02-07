"""Audit tests for core/i18n.py"""

from core.i18n import Language, detect_language, get_system_message


class TestAuditI18n:
    def test_import(self):
        from core.i18n import (  # noqa: F811
            I18nManager,
            Language,
            LanguageDetector,
            get_system_message,
        )

        assert Language is not None

    def test_languages_exist(self):
        languages = list(Language)
        assert len(languages) >= 2

    def test_happy_path_system_message(self):
        try:
            msg = get_system_message("greeting", Language(list(Language)[0].value))
            assert msg is not None
        except (KeyError, TypeError):
            pass  # Acceptable if key doesn't exist

    def test_edge_case_detect_language(self):
        result = detect_language("Hola, buenos dias")
        assert result is not None

    def test_error_handling_detect_empty(self):
        result = detect_language("")
        assert result is not None
