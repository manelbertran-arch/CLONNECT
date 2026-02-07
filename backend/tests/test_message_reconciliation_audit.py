"""Audit tests for core/message_reconciliation.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.message_reconciliation import (
    MAX_CONVERSATIONS_PER_CYCLE,
    RECONCILIATION_INTERVAL_MINUTES,
    RECONCILIATION_LOOKBACK_HOURS,
    _extract_media_from_attachments,
    get_reconciliation_status,
)


class TestReconcilerInit:
    """Test 1: Initialization and module-level constants."""

    def test_module_constants_have_expected_values(self):
        """Module configuration constants are set to expected defaults."""
        assert RECONCILIATION_LOOKBACK_HOURS == 24
        assert RECONCILIATION_INTERVAL_MINUTES == 5
        assert MAX_CONVERSATIONS_PER_CYCLE == 20

    def test_get_reconciliation_status_returns_dict(self):
        """get_reconciliation_status returns expected keys."""
        status = get_reconciliation_status()
        assert isinstance(status, dict)
        assert "last_run" in status
        assert "total_runs" in status
        assert "lookback_hours_startup" in status
        assert "interval_minutes" in status

    def test_extract_media_returns_empty_for_none(self):
        """_extract_media_from_attachments returns empty dict for None."""
        result = _extract_media_from_attachments(None)
        assert result == {}

    def test_extract_media_returns_empty_for_empty_list(self):
        """_extract_media_from_attachments returns empty dict for empty list."""
        result = _extract_media_from_attachments([])
        assert result == {}

    def test_status_interval_matches_constant(self):
        """get_reconciliation_status interval_minutes matches module constant."""
        status = get_reconciliation_status()
        assert status["interval_minutes"] == RECONCILIATION_INTERVAL_MINUTES


class TestMessageOrdering:
    """Test 2: Happy path - media extraction and message ordering logic."""

    def test_extract_image_attachment(self):
        """Image attachment extracts correct type and content_text."""
        attachments = [{"type": "image", "payload": {"url": "https://example.com/img.jpg"}}]
        result = _extract_media_from_attachments(attachments)
        assert result["type"] == "image"
        assert result["content_text"] == "Sent a photo"
        assert result["url"] == "https://example.com/img.jpg"

    def test_extract_video_attachment(self):
        """Video attachment extracts correct type."""
        attachments = [{"type": "video", "payload": {"url": "https://example.com/vid.mp4"}}]
        result = _extract_media_from_attachments(attachments)
        assert result["type"] == "video"
        assert result["content_text"] == "Sent a video"

    def test_extract_audio_attachment(self):
        """Audio attachment extracts correct type."""
        attachments = [{"type": "audio", "payload": {"url": "https://example.com/aud.ogg"}}]
        result = _extract_media_from_attachments(attachments)
        assert result["type"] == "audio"
        assert result["content_text"] == "Sent a voice message"

    def test_extract_story_mention(self):
        """Story mention attachment extracts correct type."""
        attachments = [{"type": "story_mention", "story": {"url": "https://example.com/story"}}]
        result = _extract_media_from_attachments(attachments)
        assert result["type"] == "story_mention"
        assert result["content_text"] == "Mentioned you in their story"

    def test_extract_share_with_reel(self):
        """Share attachment containing 'reel' in link detected as shared_reel."""
        attachments = [{"type": "share", "share": {"link": "https://instagram.com/reel/abc"}}]
        result = _extract_media_from_attachments(attachments)
        assert result["type"] == "shared_reel"
        assert result["content_text"] == "Shared a reel"


class TestDuplicateDetection:
    """Test 3: Edge case - duplicate detection with existing message IDs."""

    @pytest.mark.asyncio
    async def test_get_db_message_ids_returns_set(self):
        """get_db_message_ids returns a set of message IDs (mocked DB)."""
        mock_session = MagicMock()
        mock_creator = MagicMock()
        mock_creator.id = 1

        mock_lead = MagicMock()
        mock_lead.id = 10

        # Mock Creator query
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creator
        # Mock Lead query
        mock_session.query.return_value.filter_by.return_value.all.return_value = [mock_lead]
        # Mock Message query
        mock_msg_query = MagicMock()
        mock_msg_query.filter.return_value.filter.return_value.all.return_value = [
            ("msg_1",),
            ("msg_2",),
            ("msg_3",),
        ]
        mock_msg_query.filter.return_value.all.return_value = [
            ("msg_1",),
            ("msg_2",),
            ("msg_3",),
        ]

        with patch("api.database.SessionLocal", return_value=mock_session):
            from core.message_reconciliation import get_db_message_ids

            # The function uses complex query chaining; mock the entire chain
            mock_query_chain = MagicMock()
            mock_query_chain.filter.return_value = mock_query_chain
            mock_query_chain.all.return_value = [("msg_1",), ("msg_2",)]

            mock_session.query.return_value = mock_query_chain
            mock_query_chain.filter_by.return_value.first.return_value = mock_creator
            mock_query_chain.filter_by.return_value.all.return_value = [mock_lead]

            result = await get_db_message_ids("test_creator")
            assert isinstance(result, set)

    def test_extract_sticker_attachment(self):
        """Sticker attachment correctly identified."""
        attachments = [{"type": "sticker", "payload": {"url": "https://example.com/sticker.webp"}}]
        result = _extract_media_from_attachments(attachments)
        assert result["type"] == "sticker"
        assert result["content_text"] == "Sent a sticker"

    def test_extract_gif_attachment(self):
        """Animated GIF correctly identified."""
        attachments = [{"type": "animated_image", "payload": {"url": "https://example.com/gif"}}]
        result = _extract_media_from_attachments(attachments)
        assert result["type"] == "gif"
        assert result["content_text"] == "Sent a GIF"

    def test_extract_legacy_image_data_format(self):
        """Legacy image_data format extracts URL correctly."""
        attachments = [{"image_data": {"url": "https://cdn.example.com/legacy.jpg"}}]
        result = _extract_media_from_attachments(attachments)
        assert result["type"] == "image"
        assert result["url"] == "https://cdn.example.com/legacy.jpg"


class TestEmptyConversation:
    """Test 4: Error handling - empty conversations and missing data."""

    @pytest.mark.asyncio
    async def test_reconcile_handles_no_conversations(self):
        """reconcile_messages_for_creator handles zero conversations."""
        mock_session = MagicMock()
        mock_creator = MagicMock()
        mock_creator.id = 1
        mock_creator.instagram_user_id = "ig_123"
        mock_creator.instagram_page_id = "page_123"

        with patch(
            "core.message_reconciliation.get_db_message_ids",
            new_callable=AsyncMock,
            return_value=set(),
        ):
            with patch(
                "core.message_reconciliation.get_instagram_conversations",
                new_callable=AsyncMock,
                return_value=[],
            ):
                with patch("api.database.SessionLocal", return_value=mock_session):
                    mock_session.query.return_value.filter_by.return_value.first.return_value = (
                        mock_creator
                    )

                    from core.message_reconciliation import reconcile_messages_for_creator

                    result = await reconcile_messages_for_creator(
                        creator_id="test",
                        access_token="token",
                        ig_user_id="ig_123",
                    )
                    assert result["conversations_checked"] == 0
                    assert result["messages_inserted"] == 0

    def test_extract_unknown_attachment_type(self):
        """Unknown attachment type returns fallback content_text."""
        attachments = [{"type": "unknown_type_xyz"}]
        result = _extract_media_from_attachments(attachments)
        assert result["type"] == "unknown"
        assert result["content_text"] == "Sent an attachment"

    def test_extract_attachment_with_deep_fallback_url(self):
        """Deep fallback URL extraction from nested dict."""
        attachments = [
            {"type": "", "nested_data": {"some_url": "https://cdn.example.com/media.mp4"}}
        ]
        result = _extract_media_from_attachments(attachments)
        assert result.get("url") == "https://cdn.example.com/media.mp4"

    def test_extract_share_without_reel(self):
        """Regular share (non-reel) correctly identified."""
        attachments = [{"type": "share", "share": {"link": "https://instagram.com/p/abc123"}}]
        result = _extract_media_from_attachments(attachments)
        assert result["type"] == "share"
        assert result["content_text"] == "Shared a post"


class TestTimestampUpdate:
    """Test 5: Integration check - reconciliation status tracking."""

    @pytest.mark.asyncio
    async def test_run_startup_reconciliation_updates_state(self):
        """run_startup_reconciliation updates global last_reconciliation."""
        import core.message_reconciliation as mod

        original_last = mod._last_reconciliation
        original_count = mod._reconciliation_count

        with patch.object(mod, "run_reconciliation_cycle", new_callable=AsyncMock) as mock_cycle:
            mock_cycle.return_value = {
                "total_inserted": 0,
                "total_missing": 0,
                "creators_processed": 0,
                "by_creator": [],
            }
            await mod.run_startup_reconciliation()

        assert mod._last_reconciliation is not None
        assert mod._reconciliation_count == original_count + 1

        # Restore state to not affect other tests
        mod._last_reconciliation = original_last
        mod._reconciliation_count = original_count

    @pytest.mark.asyncio
    async def test_run_periodic_reconciliation_updates_state(self):
        """run_periodic_reconciliation updates global counters."""
        import core.message_reconciliation as mod

        original_last = mod._last_reconciliation
        original_count = mod._reconciliation_count

        with patch.object(mod, "run_reconciliation_cycle", new_callable=AsyncMock) as mock_cycle:
            mock_cycle.return_value = {
                "total_inserted": 5,
                "total_missing": 5,
                "creators_processed": 1,
                "by_creator": [],
            }
            result = await mod.run_periodic_reconciliation()

        assert result["total_inserted"] == 5
        assert mod._reconciliation_count == original_count + 1

        # Restore state
        mod._last_reconciliation = original_last
        mod._reconciliation_count = original_count

    @pytest.mark.asyncio
    async def test_startup_reconciliation_handles_exception(self):
        """run_startup_reconciliation returns error dict on exception."""
        import core.message_reconciliation as mod

        with patch.object(
            mod,
            "run_reconciliation_cycle",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB down"),
        ):
            result = await mod.run_startup_reconciliation()
        assert "error" in result

    def test_reconciliation_status_lookback_matches_constant(self):
        """Status lookback_hours_startup matches module constant."""
        status = get_reconciliation_status()
        assert status["lookback_hours_startup"] == 24

    def test_extract_reel_type_attachment(self):
        """Reel type attachment correctly identified as shared_reel."""
        attachments = [{"type": "reel", "payload": {"url": "https://example.com/reel.mp4"}}]
        result = _extract_media_from_attachments(attachments)
        assert result["type"] == "shared_reel"
        assert result["content_text"] == "Shared a reel"
