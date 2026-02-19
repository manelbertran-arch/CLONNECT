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
            "test_creator", "msg_1", "edited text"
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

        mock_service.get_pending_responses.assert_called_once_with("creator_alpha", 10, 5)

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
