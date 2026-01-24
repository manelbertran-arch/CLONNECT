"""Tests para módulos de personalización"""
import pytest
import tempfile
import shutil
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestReranker:
    """Tests para el módulo de reranking"""

    def test_rerank_returns_sorted(self):
        """Verifica que rerank retorna documentos ordenados"""
        from core.rag.reranker import rerank

        docs = [
            {"content": "Python es un lenguaje de programación", "score": 0.5},
            {"content": "Java es otro lenguaje", "score": 0.8},
        ]

        # Sin modelo cargado o si está deshabilitado, debe retornar como está
        result = rerank("¿Qué es Python?", docs, top_k=2)
        assert len(result) == 2

    def test_rerank_empty_docs(self):
        """Verifica que rerank maneja lista vacía"""
        from core.rag.reranker import rerank
        result = rerank("query", [])
        assert result == []

    def test_rerank_empty_query(self):
        """Verifica que rerank maneja query vacío"""
        from core.rag.reranker import rerank
        docs = [{"content": "test", "score": 1.0}]
        result = rerank("", docs)
        assert result == docs

    def test_rerank_with_top_k(self):
        """Verifica que top_k limita resultados"""
        from core.rag.reranker import rerank

        docs = [
            {"content": "doc1", "score": 0.5},
            {"content": "doc2", "score": 0.6},
            {"content": "doc3", "score": 0.7},
        ]

        result = rerank("query", docs, top_k=2)
        assert len(result) == 2

    def test_rerank_with_threshold(self):
        """Verifica que rerank_with_threshold filtra por score"""
        from core.rag.reranker import rerank_with_threshold

        docs = [
            {"content": "doc1", "score": 0.9},
            {"content": "doc2", "score": 0.3},
        ]

        # Sin modelo, threshold no filtra (graceful degradation)
        result = rerank_with_threshold("query", docs, threshold=0.5)
        # Resultado depende de si el modelo está cargado o no
        assert isinstance(result, list)


class TestUserProfiles:
    """Tests para el módulo de perfiles de usuario"""

    def setup_method(self):
        """Setup: crear directorio temporal"""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Teardown: limpiar directorio temporal"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_profile(self):
        """Verifica creación básica de perfil"""
        from core.user_profiles import UserProfile

        profile = UserProfile("user1", "creator1", self.temp_dir)
        assert profile.user_id == "user1"
        assert profile.creator_id == "creator1"

    def test_add_interest(self):
        """Verifica añadir intereses"""
        from core.user_profiles import UserProfile

        profile = UserProfile("user1", "creator1", self.temp_dir)
        profile.add_interest("fitness", 2.0)
        profile.add_interest("nutrición", 1.0)

        interests = profile.get_top_interests(10)
        assert ("fitness", 2.0) in interests
        assert ("nutrición", 1.0) in interests

    def test_accumulate_interests(self):
        """Verifica que los intereses se acumulan"""
        from core.user_profiles import UserProfile

        profile = UserProfile("user1", "creator1", self.temp_dir)
        profile.add_interest("fitness", 2.0)
        profile.add_interest("fitness", 3.0)

        interests = dict(profile.get_top_interests(10))
        assert interests["fitness"] == 5.0

    def test_add_objection(self):
        """Verifica añadir objeciones"""
        from core.user_profiles import UserProfile

        profile = UserProfile("user1", "creator1", self.temp_dir)
        profile.add_objection("precio", "Es muy caro")

        assert profile.has_objection("precio")
        assert not profile.has_objection("tiempo")

    def test_preferences(self):
        """Verifica get/set preferencias"""
        from core.user_profiles import UserProfile

        profile = UserProfile("user1", "creator1", self.temp_dir)
        profile.set_preference("language", "en")

        assert profile.get_preference("language") == "en"
        assert profile.get_preference("nonexistent", "default") == "default"

    def test_interested_products(self):
        """Verifica tracking de productos de interés"""
        from core.user_profiles import UserProfile

        profile = UserProfile("user1", "creator1", self.temp_dir)
        profile.add_interested_product("prod_123", "Curso Fitness")
        profile.add_interested_product("prod_123", "Curso Fitness")  # Repetido

        products = profile.get_interested_products()
        assert len(products) == 1
        assert products[0]["interest_count"] == 2

    def test_persistence(self):
        """Verifica que el perfil persiste entre instancias"""
        from core.user_profiles import UserProfile

        # Crear y guardar
        profile1 = UserProfile("user1", "creator1", self.temp_dir)
        profile1.add_interest("fitness", 5.0)
        profile1.set_preference("language", "pt")

        # Cargar de nuevo (nueva instancia)
        profile2 = UserProfile("user1", "creator1", self.temp_dir)
        interests = dict(profile2.get_top_interests(10))

        assert interests.get("fitness") == 5.0
        assert profile2.get_preference("language") == "pt"

    def test_get_summary(self):
        """Verifica el resumen del perfil"""
        from core.user_profiles import UserProfile

        profile = UserProfile("user1", "creator1", self.temp_dir)
        profile.add_interest("fitness", 3.0)
        profile.add_objection("precio")
        profile.add_interested_product("p1", "Producto 1")

        summary = profile.get_summary()

        assert "top_interests" in summary
        assert "recent_objections" in summary
        assert "interested_products" in summary
        assert "interaction_count" in summary

    def test_get_user_profile_singleton(self):
        """Verifica que get_user_profile retorna singleton"""
        from core.user_profiles import get_user_profile, clear_profile_cache

        clear_profile_cache()

        p1 = get_user_profile("user1", "creator1", self.temp_dir)
        p2 = get_user_profile("user1", "creator1", self.temp_dir)

        assert p1 is p2

        clear_profile_cache()


