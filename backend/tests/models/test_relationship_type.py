"""Tests for RelationshipType enum.

TDD: Tests written FIRST before implementation.
Part of RELATIONSHIP-DNA feature.
"""


class TestRelationshipType:
    """Test suite for RelationshipType enum."""

    def test_all_types_exist(self):
        """Verify all relationship types are defined."""
        from models.relationship_dna import RelationshipType

        assert RelationshipType.INTIMA.value == "INTIMA"
        assert RelationshipType.AMISTAD_CERCANA.value == "AMISTAD_CERCANA"
        assert RelationshipType.AMISTAD_CASUAL.value == "AMISTAD_CASUAL"
        assert RelationshipType.CLIENTE.value == "CLIENTE"
        assert RelationshipType.COLABORADOR.value == "COLABORADOR"
        assert RelationshipType.DESCONOCIDO.value == "DESCONOCIDO"

    def test_type_is_string_enum(self):
        """Verify enum values are strings for JSON serialization."""
        from models.relationship_dna import RelationshipType

        assert isinstance(RelationshipType.INTIMA.value, str)
        assert isinstance(RelationshipType.AMISTAD_CERCANA.value, str)
        assert isinstance(RelationshipType.CLIENTE.value, str)

    def test_default_is_desconocido(self):
        """Verify DESCONOCIDO is available for new leads without history."""
        from models.relationship_dna import RelationshipType

        default = RelationshipType.DESCONOCIDO
        assert default.value == "DESCONOCIDO"
        assert default.name == "DESCONOCIDO"
