"""Regression test for BUG 1 — W8 T1 audit.

Prior state: `core/copilot/actions.py:discard_response_impl` referenced
`_Cr` and `_lead` (never imported / never defined), so the outer
try/except silently swallowed a NameError and the `copilot_discard`
feedback signal NEVER fired in prod.

This test exercises the preference-pairs path and asserts that
`feedback_capture` is scheduled (meaning the NameError is gone).
"""
import sys
import os
import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest


@pytest.mark.asyncio
async def test_discard_response_fires_preference_pairs_hook():
    """After discard, feedback_capture must be called with signal_type=copilot_discard."""
    from core.copilot import actions as copilot_actions

    # Build fake ORM objects
    lead_id = uuid.uuid4()
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.lead_id = lead_id
    msg.created_at = datetime.now(timezone.utc)
    msg.msg_metadata = {}
    msg.intent = "pregunta"
    msg.suggested_response = "hola que tal"
    msg.confidence_score = 0.82

    creator = MagicMock()
    creator.id = uuid.uuid4()

    lead = MagicMock()
    lead.status = "new"

    # Session mock: query(...).filter_by(...).first() returns different models by type
    session = MagicMock()

    def _query_side_effect(model):
        q = MagicMock()

        def _filter_by(**kwargs):
            fb = MagicMock()
            name = getattr(model, "__name__", str(model))
            if name == "Message":
                fb.first.return_value = msg
            elif name == "Creator":
                fb.first.return_value = creator
            elif name == "Lead":
                fb.first.return_value = lead
            else:
                fb.first.return_value = None
            return fb

        q.filter_by.side_effect = _filter_by

        # Preceding-user-message query uses .filter(...) + .order_by(...).first()
        preceding_chain = MagicMock()
        preceding_chain.order_by.return_value.first.return_value = ("hola",)
        q.filter.return_value = preceding_chain
        return q

    session.query.side_effect = _query_side_effect
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()

    captured = {}

    async def fake_capture(**kwargs):
        captured.update(kwargs)
        return None

    with patch("api.database.SessionLocal", return_value=session):
        with patch("services.feedback_store.capture", new=fake_capture):
            result = await copilot_actions.discard_response_impl(
                service=MagicMock(),
                creator_id="iris_bertran",
                message_id=str(msg.id),
                discard_reason="wrong tone",
            )

            # Let the fire-and-forget task run
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in pending:
                try:
                    await asyncio.wait_for(t, timeout=1.0)
                except Exception:
                    pass

    assert result["success"] is True
    assert captured.get("signal_type") == "copilot_discard", (
        f"feedback_capture never fired with copilot_discard — NameError regression? "
        f"captured={captured}"
    )
    assert captured.get("creator_db_id") == creator.id
    assert captured.get("lead_id") == lead_id
    assert captured["metadata"]["lead_stage"] == "new"
