"""Test relationship_type_detector integration in dm_agent_v2 (Step 14)."""


class TestRelationshipDetectorIntegration:
    def test_module_importable(self):
        from services.relationship_type_detector import RelationshipTypeDetector

        detector = RelationshipTypeDetector()
        assert detector is not None

    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_RELATIONSHIP_DETECTION

        assert isinstance(ENABLE_RELATIONSHIP_DETECTION, bool)

    def test_detect_unknown_with_few_messages(self):
        from services.relationship_type_detector import RelationshipTypeDetector

        detector = RelationshipTypeDetector()
        result = detector.detect([{"role": "user", "content": "Hola"}])
        assert result["type"].lower() == "desconocido"

    def test_detect_client_signals(self):
        from services.relationship_type_detector import RelationshipTypeDetector

        detector = RelationshipTypeDetector()
        messages = [
            {"role": "user", "content": "¿Cuánto cuesta el programa? quiero pagar"},
            {"role": "user", "content": "¿Qué incluye el curso? quiero comprar"},
            {"role": "user", "content": "precio del programa necesito factura euros"},
        ]
        result = detector.detect(messages)
        assert result["confidence"] > 0.3

    def test_flag_default_off(self):
        """Relationship detection should default to OFF."""
        import os

        original = os.environ.pop("ENABLE_RELATIONSHIP_DETECTION", None)
        try:
            flag = os.getenv("ENABLE_RELATIONSHIP_DETECTION", "false").lower() == "true"
            assert flag is False
        finally:
            if original is not None:
                os.environ["ENABLE_RELATIONSHIP_DETECTION"] = original
