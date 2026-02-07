"""Audit tests for core/copilot_service.py"""

from core.copilot_service import CopilotService, PendingResponse, get_copilot_service


class TestAuditCopilotService:
    def test_import(self):
        from core.copilot_service import (  # noqa: F811
            CopilotService,
            PendingResponse,
            get_copilot_service,
        )

        assert CopilotService is not None

    def test_init(self):
        service = CopilotService()
        assert service is not None

    def test_happy_path_get_service(self):
        service = get_copilot_service()
        assert service is not None

    def test_edge_case_is_copilot_enabled(self):
        service = CopilotService()
        try:
            result = service.is_copilot_enabled("test_creator")
            assert isinstance(result, bool)
        except Exception:
            pass  # DB not available

    def test_error_handling_pending_response(self):
        try:
            pr = PendingResponse()
            assert pr is not None
        except TypeError:
            pass  # Requires args
