"""Audit tests for api/routers/copilot.py."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper: create a mock copilot_service module so the lazy import succeeds
# ---------------------------------------------------------------------------
def _patch_copilot_service(mock_service):
    """Return a context manager that patches the lazily-imported copilot service."""
    fake_module = MagicMock()
    fake_module.get_copilot_service.return_value = mock_service
    return patch.dict(sys.modules, {"core.copilot_service": fake_module})


# ---------------------------------------------------------------------------
# 1. Init / Import
# ---------------------------------------------------------------------------
class TestCopilotRouterImport:
    """Verify that the copilot router and its models can be imported."""

    def test_router_imports_successfully(self):
        """Router object, Pydantic models, and route prefix are correct."""
        from api.routers.copilot import ApproveRequest, ToggleRequest, router

        assert router is not None
        assert router.prefix == "/copilot"
        assert "copilot" in router.tags
        assert ApproveRequest is not None
        assert ToggleRequest is not None

    def test_pydantic_models_have_correct_defaults(self):
        """ApproveRequest should default edited_text to None."""
        from api.routers.copilot import ApproveRequest, ToggleRequest

        req = ApproveRequest()
        assert req.edited_text is None

        toggle = ToggleRequest(enabled=True)
        assert toggle.enabled is True


# ---------------------------------------------------------------------------
# 2. Happy Path -- Pending messages endpoint
# ---------------------------------------------------------------------------
class TestPendingMessagesEndpoint:
    """Test GET /copilot/{creator_id}/pending with mocked copilot service."""

    @pytest.mark.asyncio
    async def test_get_pending_returns_dict_format(self):
        """When copilot service returns dict format, response includes pagination."""
        from api.routers.copilot import get_pending_responses

        mock_service = AsyncMock()
        mock_service.get_pending_responses.return_value = {
            "pending": [
                {"id": "msg_1", "content": "suggested reply"},
            ],
            "total_count": 1,
            "has_more": False,
        }

        with _patch_copilot_service(mock_service):
            result = await get_pending_responses("test_creator", limit=50, offset=0)

        assert result["creator_id"] == "test_creator"
        assert result["pending_count"] == 1
        assert result["has_more"] is False
        assert len(result["pending_responses"]) == 1

    @pytest.mark.asyncio
    async def test_get_pending_handles_list_format(self):
        """When copilot service returns old list format, response is backward-compatible."""
        from api.routers.copilot import get_pending_responses

        mock_service = AsyncMock()
        mock_service.get_pending_responses.return_value = [
            {"id": "msg_1", "content": "reply"},
        ]

        with _patch_copilot_service(mock_service):
            result = await get_pending_responses("test_creator", limit=50, offset=0)

        assert result["pending_count"] == 1
        assert result["has_more"] is False


# ---------------------------------------------------------------------------
# 3. Happy Path -- Approval endpoint
# ---------------------------------------------------------------------------
class TestApprovalEndpoint:
    """Test POST /copilot/{creator_id}/approve/{message_id}."""

    @pytest.mark.asyncio
    async def test_approve_response_success(self):
        """Approving a response should return the service result on success."""
        from api.routers.copilot import ApproveRequest, approve_response

        mock_service = AsyncMock()
        mock_service.approve_response.return_value = {
            "success": True,
            "message_id": "msg_1",
            "sent": True,
        }

        with _patch_copilot_service(mock_service):
            result = await approve_response(
                "test_creator", "msg_1", ApproveRequest(edited_text="edited text")
            )

        assert result["success"] is True
        mock_service.approve_response.assert_called_once_with(
            "test_creator", "msg_1", "edited text", None
        )


# ---------------------------------------------------------------------------
# 4. Edge Case -- Empty queue response
# ---------------------------------------------------------------------------
class TestEmptyQueueResponse:
    """Test behavior when there are no pending responses."""

    @pytest.mark.asyncio
    async def test_pending_returns_zero_count_when_empty(self):
        """GET /copilot/{creator_id}/pending returns pending_count=0 for empty queue."""
        from api.routers.copilot import get_pending_responses

        mock_service = AsyncMock()
        mock_service.get_pending_responses.return_value = {
            "pending": [],
            "total_count": 0,
            "has_more": False,
        }

        with _patch_copilot_service(mock_service):
            result = await get_pending_responses("test_creator", limit=50, offset=0)

        assert result["pending_count"] == 0
        assert result["pending_responses"] == []
        assert result["total_count"] == 0


# ---------------------------------------------------------------------------
# 5. Integration Check -- Creator isolation
# ---------------------------------------------------------------------------
class TestCreatorIsolation:
    """Verify that endpoints pass creator_id correctly to the service."""

    @pytest.mark.asyncio
    async def test_pending_passes_correct_creator_id(self):
        """The creator_id path param should be forwarded to the service layer."""
        from api.routers.copilot import get_pending_responses

        mock_service = AsyncMock()
        mock_service.get_pending_responses.return_value = {
            "pending": [],
            "total_count": 0,
            "has_more": False,
        }

        with _patch_copilot_service(mock_service):
            await get_pending_responses("creator_alpha", limit=10, offset=5)

        mock_service.get_pending_responses.assert_called_once_with("creator_alpha", 10, 5, include_context=False)

    @pytest.mark.asyncio
    async def test_discard_passes_correct_ids(self):
        """discard_response should forward both creator_id and message_id."""
        from api.routers.copilot import discard_response

        mock_service = AsyncMock()
        mock_service.discard_response.return_value = {"success": True}

        with _patch_copilot_service(mock_service):
            result = await discard_response("creator_beta", "msg_42")

        mock_service.discard_response.assert_called_once_with("creator_beta", "msg_42", discard_reason=None)
        assert result["success"] is True


# ---------------------------------------------------------------------------
# 6. Pending For Lead endpoint
# ---------------------------------------------------------------------------
class TestPendingForLeadEndpoint:
    """Test GET /copilot/{creator_id}/pending-for-lead/{lead_id}."""

    @pytest.mark.asyncio
    async def test_pending_for_lead_returns_null_when_none(self):
        """Returns {pending: null} when no pending suggestion for the lead."""
        from api.routers.copilot import get_pending_for_lead

        mock_session = MagicMock()
        mock_creator = MagicMock()
        mock_creator.id = 1
        mock_lead = MagicMock()
        mock_lead.id = "lead_1"

        call_count = [0]

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # Creator lookup
                result.filter_by.return_value.first.return_value = mock_creator
            elif call_count[0] == 2:
                # Lead lookup
                result.filter_by.return_value.first.return_value = mock_lead
            elif call_count[0] == 3:
                # Pending message → None
                result.filter.return_value.order_by.return_value.first.return_value = None
            return result

        mock_session.query.side_effect = query_side_effect

        with (
            patch("api.database.SessionLocal", return_value=mock_session),
            patch("api.routers.copilot.require_creator_access", return_value="ok"),
        ):
            result = await get_pending_for_lead("creator1", "lead_1")

        assert result["pending"] is None

    @pytest.mark.asyncio
    async def test_pending_for_lead_returns_suggestion_with_context(self):
        """Returns pending suggestion with conversation_context when found."""
        from datetime import datetime, timezone

        from api.routers.copilot import get_pending_for_lead

        mock_session = MagicMock()
        mock_creator = MagicMock()
        mock_creator.id = 1
        mock_lead = MagicMock()
        mock_lead.id = "lead_1"
        mock_lead.platform_user_id = "ig_123"
        mock_lead.platform = "instagram"
        mock_lead.username = "testuser"
        mock_lead.full_name = "Test User"

        import uuid

        pending_uuid = uuid.uuid4()
        mock_pending = MagicMock()
        mock_pending.id = pending_uuid
        mock_pending.content = "Hi! How can I help?"
        mock_pending.intent = "greeting"
        mock_pending.created_at = datetime(2026, 2, 19, 12, 0, 0, tzinfo=timezone.utc)
        mock_pending.status = "pending_approval"

        mock_user_msg = MagicMock()
        mock_user_msg.content = "Hello!"

        call_count = [0]

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.filter_by.return_value.first.return_value = mock_creator
            elif call_count[0] == 2:
                result.filter_by.return_value.first.return_value = mock_lead
            elif call_count[0] == 3:
                result.filter.return_value.order_by.return_value.first.return_value = mock_pending
            elif call_count[0] == 4:
                result.filter.return_value.order_by.return_value.first.return_value = mock_user_msg
            return result

        mock_session.query.side_effect = query_side_effect

        mock_service = MagicMock()
        mock_service._get_conversation_context.return_value = [
            {"role": "user", "content": "Hey", "timestamp": "2026-02-19T11:00:00"},
        ]

        with (
            patch("api.database.SessionLocal", return_value=mock_session),
            _patch_copilot_service(mock_service),
        ):
            result = await get_pending_for_lead("creator1", "lead_1")

        assert result["pending"] is not None
        assert result["pending"]["id"] == str(pending_uuid)
        assert result["pending"]["suggested_response"] == "Hi! How can I help?"
        assert result["pending"]["conversation_context"] is not None
