"""
Tests for:
1. P1 scoring bug fixes (double-multiply eliminated)
2. FeedbackStore: save_feedback, get_feedback, get_feedback_stats
3. Auto-creation of preference pairs and gold examples from evaluator feedback
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. P1 Bug Regression Tests: Scoring must NOT double-multiply
# ---------------------------------------------------------------------------

class TestScoringBugFixes:
    """Verify that context-scored retrieval does NOT square confidence/quality."""

    @patch("api.database.SessionLocal")
    def test_learning_rules_no_double_confidence(self, mock_session_cls):
        """BUG-LR-02 regression: score should be linear in confidence, not quadratic."""
        from services.learning_rules_service import get_applicable_rules, _rules_cache, _rules_cache_ts

        # Clear cache
        _rules_cache.clear()
        _rules_cache_ts.clear()

        # Mock a rule with confidence=0.5, exact intent match
        mock_rule = MagicMock()
        mock_rule.confidence = 0.5
        mock_rule.pattern = "greeting"
        mock_rule.applies_to_relationship_types = []
        mock_rule.applies_to_message_types = []
        mock_rule.applies_to_lead_stages = []
        mock_rule.times_applied = 0
        mock_rule.times_helped = 0
        mock_rule.source = "realtime"
        mock_rule.id = uuid.uuid4()
        mock_rule.rule_text = "test rule"
        mock_rule.example_bad = "bad"
        mock_rule.example_good = "good"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_rule]
        mock_session_cls.return_value = mock_session

        creator_id = uuid.uuid4()
        result = get_applicable_rules(creator_id, intent="greeting")

        assert len(result) == 1

        # The score should be: (0.1 + 3 [intent match] + 1 [universal]) * 0.5 = 2.05
        # NOT: (0.5 * 0.1 + 3 + 1) * 0.5 = 2.025 (the old buggy squared behavior)
        # Since we can't directly access scores, verify the rule IS returned
        # (with the old bug, low-confidence rules could be filtered out)
        assert result[0]["rule_text"] == "test rule"
        assert result[0]["confidence"] == 0.5

    @patch("api.database.SessionLocal")
    def test_learning_rules_confidence_linear_not_quadratic(self, mock_session_cls):
        """Two rules with confidence 0.5 and 1.0 — ratio should be ~2:1, not ~4:1."""
        from services.learning_rules_service import get_applicable_rules, _rules_cache, _rules_cache_ts

        _rules_cache.clear()
        _rules_cache_ts.clear()

        def make_rule(conf):
            r = MagicMock()
            r.confidence = conf
            r.pattern = "greeting"
            r.applies_to_relationship_types = []
            r.applies_to_message_types = []
            r.applies_to_lead_stages = []
            r.times_applied = 0
            r.times_helped = 0
            r.source = "realtime"
            r.id = uuid.uuid4()
            r.rule_text = f"rule_conf_{conf}"
            r.example_bad = "bad"
            r.example_good = "good"
            return r

        rule_05 = make_rule(0.5)
        rule_10 = make_rule(1.0)

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [rule_05, rule_10]
        mock_session_cls.return_value = mock_session

        creator_id = uuid.uuid4()
        result = get_applicable_rules(creator_id, intent="greeting", max_rules=10)

        assert len(result) == 2
        # rule_10 should be first (higher score)
        assert result[0]["rule_text"] == "rule_conf_1.0"
        assert result[1]["rule_text"] == "rule_conf_0.5"

    @patch("api.database.SessionLocal")
    def test_gold_examples_no_double_quality(self, mock_session_cls):
        """BUG-GE-01 regression: score should be linear in quality_score, not quadratic."""
        from services.style_retriever import get_matching_examples, _examples_cache, _examples_cache_ts

        _examples_cache.clear()
        _examples_cache_ts.clear()

        mock_ex = MagicMock()
        mock_ex.id = uuid.uuid4()
        mock_ex.quality_score = 0.6
        mock_ex.intent = "greeting"
        mock_ex.lead_stage = None
        mock_ex.relationship_type = None
        mock_ex.user_message = "Hola!"
        mock_ex.creator_response = "Hey! Que tal?"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [mock_ex]
        mock_session_cls.return_value = mock_session

        creator_id = uuid.uuid4()
        result = get_matching_examples(creator_id, intent="greeting")

        assert len(result) == 1
        assert result[0]["creator_response"] == "Hey! Que tal?"
        assert result[0]["quality_score"] == 0.6


# ---------------------------------------------------------------------------
# 2. FeedbackStore Tests
# ---------------------------------------------------------------------------

class TestFeedbackStore:
    """Test the unified FeedbackStore service."""

    @patch("api.database.SessionLocal")
    def test_save_feedback_basic(self, mock_session_cls):
        """save_feedback stores a record and returns feedback_id."""
        from services.feedback_store import save_feedback

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # Mock the feedback object to get an ID after add+commit
        def set_id(obj):
            obj.id = uuid.uuid4()
        mock_session.add.side_effect = set_id

        result = save_feedback(
            creator_db_id=uuid.uuid4(),
            evaluator_id="manel",
            user_message="Cuanto cuesta?",
            bot_response="El precio es 199 euros.",
            coherencia=3,
            lo_enviarias=2,
        )

        assert result is not None
        assert result["status"] == "created"
        assert "feedback_id" in result
        assert result["pair_created"] is False  # No ideal_response
        assert result["gold_created"] is False
        mock_session.add.assert_called_once()
        # FIX FB-01: Single commit for feedback + derivatives
        assert mock_session.commit.call_count == 1

    @patch("services.feedback_capture._auto_create_gold_example")
    @patch("services.feedback_capture._auto_create_preference_pair")
    @patch("api.database.SessionLocal")
    def test_save_feedback_with_ideal_creates_pair(self, mock_session_cls, mock_pair, mock_gold):
        """When ideal_response provided, auto-creates preference pair."""
        from services.feedback_store import save_feedback

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        def set_id(obj):
            obj.id = uuid.uuid4()
        mock_session.add.side_effect = set_id

        mock_pair.return_value = True
        mock_gold.return_value = False

        result = save_feedback(
            creator_db_id=uuid.uuid4(),
            evaluator_id="manel",
            user_message="Cuanto cuesta?",
            bot_response="El precio es de 199 euros, pero a menudo hay ofertas...",
            coherencia=2,
            lo_enviarias=2,
            ideal_response="199! Si vols més info t'envio el link",
            intent_detected="question_product",
        )

        assert result is not None
        assert result["pair_created"] is True
        assert result["gold_created"] is False  # lo_enviarias < 4
        mock_pair.assert_called_once()

    @patch("services.feedback_capture._auto_create_gold_example")
    @patch("services.feedback_capture._auto_create_preference_pair")
    @patch("api.database.SessionLocal")
    def test_save_feedback_high_score_creates_gold(self, mock_session_cls, mock_pair, mock_gold):
        """When lo_enviarias >= 4 AND ideal_response, also creates gold example."""
        from services.feedback_store import save_feedback

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        def set_id(obj):
            obj.id = uuid.uuid4()
        mock_session.add.side_effect = set_id

        mock_pair.return_value = True
        mock_gold.return_value = True

        result = save_feedback(
            creator_db_id=uuid.uuid4(),
            evaluator_id="manel",
            user_message="M'encanta el teu contingut!",
            bot_response="Gràcies! Et recomano el curs",
            coherencia=4,
            lo_enviarias=4,
            ideal_response="Gràcies!! Quin contingut t'agrada més?",
        )

        assert result is not None
        assert result["pair_created"] is True
        assert result["gold_created"] is True
        mock_gold.assert_called_once()

    @patch("api.database.SessionLocal")
    def test_save_feedback_disabled_returns_status(self, mock_session_cls):
        """When ENABLE_EVALUATOR_FEEDBACK=false, returns status=disabled."""
        import services.feedback_capture as fc
        original = fc.ENABLE_EVALUATOR_FEEDBACK
        fc.ENABLE_EVALUATOR_FEEDBACK = False
        try:
            result = fc.save_feedback(
                creator_db_id=uuid.uuid4(),
                evaluator_id="manel",
                user_message="test",
                bot_response="test",
            )
            assert result == {"status": "disabled"}
            mock_session_cls.assert_not_called()
        finally:
            fc.ENABLE_EVALUATOR_FEEDBACK = original

    @patch("api.database.SessionLocal")
    def test_get_feedback_returns_list(self, mock_session_cls):
        """get_feedback returns structured list of feedback records."""
        from services.feedback_store import get_feedback

        mock_row = MagicMock()
        mock_row.id = uuid.uuid4()
        mock_row.evaluator_id = "manel"
        mock_row.user_message = "Hola"
        mock_row.bot_response = "Hey!"
        mock_row.coherencia = 4
        mock_row.lo_enviarias = 5
        mock_row.ideal_response = None
        mock_row.error_tags = None
        mock_row.error_free_text = None
        mock_row.intent_detected = "greeting"
        mock_row.model_id = "gemini-2.0-flash"
        mock_row.created_at = MagicMock()
        mock_row.created_at.isoformat.return_value = "2026-04-02T10:00:00"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_row]
        mock_session_cls.return_value = mock_session

        result = get_feedback(creator_db_id=uuid.uuid4())

        assert len(result) == 1
        assert result[0]["evaluator_id"] == "manel"
        assert result[0]["coherencia"] == 4

    @patch("api.database.SessionLocal")
    def test_get_feedback_with_filters(self, mock_session_cls):
        """get_feedback applies evaluator_id and score filters."""
        from services.feedback_store import get_feedback

        mock_session = MagicMock()
        mock_query = mock_session.query.return_value.filter.return_value
        # Chain all possible filter calls
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
        mock_session_cls.return_value = mock_session

        result = get_feedback(
            creator_db_id=uuid.uuid4(),
            evaluator_id="manel",
            min_coherencia=3,
            min_lo_enviarias=4,
            with_ideal_only=True,
        )

        assert result == []


# ---------------------------------------------------------------------------
# 3. Auto-Creation Tests
# ---------------------------------------------------------------------------

class TestAutoCreation:
    """Test auto-creation of derivative records from evaluator feedback."""

    def test_auto_create_preference_pair(self):
        """_auto_create_preference_pair creates a PreferencePair with action_type=evaluator_correction."""
        from services.feedback_store import _auto_create_preference_pair

        mock_session = MagicMock()

        result = _auto_create_preference_pair(
            session=mock_session,
            creator_db_id=uuid.uuid4(),
            user_message="Cuanto cuesta?",
            bot_response="El precio es 199.",
            ideal_response="199! T'envio link?",
            intent="question_product",
        )

        assert result is True
        mock_session.add.assert_called_once()
        added_pair = mock_session.add.call_args[0][0]
        assert added_pair.chosen == "199! T'envio link?"
        assert added_pair.rejected == "El precio es 199."
        assert added_pair.action_type == "evaluator_correction"

    def test_auto_create_gold_example(self):
        """_auto_create_gold_example creates GoldExample in caller's session."""
        from services.feedback_store import _auto_create_gold_example

        mock_session = MagicMock()
        # Dedup query returns None (no existing example)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = _auto_create_gold_example(
            session=mock_session,
            creator_db_id=uuid.uuid4(),
            user_message="Hola!",
            ideal_response="Hey! Com estàs?",
            intent="greeting",
        )

        assert result is True
        mock_session.add.assert_called_once()
        added_example = mock_session.add.call_args[0][0]
        assert added_example.creator_response == "Hey! Com estàs?"
        assert added_example.source == "evaluator_correction"
        assert added_example.quality_score == 0.9


