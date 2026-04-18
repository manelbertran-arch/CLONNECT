"""W8-T1-BUG4: Debounce race condition.

If the creator replies manually while the debounce is sleeping (e.g. at
T+12s of a 15s debounce), the regeneration must NOT overwrite the pending
suggestion. The fix adds `debounce_started_at` to metadata and calls
`service.has_creator_reply_after(lead_id, debounce_started_at)` both after
the sleep and immediately before commit.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_debounce_regen_skips_if_creator_replied_during_sleep():
    """Regen must abort without committing when has_creator_reply_after=True."""
    from core.copilot.messaging import _debounced_regeneration_impl

    lead_key = "lead-race-1"
    started = datetime.now(timezone.utc) - timedelta(seconds=15)

    service = MagicMock()
    service._debounce_metadata = {
        lead_key: {
            "creator_id": "creator1",
            "follower_id": "ig_999",
            "platform": "instagram",
            "pending_message_id": "msg-race-1",
            "username": "testuser",
            "debounce_started_at": started,
            "lead_id": lead_key,
        }
    }
    service._debounce_tasks = {}
    service.has_creator_reply_after = MagicMock(return_value=True)

    pending_msg = MagicMock()
    pending_msg.status = "pending_approval"
    pending_msg.lead_id = lead_key
    pending_msg.content = "ORIGINAL"
    pending_msg.suggested_response = "ORIGINAL"

    mock_session = MagicMock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = pending_msg

    with (
        patch("core.copilot.messaging.asyncio.sleep", new_callable=AsyncMock),
        patch("api.database.SessionLocal", return_value=mock_session),
    ):
        # Sentinel: if process_dm is accidentally called the test should fail.
        with patch("core.dm_agent_v2.get_dm_agent") as mock_agent_getter:
            mock_agent_getter.return_value.process_dm = AsyncMock(
                return_value=MagicMock(content="SHOULD_NOT_OVERWRITE")
            )
            await _debounced_regeneration_impl(service, lead_key)

    service.has_creator_reply_after.assert_called_once()
    args, kwargs = service.has_creator_reply_after.call_args
    # lead_id and since_time must match meta
    assert args[0] == lead_key
    assert args[1] == started

    # No overwrite
    assert pending_msg.content == "ORIGINAL"
    assert pending_msg.suggested_response == "ORIGINAL"
    mock_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_debounce_regen_proceeds_when_no_manual_reply():
    """Sanity: when has_creator_reply_after=False, regen still commits."""
    from core.copilot.messaging import _debounced_regeneration_impl

    lead_key = "lead-race-2"
    started = datetime.now(timezone.utc) - timedelta(seconds=15)

    service = MagicMock()
    service._debounce_metadata = {
        lead_key: {
            "creator_id": "creator1",
            "follower_id": "ig_888",
            "platform": "instagram",
            "pending_message_id": "msg-race-2",
            "username": "testuser",
            "debounce_started_at": started,
            "lead_id": lead_key,
        }
    }
    service._debounce_tasks = {}
    service.has_creator_reply_after = MagicMock(return_value=False)

    pending_msg = MagicMock()
    pending_msg.status = "pending_approval"
    pending_msg.lead_id = lead_key
    pending_msg.msg_metadata = None

    latest_user = MagicMock()
    latest_user.content = "hola"

    mock_session = MagicMock()
    # First query: pending_msg lookup (filter_by.first)
    # Second query: latest user msg (filter.order_by.first)
    pending_q = MagicMock()
    pending_q.filter_by.return_value.first.return_value = pending_msg
    user_q = MagicMock()
    user_q.filter.return_value.order_by.return_value.first.return_value = latest_user
    mock_session.query.side_effect = [pending_q, user_q]

    dm_response = MagicMock()
    dm_response.content = "REGENERATED"
    dm_response.metadata = {}

    with (
        patch("core.copilot.messaging.asyncio.sleep", new_callable=AsyncMock),
        patch("api.database.SessionLocal", return_value=mock_session),
    ):
        with patch("core.dm_agent_v2.get_dm_agent") as mock_agent_getter:
            mock_agent_getter.return_value.process_dm = AsyncMock(return_value=dm_response)
            await _debounced_regeneration_impl(service, lead_key)

    # has_creator_reply_after must have been called at least once (post-sleep
    # gate); may be called twice if the pre-commit gate also fires.
    assert service.has_creator_reply_after.call_count >= 1
    assert pending_msg.content == "REGENERATED"
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_debounce_regen_skips_if_creator_replies_during_llm_call():
    """Creator replies during the LLM call: pre-commit re-check catches it."""
    from core.copilot.messaging import _debounced_regeneration_impl

    lead_key = "lead-race-3"
    started = datetime.now(timezone.utc) - timedelta(seconds=15)

    service = MagicMock()
    service._debounce_metadata = {
        lead_key: {
            "creator_id": "creator1",
            "follower_id": "ig_777",
            "platform": "instagram",
            "pending_message_id": "msg-race-3",
            "username": "testuser",
            "debounce_started_at": started,
            "lead_id": lead_key,
        }
    }
    service._debounce_tasks = {}

    # First call (post-sleep): no reply yet. Second call (pre-commit): reply arrived.
    service.has_creator_reply_after = MagicMock(side_effect=[False, True])

    pending_msg = MagicMock()
    pending_msg.status = "pending_approval"
    pending_msg.lead_id = lead_key
    pending_msg.content = "ORIGINAL"
    pending_msg.suggested_response = "ORIGINAL"
    pending_msg.msg_metadata = None

    latest_user = MagicMock()
    latest_user.content = "hola"

    mock_session = MagicMock()
    pending_q = MagicMock()
    pending_q.filter_by.return_value.first.return_value = pending_msg
    user_q = MagicMock()
    user_q.filter.return_value.order_by.return_value.first.return_value = latest_user
    mock_session.query.side_effect = [pending_q, user_q]

    dm_response = MagicMock()
    dm_response.content = "REGENERATED"
    dm_response.metadata = {}

    with (
        patch("core.copilot.messaging.asyncio.sleep", new_callable=AsyncMock),
        patch("api.database.SessionLocal", return_value=mock_session),
    ):
        with patch("core.dm_agent_v2.get_dm_agent") as mock_agent_getter:
            mock_agent_getter.return_value.process_dm = AsyncMock(return_value=dm_response)
            await _debounced_regeneration_impl(service, lead_key)

    assert service.has_creator_reply_after.call_count == 2
    # No overwrite — pre-commit gate catches the race
    assert pending_msg.content == "ORIGINAL"
    mock_session.commit.assert_not_called()
