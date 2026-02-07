"""Audit tests for core/frustration_detector.py"""

from core.frustration_detector import FrustrationDetector


class TestAuditFrustrationDetector:
    def test_import(self):
        from core.frustration_detector import FrustrationDetector  # noqa: F811

        assert FrustrationDetector is not None

    def test_init(self):
        detector = FrustrationDetector()
        assert detector is not None

    def test_happy_path_calm_message(self):
        detector = FrustrationDetector()
        signals, score = detector.analyze_message("Hola, todo bien por aqui", "conv_test_1")
        assert signals is not None
        assert isinstance(score, float)

    def test_edge_case_frustrated_message(self):
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(
            "No entiendo nada!! Esto es horrible!!!", "conv_test_2"
        )
        assert signals is not None
        assert score >= 0

    def test_error_handling_empty(self):
        detector = FrustrationDetector()
        signals, score = detector.analyze_message("", "conv_test_3")
        assert signals is not None
        assert isinstance(score, float)