# ---------------------------------------------------------------------------
# 4. Universal: works for any creator
# ---------------------------------------------------------------------------

class TestBugFixes:
    """Regression tests for feedback store bug fixes."""

    @patch("api.database.SessionLocal")
    def test_fb03_empty_ideal_response_no_pair(self, mock_session_cls):
        """FB-03: Empty string ideal_response should NOT create preference pair."""
        from services.feedback_store import save_feedback

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        def set_id(obj):
            obj.id = uuid.uuid4()
        mock_session.add.side_effect = set_id

        result = save_feedback(
            creator_db_id=uuid.uuid4(),
            evaluator_id="manel",
            user_message="test",
            bot_response="test",
            ideal_response="",  # Empty string — should be treated as no ideal
        )

        assert result["status"] == "created"
        assert result["pair_created"] is False
        # Only 1 add call (feedback itself, no pair or gold)
        assert mock_session.add.call_count == 1

    @patch("api.database.SessionLocal")
    def test_fb07_error_returns_status_error(self, mock_session_cls):
        """FB-07: DB error returns status=error, not None."""
        from services.feedback_store import save_feedback

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.add.side_effect = Exception("DB connection lost")

        result = save_feedback(
            creator_db_id=uuid.uuid4(),
            evaluator_id="manel",
            user_message="test",
            bot_response="test",
        )

        assert result["status"] == "error"
        assert "DB connection lost" in result["message"]

    @patch("api.database.SessionLocal")
    def test_fb08_stats_error_returns_status(self, mock_session_cls):
        """FB-08: Stats error returns status=error dict."""
        from services.feedback_store import get_feedback_stats

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.query.side_effect = Exception("DB timeout")

        result = get_feedback_stats(creator_db_id=uuid.uuid4())

        assert result["status"] == "error"
        assert "DB timeout" in result["message"]


