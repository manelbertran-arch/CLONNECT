"""
Tests for CCEE metric fixes:
  - Fix 1: L2 configurable threshold + 50.0 fallback instead of None
  - Fix 2: J5 scores up to 2 post-shift turns (mean)
  - Fix 3: C3 injects creator_style_note into prompt
"""

import importlib
import os
import sys
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_history(*messages):
    """Build a minimal conversation history from (role, content) pairs."""
    return [{"role": role, "content": content} for role, content in messages]


def _multi_turn_conv(history, belief_shift_turn=None):
    conv = {"history": history}
    if belief_shift_turn is not None:
        conv["belief_shift_turn"] = belief_shift_turn
    return conv


# ---------------------------------------------------------------------------
# Fix 1: L2 — configurable threshold + 50.0 fallback
# ---------------------------------------------------------------------------

class TestL2Threshold:

    def _import_scorer(self):
        """Re-import multi_turn_scorer so env vars take effect."""
        if "core.evaluation.multi_turn_scorer" in sys.modules:
            del sys.modules["core.evaluation.multi_turn_scorer"]
        import core.evaluation.multi_turn_scorer as m
        return m

    def test_all_turns_below_threshold_returns_50(self):
        """When every bot turn is shorter than L2_MIN_LENGTH, score=50.0 not None."""
        import core.evaluation.multi_turn_scorer as scorer
        history = _make_history(
            ("user", "hola"),
            ("assistant", "hey!"),           # 4 chars — well below 20
            ("user", "qué tal?"),
            ("assistant", "bien :)"),         # 7 chars
        )
        conv = _multi_turn_conv(history)

        with patch.object(scorer, "_load_compressed_doc_d", return_value="mock doc d"):
            result = scorer.score_l2_logical_reasoning(conv, "test_creator")

        assert result["score"] == 50.0
        assert "all_turns_below_min_length" in result.get("reason", "")

    def test_turns_at_20_chars_are_scored(self):
        """Bot turns >= 20 chars are now included (previously excluded at < 40)."""
        import core.evaluation.multi_turn_scorer as scorer
        # Exactly 20 chars (new threshold default)
        bot_msg = "a" * 20
        history = _make_history(
            ("user", "pregunta"),
            ("assistant", bot_msg),
        )
        conv = _multi_turn_conv(history)

        mock_raw = "Feedback: ok [RESULT] 3"
        with patch.object(scorer, "_load_compressed_doc_d", return_value="doc d"), \
             patch.object(scorer, "_call_judge", return_value=mock_raw), \
             patch.object(scorer, "_parse_result_score", return_value=3):
            result = scorer.score_l2_logical_reasoning(conv, "test_creator")

        assert result["score"] is not None
        assert result["score"] != 50.0 or result.get("reason") is None
        assert result.get("n_turns_scored", 0) >= 1

    def test_env_var_overrides_threshold(self):
        """L2_MIN_CHAR_THRESHOLD env var changes the threshold."""
        env = {**os.environ, "L2_MIN_CHAR_THRESHOLD": "10"}
        with patch.dict(os.environ, env):
            m = self._import_scorer()
            assert m.L2_MIN_LENGTH == 10

    def test_default_threshold_is_20(self):
        """Default threshold is 20 when env var not set."""
        env = {k: v for k, v in os.environ.items() if k != "L2_MIN_CHAR_THRESHOLD"}
        with patch.dict(os.environ, env, clear=True):
            m = self._import_scorer()
            assert m.L2_MIN_LENGTH == 20

    def test_turns_below_40_but_above_20_now_scored(self):
        """Turns between 20-39 chars (old dead zone) are now included."""
        import core.evaluation.multi_turn_scorer as scorer
        bot_msg = "a" * 30  # 30 chars: above 20, below old 40
        history = _make_history(
            ("user", "test question here"),
            ("assistant", bot_msg),
        )
        conv = _multi_turn_conv(history)
        mock_raw = "Feedback: generic [RESULT] 3"
        with patch.object(scorer, "_load_compressed_doc_d", return_value="doc d"), \
             patch.object(scorer, "_call_judge", return_value=mock_raw), \
             patch.object(scorer, "_parse_result_score", return_value=3):
            result = scorer.score_l2_logical_reasoning(conv, "test_creator")
        # Must not be the "no substantive turns" fallback
        assert result.get("reason") != "all_turns_below_min_length"
        assert result.get("n_turns_scored", 0) == 1

    def test_doc_d_unavailable_still_returns_none_score(self):
        """When doc_d is unavailable, score is still None (different from threshold issue)."""
        import core.evaluation.multi_turn_scorer as scorer
        bot_msg = "a" * 50
        history = _make_history(
            ("user", "pregunta larga"),
            ("assistant", bot_msg),
        )
        conv = _multi_turn_conv(history)
        with patch.object(scorer, "_load_compressed_doc_d", return_value=None):
            result = scorer.score_l2_logical_reasoning(conv, "test_creator")
        assert result["score"] is None
        assert result.get("reason") == "doc_d_unavailable"


