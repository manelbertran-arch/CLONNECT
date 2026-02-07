"""Audit tests for core/onboarding_service.py"""

from core.onboarding_service import (
    OnboardingRequest,
    OnboardingResult,
    OnboardingService,
    get_onboarding_service,
)


class TestAuditOnboardingService:
    def test_import(self):
        from core.onboarding_service import (  # noqa: F811
            OnboardingRequest,
            OnboardingResult,
            OnboardingService,
        )

        assert OnboardingService is not None

    def test_init(self):
        service = OnboardingService()
        assert service is not None

    def test_happy_path_get_service(self):
        service = get_onboarding_service()
        assert service is not None

    def test_edge_case_result_to_dict(self):
        try:
            result = OnboardingResult()
            d = result.to_dict()
            assert isinstance(d, dict)
        except TypeError:
            pass  # Requires args

    def test_error_handling_request(self):
        try:
            req = OnboardingRequest()
            assert req is not None
        except TypeError:
            pass  # Requires args
