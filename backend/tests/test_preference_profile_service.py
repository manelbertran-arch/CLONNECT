"""
Tests for services/preference_profile_service.py

format_preference_profile_for_prompt is pure (no DB) — tested exhaustively.
compute_preference_profile is DB-dependent — tested with mocks.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, patch
from services.preference_profile_service import (
    format_preference_profile_for_prompt,
    compute_preference_profile,
    _profile_cache,
    _profile_cache_ts,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FULL_PROFILE = {
    "response_length": {"min": 40, "max": 320, "avg": 130, "label": "corta"},
    "emoji_usage": {"rate": 0.35, "style": "moderado"},
    "question_ending": {"rate": 0.45},
    "cta_inclusion": {"rate": 0.20},
    "formality": {"level": "informal"},
    "sample_size": 30,
}


@pytest.fixture(autouse=True)
def clear_profile_cache():
    """Clear module-level profile cache before each test."""
    _profile_cache.clear()
    _profile_cache_ts.clear()
    yield
    _profile_cache.clear()
    _profile_cache_ts.clear()


# ---------------------------------------------------------------------------
# format_preference_profile_for_prompt — pure function
# ---------------------------------------------------------------------------

class TestFormatPreferenceProfileForPrompt:

    def test_returns_empty_string_for_none(self):
        assert format_preference_profile_for_prompt(None) == ""

    def test_returns_empty_string_for_empty_dict(self):
        assert format_preference_profile_for_prompt({}) == ""

    def test_includes_section_headers(self):
        result = format_preference_profile_for_prompt(FULL_PROFILE)
        assert "=== PERFIL" in result
        assert "=== FIN PERFIL ===" in result

    def test_includes_average_response_length(self):
        result = format_preference_profile_for_prompt(FULL_PROFILE)
        assert "130" in result  # avg

    def test_includes_length_label(self):
        result = format_preference_profile_for_prompt(FULL_PROFILE)
        assert "corta" in result

    def test_includes_emoji_style(self):
        result = format_preference_profile_for_prompt(FULL_PROFILE)
        assert "moderado" in result

    def test_includes_emoji_rate_as_percentage(self):
        result = format_preference_profile_for_prompt(FULL_PROFILE)
        assert "35%" in result

    def test_includes_formality_level(self):
        result = format_preference_profile_for_prompt(FULL_PROFILE)
        assert "informal" in result

    def test_includes_creator_name_uppercased(self):
        result = format_preference_profile_for_prompt(FULL_PROFILE, "stefano_bonanno")
        assert "STEFANO_BONANNO" in result

    def test_no_creator_name_omits_name_section(self):
        result = format_preference_profile_for_prompt(FULL_PROFILE, "")
        assert "=== PERFIL DE PREFERENCIAS ===" in result
        # No " DE " connector when name is empty
        assert " DE  " not in result

    def test_question_ending_label_frecuente_above_40pct(self):
        profile = {**FULL_PROFILE, "question_ending": {"rate": 0.5}}
        result = format_preference_profile_for_prompt(profile)
        assert "frecuente" in result

    def test_question_ending_label_ocasional_between_15_and_40pct(self):
        profile = {**FULL_PROFILE, "question_ending": {"rate": 0.25}}
        result = format_preference_profile_for_prompt(profile)
        assert "ocasional" in result

    def test_question_ending_label_raro_below_15pct(self):
        profile = {**FULL_PROFILE, "question_ending": {"rate": 0.05}}
        result = format_preference_profile_for_prompt(profile)
        assert "raro" in result

    def test_handles_partial_profile_no_crash(self):
        """Partial profiles (missing keys) should not raise."""
        partial = {"response_length": {"avg": 100, "label": "corta"}}
        result = format_preference_profile_for_prompt(partial)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_question_rate_shown_as_percentage(self):
        profile = {**FULL_PROFILE, "question_ending": {"rate": 0.33}}
        result = format_preference_profile_for_prompt(profile)
        assert "33%" in result


# ---------------------------------------------------------------------------
# compute_preference_profile — DB-dependent (mocked)
# ---------------------------------------------------------------------------

class TestComputePreferenceProfile:
    # compute_preference_profile imports SessionLocal lazily:
    #   from api.database import SessionLocal
    # So we patch api.database.SessionLocal, not the module attribute.

    def _make_session(self, messages):
        """Build a mock session whose SQLAlchemy chain returns the given messages.

        Actual query: session.query(Message.content)
                           .join(Lead, ...)
                           .filter(...)
                           .order_by(...)
                           .limit(100)
                           .all()
        """
        session = MagicMock()
        (session.query.return_value
             .join.return_value
             .filter.return_value
             .order_by.return_value
             .limit.return_value
             .all.return_value) = messages
        session.close = MagicMock()
        return session

    def test_returns_none_on_db_query_error(self):
        """DB error inside try block → except handler returns None."""
        session = MagicMock()
        session.query.side_effect = RuntimeError("DB query failed")
        session.close = MagicMock()

        with patch("api.database.SessionLocal", return_value=session):
            result = compute_preference_profile("fake_creator_uuid")
        assert result is None

    def test_returns_none_when_fewer_than_10_messages(self):
        """Minimum sample size is 10; fewer returns None."""
        five_messages = [("Respuesta corta",) for _ in range(5)]
        session = self._make_session(five_messages)

        with patch("api.database.SessionLocal", return_value=session):
            result = compute_preference_profile("creator_uuid_abc")
        assert result is None

    def test_returns_profile_dict_with_correct_keys(self):
        """With >=10 valid messages, should return a structured profile."""
        messages = [(f"Respuesta de longitud media número {i}",) for i in range(15)]
        session = self._make_session(messages)

        with patch("api.database.SessionLocal", return_value=session):
            result = compute_preference_profile("creator_uuid_def")
        assert result is not None
        assert "response_length" in result
        assert "emoji_usage" in result
        assert "question_ending" in result
        assert "formality" in result
        assert "sample_size" in result
        assert result["sample_size"] == 15

    def test_caches_result_on_second_call(self):
        """Second call with same creator_id returns cached result without hitting DB."""
        messages = [(f"Msg {i} con suficiente texto para procesar",) for i in range(10)]
        call_count = {"n": 0}

        def make_session():
            call_count["n"] += 1
            session = MagicMock()
            (session.query.return_value
                 .join.return_value
                 .filter.return_value
                 .order_by.return_value
                 .limit.return_value
                 .all.return_value) = messages
            session.close = MagicMock()
            return session

        with patch("api.database.SessionLocal", make_session):
            r1 = compute_preference_profile("cached_creator_xy")
            r2 = compute_preference_profile("cached_creator_xy")
        assert r1 == r2
        assert call_count["n"] == 1  # DB only queried once
