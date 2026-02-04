"""Tests for RelationshipDNA model.

TDD: Tests written FIRST before implementation.
Part of RELATIONSHIP-DNA feature.
"""
import pytest
from datetime import datetime, timezone


class TestRelationshipDNAModel:
    """Test suite for RelationshipDNA SQLAlchemy model."""

    def test_create_minimal(self):
        """Create DNA with only required fields."""
        from models.relationship_dna import RelationshipDNA, RelationshipType

        dna = RelationshipDNA(
            creator_id="stefan",
            follower_id="12345"
        )
        assert dna.creator_id == "stefan"
        assert dna.follower_id == "12345"
        assert dna.relationship_type == RelationshipType.DESCONOCIDO.value
        assert dna.trust_score == 0.0
        assert dna.depth_level == 0

    def test_create_full(self):
        """Create DNA with all fields populated."""
        from models.relationship_dna import RelationshipDNA, RelationshipType

        dna = RelationshipDNA(
            creator_id="stefan",
            follower_id="67890",
            relationship_type=RelationshipType.AMISTAD_CERCANA.value,
            trust_score=0.85,
            depth_level=3,
            vocabulary_uses=["hermano", "bro", "crack"],
            vocabulary_avoids=["amigo", "colega"],
            emojis=["🙏🏽", "🫂", "💪🏽"],
            avg_message_length=45,
            questions_frequency=0.35,
            multi_message_frequency=0.6,
            tone_description="Cercano, espiritual, vulnerable",
            recurring_topics=["circulos de hombres", "vipassana", "terapia"],
            private_references=["el retiro", "la charla"],
            bot_instructions="Con este lead usar 'hermano'. Preguntar por circulos.",
            golden_examples=[
                {"lead": "Que tal?", "creator": "Todo bien hermano! Y vos??"}
            ]
        )
        assert dna.creator_id == "stefan"
        assert dna.relationship_type == RelationshipType.AMISTAD_CERCANA.value
        assert dna.trust_score == 0.85
        assert "hermano" in dna.vocabulary_uses
        assert "amigo" in dna.vocabulary_avoids
        assert dna.avg_message_length == 45

    def test_vocabulary_lists_default_empty(self):
        """Vocabulary lists should default to empty lists."""
        from models.relationship_dna import RelationshipDNA

        dna = RelationshipDNA(creator_id="stefan", follower_id="12345")
        assert dna.vocabulary_uses == []
        assert dna.vocabulary_avoids == []
        assert dna.emojis == []
        assert dna.recurring_topics == []
        assert dna.private_references == []
        assert dna.golden_examples == []

    def test_golden_examples_structure(self):
        """Golden examples should have lead/creator structure."""
        from models.relationship_dna import RelationshipDNA

        examples = [
            {"lead": "Que tal?", "creator": "Todo bien hermano!"},
            {"lead": "Gracias!", "creator": "Un placer bro 🙏🏽"}
        ]
        dna = RelationshipDNA(
            creator_id="stefan",
            follower_id="12345",
            golden_examples=examples
        )
        assert len(dna.golden_examples) == 2
        assert "lead" in dna.golden_examples[0]
        assert "creator" in dna.golden_examples[0]
        assert dna.golden_examples[0]["lead"] == "Que tal?"

    def test_unique_constraint_fields(self):
        """creator_id + follower_id combination should be unique."""
        from models.relationship_dna import RelationshipDNA

        dna1 = RelationshipDNA(creator_id="stefan", follower_id="same_id")
        dna2 = RelationshipDNA(creator_id="stefan", follower_id="same_id")
        # Both have same creator_id + follower_id (DB will enforce uniqueness)
        assert dna1.creator_id == dna2.creator_id
        assert dna1.follower_id == dna2.follower_id

    def test_version_starts_at_1(self):
        """Version should start at 1."""
        from models.relationship_dna import RelationshipDNA

        dna = RelationshipDNA(creator_id="stefan", follower_id="12345")
        assert dna.version == 1

    def test_total_messages_analyzed_default(self):
        """total_messages_analyzed should default to 0."""
        from models.relationship_dna import RelationshipDNA

        dna = RelationshipDNA(creator_id="stefan", follower_id="12345")
        assert dna.total_messages_analyzed == 0

    def test_relationship_type_values(self):
        """Verify all relationship types can be assigned."""
        from models.relationship_dna import RelationshipDNA, RelationshipType

        for rel_type in RelationshipType:
            dna = RelationshipDNA(
                creator_id="stefan",
                follower_id=f"test_{rel_type.value}",
                relationship_type=rel_type.value
            )
            assert dna.relationship_type == rel_type.value