# ---------------------------------------------------------------------------
# Fix 2: J5 — score up to 2 post-shift turns
# ---------------------------------------------------------------------------

class TestJ5MultiTurn:

    def test_two_post_shift_turns_both_scored(self):
        """When 2 post-shift creator turns exist, both are scored and mean returned."""
        import core.evaluation.multi_turn_scorer as scorer
        history = _make_history(
            ("user", "pre-shift message"),
            ("assistant", "pre-shift response"),
            ("user", "sudden topic change!"),   # shift turn (idx 1 in turn count)
            ("assistant", "handling shift turn 1"),
            ("user", "follow-up after shift"),
            ("assistant", "handling shift turn 2"),
        )
        conv = _multi_turn_conv(history, belief_shift_turn=1)

        # Judge returns 4 for turn 1 and 3 for turn 2
        call_results = iter(["Feedback: good [RESULT] 4", "Feedback: ok [RESULT] 3"])
        parse_results = iter([4, 3])

        with patch.object(scorer, "_call_judge", side_effect=lambda *a, **kw: next(call_results)), \
             patch.object(scorer, "_parse_result_score", side_effect=lambda *a: next(parse_results)):
            result = scorer.score_j5_belief_drift(conv)

        # Mean of 4 and 3 = 3.5 → _score_to_100(3.5) = (3.5-1)/4*100 = 62.5
        assert result["score"] is not None
        assert result["n_post_shift_turns"] == 2
        assert len(result["raw_scores_1_5"]) == 2
        assert result["raw_scores_1_5"] == [4, 3]
        expected_score = round((4 + 3) / 2 - 1) / 4 * 100  # rough check
        # Just verify it's between 50 and 75 (between scores 3→50 and 4→75)
        assert 50.0 <= result["score"] <= 75.0

    def test_one_post_shift_turn_single_score(self):
        """When only 1 post-shift creator turn exists, single score returned."""
        import core.evaluation.multi_turn_scorer as scorer
        history = _make_history(
            ("user", "pre-shift message"),
            ("assistant", "pre-shift response"),
            ("user", "sudden topic change!"),
            ("assistant", "single shift response"),
        )
        conv = _multi_turn_conv(history, belief_shift_turn=1)

        with patch.object(scorer, "_call_judge", return_value="Feedback: ok [RESULT] 4"), \
             patch.object(scorer, "_parse_result_score", return_value=4):
            result = scorer.score_j5_belief_drift(conv)

        assert result["score"] is not None
        assert result["n_post_shift_turns"] == 1
        assert result["raw_scores_1_5"] == [4]
        assert result["score"] == pytest.approx(75.0)  # _score_to_100(4) = 75

    def test_no_belief_shift_returns_50(self):
        """Conversations without belief_shift_turn return 50.0 (unchanged)."""
        import core.evaluation.multi_turn_scorer as scorer
        history = _make_history(
            ("user", "normal message"),
            ("assistant", "normal response"),
        )
        conv = _multi_turn_conv(history)  # no belief_shift_turn
        result = scorer.score_j5_belief_drift(conv)
        assert result["score"] == 50.0

    def test_score_key_is_single_float(self):
        """Interface contract: 'score' is always a single float, never a list."""
        import core.evaluation.multi_turn_scorer as scorer
        history = _make_history(
            ("user", "pre-shift"),
            ("assistant", "pre"),
            ("user", "shift!"),
            ("assistant", "response 1"),
            ("user", "follow"),
            ("assistant", "response 2"),
        )
        conv = _multi_turn_conv(history, belief_shift_turn=1)
        call_seq = iter(["Feedback: a [RESULT] 3", "Feedback: b [RESULT] 4"])
        parse_seq = iter([3, 4])
        with patch.object(scorer, "_call_judge", side_effect=lambda *a, **kw: next(call_seq)), \
             patch.object(scorer, "_parse_result_score", side_effect=lambda *a: next(parse_seq)):
            result = scorer.score_j5_belief_drift(conv)
        assert isinstance(result["score"], float)

    def test_no_creator_responses_after_shift_returns_50(self):
        """If shift context has no assistant messages, returns 50.0."""
        import core.evaluation.multi_turn_scorer as scorer
        history = _make_history(
            ("user", "pre-shift"),
            ("assistant", "pre"),
            ("user", "shift!"),
            # No assistant response follows
        )
        conv = _multi_turn_conv(history, belief_shift_turn=1)
        result = scorer.score_j5_belief_drift(conv)
        assert result["score"] == 50.0


