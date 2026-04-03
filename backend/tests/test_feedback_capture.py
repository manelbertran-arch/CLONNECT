"""
Tests for System A: FeedbackCapture (services/feedback_capture.py)
8 tests covering signal routing, dedup, quality scoring, and backward compat.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCaptureEvaluatorScore:
    """capture(evaluator_score) routes to save_feedback and returns correct fields."""

    @pytest.mark.asyncio
    @patch("api.database.SessionLocal")
    async def test_capture_evaluator_score(self, mock_session_cls):
        from services.feedback_capture import capture

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.add.side_effect = lambda obj: setattr(obj, "id", uuid.uuid4())

        result = await capture(
            signal_type="evaluator_score",
            creator_db_id=uuid.uuid4(),
            user_message="Hola!",
            bot_response="Hey!",
            metadata={"evaluator_id": "manel", "lo_enviarias": 5, "coherencia": 4},
        )

        assert result["status"] == "created"
        assert result["quality_score"] == 1.0  # 5/5.0
        assert result["signal_type"] == "evaluator_score"
        assert "feedback_id" in result


class TestCaptureCopilotActions:
    """capture(copilot_*) creates preference pairs with correct action mapping."""

    @pytest.mark.asyncio
    @patch("services.feedback_capture.create_pairs_from_action")
    async def test_capture_copilot_edit(self, mock_create_pairs):
        from services.feedback_capture import capture

        mock_create_pairs.return_value = 1

        result = await capture(
            signal_type="copilot_edit",
            creator_db_id=uuid.uuid4(),
            lead_id=uuid.uuid4(),
            user_message="Cuanto cuesta?",
            bot_response="El precio es 199.",
            creator_response="199! T'envio el link?",
            metadata={"intent": "question_product"},
        )

        assert result["status"] == "created"
        assert result["quality_score"] == 0.8
        assert result["pairs_created"] == 1
        mock_create_pairs.assert_called_once()
        assert mock_create_pairs.call_args.kwargs["action"] == "edited"

    @pytest.mark.asyncio
    @patch("services.feedback_capture.create_pairs_from_action")
    async def test_capture_copilot_approve(self, mock_create_pairs):
        from services.feedback_capture import capture

        mock_create_pairs.return_value = 1
        result = await capture(
            signal_type="copilot_approve",
            creator_db_id=uuid.uuid4(),
            bot_response="Hola! 😊",
        )
        assert result["quality_score"] == 0.6
        assert mock_create_pairs.call_args.kwargs["action"] == "approved"

    @pytest.mark.asyncio
    @patch("services.feedback_capture.create_pairs_from_action")
    async def test_capture_copilot_discard(self, mock_create_pairs):
        from services.feedback_capture import capture

        mock_create_pairs.return_value = 0
        result = await capture(
            signal_type="copilot_discard",
            creator_db_id=uuid.uuid4(),
            bot_response="Bad",
        )
        assert result["quality_score"] == 0.4
        assert mock_create_pairs.call_args.kwargs["action"] == "discarded"

    @pytest.mark.asyncio
    @patch("services.feedback_capture.create_pairs_from_action")
    async def test_capture_copilot_resolved(self, mock_create_pairs):
        from services.feedback_capture import capture

        mock_create_pairs.return_value = 1
        result = await capture(
            signal_type="copilot_resolved",
            creator_db_id=uuid.uuid4(),
            bot_response="Draft",
            creator_response="Creator wrote this",
        )
        assert result["quality_score"] == 0.9
        assert mock_create_pairs.call_args.kwargs["action"] == "resolved_externally"


class TestCaptureBestOfN:
    """capture(best_of_n) creates N-1 pairs from ranked candidates."""

    @pytest.mark.asyncio
    @patch("services.feedback_capture.create_pairs_from_action")
    async def test_capture_best_of_n_creates_pairs(self, mock_create_pairs):
        from services.feedback_capture import capture

        mock_create_pairs.return_value = 2  # 3 candidates → 2 pairs

        candidates = [
            {"rank": 1, "content": "Best response", "confidence": 0.9},
            {"rank": 2, "content": "OK response", "confidence": 0.7},
            {"rank": 3, "content": "Worst response", "confidence": 0.5},
        ]

        result = await capture(
            signal_type="best_of_n",
            creator_db_id=uuid.uuid4(),
            bot_response="Best response",
            user_message="Hola!",
            metadata={"best_of_n_candidates": candidates},
        )

        assert result["status"] == "created"
        assert result["quality_score"] == 0.7
        assert result["pairs_created"] == 2
        mock_create_pairs.assert_called_once()


class TestCaptureHistoricalMine:
    """capture(historical_mine) calls mine_historical_pairs with correct args."""

    @pytest.mark.asyncio
    @patch("services.feedback_capture.mine_historical_pairs")
    async def test_capture_historical_mine(self, mock_mine):
        from services.feedback_capture import capture

        mock_mine.return_value = 42

        creator_id = uuid.uuid4()
        result = await capture(
            signal_type="historical_mine",
            creator_db_id=creator_id,
            metadata={"creator_slug": "iris_bertran", "limit": 100},
        )

        assert result["status"] == "created"
        assert result["quality_score"] == 0.5
        assert result["pairs_created"] == 42
        mock_mine.assert_called_once_with("iris_bertran", creator_id, limit=100)


class TestDedupEvaluatorFeedback:
    """Duplicate source_message_id → updates existing record, no new row."""

    @patch("api.database.SessionLocal")
    def test_dedup_evaluator_feedback(self, mock_session_cls):
        from services.feedback_capture import save_feedback

        existing = MagicMock()
        existing.id = uuid.uuid4()
        existing.coherencia = 2
        existing.lo_enviarias = 2

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = existing

        source_id = uuid.uuid4()
        result = save_feedback(
            creator_db_id=uuid.uuid4(),
            evaluator_id="manel",
            user_message="test",
            bot_response="test",
            coherencia=4,
            lo_enviarias=4,
            source_message_id=source_id,
        )

        assert result["status"] == "updated"
        assert result["feedback_id"] == str(existing.id)
        assert result["pair_created"] is False
        # No new row added
        mock_session.add.assert_not_called()


class TestQualityScoring:
    """All 8 signal types produce correct quality scores."""

    def test_all_signal_quality_scores(self):
        from services.feedback_capture import _compute_quality

        assert _compute_quality("copilot_approve", {}) == 0.6
        assert _compute_quality("copilot_edit", {}) == 0.8
        assert _compute_quality("copilot_discard", {}) == 0.4
        assert _compute_quality("copilot_manual", {}) == 0.8
        assert _compute_quality("copilot_resolved", {}) == 0.9
        assert _compute_quality("historical_mine", {}) == 0.5
        assert _compute_quality("best_of_n", {}) == 0.7
        # evaluator_score: dynamic
        assert _compute_quality("evaluator_score", {"lo_enviarias": 4}) == 0.8
        assert _compute_quality("evaluator_score", {"lo_enviarias": 5}) == 1.0
        assert _compute_quality("evaluator_score", {}) == 0.5  # default


class TestAutoCreateGoldFromEvaluator:
    """lo_enviarias >= 4 + ideal_response → auto-creates gold example."""

    @patch("api.database.SessionLocal")
    def test_auto_create_gold_from_evaluator(self, mock_session_cls):
        from services.feedback_capture import save_feedback

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None  # no dedup hit
        mock_session.add.side_effect = lambda obj: setattr(obj, "id", uuid.uuid4())

        result = save_feedback(
            creator_db_id=uuid.uuid4(),
            evaluator_id="manel",
            user_message="Que fas?",
            bot_response="Aqui estic!",
            coherencia=4,
            lo_enviarias=4,
            ideal_response="Que? On?",
        )

        assert result["status"] == "created"
        assert result["pair_created"] is True
        assert result["gold_created"] is True


class TestBackwardCompatImports:
    """from services.feedback_store import capture still works via re-export shim."""

    def test_backward_compat_feedback_store(self):
        from services.feedback_store import (
            ENABLE_EVALUATOR_FEEDBACK,
            QUALITY_SCORES,
            _compute_quality,
            capture,
            get_feedback,
            get_feedback_stats,
            save_feedback,
        )

        assert callable(capture)
        assert callable(save_feedback)
        assert callable(get_feedback)
        assert callable(get_feedback_stats)
        assert callable(_compute_quality)
        assert isinstance(QUALITY_SCORES, dict)
        assert isinstance(ENABLE_EVALUATOR_FEEDBACK, bool)

    def test_backward_compat_preference_pairs_service(self):
        from services.preference_pairs_service import (
            ENABLE_PREFERENCE_PAIRS,
            create_pairs_from_action,
            curate_pairs,
            get_pairs_for_export,
            mark_exported,
            mine_historical_pairs,
        )

        assert callable(create_pairs_from_action)
        assert callable(get_pairs_for_export)
        assert callable(mark_exported)
        assert callable(mine_historical_pairs)
        assert callable(curate_pairs)
        assert isinstance(ENABLE_PREFERENCE_PAIRS, bool)
