"""Tests for RelationshipTypeDetector service.

TDD: Tests written FIRST before implementation.
Part of RELATIONSHIP-DNA feature.
"""

from models.relationship_dna import RelationshipType


class TestRelationshipTypeDetector:
    """Test suite for RelationshipTypeDetector service."""

    def test_detect_intima(self):
        """Should detect INTIMA relationship from intimate conversation."""
        from services.relationship_type_detector import RelationshipTypeDetector

        detector = RelationshipTypeDetector()
        messages = [
            {"role": "user", "content": "Te amo mucho mi amor 💙"},
            {"role": "assistant", "content": "Yo también te amo preciosa 💙"},
            {"role": "user", "content": "Te extraño"},
            {"role": "assistant", "content": "Y yo a ti cariño, mucho"},
        ]

        result = detector.detect(messages)

        assert result["type"] == RelationshipType.INTIMA.value
        assert result["confidence"] >= 0.8

    def test_detect_amistad_cercana(self):
        """Should detect AMISTAD_CERCANA from close friend conversation."""
        from services.relationship_type_detector import RelationshipTypeDetector

        detector = RelationshipTypeDetector()
        messages = [
            {"role": "user", "content": "Hermano que tal el circulo?"},
            {"role": "assistant", "content": "Brutal bro, muy transformador"},
            {"role": "user", "content": "Me alegro hermano!"},
            {"role": "assistant", "content": "Gracias! El proximo va a estar genial 🙏🏽"},
        ]

        result = detector.detect(messages)

        assert result["type"] == RelationshipType.AMISTAD_CERCANA.value
        assert result["confidence"] >= 0.7

    def test_detect_amistad_casual(self):
        """Should detect AMISTAD_CASUAL from casual conversation."""
        from services.relationship_type_detector import RelationshipTypeDetector

        detector = RelationshipTypeDetector()
        messages = [
            {"role": "user", "content": "Crack! Vi tu ultimo video"},
            {"role": "assistant", "content": "Gracias tio! Que te parecio?"},
            {"role": "user", "content": "Muy bueno, maquina"},
            {"role": "assistant", "content": "Me alegro! Viene mas contenido 😄"},
        ]

        result = detector.detect(messages)

        assert result["type"] == RelationshipType.AMISTAD_CASUAL.value
        assert result["confidence"] >= 0.6

    def test_detect_cliente(self):
        """Should detect CLIENTE from business conversation."""
        from services.relationship_type_detector import RelationshipTypeDetector

        detector = RelationshipTypeDetector()
        messages = [
            {"role": "user", "content": "Hola, cuanto cuesta el programa?"},
            {"role": "assistant", "content": "Hola! Son 497 euros"},
            {"role": "user", "content": "Y que incluye?"},
            {"role": "assistant", "content": "Incluye 8 sesiones y acceso a la comunidad"},
            {"role": "user", "content": "Como puedo pagar?"},
        ]

        result = detector.detect(messages)

        assert result["type"] == RelationshipType.CLIENTE.value
        assert result["confidence"] >= 0.7

    def test_detect_colaborador(self):
        """Should detect COLABORADOR from collaboration conversation."""
        from services.relationship_type_detector import RelationshipTypeDetector

        detector = RelationshipTypeDetector()
        messages = [
            {"role": "user", "content": "Hola, me gustaria proponerte una colaboracion"},
            {"role": "assistant", "content": "Hola! Cuentame mas"},
            {"role": "user", "content": "Tenemos audiencias similares, podriamos hacer un directo juntos"},
            {"role": "assistant", "content": "Suena interesante, que propones exactamente?"},
        ]

        result = detector.detect(messages)

        assert result["type"] == RelationshipType.COLABORADOR.value
        assert result["confidence"] >= 0.6

    def test_detect_desconocido(self):
        """Should detect DESCONOCIDO for new/unclear conversations."""
        from services.relationship_type_detector import RelationshipTypeDetector

        detector = RelationshipTypeDetector()
        messages = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola! Como estas?"},
        ]

        result = detector.detect(messages)

        assert result["type"] == RelationshipType.DESCONOCIDO.value
        # Low confidence for unknown
        assert result["confidence"] <= 0.5
