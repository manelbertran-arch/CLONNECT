"""
Test de integracion: Verifica que todos los modulos de personalizacion
trabajan juntos correctamente.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestPersonalizationModulesLoaded:
    """Verifica que todos los modulos de personalizacion se cargan correctamente"""

    def test_user_profiles_module_loads(self):
        """user_profiles module loads without errors"""
        from core.user_profiles import get_user_profile, UserProfile
        assert callable(get_user_profile)
        assert UserProfile is not None

    def test_personalized_ranking_module_loads(self):
        """personalized_ranking module loads without errors"""
        from core.personalized_ranking import adapt_system_prompt, personalize_results
        assert callable(adapt_system_prompt)
        assert callable(personalize_results)

    def test_reranker_module_loads(self):
        """reranker module loads without errors"""
        from core.rag.reranker import rerank, ENABLE_RERANKING
        assert callable(rerank)
        assert isinstance(ENABLE_RERANKING, bool)

    def test_semantic_memory_pgvector_module_loads(self):
        """semantic_memory_pgvector module loads without errors"""
        from core.semantic_memory_pgvector import (
            get_semantic_memory,
            ENABLE_SEMANTIC_MEMORY_PGVECTOR
        )
        assert callable(get_semantic_memory)
        assert isinstance(ENABLE_SEMANTIC_MEMORY_PGVECTOR, bool)

    def test_semantic_memory_chromadb_module_loads(self):
        """semantic_memory (ChromaDB) module loads without errors"""
        from core.semantic_memory import (
            get_conversation_memory,
            ENABLE_SEMANTIC_MEMORY
        )
        assert callable(get_conversation_memory)
        assert isinstance(ENABLE_SEMANTIC_MEMORY, bool)


class TestAdaptSystemPrompt:
    """Tests para adapt_system_prompt()"""

    def test_adapt_prompt_with_interests(self):
        """adapt_system_prompt adds user interests to prompt"""
        from core.personalized_ranking import adapt_system_prompt

        mock_profile = MagicMock()
        mock_profile.get_summary.return_value = {
            "top_interests": [("marketing", 1.0), ("ventas", 0.8)],
            "recent_objections": [],
            "interested_products": [],
            "preferences": {}
        }

        base_prompt = "Eres un asistente de ventas."
        adapted = adapt_system_prompt(base_prompt, mock_profile)

        assert "CONTEXTO DEL USUARIO" in adapted
        assert "marketing" in adapted
        assert "ventas" in adapted

    def test_adapt_prompt_with_objections(self):
        """adapt_system_prompt adds objections to prompt"""
        from core.personalized_ranking import adapt_system_prompt

        mock_profile = MagicMock()
        mock_profile.get_summary.return_value = {
            "top_interests": [],
            "recent_objections": ["precio alto", "falta de tiempo"],
            "interested_products": [],
            "preferences": {}
        }

        base_prompt = "Eres un asistente."
        adapted = adapt_system_prompt(base_prompt, mock_profile)

        assert "objeciones" in adapted.lower()
        assert "precio alto" in adapted

    def test_adapt_prompt_no_data_returns_original(self):
        """adapt_system_prompt returns original if no user data"""
        from core.personalized_ranking import adapt_system_prompt

        mock_profile = MagicMock()
        mock_profile.get_summary.return_value = {
            "top_interests": [],
            "recent_objections": [],
            "interested_products": [],
            "preferences": {}
        }

        base_prompt = "Eres un asistente."
        adapted = adapt_system_prompt(base_prompt, mock_profile)

        assert adapted == base_prompt

    def test_adapt_prompt_none_profile_returns_original(self):
        """adapt_system_prompt returns original if profile is None"""
        from core.personalized_ranking import adapt_system_prompt

        base_prompt = "Eres un asistente."
        adapted = adapt_system_prompt(base_prompt, None)

        assert adapted == base_prompt


class TestPersonalizeResults:
    """Tests para personalize_results()"""

    def test_personalize_results_with_interests(self):
        """personalize_results boosts results matching interests"""
        from core.personalized_ranking import personalize_results

        mock_profile = MagicMock()
        mock_profile.get_top_interests.return_value = [("marketing", 1.0)]
        mock_profile.get_content_score.return_value = 0.0

        # Use similar base scores so personalization can make a difference
        results = [
            {"content": "Curso de cocina", "score": 0.75},
            {"content": "Curso de marketing digital", "score": 0.70},
        ]

        personalized = personalize_results(results, mock_profile, alpha=0.5)

        # Marketing result should be boosted due to interest match
        assert personalized[0]["content"] == "Curso de marketing digital"
        # Verify final_score was added
        assert "final_score" in personalized[0]
        assert "personal_score" in personalized[0]

    def test_personalize_results_empty_returns_empty(self):
        """personalize_results returns empty for empty input"""
        from core.personalized_ranking import personalize_results

        mock_profile = MagicMock()
        result = personalize_results([], mock_profile)

        assert result == []

    def test_personalize_results_none_profile_returns_original(self):
        """personalize_results returns original if profile is None"""
        from core.personalized_ranking import personalize_results

        results = [{"content": "test", "score": 0.5}]
        result = personalize_results(results, None)

        assert result == results


class TestFeatureFlags:
    """Tests para verificar feature flags"""

    def test_reranking_flag_defaults_true(self):
        """ENABLE_RERANKING should default to true"""
        import os
        # Only test if env var is not explicitly set
        if "ENABLE_RERANKING" not in os.environ:
            from core.rag.reranker import ENABLE_RERANKING
            assert ENABLE_RERANKING == True

    def test_semantic_memory_flag_defaults_false(self):
        """ENABLE_SEMANTIC_MEMORY should default to false"""
        import os
        if "ENABLE_SEMANTIC_MEMORY" not in os.environ:
            from core.semantic_memory import ENABLE_SEMANTIC_MEMORY
            assert ENABLE_SEMANTIC_MEMORY == False

    def test_pgvector_flag_defaults_true(self):
        """ENABLE_SEMANTIC_MEMORY_PGVECTOR should default to true"""
        import os
        if "ENABLE_SEMANTIC_MEMORY_PGVECTOR" not in os.environ:
            from core.semantic_memory_pgvector import ENABLE_SEMANTIC_MEMORY_PGVECTOR
            assert ENABLE_SEMANTIC_MEMORY_PGVECTOR == True


class TestUserProfilePersistence:
    """Tests para persistencia de perfiles"""

    def test_user_profile_factory_creates_instance(self):
        """get_user_profile creates a profile instance"""
        with patch('core.user_profiles.USER_PROFILES_USE_DB', False):
            with patch('core.user_profiles.UserProfile._load_from_json', return_value={}):
                with patch('core.user_profiles.UserProfile._save_to_json'):
                    from core.user_profiles import get_user_profile, clear_profile_cache

                    clear_profile_cache()
                    profile = get_user_profile("test_user", "test_creator")

                    assert profile is not None
                    assert profile.user_id == "test_user"
                    assert profile.creator_id == "test_creator"

    def test_user_profile_cache_returns_same_instance(self):
        """get_user_profile returns cached instance"""
        with patch('core.user_profiles.USER_PROFILES_USE_DB', False):
            with patch('core.user_profiles.UserProfile._load_from_json', return_value={}):
                with patch('core.user_profiles.UserProfile._save_to_json'):
                    from core.user_profiles import get_user_profile, clear_profile_cache

                    clear_profile_cache()
                    profile1 = get_user_profile("test_user", "test_creator")
                    profile2 = get_user_profile("test_user", "test_creator")

                    assert profile1 is profile2


class TestSemanticMemoryIntegration:
    """Tests para integracion de memoria semantica"""

    def test_pgvector_memory_factory_creates_instance(self):
        """get_semantic_memory creates a memory instance"""
        from core.semantic_memory_pgvector import get_semantic_memory, clear_memory_cache

        clear_memory_cache()
        memory = get_semantic_memory("test_creator", "test_follower")

        assert memory is not None
        assert memory.creator_id == "test_creator"
        assert memory.follower_id == "test_follower"

    def test_chromadb_memory_factory_creates_instance(self):
        """get_conversation_memory creates a memory instance"""
        with patch('core.semantic_memory.ConversationMemory._init_vector_store'):
            from core.semantic_memory import get_conversation_memory, _memories

            _memories.clear()
            memory = get_conversation_memory("test_user", "test_creator")

            assert memory is not None
