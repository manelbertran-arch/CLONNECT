"""Tests for PostContext repository.

TDD: Tests written FIRST before implementation.
Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from models.post_context import PostContext


class TestPostContextRepository:
    """Test suite for PostContext repository functions."""

    def test_get_post_context_found(self):
        """Should return PostContext when exists in DB."""
        from services.post_context_repository import get_post_context

        mock_row = MagicMock()
        mock_row.creator_id = "stefan"
        mock_row.active_promotion = "Curso 20% dto"
        mock_row.promotion_deadline = None
        mock_row.promotion_urgency = "48h"
        mock_row.recent_topics = ["meditación"]
        mock_row.recent_products = ["Curso Meditación"]
        mock_row.availability_hint = None
        mock_row.context_instructions = "Menciona el curso"
        mock_row.posts_analyzed = 5
        mock_row.analyzed_at = datetime.now(timezone.utc)
        mock_row.expires_at = datetime.now(timezone.utc) + timedelta(hours=6)
        mock_row.source_posts = ["post1", "post2"]

        with patch("services.post_context_repository.get_session") as mock_session:
            session = MagicMock()
            mock_session.return_value = session
            session.query.return_value.filter_by.return_value.first.return_value = mock_row

            result = get_post_context("stefan")

            assert result is not None
            assert result["creator_id"] == "stefan"
            assert result["active_promotion"] == "Curso 20% dto"

    def test_get_post_context_not_found(self):
        """Should return None when no context exists."""
        from services.post_context_repository import get_post_context

        with patch("services.post_context_repository.get_session") as mock_session:
            session = MagicMock()
            mock_session.return_value = session
            session.query.return_value.filter_by.return_value.first.return_value = None

            result = get_post_context("unknown_creator")

            assert result is None

    def test_create_post_context(self):
        """Should create new PostContext in DB."""
        from services.post_context_repository import create_post_context

        context_data = {
            "creator_id": "stefan",
            "active_promotion": "Flash Sale",
            "context_instructions": "Menciona la promo",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=6),
            "posts_analyzed": 3,
        }

        with patch("services.post_context_repository.get_session") as mock_session:
            session = MagicMock()
            mock_session.return_value = session

            result = create_post_context(context_data)

            assert result is True
            session.add.assert_called_once()
            session.commit.assert_called_once()

    def test_update_post_context(self):
        """Should update existing PostContext."""
        from services.post_context_repository import update_post_context

        mock_row = MagicMock()

        with patch("services.post_context_repository.get_session") as mock_session:
            session = MagicMock()
            mock_session.return_value = session
            session.query.return_value.filter_by.return_value.first.return_value = mock_row

            update_data = {
                "active_promotion": "New Promo",
                "promotion_urgency": "24h",
            }
            result = update_post_context("stefan", update_data)

            assert result is True
            session.commit.assert_called_once()

    def test_delete_post_context(self):
        """Should delete PostContext from DB."""
        from services.post_context_repository import delete_post_context

        mock_row = MagicMock()

        with patch("services.post_context_repository.get_session") as mock_session:
            session = MagicMock()
            mock_session.return_value = session
            session.query.return_value.filter_by.return_value.first.return_value = mock_row

            result = delete_post_context("stefan")

            assert result is True
            session.delete.assert_called_once_with(mock_row)
            session.commit.assert_called_once()

    def test_get_or_create_creates_new(self):
        """Should create new context when none exists."""
        from services.post_context_repository import get_or_create_post_context

        with patch("services.post_context_repository.get_session") as mock_session:
            session = MagicMock()
            mock_session.return_value = session
            # First query returns None (not found)
            session.query.return_value.filter_by.return_value.first.return_value = None

            context_data = {
                "creator_id": "stefan",
                "context_instructions": "Default context",
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=6),
            }
            result = get_or_create_post_context("stefan", context_data)

            assert result is not None
            session.add.assert_called_once()

    def test_get_expired_contexts(self):
        """Should return list of expired contexts."""
        from services.post_context_repository import get_expired_contexts

        mock_row1 = MagicMock()
        mock_row1.creator_id = "creator1"
        mock_row2 = MagicMock()
        mock_row2.creator_id = "creator2"

        with patch("services.post_context_repository.get_session") as mock_session:
            session = MagicMock()
            mock_session.return_value = session
            session.query.return_value.filter.return_value.all.return_value = [
                mock_row1,
                mock_row2,
            ]

            result = get_expired_contexts()

            assert len(result) == 2
            assert result[0]["creator_id"] == "creator1"

    def test_context_to_model_object(self):
        """Should convert PostContext to model object for saving."""
        from services.post_context_repository import _context_to_model

        ctx = PostContext(
            creator_id="stefan",
            active_promotion="Promo",
            context_instructions="Instructions",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )

        with patch("api.models.PostContextModel") as MockModel:
            MockModel.return_value = MagicMock()
            result = _context_to_model(ctx)
            assert MockModel.called