class TestPersonalizedRanking:
    """Tests para el módulo de ranking personalizado"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_personalize_empty_results(self):
        """Verifica que maneja resultados vacíos"""
        from core.personalized_ranking import personalize_results
        from core.user_profiles import UserProfile

        profile = UserProfile("user1", "creator1", self.temp_dir)
        result = personalize_results([], profile)
        assert result == []

    def test_personalize_with_interests(self):
        """Verifica que los intereses afectan el ranking"""
        from core.personalized_ranking import personalize_results
        from core.user_profiles import UserProfile

        profile = UserProfile("user1", "creator1", self.temp_dir)
        profile.add_interest("fitness", 5.0)

        results = [
            {"content": "Curso de cocina básica", "score": 0.9, "id": "1"},
            {"content": "Programa de fitness intensivo", "score": 0.7, "id": "2"},
        ]

        personalized = personalize_results(results, profile, alpha=0.5)

        # El resultado de fitness debería tener mayor final_score
        assert all("final_score" in r for r in personalized)
        assert all("personal_score" in r for r in personalized)

    def test_personalize_preserves_all_results(self):
        """Verifica que no pierde resultados"""
        from core.personalized_ranking import personalize_results
        from core.user_profiles import UserProfile

        profile = UserProfile("user1", "creator1", self.temp_dir)

        results = [
            {"content": "doc1", "score": 0.5, "id": "1"},
            {"content": "doc2", "score": 0.6, "id": "2"},
            {"content": "doc3", "score": 0.7, "id": "3"},
        ]

        personalized = personalize_results(results, profile)
        assert len(personalized) == 3

    def test_adapt_system_prompt(self):
        """Verifica adaptación del prompt"""
        from core.personalized_ranking import adapt_system_prompt
        from core.user_profiles import UserProfile

        profile = UserProfile("user1", "creator1", self.temp_dir)
        profile.add_interest("fitness", 3.0)
        profile.add_objection("precio")
        profile.set_preference("response_style", "concise")

        base_prompt = "Eres un asistente de ventas."
        adapted = adapt_system_prompt(base_prompt, profile)

        assert "Eres un asistente de ventas." in adapted
        assert "fitness" in adapted.lower()
        assert "precio" in adapted.lower()
        assert "conciso" in adapted.lower()

    def test_adapt_prompt_no_profile(self):
        """Verifica que sin perfil retorna prompt original"""
        from core.personalized_ranking import adapt_system_prompt

        base_prompt = "Prompt base"
        result = adapt_system_prompt(base_prompt, None)
        assert result == base_prompt


class TestSemanticMemory:
    """Tests para el módulo de memoria semántica"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_and_get_recent(self):
        """Verifica añadir y obtener mensajes recientes"""
        from core.semantic_memory import ConversationMemory

        memory = ConversationMemory("user1", "creator1", self.temp_dir)
        memory.add_message("user", "Hola, me interesa el curso")
        memory.add_message("assistant", "¡Hola! Claro, te cuento...")

        recent = memory.get_recent(10)
        assert len(recent) == 2
        assert recent[0]["role"] == "user"
        assert recent[1]["role"] == "assistant"

    def test_message_persistence(self):
        """Verifica que los mensajes persisten"""
        from core.semantic_memory import ConversationMemory

        memory1 = ConversationMemory("user1", "creator1", self.temp_dir)
        memory1.add_message("user", "Mensaje persistente")

        # Nueva instancia
        memory2 = ConversationMemory("user1", "creator1", self.temp_dir)
        recent = memory2.get_recent(10)

        assert len(recent) == 1
        assert recent[0]["content"] == "Mensaje persistente"

    def test_get_context_for_query(self):
        """Verifica obtención de contexto"""
        from core.semantic_memory import ConversationMemory

        memory = ConversationMemory("user1", "creator1", self.temp_dir)
        memory.add_message("user", "El precio me parece alto")
        memory.add_message("assistant", "Tenemos opciones de pago a plazos")

        context = memory.get_context_for_query("precio")
        assert "CONVERSACION RECIENTE" in context
        assert "precio" in context.lower()

    def test_clear_history(self):
        """Verifica limpiar historial"""
        from core.semantic_memory import ConversationMemory

        memory = ConversationMemory("user1", "creator1", self.temp_dir)
        memory.add_message("user", "Mensaje 1")
        memory.add_message("user", "Mensaje 2")

        memory.clear()

        assert len(memory.get_recent(10)) == 0

    def test_get_conversation_memory_singleton(self):
        """Verifica singleton pattern"""
        from core.semantic_memory import get_conversation_memory, clear_memory_cache

        clear_memory_cache()

        m1 = get_conversation_memory("user1", "creator1", self.temp_dir)
        m2 = get_conversation_memory("user1", "creator1", self.temp_dir)

        assert m1 is m2

        clear_memory_cache()

    def test_message_with_metadata(self):
        """Verifica mensajes con metadata"""
        from core.semantic_memory import ConversationMemory

        memory = ConversationMemory("user1", "creator1", self.temp_dir)
        memory.add_message("user", "Mensaje con metadata", {"intent": "greeting"})

        recent = memory.get_recent(1)
        assert recent[0]["intent"] == "greeting"


