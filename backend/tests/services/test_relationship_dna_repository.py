"""Tests for RelationshipDNA repository functions.

TDD: Tests written FIRST before implementation.
Part of RELATIONSHIP-DNA feature.
"""

from unittest.mock import MagicMock, patch

from models.relationship_dna import RelationshipType


class TestRelationshipDNARepository:
    """Test suite for RelationshipDNA repository functions."""

    def test_create_relationship_dna(self):
        """Should create a new RelationshipDNA record."""
        from services.relationship_dna_repository import create_relationship_dna

        # Mock the database session
        with patch("services.relationship_dna_repository.get_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            result = create_relationship_dna(
                creator_id="stefan",
                follower_id="12345",
                relationship_type=RelationshipType.AMISTAD_CERCANA.value,
                trust_score=0.8,
            )

            assert result is not None
            assert "id" in result
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()

    def test_get_by_creator_and_follower(self):
        """Should retrieve DNA by creator_id and follower_id."""
        from services.relationship_dna_repository import get_relationship_dna

        with patch("services.relationship_dna_repository.get_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            # Mock query result
            mock_dna = MagicMock()
            mock_dna.id = "test-uuid"
            mock_dna.creator_id = "stefan"
            mock_dna.follower_id = "12345"
            mock_dna.relationship_type = RelationshipType.AMISTAD_CERCANA.value
            mock_dna.trust_score = 0.8
            mock_dna.depth_level = 2
            mock_dna.vocabulary_uses = ["hermano", "bro"]
            mock_dna.vocabulary_avoids = []
            mock_dna.emojis = ["🙏🏽"]
            mock_dna.bot_instructions = "Use hermano"
            mock_dna.golden_examples = []
            mock_dna.total_messages_analyzed = 50
            mock_dna.version = 1

            mock_db.query.return_value.filter_by.return_value.first.return_value = (
                mock_dna
            )

            result = get_relationship_dna("stefan", "12345")

            assert result is not None
            assert result["creator_id"] == "stefan"
            assert result["follower_id"] == "12345"
            assert result["relationship_type"] == RelationshipType.AMISTAD_CERCANA.value

    def test_get_returns_none_when_not_found(self):
        """Should return None when DNA not found."""
        from services.relationship_dna_repository import get_relationship_dna

        with patch("services.relationship_dna_repository.get_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.first.return_value = None

            result = get_relationship_dna("stefan", "nonexistent")

            assert result is None

    def test_update_relationship_dna(self):
        """Should update an existing RelationshipDNA record."""
        from services.relationship_dna_repository import update_relationship_dna

        with patch("services.relationship_dna_repository.get_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            # Mock existing record
            mock_dna = MagicMock()
            mock_dna.id = "test-uuid"
            mock_db.query.return_value.filter_by.return_value.first.return_value = (
                mock_dna
            )

            result = update_relationship_dna(
                creator_id="stefan",
                follower_id="12345",
                data={
                    "trust_score": 0.9,
                    "vocabulary_uses": ["hermano", "bro", "crack"],
                },
            )

            assert result is True
            mock_db.commit.assert_called_once()

    def test_get_or_create_returns_existing(self):
        """Should return existing DNA if found."""
        from services.relationship_dna_repository import get_or_create_relationship_dna

        with patch("services.relationship_dna_repository.get_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            # Mock existing record
            mock_dna = MagicMock()
            mock_dna.id = "existing-uuid"
            mock_dna.creator_id = "stefan"
            mock_dna.follower_id = "12345"
            mock_dna.relationship_type = RelationshipType.DESCONOCIDO.value
            mock_dna.trust_score = 0.0
            mock_dna.depth_level = 0
            mock_dna.vocabulary_uses = []
            mock_dna.vocabulary_avoids = []
            mock_dna.emojis = []
            mock_dna.bot_instructions = None
            mock_dna.golden_examples = []
            mock_dna.total_messages_analyzed = 0
            mock_dna.version = 1

            mock_db.query.return_value.filter_by.return_value.first.return_value = (
                mock_dna
            )

            result = get_or_create_relationship_dna("stefan", "12345")

            assert result is not None
            assert result["id"] == "existing-uuid"
            # Should NOT have called add (existing record)
            mock_db.add.assert_not_called()

    def test_get_or_create_creates_new(self):
        """Should create new DNA if not found."""
        from services.relationship_dna_repository import get_or_create_relationship_dna

        with patch("services.relationship_dna_repository.get_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            # Mock no existing record
            mock_db.query.return_value.filter_by.return_value.first.return_value = None

            result = get_or_create_relationship_dna("stefan", "new_follower")

            assert result is not None
            # Should have called add (new record)
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called()

    def test_list_by_creator(self):
        """Should list all DNAs for a creator."""
        from services.relationship_dna_repository import list_relationship_dnas_by_creator

        with patch("services.relationship_dna_repository.get_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            # Mock multiple records
            mock_dna1 = MagicMock()
            mock_dna1.id = "uuid-1"
            mock_dna1.creator_id = "stefan"
            mock_dna1.follower_id = "follower1"
            mock_dna1.relationship_type = RelationshipType.INTIMA.value
            mock_dna1.trust_score = 0.95
            mock_dna1.depth_level = 4
            mock_dna1.vocabulary_uses = []
            mock_dna1.vocabulary_avoids = []
            mock_dna1.emojis = []
            mock_dna1.bot_instructions = None
            mock_dna1.golden_examples = []
            mock_dna1.total_messages_analyzed = 100
            mock_dna1.version = 1

            mock_dna2 = MagicMock()
            mock_dna2.id = "uuid-2"
            mock_dna2.creator_id = "stefan"
            mock_dna2.follower_id = "follower2"
            mock_dna2.relationship_type = RelationshipType.CLIENTE.value
            mock_dna2.trust_score = 0.5
            mock_dna2.depth_level = 1
            mock_dna2.vocabulary_uses = []
            mock_dna2.vocabulary_avoids = []
            mock_dna2.emojis = []
            mock_dna2.bot_instructions = None
            mock_dna2.golden_examples = []
            mock_dna2.total_messages_analyzed = 20
            mock_dna2.version = 1

            mock_db.query.return_value.filter_by.return_value.all.return_value = [
                mock_dna1,
                mock_dna2,
            ]

            result = list_relationship_dnas_by_creator("stefan")

            assert len(result) == 2
            assert result[0]["follower_id"] == "follower1"
            assert result[1]["follower_id"] == "follower2"

    def test_delete_relationship_dna(self):
        """Should delete a RelationshipDNA record."""
        from services.relationship_dna_repository import delete_relationship_dna

        with patch("services.relationship_dna_repository.get_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            # Mock existing record
            mock_dna = MagicMock()
            mock_db.query.return_value.filter_by.return_value.first.return_value = (
                mock_dna
            )

            result = delete_relationship_dna("stefan", "12345")

            assert result is True
            mock_db.delete.assert_called_once_with(mock_dna)
            mock_db.commit.assert_called_once()

    def test_delete_returns_false_when_not_found(self):
        """Should return False when trying to delete non-existent DNA."""
        from services.relationship_dna_repository import delete_relationship_dna

        with patch("services.relationship_dna_repository.get_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.first.return_value = None

            result = delete_relationship_dna("stefan", "nonexistent")

            assert result is False
            mock_db.delete.assert_not_called()