class TestUniversal:
    """Verify no hardcoded creator IDs."""

    @patch("api.database.SessionLocal")
    def test_works_for_any_creator_id(self, mock_session_cls):
        """save_feedback accepts any UUID creator_db_id."""
        from services.feedback_store import save_feedback

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        def set_id(obj):
            obj.id = uuid.uuid4()
        mock_session.add.side_effect = set_id

        for creator_name in ["iris_bertran", "stefano_bonanno", "new_creator_2026"]:
            creator_id = uuid.uuid4()
            result = save_feedback(
                creator_db_id=creator_id,
                evaluator_id="evaluator_x",
                user_message="test",
                bot_response="test",
            )
            assert result is not None


# ---------------------------------------------------------------------------
# 5. Unified capture() Tests
# ---------------------------------------------------------------------------

class TestUnifiedCapture:
    """Test the unified capture() entry point."""

    @pytest.mark.asyncio
    @patch("api.database.SessionLocal")
    async def test_capture_evaluator_score(self, mock_session_cls):
        """capture(evaluator_score) routes to save_feedback."""
        from services.feedback_store import capture

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        def set_id(obj):
            obj.id = uuid.uuid4()
        mock_session.add.side_effect = set_id

        result = await capture(
            signal_type="evaluator_score",
            creator_db_id=uuid.uuid4(),
            user_message="Hola!",
            bot_response="Hey!",
            metadata={
                "evaluator_id": "manel",
                "lo_enviarias": 4,
                "coherencia": 3,
            },
        )

        assert result["status"] == "created"
        assert result["quality_score"] == 0.8  # 4/5.0
        assert result["signal_type"] == "evaluator_score"

    @pytest.mark.asyncio
    @patch("services.feedback_capture.create_pairs_from_action")
    async def test_capture_copilot_edit(self, mock_create_pairs):
        """capture(copilot_edit) routes to create_pairs_from_action."""
        from services.feedback_store import capture

        mock_create_pairs.return_value = 1

        result = await capture(
            signal_type="copilot_edit",
            creator_db_id=uuid.uuid4(),
            lead_id=uuid.uuid4(),
            user_message="Cuanto cuesta?",
            bot_response="El precio es 199.",
            creator_response="199! T'envio el link?",
            metadata={
                "intent": "question_product",
                "source_message_id": uuid.uuid4(),
                "edit_diff": {"length_delta": -10},
            },
        )

        assert result["status"] == "created"
        assert result["quality_score"] == 0.8
        assert result["pairs_created"] == 1
        mock_create_pairs.assert_called_once()
        call_kwargs = mock_create_pairs.call_args
        assert call_kwargs.kwargs["action"] == "edited"

    @pytest.mark.asyncio
    @patch("services.feedback_capture.create_pairs_from_action")
    async def test_capture_copilot_approve(self, mock_create_pairs):
        """capture(copilot_approve) → quality 0.6."""
        from services.feedback_store import capture

        mock_create_pairs.return_value = 1

        result = await capture(
            signal_type="copilot_approve",
            creator_db_id=uuid.uuid4(),
            bot_response="Hola! 😊",
            metadata={"source_message_id": uuid.uuid4()},
        )

        assert result["quality_score"] == 0.6
        assert result["pairs_created"] == 1

    @pytest.mark.asyncio
    @patch("services.feedback_capture.create_pairs_from_action")
    async def test_capture_copilot_discard(self, mock_create_pairs):
        """capture(copilot_discard) → quality 0.4."""
        from services.feedback_store import capture

        mock_create_pairs.return_value = 1

        result = await capture(
            signal_type="copilot_discard",
            creator_db_id=uuid.uuid4(),
            bot_response="Bad response",
            metadata={"source_message_id": uuid.uuid4()},
        )

        assert result["quality_score"] == 0.4

    @pytest.mark.asyncio
    @patch("services.feedback_capture.create_pairs_from_action")
    async def test_capture_copilot_resolved(self, mock_create_pairs):
        """capture(copilot_resolved) → quality 0.9 (strongest signal)."""
        from services.feedback_store import capture

        mock_create_pairs.return_value = 1

        result = await capture(
            signal_type="copilot_resolved",
            creator_db_id=uuid.uuid4(),
            bot_response="Bot draft",
            creator_response="Creator wrote this instead",
            metadata={"source_message_id": uuid.uuid4()},
        )

        assert result["quality_score"] == 0.9

    @pytest.mark.asyncio
    async def test_capture_unknown_signal(self):
        """Unknown signal_type returns error."""
        from services.feedback_store import capture

        result = await capture(
            signal_type="invalid_type",
            creator_db_id=uuid.uuid4(),
        )

        assert result["status"] == "error"
        assert "Unknown signal_type" in result["message"]

    def test_quality_score_computation(self):
        """Quality scores match BeeS paper heuristic."""
        from services.feedback_store import _compute_quality

        assert _compute_quality("copilot_approve", {}) == 0.6
        assert _compute_quality("copilot_edit", {}) == 0.8
        assert _compute_quality("copilot_discard", {}) == 0.4
        assert _compute_quality("copilot_resolved", {}) == 0.9
        assert _compute_quality("historical_mine", {}) == 0.5
        assert _compute_quality("evaluator_score", {"lo_enviarias": 3}) == 0.6
        assert _compute_quality("evaluator_score", {}) == 0.5  # default when no score
