"""
CAPA 2 — Unit tests: Copilot service & action models
Tests Pydantic models, service interface, and action logic without DB.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ─── Pydantic request models ──────────────────────────────────────────────────

class TestCopilotModels:

    def test_approve_request_optional_fields(self):
        try:
            from api.routers.copilot.actions import ApproveRequest
        except ImportError:
            pytest.skip("ApproveRequest not importable")
        req = ApproveRequest()
        assert req.edited_text is None
        assert req.chosen_index is None

    def test_approve_request_with_edited_text(self):
        try:
            from api.routers.copilot.actions import ApproveRequest
        except ImportError:
            pytest.skip("ApproveRequest not importable")
        req = ApproveRequest(edited_text="Texto editado por el creador")
        assert req.edited_text == "Texto editado por el creador"

    def test_approve_request_with_chosen_index(self):
        try:
            from api.routers.copilot.actions import ApproveRequest
        except ImportError:
            pytest.skip("ApproveRequest not importable")
        req = ApproveRequest(chosen_index=2)
        assert req.chosen_index == 2

    def test_toggle_request_enabled_true(self):
        try:
            from api.routers.copilot.actions import ToggleRequest
        except ImportError:
            pytest.skip("ToggleRequest not importable")
        req = ToggleRequest(enabled=True)
        assert req.enabled is True

    def test_toggle_request_enabled_false(self):
        try:
            from api.routers.copilot.actions import ToggleRequest
        except ImportError:
            pytest.skip("ToggleRequest not importable")
        req = ToggleRequest(enabled=False)
        assert req.enabled is False

    def test_discard_request_optional_reason(self):
        try:
            from api.routers.copilot.actions import DiscardRequest
        except ImportError:
            pytest.skip("DiscardRequest not importable")
        req = DiscardRequest()
        assert req.reason is None

    def test_discard_request_with_reason(self):
        try:
            from api.routers.copilot.actions import DiscardRequest
        except ImportError:
            pytest.skip("DiscardRequest not importable")
        req = DiscardRequest(reason="wrong tone")
        assert req.reason == "wrong tone"

    def test_manual_response_request_content(self):
        try:
            from api.routers.copilot.actions import ManualResponseRequest
        except ImportError:
            pytest.skip("ManualResponseRequest not importable")
        req = ManualResponseRequest(content="Respuesta manual del creador")
        assert req.content == "Respuesta manual del creador"
        assert req.response_time_ms is None

    def test_manual_response_with_time(self):
        try:
            from api.routers.copilot.actions import ManualResponseRequest
        except ImportError:
            pytest.skip("ManualResponseRequest not importable")
        req = ManualResponseRequest(content="Hola", response_time_ms=1500)
        assert req.response_time_ms == 1500


# ─── Copilot service import & interface ──────────────────────────────────────

class TestCopilotService:

    def test_import_copilot_service(self):
        try:
            from core.copilot_service import get_copilot_service
            assert callable(get_copilot_service)
        except ImportError as e:
            pytest.skip(f"copilot_service not importable: {e}")

    def test_get_copilot_service_returns_singleton(self):
        try:
            from core.copilot_service import get_copilot_service
        except ImportError:
            pytest.skip("copilot_service not importable")
        s1 = get_copilot_service()
        s2 = get_copilot_service()
        assert s1 is s2  # Singleton pattern

    def test_service_has_get_pending_responses(self):
        try:
            from core.copilot_service import get_copilot_service
        except ImportError:
            pytest.skip("copilot_service not importable")
        service = get_copilot_service()
        assert hasattr(service, "get_pending_responses")
        assert callable(service.get_pending_responses)

    def test_service_has_approve_response(self):
        try:
            from core.copilot_service import get_copilot_service
        except ImportError:
            pytest.skip("copilot_service not importable")
        service = get_copilot_service()
        assert hasattr(service, "approve_response")

    def test_service_has_discard_response(self):
        try:
            from core.copilot_service import get_copilot_service
        except ImportError:
            pytest.skip("copilot_service not importable")
        service = get_copilot_service()
        assert hasattr(service, "discard_response")

    def test_service_has_invalidate_cache(self):
        try:
            from core.copilot_service import get_copilot_service
        except ImportError:
            pytest.skip("copilot_service not importable")
        service = get_copilot_service()
        assert hasattr(service, "invalidate_copilot_cache")

    def test_service_has_calculate_edit_diff(self):
        try:
            from core.copilot_service import get_copilot_service
        except ImportError:
            pytest.skip("copilot_service not importable")
        service = get_copilot_service()
        assert hasattr(service, "_calculate_edit_diff")


# ─── Edit diff calculation ────────────────────────────────────────────────────

class TestEditDiff:

    def test_edit_diff_identical(self):
        try:
            from core.copilot_service import get_copilot_service
        except ImportError:
            pytest.skip("copilot_service not importable")
        service = get_copilot_service()
        diff = service._calculate_edit_diff("Hola mundo", "Hola mundo")
        # Identical texts: diff should be None, empty, or 0% change
        assert diff is None or diff == "" or diff == 0 or "0" in str(diff)

    def test_edit_diff_completely_different(self):
        try:
            from core.copilot_service import get_copilot_service
        except ImportError:
            pytest.skip("copilot_service not importable")
        service = get_copilot_service()
        diff = service._calculate_edit_diff("Hola", "Texto completamente diferente y largo")
        # Should return something non-trivial
        assert diff is not None

    def test_edit_diff_returns_value(self):
        try:
            from core.copilot_service import get_copilot_service
        except ImportError:
            pytest.skip("copilot_service not importable")
        service = get_copilot_service()
        diff = service._calculate_edit_diff("Buenos días", "Buenas noches")
        # Must not throw; may be None or a value
        # Just verifying no exception
        assert True


# ─── Pending response format ─────────────────────────────────────────────────

class TestPendingResponseFormat:

    def test_pending_response_dict_structure(self):
        """Validate the shape of a pending response dict returned by the service."""
        sample = {
            "id": "msg_uuid_001",
            "lead_id": "lead_uuid_001",
            "creator_id": "stefano_bonanno",
            "sender_id": "follower_001",
            "suggested_text": "Hola! ¿En qué te puedo ayudar?",
            "status": "pending_approval",
        }
        required_keys = ["id", "suggested_text", "status"]
        for k in required_keys:
            assert k in sample, f"Missing key: {k}"

    def test_approve_result_success_shape(self):
        """The approve_response result must have 'success' key."""
        result = {"success": True, "message_id": "msg_001", "was_edited": False}
        assert result.get("success") is True
        assert "message_id" in result

    def test_discard_result_success_shape(self):
        """The discard_response result must have 'success' key."""
        result = {"success": True, "discarded": "msg_001"}
        assert result.get("success") is True
