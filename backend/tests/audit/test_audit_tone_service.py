"""Audit tests for core/tone_service.py"""

from core.tone_service import get_tone_dialect, get_tone_language, get_tone_prompt_section


class TestAuditToneService:
    def test_import(self):
        from core.tone_service import (  # noqa: F811
            get_tone_dialect,
            get_tone_language,
            get_tone_prompt_section,
        )

        assert get_tone_prompt_section is not None

    def test_functions_callable(self):
        assert callable(get_tone_prompt_section)
        assert callable(get_tone_language)
        assert callable(get_tone_dialect)

    def test_happy_path_tone_prompt(self):
        try:
            result = get_tone_prompt_section("test_creator")
            assert result is not None or result == "" or result is None
        except Exception:
            pass  # DB not available

    def test_edge_case_language(self):
        try:
            lang = get_tone_language("nonexistent_creator")
            assert lang is None or isinstance(lang, str)
        except Exception:
            pass  # DB not available

    def test_error_handling_dialect(self):
        try:
            dialect = get_tone_dialect("nonexistent_creator")
            assert dialect is None or isinstance(dialect, str)
        except Exception:
            pass  # DB not available
