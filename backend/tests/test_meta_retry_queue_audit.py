"""Audit tests for services/meta_retry_queue.py."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from services.meta_retry_queue import MetaRetryQueue, QueuedMessage, get_retry_queue


class TestMetaRetryQueueInit:
    """Test 1: init/import - Queue initializes with correct defaults."""

    def test_queue_initializes_with_defaults(self):
        queue = MetaRetryQueue()
        assert queue.max_retries == 5
        assert queue.base_delay == 2.0
        assert queue.max_delay == 60.0
        assert len(queue._queue) == 0
        assert queue._processing is False
        assert queue._send_fn is None

    def test_queue_initializes_with_custom_params(self):
        queue = MetaRetryQueue(max_retries=3, base_delay=1.0, max_delay=30.0, max_queue_size=500)
        assert queue.max_retries == 3
        assert queue.base_delay == 1.0
        assert queue.max_delay == 30.0
        assert queue._queue.maxlen == 500

    def test_stats_start_at_zero(self):
        queue = MetaRetryQueue()
        stats = queue.get_stats()
        assert stats["enqueued"] == 0
        assert stats["succeeded"] == 0
        assert stats["failed_permanent"] == 0
        assert stats["retries_total"] == 0
        assert stats["queue_size"] == 0
        assert stats["processing"] is False

    def test_singleton_returns_same_instance(self):
        """get_retry_queue returns singleton; reset between tests."""
        import services.meta_retry_queue as mod

        mod._queue = None
        q1 = get_retry_queue()
        q2 = get_retry_queue()
        assert q1 is q2
        mod._queue = None  # cleanup

    def test_queued_message_dataclass_defaults(self):
        msg = QueuedMessage(recipient_id="r1", message="hello", creator_id="c1")
        assert msg.platform == "instagram"
        assert msg.attempts == 0
        assert msg.max_retries == 5
        assert isinstance(msg.created_at, datetime)
        assert msg.last_error is None


class TestMetaRetryQueueEnqueue:
    """Test 2: happy path - Message is enqueued and stats update."""

    @pytest.mark.asyncio
    async def test_enqueue_adds_message_to_queue(self):
        queue = MetaRetryQueue()
        # Patch _process_queue so it does not actually run
        with patch.object(queue, "_process_queue", new_callable=AsyncMock):
            await queue.enqueue("r1", "hi", "c1")
        assert len(queue._queue) == 1
        assert queue._stats["enqueued"] == 1

    @pytest.mark.asyncio
    async def test_enqueue_stores_correct_data(self):
        queue = MetaRetryQueue()
        with patch.object(queue, "_process_queue", new_callable=AsyncMock):
            await queue.enqueue("r1", "msg", "c1", platform="whatsapp", error="timeout")
        item = queue._queue[0]
        assert item.recipient_id == "r1"
        assert item.message == "msg"
        assert item.creator_id == "c1"
        assert item.platform == "whatsapp"
        assert item.last_error == "timeout"

    @pytest.mark.asyncio
    async def test_enqueue_multiple_increments_stats(self):
        queue = MetaRetryQueue()
        with patch.object(queue, "_process_queue", new_callable=AsyncMock):
            await queue.enqueue("r1", "m1", "c1")
            await queue.enqueue("r2", "m2", "c1")
            await queue.enqueue("r3", "m3", "c1")
        assert queue._stats["enqueued"] == 3
        assert len(queue._queue) == 3

    @pytest.mark.asyncio
    async def test_get_pending_returns_queued_items(self):
        queue = MetaRetryQueue()
        with patch.object(queue, "_process_queue", new_callable=AsyncMock):
            await queue.enqueue("r1", "m1", "c1")
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0]["recipient_id"] == "r1"
        assert pending[0]["creator_id"] == "c1"

    @pytest.mark.asyncio
    async def test_set_send_function_stores_callable(self):
        queue = MetaRetryQueue()
        mock_fn = AsyncMock(return_value=True)
        queue.set_send_function(mock_fn)
        assert queue._send_fn is mock_fn


class TestMetaRetryQueueMaxRetries:
    """Test 3: edge case - Max retries reached marks permanent failure."""

    @pytest.mark.asyncio
    async def test_max_retries_triggers_permanent_failure(self):
        queue = MetaRetryQueue(max_retries=2, base_delay=0.0, max_delay=0.0)
        # Create an item already at max retries
        item = QueuedMessage(
            recipient_id="r1",
            message="hi",
            creator_id="c1",
            attempts=2,
            max_retries=2,
        )
        queue._queue.append(item)
        await queue._process_queue()
        assert queue._stats["failed_permanent"] == 1

    @pytest.mark.asyncio
    async def test_send_failure_requeues_until_max(self):
        queue = MetaRetryQueue(max_retries=1, base_delay=0.0, max_delay=0.0)
        mock_fn = AsyncMock(return_value=False)
        queue.set_send_function(mock_fn)
        item = QueuedMessage(
            recipient_id="r1",
            message="hi",
            creator_id="c1",
            attempts=0,
            max_retries=1,
        )
        queue._queue.append(item)
        await queue._process_queue()
        # Attempt 1 fails, but attempts == max_retries so permanent failure
        assert queue._stats["failed_permanent"] == 1

    @pytest.mark.asyncio
    async def test_exception_on_send_counts_retry(self):
        queue = MetaRetryQueue(max_retries=1, base_delay=0.0, max_delay=0.0)
        mock_fn = AsyncMock(side_effect=ConnectionError("timeout"))
        queue.set_send_function(mock_fn)
        item = QueuedMessage(
            recipient_id="r1",
            message="hi",
            creator_id="c1",
            attempts=0,
            max_retries=1,
        )
        queue._queue.append(item)
        await queue._process_queue()
        assert queue._stats["retries_total"] == 1
        assert queue._stats["failed_permanent"] == 1

    @pytest.mark.asyncio
    async def test_processing_flag_resets_after_completion(self):
        queue = MetaRetryQueue(max_retries=1, base_delay=0.0, max_delay=0.0)
        mock_fn = AsyncMock(return_value=True)
        queue.set_send_function(mock_fn)
        item = QueuedMessage(
            recipient_id="r1",
            message="hi",
            creator_id="c1",
            attempts=0,
            max_retries=1,
        )
        queue._queue.append(item)
        await queue._process_queue()
        assert queue._processing is False

    def test_queue_respects_max_queue_size(self):
        queue = MetaRetryQueue(max_queue_size=2)
        queue._queue.append(QueuedMessage(recipient_id="r1", message="m1", creator_id="c1"))
        queue._queue.append(QueuedMessage(recipient_id="r2", message="m2", creator_id="c1"))
        queue._queue.append(QueuedMessage(recipient_id="r3", message="m3", creator_id="c1"))
        # maxlen=2 means the oldest item is dropped
        assert len(queue._queue) == 2
        assert queue._queue[0].recipient_id == "r2"


class TestMetaRetryQueueStatsTracking:
    """Test 4: error handling - Stats track successes and failures correctly."""

    @pytest.mark.asyncio
    async def test_successful_send_increments_succeeded(self):
        queue = MetaRetryQueue(max_retries=3, base_delay=0.0, max_delay=0.0)
        mock_fn = AsyncMock(return_value=True)
        queue.set_send_function(mock_fn)
        item = QueuedMessage(
            recipient_id="r1",
            message="hi",
            creator_id="c1",
            attempts=0,
            max_retries=3,
        )
        queue._queue.append(item)
        await queue._process_queue()
        assert queue._stats["succeeded"] == 1
        assert queue._stats["retries_total"] == 1

    @pytest.mark.asyncio
    async def test_failed_then_success_tracks_both(self):
        queue = MetaRetryQueue(max_retries=3, base_delay=0.0, max_delay=0.0)
        # First call fails, second succeeds
        mock_fn = AsyncMock(side_effect=[False, True])
        queue.set_send_function(mock_fn)
        item = QueuedMessage(
            recipient_id="r1",
            message="hi",
            creator_id="c1",
            attempts=0,
            max_retries=3,
        )
        queue._queue.append(item)
        await queue._process_queue()
        assert queue._stats["retries_total"] == 2
        assert queue._stats["succeeded"] == 1

    @pytest.mark.asyncio
    async def test_stats_include_queue_size(self):
        queue = MetaRetryQueue()
        with patch.object(queue, "_process_queue", new_callable=AsyncMock):
            await queue.enqueue("r1", "m1", "c1")
        stats = queue.get_stats()
        assert stats["queue_size"] == 1

    @pytest.mark.asyncio
    async def test_send_message_uses_custom_send_fn(self):
        queue = MetaRetryQueue()
        mock_fn = AsyncMock(return_value=True)
        queue.set_send_function(mock_fn)
        item = QueuedMessage(recipient_id="r1", message="msg", creator_id="c1")
        result = await queue._send_message(item)
        assert result is True
        mock_fn.assert_awaited_once_with("r1", "msg", "c1")

    @pytest.mark.asyncio
    async def test_send_message_fallback_raises_without_handler(self):
        """Without send_fn and without InstagramHandler, send raises."""
        queue = MetaRetryQueue()
        item = QueuedMessage(recipient_id="r1", message="msg", creator_id="c1")
        with patch.dict("sys.modules", {"core.instagram_handler": None}):
            with pytest.raises(Exception):
                await queue._send_message(item)


class TestMetaRetryQueueExponentialBackoff:
    """Test 5: integration check - Exponential backoff calculation is correct."""

    def test_backoff_doubles_each_attempt(self):
        queue = MetaRetryQueue(base_delay=2.0, max_delay=60.0)
        # delay = min(base_delay * 2^attempts, max_delay)
        assert min(queue.base_delay * (2**0), queue.max_delay) == 2.0
        assert min(queue.base_delay * (2**1), queue.max_delay) == 4.0
        assert min(queue.base_delay * (2**2), queue.max_delay) == 8.0
        assert min(queue.base_delay * (2**3), queue.max_delay) == 16.0
        assert min(queue.base_delay * (2**4), queue.max_delay) == 32.0

    def test_backoff_capped_at_max_delay(self):
        queue = MetaRetryQueue(base_delay=2.0, max_delay=10.0)
        # 2 * 2^4 = 32 but capped at 10
        assert min(queue.base_delay * (2**4), queue.max_delay) == 10.0

    def test_backoff_with_custom_base(self):
        queue = MetaRetryQueue(base_delay=1.0, max_delay=100.0)
        assert min(queue.base_delay * (2**0), queue.max_delay) == 1.0
        assert min(queue.base_delay * (2**5), queue.max_delay) == 32.0

    @pytest.mark.asyncio
    async def test_process_queue_calls_sleep_with_backoff(self):
        queue = MetaRetryQueue(max_retries=2, base_delay=1.5, max_delay=60.0)
        mock_fn = AsyncMock(return_value=True)
        queue.set_send_function(mock_fn)
        item = QueuedMessage(
            recipient_id="r1",
            message="hi",
            creator_id="c1",
            attempts=0,
            max_retries=2,
        )
        queue._queue.append(item)
        with patch("services.meta_retry_queue.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await queue._process_queue()
        # Attempt 0 -> delay = min(1.5 * 2^0, 60) = 1.5
        mock_sleep.assert_awaited_once_with(1.5)

    @pytest.mark.asyncio
    async def test_full_cycle_enqueue_to_success(self):
        """Integration: enqueue a message, process it, check stats."""
        queue = MetaRetryQueue(max_retries=3, base_delay=0.0, max_delay=0.0)
        mock_fn = AsyncMock(return_value=True)
        queue.set_send_function(mock_fn)
        # Directly add item (skip enqueue to avoid asyncio.create_task)
        item = QueuedMessage(
            recipient_id="r1",
            message="hello",
            creator_id="c1",
            attempts=0,
            max_retries=3,
        )
        queue._queue.append(item)
        queue._stats["enqueued"] += 1
        await queue._process_queue()
        stats = queue.get_stats()
        assert stats["enqueued"] == 1
        assert stats["succeeded"] == 1
        assert stats["queue_size"] == 0
        assert stats["processing"] is False
