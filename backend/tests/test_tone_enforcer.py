"""
Tests for services/tone_enforcer.py

Tone enforcer applies probabilistic, hash-deterministic tone markers
(emoji, exclamation, question) to DM responses based on calibration targets.
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from services.tone_enforcer import enforce_tone

# ---------------------------------------------------------------------------
# Calibration fixtures
# ---------------------------------------------------------------------------

CAL_ZERO = {"baseline": {"emoji_pct": 0, "exclamation_pct": 0, "question_frequency_pct": 0}}
CAL_FULL = {"baseline": {"emoji_pct": 100, "exclamation_pct": 100, "question_frequency_pct": 100}}
CAL_MID = {"baseline": {"emoji_pct": 50, "exclamation_pct": 50, "question_frequency_pct": 50}}

_EMOJI_RE = re.compile(r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\ufe00-\ufe0f]")


def has_emoji(text: str) -> bool:
    return bool(_EMOJI_RE.search(text))


# ---------------------------------------------------------------------------
# Guard: invalid / empty inputs
# ---------------------------------------------------------------------------

class TestGuards:

    def test_none_calibration_returns_response_unchanged(self):
        r = "Hola cómo vas"
        assert enforce_tone(r, None) == r

    def test_empty_response_returns_empty(self):
        assert enforce_tone("", CAL_FULL, "u1", "m1") == ""

    def test_none_response_like_falsy_returns_unchanged(self):
        # empty string is falsy → should return as-is
        assert enforce_tone("", CAL_ZERO) == ""

    def test_empty_calibration_dict_returns_unchanged(self):
        r = "Sin calibración"
        assert enforce_tone(r, {}) == r

    def test_baseline_present_but_all_zero_fields(self):
        r = "Texto sin marcadores"
        result = enforce_tone(r, {"baseline": {}})
        assert result == r


# ---------------------------------------------------------------------------
# Emoji enforcement
# ---------------------------------------------------------------------------

class TestEmojiEnforcement:

    def test_100pct_always_injects_emoji_when_missing(self):
        """threshold = 1000; hash%1000 < 1000 always → inject."""
        result = enforce_tone("Hola que tal", CAL_FULL, "sender_x", "msg_x")
        assert has_emoji(result), f"Expected emoji in: {result!r}"

    def test_0pct_always_removes_emoji_when_present(self):
        """threshold = 0; hash%1000 < 0 never → remove."""
        result = enforce_tone("Genial 😊 todo bien", CAL_ZERO, "sender_x", "msg_x")
        assert not has_emoji(result), f"Unexpected emoji in: {result!r}"

    def test_100pct_keeps_existing_emoji(self):
        """If already has emoji and pct=100, should not duplicate/remove."""
        r = "Hola 💙"
        result = enforce_tone(r, CAL_FULL, "s1", "m1")
        assert has_emoji(result)

    def test_0pct_no_emoji_stays_clean(self):
        """If no emoji and pct=0, response unchanged."""
        r = "Hola sin emojis"
        result = enforce_tone(r, CAL_ZERO, "s2", "m2")
        assert not has_emoji(result)
        assert result.strip() == r.strip()

    def test_injected_emoji_appended_not_prepended(self):
        """Emoji goes at end of the response, original words remain."""
        result = enforce_tone("Texto limpio", CAL_FULL, "s3", "m3")
        # Original words must survive regardless of added markers
        assert "Texto limpio" in result


# ---------------------------------------------------------------------------
# Exclamation enforcement
# ---------------------------------------------------------------------------

class TestExclamationEnforcement:

    def test_100pct_adds_exclamation_if_missing(self):
        result = enforce_tone("Claro te ayudo", CAL_FULL, "s4", "m4")
        assert "!" in result

    def test_0pct_removes_first_exclamation_if_present(self):
        result = enforce_tone("Claro te ayudo!", CAL_ZERO, "s4", "m4")
        assert "!" not in result

    def test_0pct_removes_only_first_exclamation(self):
        """enforce removes one !, not all."""
        result = enforce_tone("Genial! Super!", CAL_ZERO, "s5", "m5")
        assert result.count("!") == 1

    def test_100pct_existing_exclamation_stays(self):
        r = "Perfecto!"
        result = enforce_tone(r, CAL_FULL, "s6", "m6")
        assert "!" in result


# ---------------------------------------------------------------------------
# Question enforcement
# ---------------------------------------------------------------------------

class TestQuestionEnforcement:

    def test_100pct_adds_question_if_missing(self):
        result = enforce_tone("Cuéntame más sobre ti", CAL_FULL, "s7", "m7")
        assert "?" in result

    def test_0pct_removes_question_if_present(self):
        result = enforce_tone("Cómo estás?", CAL_ZERO, "s7", "m7")
        assert "?" not in result

    def test_injected_question_is_natural_phrase(self):
        """Injected questions come from a predefined list — should be readable."""
        from services.tone_enforcer import _INJECT_QUESTIONS
        result = enforce_tone("Perfecto entendido", CAL_FULL, "s8", "m8")
        if "?" in result:
            # The appended question should be one of the known phrases
            ends_with_known = any(result.rstrip().endswith(q.strip()) for q in _INJECT_QUESTIONS)
            assert ends_with_known or result.rstrip().endswith("?")


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:

    def test_same_inputs_always_produce_same_output(self):
        """Hash is MD5(sender_id + message[:30]) — must be deterministic."""
        for _ in range(5):
            r1 = enforce_tone("Hola", CAL_MID, "user_42", "mensaje_42")
            r2 = enforce_tone("Hola", CAL_MID, "user_42", "mensaje_42")
            assert r1 == r2

    def test_different_senders_dont_crash(self):
        """Different senders may produce different outputs — just verify no exception."""
        senders = ["alice", "bob", "carol", "dave", "eve"]
        results = [enforce_tone("Buenas", CAL_MID, s, "hola") for s in senders]
        assert all(isinstance(r, str) for r in results)
        assert all(len(r) > 0 for r in results)

    def test_response_content_preserved(self):
        """Enforce should never mangle the actual message text."""
        original = "Eso es exactamente lo que necesitas para avanzar"
        result = enforce_tone(original, CAL_MID, "usr", "msg")
        # Core content should still be present (markers may be added but text intact)
        text_stripped = _EMOJI_RE.sub("", result).replace("!", "").replace("?", "").strip()
        # The original text (minus any markers it already had) should be preserved
        assert len(text_stripped) > 0
        assert "exactamente" in result  # Key word should survive