# ---------------------------------------------------------------------------
# Fix 3: C3 — creator_style_note injection
# ---------------------------------------------------------------------------

class TestC3StyleNote:

    @pytest.mark.asyncio
    async def test_style_note_injected_in_prompt(self):
        """When creator_style_note is provided, prompt contains it."""
        import core.evaluation.llm_judge as judge
        captured = {}

        async def mock_call(prompt, system):
            captured["prompt"] = prompt
            return '{"rating": 4, "reason": "ok"}'

        with patch.object(judge, "_call_judge", side_effect=mock_call):
            await judge.score_c3_contextual_appropriateness(
                bot_response="hey como va todo",
                user_input="hola!",
                context_type="",
                creator_style_note="Casual, informal, Catalan/Spanish mix, short DMs",
            )

        assert "Casual, informal" in captured["prompt"]
        assert "creator" in captured["prompt"].lower()

    @pytest.mark.asyncio
    async def test_no_style_note_prompt_unchanged(self):
        """When creator_style_note is empty, prompt doesn't include style noise."""
        import core.evaluation.llm_judge as judge
        captured = {}

        async def mock_call(prompt, system):
            captured["prompt"] = prompt
            return '{"rating": 3, "reason": "ok"}'

        with patch.object(judge, "_call_judge", side_effect=mock_call):
            await judge.score_c3_contextual_appropriateness(
                bot_response="fine response",
                user_input="question",
                context_type="",
                creator_style_note="",
            )

        # Style note should not pollute prompt when empty
        assert "Creator style:" not in captured["prompt"]

    @pytest.mark.asyncio
    async def test_batch_passes_truncated_creator_description_to_c3(self):
        """score_llm_judge_batch derives style_note from creator_description and passes to C3."""
        import core.evaluation.llm_judge as judge

        c3_calls = []

        original_c3 = judge.score_c3_contextual_appropriateness

        async def spy_c3(bot_response, user_input, context_type="", creator_style_note=""):
            c3_calls.append({"style_note": creator_style_note})
            return 75.0

        long_desc = "X" * 300  # 300 chars — should be truncated to 200
        test_cases = [{"user_input": "hola", "input_type": "greeting"}]
        bot_responses = ["respuesta"]

        with patch.object(judge, "score_c3_contextual_appropriateness", side_effect=spy_c3), \
             patch.object(judge, "score_b2_persona_consistency", new_callable=AsyncMock, return_value=75.0), \
             patch.object(judge, "score_b5_emotional_signature", new_callable=AsyncMock, return_value=75.0), \
             patch.object(judge, "score_c2_naturalness", new_callable=AsyncMock, return_value=75.0):
            await judge.score_llm_judge_batch(
                test_cases=test_cases,
                bot_responses=bot_responses,
                creator_description=long_desc,
            )

        assert len(c3_calls) == 1
        assert len(c3_calls[0]["style_note"]) <= 200
        assert c3_calls[0]["style_note"] == long_desc[:200].strip()

    @pytest.mark.asyncio
    async def test_batch_empty_creator_description_sends_empty_style_note(self):
        """When creator_description is empty, style_note passed to C3 is also empty."""
        import core.evaluation.llm_judge as judge

        c3_calls = []

        async def spy_c3(bot_response, user_input, context_type="", creator_style_note=""):
            c3_calls.append({"style_note": creator_style_note})
            return 50.0

        test_cases = [{"user_input": "hola", "input_type": ""}]
        bot_responses = ["resp"]

        with patch.object(judge, "score_c3_contextual_appropriateness", side_effect=spy_c3), \
             patch.object(judge, "score_b2_persona_consistency", new_callable=AsyncMock, return_value=50.0), \
             patch.object(judge, "score_b5_emotional_signature", new_callable=AsyncMock, return_value=50.0), \
             patch.object(judge, "score_c2_naturalness", new_callable=AsyncMock, return_value=50.0):
            await judge.score_llm_judge_batch(
                test_cases=test_cases,
                bot_responses=bot_responses,
                creator_description="",
            )

        assert c3_calls[0]["style_note"] == ""

    @pytest.mark.asyncio
    async def test_c3_rubric_references_creator_style_when_note_provided(self):
        """Prompt framing shifts from 'generic context' to 'this creator's style'."""
        import core.evaluation.llm_judge as judge
        captured = {}

        async def mock_call(prompt, system):
            captured["prompt"] = prompt
            return '{"rating": 5, "reason": "ok"}'

        with patch.object(judge, "_call_judge", side_effect=mock_call):
            await judge.score_c3_contextual_appropriateness(
                bot_response="tio que bueno",
                user_input="esto mola",
                creator_style_note="Very casual, uses slang, short replies",
            )

        # Prompt should reference "creator" style, not just generic context
        prompt_lower = captured["prompt"].lower()
        assert "creator" in prompt_lower or "style" in prompt_lower


