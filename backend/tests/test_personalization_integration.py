"""
Test de integracion: Verifica que todos los modulos de personalizacion
trabajan juntos correctamente.
"""
from unittest.mock import patch, MagicMock


class TestPersonalizationModulesLoaded:
    """Verifica que todos los modulos de personalizacion se cargan correctamente"""

    def test_user_profiles_module_loads(self):
        """user_profiles module loads without errors"""
        from core.user_profiles import get_user_profile, UserProfile
        assert callable(get_user_profile)
        assert UserProfile is not None

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
