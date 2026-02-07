"""Audit tests for services/relationship_dna_service.py."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from services.relationship_dna_service import RelationshipDNAService, get_dna_service


class TestRelationshipDNAServiceInit:
    """Test 1: init/import - Service initializes correctly."""

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    def test_service_initializes(self, mock_gen):
        svc = RelationshipDNAService()
        assert svc._cache == {}
        assert svc._instructions_generator is not None

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    def test_cache_starts_empty(self, mock_gen):
        svc = RelationshipDNAService()
        assert len(svc._cache) == 0

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    def test_singleton_returns_same_instance(self, mock_gen):
        import services.relationship_dna_service as mod

        mod._dna_service = None
        s1 = get_dna_service()
        s2 = get_dna_service()
        assert s1 is s2
        mod._dna_service = None  # cleanup

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    def test_instructions_generator_initialized(self, mock_gen):
        RelationshipDNAService()
        mock_gen.assert_called_once()

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    def test_module_level_imports_exist(self, mock_gen):
        import services.relationship_dna_service as mod

        assert hasattr(mod, "RelationshipDNAService")
        assert hasattr(mod, "get_dna_service")


class TestDNACalculation:
    """Test 2: happy path - DNA retrieval and prompt generation."""

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_get_dna_for_lead_from_db(self, mock_get_dna, mock_gen):
        mock_get_dna.return_value = {
            "relationship_type": "AMISTAD_CERCANA",
            "trust_score": 0.8,
            "depth_level": 3,
        }
        svc = RelationshipDNAService()
        dna = svc.get_dna_for_lead("c1", "f1")
        assert dna["relationship_type"] == "AMISTAD_CERCANA"
        mock_get_dna.assert_called_once_with("c1", "f1")

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_get_dna_caches_result(self, mock_get_dna, mock_gen):
        mock_get_dna.return_value = {"relationship_type": "CLIENTE"}
        svc = RelationshipDNAService()
        svc.get_dna_for_lead("c1", "f1")
        svc.get_dna_for_lead("c1", "f1")
        # DB should only be called once thanks to cache
        mock_get_dna.assert_called_once()

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    def test_get_prompt_instructions_calls_generator(self, mock_gen_cls):
        mock_gen_instance = MagicMock()
        mock_gen_instance.generate.return_value = "Be friendly"
        mock_gen_cls.return_value = mock_gen_instance

        svc = RelationshipDNAService()
        dna_data = {"relationship_type": "AMISTAD_CASUAL"}
        result = svc.get_prompt_instructions(dna_data)
        assert result == "Be friendly"
        mock_gen_instance.generate.assert_called_once_with(dna_data)

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_get_instructions_for_lead_end_to_end(self, mock_get_dna, mock_gen_cls):
        mock_gen_instance = MagicMock()
        mock_gen_instance.generate.return_value = "Professional tone"
        mock_gen_cls.return_value = mock_gen_instance
        mock_get_dna.return_value = {"relationship_type": "CLIENTE"}

        svc = RelationshipDNAService()
        result = svc.get_instructions_for_lead("c1", "f1")
        assert result == "Professional tone"

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.get_or_create_relationship_dna")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_get_or_create_creates_new_if_missing(self, mock_get_dna, mock_get_or_create, mock_gen):
        mock_get_dna.return_value = None
        mock_get_or_create.return_value = {"relationship_type": "DESCONOCIDO"}

        svc = RelationshipDNAService()
        dna = svc.get_or_create_dna("c1", "f1")
        assert dna["relationship_type"] == "DESCONOCIDO"
        mock_get_or_create.assert_called_once()


class TestMissingDataHandling:
    """Test 3: edge case - Missing DNA and empty data."""

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_get_dna_returns_none_when_not_found(self, mock_get_dna, mock_gen):
        mock_get_dna.return_value = None
        svc = RelationshipDNAService()
        result = svc.get_dna_for_lead("c1", "f_unknown")
        assert result is None

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    def test_get_prompt_instructions_with_none(self, mock_gen):
        svc = RelationshipDNAService()
        result = svc.get_prompt_instructions(None)
        assert result == ""

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_get_instructions_for_nonexistent_lead(self, mock_get_dna, mock_gen):
        mock_get_dna.return_value = None
        svc = RelationshipDNAService()
        result = svc.get_instructions_for_lead("c1", "unknown")
        assert result == ""

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_record_interaction_returns_false_if_no_dna(self, mock_get_dna, mock_gen):
        mock_get_dna.return_value = None
        svc = RelationshipDNAService()
        result = svc.record_interaction("c1", "f1")
        assert result is False

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.get_or_create_relationship_dna")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_get_or_create_returns_existing_if_present(
        self, mock_get_dna, mock_get_or_create, mock_gen
    ):
        mock_get_dna.return_value = {"relationship_type": "INTIMA"}
        svc = RelationshipDNAService()
        dna = svc.get_or_create_dna("c1", "f1")
        assert dna["relationship_type"] == "INTIMA"
        # Should NOT call get_or_create since it already exists
        mock_get_or_create.assert_not_called()


class TestDNAUpdate:
    """Test 4: error handling - DNA update and cache invalidation."""

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.update_relationship_dna")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_record_interaction_updates_count(self, mock_get_dna, mock_update, mock_gen):
        mock_get_dna.return_value = {
            "relationship_type": "CLIENTE",
            "total_messages_analyzed": 5,
        }
        mock_update.return_value = True
        svc = RelationshipDNAService()
        result = svc.record_interaction("c1", "f1")
        assert result is True
        mock_update.assert_called_once()
        update_args = mock_update.call_args
        assert update_args[0][2]["total_messages_analyzed"] == 6

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.update_relationship_dna")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_record_interaction_invalidates_cache(self, mock_get_dna, mock_update, mock_gen):
        mock_get_dna.return_value = {"total_messages_analyzed": 0}
        mock_update.return_value = True
        svc = RelationshipDNAService()
        svc._cache["c1:f1"] = {"cached": True}
        svc.record_interaction("c1", "f1")
        assert "c1:f1" not in svc._cache

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    def test_clear_cache_specific_lead(self, mock_gen):
        svc = RelationshipDNAService()
        svc._cache["c1:f1"] = {"data": 1}
        svc._cache["c1:f2"] = {"data": 2}
        svc.clear_cache(creator_id="c1", follower_id="f1")
        assert "c1:f1" not in svc._cache
        assert "c1:f2" in svc._cache

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    def test_clear_cache_all_for_creator(self, mock_gen):
        svc = RelationshipDNAService()
        svc._cache["c1:f1"] = {"data": 1}
        svc._cache["c1:f2"] = {"data": 2}
        svc._cache["c2:f3"] = {"data": 3}
        svc.clear_cache(creator_id="c1")
        assert "c1:f1" not in svc._cache
        assert "c1:f2" not in svc._cache
        assert "c2:f3" in svc._cache

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    def test_clear_cache_all(self, mock_gen):
        svc = RelationshipDNAService()
        svc._cache["c1:f1"] = {"data": 1}
        svc._cache["c2:f2"] = {"data": 2}
        svc.clear_cache()
        assert len(svc._cache) == 0


class TestScoreValidation:
    """Test 5: integration check - Full flow from DNA load to instructions."""

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_full_flow_load_to_instructions(self, mock_get_dna, mock_gen_cls):
        mock_gen_instance = MagicMock()
        mock_gen_instance.generate.return_value = (
            "Esta es una amistad cercana. Usa un tono fraternal."
        )
        mock_gen_cls.return_value = mock_gen_instance
        mock_get_dna.return_value = {
            "relationship_type": "AMISTAD_CERCANA",
            "trust_score": 0.85,
            "depth_level": 3,
            "vocabulary_uses": ["hermano", "bro"],
            "vocabulary_avoids": ["usted"],
        }

        svc = RelationshipDNAService()
        instructions = svc.get_instructions_for_lead("c1", "f1")
        assert "fraternal" in instructions

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.update_relationship_dna")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_record_interaction_includes_timestamp(self, mock_get_dna, mock_update, mock_gen):
        mock_get_dna.return_value = {"total_messages_analyzed": 10}
        mock_update.return_value = True
        svc = RelationshipDNAService()
        svc.record_interaction("c1", "f1")
        update_args = mock_update.call_args[0][2]
        assert "last_analyzed_at" in update_args
        assert isinstance(update_args["last_analyzed_at"], datetime)

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_cache_key_format(self, mock_get_dna, mock_gen):
        mock_get_dna.return_value = {"relationship_type": "CLIENTE"}
        svc = RelationshipDNAService()
        svc.get_dna_for_lead("creator_abc", "follower_xyz")
        assert "creator_abc:follower_xyz" in svc._cache

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_none_dna_not_cached(self, mock_get_dna, mock_gen):
        mock_get_dna.return_value = None
        svc = RelationshipDNAService()
        svc.get_dna_for_lead("c1", "f1")
        assert "c1:f1" not in svc._cache

    @patch("services.relationship_dna_service.BotInstructionsGenerator")
    @patch("services.relationship_dna_service.get_or_create_relationship_dna")
    @patch("services.relationship_dna_service.get_relationship_dna")
    def test_get_or_create_caches_new_dna(self, mock_get_dna, mock_get_or_create, mock_gen):
        mock_get_dna.return_value = None
        mock_get_or_create.return_value = {
            "relationship_type": "DESCONOCIDO",
            "trust_score": 0.0,
        }
        svc = RelationshipDNAService()
        dna = svc.get_or_create_dna("c1", "f1")
        assert dna is not None
        assert "c1:f1" in svc._cache
        assert svc._cache["c1:f1"]["relationship_type"] == "DESCONOCIDO"
