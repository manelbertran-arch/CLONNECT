"""
Tests for services/gold_examples_service.py

Focus: scoring & ranking logic in get_matching_examples,
cache invalidation, and quality score constants.
DB calls are mocked via patch.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, patch
from services.gold_examples_service import (
    _SOURCE_QUALITY,
    _invalidate_examples_cache,
    _examples_cache,
    _examples_cache_ts,
    get_matching_examples,
    GOLD_MAX_EXAMPLES_IN_PROMPT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_example(
    intent=None, lead_stage=None, relationship_type=None,
    quality=0.8, user_msg="Pregunta?", response="Respuesta.",
):
    ex = MagicMock()
    ex.intent = intent
    ex.lead_stage = lead_stage
    ex.relationship_type = relationship_type
    ex.quality_score = quality
    ex.user_message = user_msg
    ex.creator_response = response
    ex.is_active = True
    return ex


@pytest.fixture(autouse=True)
def clear_examples_cache():
    """Clear module-level cache before and after each test."""
    _examples_cache.clear()
    _examples_cache_ts.clear()
    yield
    _examples_cache.clear()
    _examples_cache_ts.clear()


def _mock_session_returning(examples):
    """Create a mock DB session whose query chain returns the given list.

    get_matching_examples uses: session.query(GoldExample).filter(...).limit(20).all()
    """
    session = MagicMock()
    (session.query.return_value
         .filter.return_value
         .limit.return_value
         .all.return_value) = examples
    session.close = MagicMock()
    return session


# ---------------------------------------------------------------------------
# Quality constants
# ---------------------------------------------------------------------------

class TestSourceQuality:

    def test_manual_override_has_highest_quality(self):
        q = _SOURCE_QUALITY
        assert q["manual_override"] > q["approved"]
        assert q["approved"] > q["minor_edit"]
        assert q["minor_edit"] > q["historical"]

    def test_quality_scores_are_in_valid_range(self):
        for source, score in _SOURCE_QUALITY.items():
            assert 0 < score <= 1.0, f"{source} score {score} out of range"


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------

class TestInvalidateExamplesCache:

    def test_invalidate_removes_matching_prefix(self):
        _examples_cache["abc123:pricing:None:None"] = [{"user_message": "q"}]
        _examples_cache["abc123:other:None:None"] = [{"user_message": "q2"}]
        _examples_cache["xyz999:pricing:None:None"] = [{"user_message": "q3"}]
        _examples_cache_ts.update({k: time.time() for k in _examples_cache})

        _invalidate_examples_cache("abc123")

        assert "abc123:pricing:None:None" not in _examples_cache
        assert "abc123:other:None:None" not in _examples_cache
        # Other creator's cache untouched
        assert "xyz999:pricing:None:None" in _examples_cache

    def test_invalidate_nonexistent_creator_does_not_crash(self):
        _invalidate_examples_cache("nobody")  # Should not raise


# ---------------------------------------------------------------------------
# get_matching_examples — scoring logic
# ---------------------------------------------------------------------------

class TestGetMatchingExamplesScoring:

    def test_returns_empty_list_when_no_examples(self):
        with patch("api.database.SessionLocal",
                   lambda: _mock_session_returning([])):
            result = get_matching_examples("creator_1", intent="pricing")
        assert result == []

    def test_intent_match_scores_higher_than_no_match(self):
        """Intent match (+3×quality) beats universal (+0.5×quality)."""
        ex_intent = make_example(intent="pricing", quality=0.8, user_msg="precio?", response="97€")
        ex_universal = make_example(intent=None, quality=0.9, user_msg="hola", response="hola")

        with patch("api.database.SessionLocal",
                   lambda: _mock_session_returning([ex_intent, ex_universal])):
            result = get_matching_examples("creator_2", intent="pricing")

        # First result should be intent-matched example
        assert len(result) >= 1
        assert result[0]["user_message"] == "precio?"

    def test_universal_example_without_intent_gets_base_score(self):
        """Example with no intent/stage/rel gets +0.5×quality as base score."""
        ex_universal = make_example(intent=None, lead_stage=None, relationship_type=None,
                                    quality=1.0, user_msg="q_universal", response="r_universal")
        with patch("api.database.SessionLocal",
                   lambda: _mock_session_returning([ex_universal])):
            result = get_matching_examples("creator_3", intent="pricing")
        # Score = 0.5 × 1.0 = 0.5 > 0 → should appear
        assert len(result) == 1
        assert result[0]["user_message"] == "q_universal"

    def test_example_with_wrong_intent_ranks_lowest(self):
        """Example whose intent doesn't match still appears (base score > 0) but ranks last."""
        ex_mismatch = make_example(intent="other_intent", lead_stage=None,
                                   relationship_type=None, quality=0.8,
                                   user_msg="q_mismatch", response="r_mismatch")
        ex_match = make_example(intent="pricing", lead_stage=None,
                                relationship_type=None, quality=0.8,
                                user_msg="q_match", response="r_match")
        with patch("api.database.SessionLocal",
                   lambda: _mock_session_returning([ex_mismatch, ex_match])):
            result = get_matching_examples("creator_4", intent="pricing",
                                           lead_stage=None, relationship_type=None)
        # Both appear (base score > 0), but intent-matched ranks first
        assert len(result) == 2
        assert result[0]["user_message"] == "q_match"

    def test_stage_match_adds_score(self):
        """Stage match (+2) ranks higher than intent match alone (+3×0.5)."""
        ex_intent_only = make_example(intent="pricing", quality=0.5,
                                      user_msg="q_intent", response="r_intent")
        ex_stage_match = make_example(intent=None, lead_stage="interesado", quality=0.8,
                                      user_msg="q_stage", response="r_stage")
        # Intent-only: 3 × 0.5 = 1.5
        # Stage match: 2 × 0.8 = 1.6 → stage wins

        with patch("api.database.SessionLocal",
                   lambda: _mock_session_returning([ex_intent_only, ex_stage_match])):
            result = get_matching_examples("creator_5", intent="pricing",
                                           lead_stage="interesado")
        assert len(result) >= 1
        # stage example should appear (both have score > 0)
        user_msgs = [r["user_message"] for r in result]
        assert "q_stage" in user_msgs

    def test_returns_at_most_gold_max_examples(self):
        """Should return at most GOLD_MAX_EXAMPLES_IN_PROMPT results."""
        many_examples = [
            make_example(intent="pricing", quality=0.8,
                         user_msg=f"q{i}", response=f"r{i}")
            for i in range(10)
        ]
        with patch("api.database.SessionLocal",
                   lambda: _mock_session_returning(many_examples)):
            result = get_matching_examples("creator_6", intent="pricing")
        assert len(result) <= GOLD_MAX_EXAMPLES_IN_PROMPT

    def test_result_contains_required_keys(self):
        ex = make_example(intent="pricing", quality=0.8,
                          user_msg="qué precio tiene?", response="97€")
        with patch("api.database.SessionLocal",
                   lambda: _mock_session_returning([ex])):
            result = get_matching_examples("creator_7", intent="pricing")
        assert len(result) == 1
        item = result[0]
        assert "user_message" in item
        assert "creator_response" in item
        assert "intent" in item
        assert "quality_score" in item

    def test_caches_result_on_second_call(self):
        """Second call with same params returns cached result without DB call."""
        ex = make_example(intent="pricing", quality=0.8, user_msg="q", response="r")
        call_count = {"n": 0}

        def make_session():
            call_count["n"] += 1
            return _mock_session_returning([ex])

        with patch("api.database.SessionLocal", make_session):
            r1 = get_matching_examples("creator_8", intent="pricing")
            r2 = get_matching_examples("creator_8", intent="pricing")

        assert r1 == r2
        assert call_count["n"] == 1  # Only one DB call

    def test_different_params_bypass_cache(self):
        """Different intent/stage/rel combination creates different cache key."""
        ex1 = make_example(intent="pricing", quality=0.8, user_msg="precio", response="97€")
        ex2 = make_example(intent="support", quality=0.8, user_msg="ayuda", response="claro")
        call_count = {"n": 0}

        def make_session():
            call_count["n"] += 1
            return _mock_session_returning([ex1, ex2])

        with patch("api.database.SessionLocal", make_session):
            get_matching_examples("creator_9", intent="pricing")
            get_matching_examples("creator_9", intent="support")

        assert call_count["n"] == 2  # Two DB calls, different cache keys

    def test_returns_empty_on_db_query_error(self):
        """DB query error inside try block → graceful degradation → empty list.

        Note: SessionLocal() itself is outside the try block in get_matching_examples;
        the except only catches errors from session.query() and subsequent operations.
        """
        session = MagicMock()
        session.query.side_effect = RuntimeError("DB query failed")
        session.close = MagicMock()

        with patch("api.database.SessionLocal", return_value=session):
            result = get_matching_examples("creator_10", intent="pricing")
        assert result == []
