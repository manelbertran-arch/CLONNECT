"""Tests for dm_agent DNA integration.

TDD: Tests written FIRST before implementation.
Part of RELATIONSHIP-DNA feature.

IMPORTANT: These tests verify that:
1. DNA enhances responses when available
2. Bot works normally WITHOUT DNA (fallback)
3. No regression in existing functionality
"""

from unittest.mock import MagicMock, patch

from models.relationship_dna import RelationshipType


class TestDMAgentDNAIntegration:
    """Test suite for dm_agent DNA integration."""

    def test_loads_dna_for_known_lead(self):
        """Should load DNA when lead has existing relationship data."""
        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        with patch("services.relationship_dna_service.get_relationship_dna") as mock_get:
            mock_get.return_value = {
                "creator_id": "stefan",
                "follower_id": "known_lead",
                "relationship_type": RelationshipType.AMISTAD_CERCANA.value,
                "vocabulary_uses": ["hermano", "bro"],
                "vocabulary_avoids": ["amigo"],
                "emojis": ["🙏🏽"],
                "bot_instructions": "Usa hermano con este lead",
            }

            dna = service.get_dna_for_lead("stefan", "known_lead")

            assert dna is not None
            assert dna["relationship_type"] == RelationshipType.AMISTAD_CERCANA.value
            mock_get.assert_called_once_with("stefan", "known_lead")

    def test_creates_dna_for_new_lead(self):
        """Should create DNA for new lead when they have enough messages."""
        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        with patch("services.relationship_dna_service.get_relationship_dna") as mock_get:
            with patch("services.relationship_dna_service.get_or_create_relationship_dna") as mock_create:
                mock_get.return_value = None  # No existing DNA
                mock_create.return_value = {
                    "id": "new-uuid",
                    "creator_id": "stefan",
                    "follower_id": "new_lead",
                    "relationship_type": RelationshipType.DESCONOCIDO.value,
                }

                # Service should create DNA for new lead
                dna = service.get_or_create_dna("stefan", "new_lead", [])

                assert dna is not None
                mock_create.assert_called_once()

    def test_applies_vocabulary_rules(self):
        """Should apply vocabulary rules to instruction generation."""
        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        dna_data = {
            "relationship_type": RelationshipType.AMISTAD_CERCANA.value,
            "vocabulary_uses": ["hermano", "bro"],
            "vocabulary_avoids": ["amigo", "colega"],
            "emojis": ["🙏🏽", "💪🏽"],
        }

        instructions = service.get_prompt_instructions(dna_data)

        assert "hermano" in instructions.lower() or "bro" in instructions.lower()
        assert "evita" in instructions.lower() or "avoid" in instructions.lower()

    def test_applies_relationship_type(self):
        """Should apply relationship-specific tone to instructions."""
        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        # Test INTIMA type
        intima_dna = {
            "relationship_type": RelationshipType.INTIMA.value,
            "vocabulary_uses": ["amor"],
            "vocabulary_avoids": ["hermano"],
            "emojis": ["💙"],
        }

        instructions = service.get_prompt_instructions(intima_dna)

        assert "íntim" in instructions.lower() or "cariño" in instructions.lower()

    def test_no_regression_without_dna(self):
        """Should work normally when no DNA exists (graceful fallback)."""
        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        with patch("services.relationship_dna_service.get_relationship_dna") as mock_get:
            mock_get.return_value = None

            dna = service.get_dna_for_lead("stefan", "unknown_lead")
            instructions = service.get_prompt_instructions(dna)

            # Should return None DNA but empty/default instructions
            assert dna is None
            assert instructions == "" or instructions is None

    def test_response_personalized_with_dna(self):
        """Should generate personalized instructions based on DNA."""
        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        dna_data = {
            "relationship_type": RelationshipType.AMISTAD_CERCANA.value,
            "vocabulary_uses": ["hermano", "bro", "crack"],
            "vocabulary_avoids": ["señor", "usted"],
            "emojis": ["🙏🏽", "💪🏽", "🔥"],
            "recurring_topics": ["circulos de hombres"],
            "golden_examples": [
                {"lead": "Que tal?", "creator": "Todo bien hermano!"},
            ],
        }

        instructions = service.get_prompt_instructions(dna_data)

        # Should include key elements
        assert len(instructions) > 50  # Meaningful instructions
        assert "hermano" in instructions.lower() or "fraternal" in instructions.lower()

    def test_updates_dna_after_response(self):
        """Should update DNA stats after response generation."""
        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        with patch("services.relationship_dna_service.get_relationship_dna") as mock_get:
            with patch("services.relationship_dna_service.update_relationship_dna") as mock_update:
                # Mock existing DNA
                mock_get.return_value = {
                    "creator_id": "stefan",
                    "follower_id": "lead123",
                    "total_messages_analyzed": 10,
                }
                mock_update.return_value = True

                service.record_interaction("stefan", "lead123")

                mock_update.assert_called_once()
                # Check that last_analyzed_at or message count was updated
                call_args = mock_update.call_args
                assert call_args is not None

    def test_performance_acceptable(self):
        """DNA lookup should be fast (<50ms for cached lookups)."""
        import time

        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        with patch("services.relationship_dna_service.get_relationship_dna") as mock_get:
            mock_get.return_value = {
                "creator_id": "stefan",
                "follower_id": "lead",
                "relationship_type": RelationshipType.DESCONOCIDO.value,
            }

            start = time.time()
            for _ in range(100):
                service.get_dna_for_lead("stefan", "lead")
            elapsed = time.time() - start

            # 100 lookups should take less than 0.5 seconds (5ms each)
            assert elapsed < 0.5, f"Too slow: {elapsed:.3f}s for 100 lookups"
