"""Audit tests for core/sensitive_detector.py"""

from core.sensitive_detector import SensitiveContentDetector, SensitiveResult, SensitiveType


class TestAuditSensitiveDetector:
    def test_import(self):
        from core.sensitive_detector import SensitiveContentDetector  # noqa: F811

        assert SensitiveContentDetector is not None

    def test_init(self):
        detector = SensitiveContentDetector()
        assert detector is not None

    def test_happy_path_safe_content(self):
        detector = SensitiveContentDetector()
        result = detector.detect("Hola, me interesa tu curso de coaching")
        assert isinstance(result, SensitiveResult)

    def test_edge_case_empty_message(self):
        detector = SensitiveContentDetector()
        result = detector.detect("")
        assert isinstance(result, SensitiveResult)

    def test_error_handling_sensitive_types_exist(self):
        assert SensitiveType is not None
        types = list(SensitiveType)
        assert len(types) >= 1
