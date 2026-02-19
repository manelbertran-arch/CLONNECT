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

    def test_detect_familia(self):
        """Should detect FAMILIA from family conversation (e.g. Richard case)."""
        from services.relationship_type_detector import RelationshipTypeDetector

        detector = RelationshipTypeDetector()
        messages = [
            {"role": "user", "content": "hola hijo"},
            {"role": "assistant", "content": "Hola! Como estas?"},
            {"role": "user", "content": "hijo necesito ayuda con el wifi"},
            {"role": "assistant", "content": "Claro, que necesitas?"},
        ]

        result = detector.detect(messages)

        assert result["type"] == RelationshipType.FAMILIA.value
        assert result["confidence"] >= 0.6

    def test_detect_familia_parent(self):
        """Should detect FAMILIA when someone mentions papá/mamá."""
        from services.relationship_type_detector import RelationshipTypeDetector

        detector = RelationshipTypeDetector()
        messages = [
            {"role": "user", "content": "papá me puedes ayudar?"},
            {"role": "assistant", "content": "Si claro"},
            {"role": "user", "content": "necesito que me expliques algo papi"},
        ]

        result = detector.detect(messages)

        assert result["type"] == RelationshipType.FAMILIA.value
        assert result["confidence"] >= 0.6

    def test_familia_not_triggered_by_casual_tio(self):
        """Should NOT detect FAMILIA from casual Spanish 'tio' usage."""
        from services.relationship_type_detector import RelationshipTypeDetector

        detector = RelationshipTypeDetector()
        messages = [
            {"role": "user", "content": "Que pasa tio!"},
            {"role": "assistant", "content": "Todo bien!"},
            {"role": "user", "content": "Maquina, vi tu video"},
        ]

        result = detector.detect(messages)

        assert result["type"] != RelationshipType.FAMILIA.value


class TestResponseStrategy:
    """Tests for the response strategy function."""

    def test_family_strategy(self):
        """Family members should get PERSONAL strategy."""
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="hola hijo",
            intent_value="greeting",
            relationship_type="FAMILIA",
            is_first_message=False,
            is_friend=True,
            follower_interests=[],
            lead_stage="nuevo",
        )
        assert "PERSONAL" in result
        assert "NUNCA" in result

    def test_help_strategy(self):
        """Help requests should get AYUDA strategy."""
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="necesito ayuda con el wifi",
            intent_value="support",
            relationship_type="DESCONOCIDO",
            is_first_message=False,
            is_friend=False,
            follower_interests=[],
            lead_stage="nuevo",
        )
        assert "AYUDA" in result

    def test_sales_strategy(self):
        """Product interest should get VENTA strategy."""
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="cuanto cuesta el programa?",
            intent_value="pricing",
            relationship_type="CLIENTE",
            is_first_message=False,
            is_friend=False,
            follower_interests=["coaching"],
            lead_stage="interesado",
        )
        assert "VENTA" in result

    def test_first_message_greeting(self):
        """First message without need should get BIENVENIDA strategy."""
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="hola",
            intent_value="greeting",
            relationship_type="DESCONOCIDO",
            is_first_message=True,
            is_friend=False,
            follower_interests=[],
            lead_stage="nuevo",
        )
        assert "BIENVENIDA" in result

    def test_first_message_with_pricing(self):
        """First message with pricing intent should get VENTA strategy (intent priority)."""
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="hola, cuanto cuesta el curso?",
            intent_value="pricing",
            relationship_type="DESCONOCIDO",
            is_first_message=True,
            is_friend=False,
            follower_interests=[],
            lead_stage="nuevo",
        )
        # Pricing intent takes priority over first-message greeting
        assert "VENTA" in result

    def test_first_message_with_help(self):
        """First message with help request should get AYUDA strategy."""
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="hola, necesito ayuda con algo",
            intent_value="support",
            relationship_type="DESCONOCIDO",
            is_first_message=True,
            is_friend=False,
            follower_interests=[],
            lead_stage="nuevo",
        )
        assert "AYUDA" in result

    def test_no_strategy_for_normal_convo(self):
        """Normal ongoing conversation should return empty string."""
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="si me parece bien",
            intent_value="affirmation",
            relationship_type="DESCONOCIDO",
            is_first_message=False,
            is_friend=False,
            follower_interests=[],
            lead_stage="interesado",
        )
        assert result == ""