# ---------------------------------------------------------------------------
# Fix A2: J6 logging — per_pair and per_probe must include response texts
# ---------------------------------------------------------------------------

class TestJ6LoggingFix:
    """J6 per_pair (within-conv) and per_probe (cross-session) must include
    probe question text and bot response texts so CCEE JSON is self-diagnostic.
    """

    def _make_probe_history(self):
        """Two probe turns with the same probe_id at turn 0 and turn 4."""
        return [
            {"role": "user",      "content": "What is your favourite food?",
             "is_qa_probe": True, "probe_id": "p1"},
            {"role": "assistant", "content": "I love sushi!"},
            {"role": "user",      "content": "Tell me about your day."},
            {"role": "assistant", "content": "It was great."},
            {"role": "user",      "content": "What is your favourite food?",
             "is_qa_probe": True, "probe_id": "p1"},
            {"role": "assistant", "content": "Sushi is definitely my favourite."},
        ]

    def test_per_pair_includes_probe_question_text(self):
        import core.evaluation.multi_turn_scorer as scorer
        conv = {"history": self._make_probe_history()}
        mock_raw = "Feedback: consistent [RESULT] 5"
        with patch.object(scorer, "_load_compressed_doc_d", return_value="doc d"), \
             patch.object(scorer, "_call_judge", return_value=mock_raw), \
             patch.object(scorer, "_parse_result_score", return_value=5):
            result = scorer.score_j6_qa_consistency(conv, "test_creator")
        assert result["mode"] == "probe_based"
        assert len(result["per_pair"]) == 1
        pair = result["per_pair"][0]
        assert pair["probe_question_text"] == "What is your favourite food?"

    def test_per_pair_includes_early_response_text(self):
        import core.evaluation.multi_turn_scorer as scorer
        conv = {"history": self._make_probe_history()}
        mock_raw = "Feedback: consistent [RESULT] 5"
        with patch.object(scorer, "_load_compressed_doc_d", return_value="doc d"), \
             patch.object(scorer, "_call_judge", return_value=mock_raw), \
             patch.object(scorer, "_parse_result_score", return_value=5):
            result = scorer.score_j6_qa_consistency(conv, "test_creator")
        pair = result["per_pair"][0]
        assert pair["early_turn_response_text"] == "I love sushi!"

    def test_per_pair_includes_late_response_text(self):
        import core.evaluation.multi_turn_scorer as scorer
        conv = {"history": self._make_probe_history()}
        mock_raw = "Feedback: consistent [RESULT] 5"
        with patch.object(scorer, "_load_compressed_doc_d", return_value="doc d"), \
             patch.object(scorer, "_call_judge", return_value=mock_raw), \
             patch.object(scorer, "_parse_result_score", return_value=5):
            result = scorer.score_j6_qa_consistency(conv, "test_creator")
        pair = result["per_pair"][0]
        assert pair["late_turn_response_text"] == "Sushi is definitely my favourite."

    def test_cross_session_per_probe_includes_texts(self):
        import core.evaluation.multi_turn_scorer as scorer
        conv1 = {"history": self._make_probe_history()}
        hist2 = [
            {"role": "user",      "content": "What is your favourite food?",
             "is_qa_probe": True, "probe_id": "p1"},
            {"role": "assistant", "content": "Without a doubt, sushi."},
        ]
        conv2 = {"history": hist2}
        mock_raw = "Feedback: consistent [RESULT] 5"
        with patch.object(scorer, "_load_compressed_doc_d", return_value="doc d"), \
             patch.object(scorer, "_call_judge", return_value=mock_raw), \
             patch.object(scorer, "_parse_result_score", return_value=5):
            result = scorer._score_j6_cross_session([conv1, conv2], "test_creator")
        assert result["score"] is not None
        probe = result["per_probe"][0]
        assert probe["probe_question_text"] == "What is your favourite food?"
        assert len(probe["cross_session_responses"]) == 2
        answers = {r["conv_idx"]: r["bot_answer"] for r in probe["cross_session_responses"]}
        assert answers[0] == "I love sushi!"
        assert answers[1] == "Without a doubt, sushi."
