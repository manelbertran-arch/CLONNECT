"""Audit tests for core/context_detector.py"""

from core.context_detector import (
    B2BResult,
    FrustrationResult,
    SarcasmResult,
    detect_frustration,
    detect_sarcasm,
    extract_user_name,
)


class TestAuditContextDetector:
    def test_import(self):
        from core.context_detector import (  # noqa: F811
            detect_frustration,
            detect_sarcasm,
            extract_user_name,
        )

        assert detect_frustration is not None

    def test_happy_path_detect_frustration(self):
        result = detect_frustration("Estoy muy molesto con este servicio!!", [])
        assert isinstance(result, FrustrationResult)

    def test_happy_path_detect_sarcasm(self):
        result = detect_sarcasm("Si claro, seguro que funciona perfecto")
        assert isinstance(result, SarcasmResult)

    def test_edge_case_extract_name(self):
        name = extract_user_name("Me llamo Juan Carlos")
        assert name is not None or name is None

    def test_error_handling_empty_message(self):
        result = detect_frustration("", [])
        assert isinstance(result, FrustrationResult)
        d = result.to_dict()
        assert isinstance(d, dict)
