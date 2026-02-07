"""Audit tests for core/sync_worker.py."""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Test 1: Init / Import
# ---------------------------------------------------------------------------


class TestSyncWorkerImport:
    """Verify the module imports correctly and key symbols are available."""

    def test_import_sync_worker_module(self):
        from core.sync_worker import SYNC_CONFIG, RateLimitError, SyncConfig

        # SyncConfig should have sane defaults
        cfg = SyncConfig()
        assert cfg.delay_between_calls == 3
        assert cfg.rate_limit_pause == 300
        assert cfg.max_retries == 3
        assert cfg.batch_size == 10
        assert cfg.batch_pause == 30

        # Global config should be an instance
        assert isinstance(SYNC_CONFIG, SyncConfig)

        # RateLimitError should be an Exception subclass
        assert issubclass(RateLimitError, Exception)


# ---------------------------------------------------------------------------
# Test 2: Happy Path -- add_conversations_to_queue adds new conversations
# ---------------------------------------------------------------------------


class TestAddConversationsToQueue:
    """Test that new conversations are added to the sync queue."""

    @pytest.mark.asyncio
    async def test_add_conversations_happy_path(self):
        from core.sync_worker import add_conversations_to_queue

        # Build a mock session that simulates "no existing job"
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = None
        mock_session.query.return_value = mock_query

        conversations = [
            {"id": "conv_1"},
            {"id": "conv_2"},
            {"id": "conv_3"},
        ]

        with patch("core.sync_worker.SyncQueue", create=True):
            added = await add_conversations_to_queue(mock_session, "creator_1", conversations)

        assert added == 3
        assert mock_session.add.call_count == 3
        mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: Edge Case -- conversations without an id are skipped
# ---------------------------------------------------------------------------


class TestAddConversationsEdgeCases:
    """Edge cases for add_conversations_to_queue."""

    @pytest.mark.asyncio
    async def test_skip_conversations_without_id(self):
        from core.sync_worker import add_conversations_to_queue

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = None
        mock_session.query.return_value = mock_query

        conversations = [
            {"id": "conv_1"},
            {},  # no id field
            {"id": None},  # id is None (falsy)
            {"id": "conv_4"},
        ]

        with patch("core.sync_worker.SyncQueue", create=True):
            added = await add_conversations_to_queue(mock_session, "creator_x", conversations)

        # Only conv_1 and conv_4 have valid ids
        assert added == 2


# ---------------------------------------------------------------------------
# Test 4: Error Handling -- RateLimitError and failed job recovery
# ---------------------------------------------------------------------------


class TestSyncWorkerErrorHandling:
    """Error recovery scenarios for sync worker."""

    def test_rate_limit_error_is_exception(self):
        from core.sync_worker import RateLimitError

        err = RateLimitError("Rate limit hit")
        assert isinstance(err, Exception)
        assert str(err) == "Rate limit hit"

    @pytest.mark.asyncio
    async def test_add_conversations_retries_failed_jobs(self):
        """Failed jobs with attempts < max_retries should be reset to pending."""
        from core.sync_worker import SYNC_CONFIG, add_conversations_to_queue

        mock_session = MagicMock()

        # Simulate an existing failed job with attempts below max
        existing_job = MagicMock()
        existing_job.status = "failed"
        existing_job.attempts = SYNC_CONFIG.max_retries - 1  # below threshold

        mock_session.query.return_value.filter_by.return_value.first.return_value = existing_job

        conversations = [{"id": "conv_retry"}]

        added = await add_conversations_to_queue(mock_session, "creator_retry", conversations)

        assert added == 1
        assert existing_job.status == "pending"

    @pytest.mark.asyncio
    async def test_add_conversations_skips_exhausted_failed_jobs(self):
        """Failed jobs at max retries should not be reset."""
        from core.sync_worker import SYNC_CONFIG, add_conversations_to_queue

        mock_session = MagicMock()

        existing_job = MagicMock()
        existing_job.status = "failed"
        existing_job.attempts = SYNC_CONFIG.max_retries  # at max

        mock_session.query.return_value.filter_by.return_value.first.return_value = existing_job

        conversations = [{"id": "conv_exhausted"}]

        added = await add_conversations_to_queue(mock_session, "creator_exhaust", conversations)

        assert added == 0


# ---------------------------------------------------------------------------
# Test 5: Integration Check -- SyncConfig and queue logic work together
# ---------------------------------------------------------------------------


class TestSyncWorkerIntegration:
    """Integration checks for config, queue functions, and state logic."""

    def test_sync_config_defaults_are_consistent(self):
        from core.sync_worker import SYNC_CONFIG, SyncConfig

        cfg = SyncConfig()
        # batch_pause should be longer than delay_between_calls
        assert cfg.batch_pause > cfg.delay_between_calls
        # rate_limit_pause should be substantially longer
        assert cfg.rate_limit_pause > cfg.batch_pause
        # Global config matches defaults
        assert SYNC_CONFIG.delay_between_calls == cfg.delay_between_calls
        assert SYNC_CONFIG.max_retries == cfg.max_retries

    @pytest.mark.asyncio
    async def test_get_or_create_sync_state_creates_new(self):
        """When no state exists, a new SyncState is created and committed."""
        from core.sync_worker import get_or_create_sync_state

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        await get_or_create_sync_state(mock_session, "new_creator")

        # A new state should have been added and committed
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        # The returned state should have the correct creator_id
        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.creator_id == "new_creator"

    @pytest.mark.asyncio
    async def test_get_or_create_sync_state_returns_existing(self):
        """When state already exists, it is returned without creating a new one."""
        from core.sync_worker import get_or_create_sync_state

        mock_session = MagicMock()
        existing_state = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = existing_state

        with patch("core.sync_worker.SyncState", MagicMock(), create=True):
            state = await get_or_create_sync_state(mock_session, "existing_creator")

        assert state is existing_state
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_next_pending_job_filters_by_creator(self):
        """get_next_pending_job filters by creator_id when provided."""
        from core.sync_worker import get_next_pending_job

        mock_session = MagicMock()
        mock_job = MagicMock()
        mock_query = MagicMock()
        mock_query.filter_by.return_value = mock_query
        mock_query.order_by.return_value.first.return_value = mock_job
        mock_session.query.return_value = mock_query

        with patch("core.sync_worker.SyncQueue", MagicMock(), create=True):
            job = await get_next_pending_job(mock_session, "specific_creator")

        assert job is mock_job
        # filter_by called twice: once for status, once for creator_id
        assert mock_query.filter_by.call_count == 2