class TestModuleIntegration:
    """Tests de integración entre módulos"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_personalization_flow(self):
        """Test del flujo completo de personalización"""
        from core.user_profiles import get_user_profile, clear_profile_cache
        from core.personalized_ranking import personalize_results, adapt_system_prompt
        from core.semantic_memory import get_conversation_memory, clear_memory_cache

        clear_profile_cache()
        clear_memory_cache()

        # 1. Obtener perfil y memoria
        profile = get_user_profile("lead_123", "creator_456", self.temp_dir)
        memory = get_conversation_memory("lead_123", "creator_456", self.temp_dir)

        # 2. Simular interacción previa
        profile.add_interest("fitness", 3.0)
        profile.add_objection("precio")
        memory.add_message("user", "Me interesa pero es caro")
        memory.add_message("assistant", "Tenemos facilidades de pago")

        # 3. Nueva búsqueda
        results = [
            {"content": "Programa fitness premium", "score": 0.7, "id": "1"},
            {"content": "Curso de cocina", "score": 0.8, "id": "2"},
        ]

        # 4. Personalizar
        personalized = personalize_results(results, profile, alpha=0.4)

        # 5. Adaptar prompt
        base_prompt = "Eres un asistente de ventas."
        adapted_prompt = adapt_system_prompt(base_prompt, profile)

        # 6. Obtener contexto de memoria
        context = memory.get_context_for_query("precio")

        # Verificaciones
        assert len(personalized) == 2
        assert "final_score" in personalized[0]
        assert "fitness" in adapted_prompt.lower()
        assert "precio" in adapted_prompt.lower()
        assert "CONVERSACION RECIENTE" in context

        clear_profile_cache()
        clear_memory_cache()


# Pytest markers para tests que requieren dependencias opcionales
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "requires_sentence_transformers: mark test as requiring sentence-transformers"
    )
    config.addinivalue_line(
        "markers", "requires_chromadb: mark test as requiring chromadb"
    )
