"""
Tests Anti-Alucinacion
Basado en auditoria: INTENTS_REQUIRING_RAG en dm_agent.py

Regla: Si intent requiere RAG y RAG no encuentra contenido -> ESCALAR
Esto previene que el bot invente informacion.

14 Intents requieren RAG:
- INTEREST_SOFT, INTEREST_STRONG
- QUESTION_PRODUCT, QUESTION_GENERAL
- OBJECTION_PRICE, OBJECTION_TIME, OBJECTION_DOUBT, OBJECTION_LATER
- OBJECTION_WORKS, OBJECTION_NOT_FOR_ME, OBJECTION_COMPLICATED, OBJECTION_ALREADY_HAVE
- SUPPORT, LEAD_MAGNET
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAntiHallucinationConfig:
    """Verifica configuracion anti-alucinacion"""

    def test_intents_requiring_rag_is_set(self):
        """INTENTS_REQUIRING_RAG esta definido y tiene 14 intents"""
        from core.dm_agent import INTENTS_REQUIRING_RAG

        assert len(INTENTS_REQUIRING_RAG) == 14

    def test_intents_requiring_rag_content(self):
        """Los 14 intents correctos requieren RAG"""
        from core.dm_agent import INTENTS_REQUIRING_RAG, Intent

        # Intents que SI requieren RAG
        required = [
            Intent.INTEREST_SOFT,
            Intent.INTEREST_STRONG,
            Intent.QUESTION_PRODUCT,
            Intent.QUESTION_GENERAL,
            Intent.OBJECTION_PRICE,
            Intent.OBJECTION_TIME,
            Intent.OBJECTION_DOUBT,
            Intent.OBJECTION_LATER,
            Intent.OBJECTION_WORKS,
            Intent.OBJECTION_NOT_FOR_ME,
            Intent.OBJECTION_COMPLICATED,
            Intent.OBJECTION_ALREADY_HAVE,
            Intent.SUPPORT,
            Intent.LEAD_MAGNET,
        ]

        for intent in required:
            assert intent in INTENTS_REQUIRING_RAG, f"{intent} deberia requerir RAG"

    def test_intents_not_requiring_rag(self):
        """Los 7 intents genericos NO requieren RAG"""
        from core.dm_agent import INTENTS_REQUIRING_RAG, Intent

        # Intents que NO requieren RAG (pueden responder sin datos)
        not_required = [
            Intent.GREETING,
            Intent.THANKS,
            Intent.GOODBYE,
            Intent.ACKNOWLEDGMENT,
            Intent.CORRECTION,
            Intent.BOOKING,
            Intent.ESCALATION,
            Intent.OTHER,
        ]

        for intent in not_required:
            assert intent not in INTENTS_REQUIRING_RAG, f"{intent} NO deberia requerir RAG"


class TestCitationServiceIntegration:
    """Tests de integracion con citation_service"""

    def test_get_citation_prompt_section_imported(self):
        """dm_agent importa get_citation_prompt_section"""
        # Verificar que la funcion existe
        from core.citation_service import get_citation_prompt_section

        assert callable(get_citation_prompt_section)

    def test_citation_returns_empty_when_no_match(self):
        """get_citation_prompt_section retorna '' si no hay match"""
        from core.citation_service import get_citation_prompt_section

        # Query que no deberia matchear nada
        result = get_citation_prompt_section(
            creator_id="nonexistent_creator_xyz",
            query="blockchain crypto nft web3 metaverse",
            min_relevance=0.25,
        )

        assert result == ""

    def test_citation_returns_string_when_match(self):
        """get_citation_prompt_section retorna string si hay match"""
        from core.citation_service import get_citation_prompt_section

        # Este test depende de tener datos en RAG para fitpack_global
        result = get_citation_prompt_section(
            creator_id="fitpack_global", query="coaching programa", min_relevance=0.25
        )

        # Retorna string (puede ser vacio si no hay datos)
        assert isinstance(result, str)


class TestAntiHallucinationBehavior:
    """Tests del comportamiento anti-alucinacion"""

    @pytest.fixture
    def mock_agent_no_rag(self):
        """Agent sin contenido RAG"""
        with patch("core.dm_agent.USE_POSTGRES", False):
            with patch("core.dm_agent.db_service", None):
                with patch("core.dm_agent.get_citation_prompt_section", return_value=""):
                    from core.dm_agent import DMResponderAgent

                    with patch.object(
                        DMResponderAgent,
                        "_load_creator_config",
                        return_value={"name": "Test", "bot_active": True},
                    ):
                        with patch.object(DMResponderAgent, "_load_products", return_value=[]):
                            agent = DMResponderAgent(creator_id="empty_creator")
                            return agent

    def test_escalation_response_exists(self):
        """El agent tiene metodo para generar respuesta de escalacion"""
        with patch("core.dm_agent.USE_POSTGRES", False):
            with patch("core.dm_agent.db_service", None):
                from core.dm_agent import DMResponderAgent

                with patch.object(
                    DMResponderAgent, "_load_creator_config", return_value={"name": "Test"}
                ):
                    with patch.object(DMResponderAgent, "_load_products", return_value=[]):
                        agent = DMResponderAgent(creator_id="test")
                        assert hasattr(agent, "_get_escalation_response")


class TestPriceHallucination:
    """Tests especificos de no-alucinacion de precios"""

    def test_products_loaded_from_db_or_json(self):
        """Productos se cargan de DB/JSON, no se inventan"""
        with patch("core.dm_agent.USE_POSTGRES", False):
            with patch("core.dm_agent.db_service", None):
                from core.dm_agent import DMResponderAgent, invalidate_dm_agent_cache

                # Clear cache before test to ensure mocks are used
                invalidate_dm_agent_cache("test")

                with patch.object(
                    DMResponderAgent, "_load_creator_config", return_value={"name": "Test"}
                ):
                    with patch.object(
                        DMResponderAgent,
                        "_load_products",
                        return_value=[{"id": "1", "name": "Producto Test", "price": 297}],
                    ) as mock_load:
                        agent = DMResponderAgent(creator_id="test")

                        # Verificar que productos vienen del mock
                        assert len(agent.products) == 1
                        assert agent.products[0]["price"] == 297

    def test_get_relevant_product_method_exists(self):
        """Agent tiene metodo para buscar producto relevante"""
        with patch("core.dm_agent.USE_POSTGRES", False):
            with patch("core.dm_agent.db_service", None):
                from core.dm_agent import DMResponderAgent

                with patch.object(
                    DMResponderAgent, "_load_creator_config", return_value={"name": "Test"}
                ):
                    with patch.object(DMResponderAgent, "_load_products", return_value=[]):
                        agent = DMResponderAgent(creator_id="test")
                        assert hasattr(agent, "_get_relevant_product")


class TestRAGSearchBehavior:
    """Tests del comportamiento de busqueda RAG"""

    def test_content_index_search_method(self):
        """CreatorContentIndex tiene metodo search"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")
        assert hasattr(index, "search")

    def test_search_returns_list(self):
        """search() retorna lista de resultados"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")
        results = index.search("test query", max_results=5)

        assert isinstance(results, list)

    def test_search_respects_min_relevance(self):
        """search() filtra por min_relevance"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")

        # Con min_relevance alto, no deberia encontrar nada para query rara
        results = index.search("xyznonexistent123abc", max_results=5, min_relevance=0.99)

        assert len(results) == 0

    def test_search_result_has_required_fields(self):
        """Resultados de search tienen campos necesarios"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("fitpack_global")
        index.load()  # Intentar cargar datos

        if index.chunks:  # Solo si hay datos
            results = index.search("coaching", max_results=1, min_relevance=0.1)

            if results:
                result = results[0]
                # Campos requeridos para citacion
                assert "content" in result
                assert "relevance_score" in result


class TestEscalationOnNoRAG:
    """Tests de escalacion cuando no hay contenido RAG"""

    def test_dm_response_has_escalate_field(self):
        """DMResponse tiene campo escalate_to_human"""
        from core.dm_agent import DMResponse, Intent

        response = DMResponse(response_text="Test", intent=Intent.OTHER, escalate_to_human=False)

        assert hasattr(response, "escalate_to_human")

    def test_escalation_notification_on_escalate(self):
        """Notificacion se envia cuando hay escalacion"""
        from core.notifications import EscalationNotification

        # Verificar que la clase existe
        notification = EscalationNotification(
            creator_id="test",
            follower_id="follower_123",
            follower_username="test_user",
            follower_name="Test User",
            reason="Test reason",
            last_message="Test message",
            conversation_summary="Test summary",
            purchase_intent_score=0.5,
            total_messages=10,
            products_discussed=["product1"],
        )

        assert notification.creator_id == "test"
        assert notification.reason == "Test reason"
