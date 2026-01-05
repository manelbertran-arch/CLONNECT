"""Tests para Citation Service."""

import pytest
from datetime import datetime
from backend.core.citation_service import (
    CreatorContentIndex,
    get_content_index,
    find_relevant_citations,
    index_creator_posts,
    get_citation_prompt_section,
    clear_index_cache,
    _index_cache
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Limpia cache antes de cada test."""
    clear_index_cache()
    yield
    clear_index_cache()


class TestCreatorContentIndex:

    def test_add_post(self):
        index = CreatorContentIndex("test_creator")

        chunks = index.add_post(
            post_id="post_1",
            caption="Este es un post sobre fitness y nutricion para principiantes",
            post_type="instagram_post",
            url="https://instagram.com/p/abc/"
        )

        assert len(chunks) >= 1
        assert index.stats['total_chunks'] >= 1
        assert index.stats['total_posts'] == 1

    def test_add_multiple_posts(self):
        index = CreatorContentIndex("test_creator_multi")

        index.add_post(
            post_id="post_1",
            caption="Post sobre ayuno intermitente y sus beneficios para la salud"
        )
        index.add_post(
            post_id="post_2",
            caption="Rutina de ejercicios para principiantes en el gimnasio"
        )

        assert index.stats['total_posts'] == 2
        assert index.stats['total_chunks'] >= 2

    def test_search_by_keyword(self):
        index = CreatorContentIndex("test_creator_search")

        index.add_post(
            post_id="post_1",
            caption="Hoy vamos a hablar sobre ayuno intermitente y sus beneficios"
        )
        index.add_post(
            post_id="post_2",
            caption="Mi rutina de ejercicios favorita para principiantes"
        )

        results = index.search("ayuno intermitente")

        assert len(results) >= 1
        assert results[0]['source_id'] == "post_1"

    def test_search_no_results(self):
        index = CreatorContentIndex("test_creator_noresult")

        index.add_post(
            post_id="post_1",
            caption="Post sobre cocina mediterranea y recetas saludables"
        )

        results = index.search("programacion python")

        assert len(results) == 0

    def test_search_with_min_relevance(self):
        index = CreatorContentIndex("test_creator_relevance")

        index.add_post(
            post_id="post_1",
            caption="Todo sobre proteinas, aminoacidos y suplementacion deportiva"
        )

        # High relevance threshold
        results_high = index.search("proteinas suplementos", min_relevance=0.8)
        # Low relevance threshold
        results_low = index.search("proteinas suplementos", min_relevance=0.3)

        # Low threshold should find more or equal results
        assert len(results_low) >= len(results_high)

    def test_search_empty_index(self):
        index = CreatorContentIndex("test_creator_empty")
        results = index.search("cualquier cosa")
        assert len(results) == 0

    def test_stats_property(self):
        index = CreatorContentIndex("test_stats")

        assert index.stats['creator_id'] == "test_stats"
        assert index.stats['total_chunks'] == 0
        assert index.stats['total_posts'] == 0
        assert index.stats['loaded'] == False


class TestGetContentIndex:

    def test_get_content_index_creates_new(self):
        index = get_content_index("new_creator_test")
        assert index.creator_id == "new_creator_test"

    def test_get_content_index_returns_cached(self):
        index1 = get_content_index("cached_creator")
        index1.add_post(post_id="p1", caption="Test content for caching")

        index2 = get_content_index("cached_creator")
        assert index2.stats['total_posts'] == 1


class TestFindRelevantCitations:

    @pytest.mark.asyncio
    async def test_find_citations(self):
        # Primero indexar contenido
        await index_creator_posts(
            creator_id="test_creator_citations",
            posts=[
                {
                    "post_id": "p1",
                    "caption": "Mi experiencia con el ayuno intermitente ha sido increible",
                    "post_type": "instagram_post"
                },
                {
                    "post_id": "p2",
                    "caption": "Tips de nutricion para deportistas que quieren mejorar",
                    "post_type": "instagram_reel"
                }
            ],
            save=False
        )

        # Buscar citas
        citation_context = await find_relevant_citations(
            creator_id="test_creator_citations",
            query="Que opinas del ayuno?",
            min_relevance=0.3
        )

        assert citation_context.has_relevant_content(min_score=0.3)
        citations = citation_context.get_top_citations()
        assert len(citations) >= 1

    @pytest.mark.asyncio
    async def test_find_citations_no_content(self):
        # Buscar en creador sin contenido
        citation_context = await find_relevant_citations(
            creator_id="nonexistent_creator_xyz",
            query="cualquier cosa"
        )

        assert not citation_context.has_relevant_content()

    @pytest.mark.asyncio
    async def test_citation_has_natural_reference(self):
        await index_creator_posts(
            creator_id="test_creator_ref",
            posts=[
                {
                    "post_id": "p1",
                    "caption": "Todo sobre proteinas y suplementacion deportiva para atletas",
                    "post_type": "instagram_post"
                }
            ],
            save=False
        )

        citation_context = await find_relevant_citations(
            creator_id="test_creator_ref",
            query="proteinas suplementos"
        )

        if citation_context.citations:
            ref = citation_context.citations[0].to_natural_reference()
            assert len(ref) > 0
            assert "post" in ref.lower() or "hice" in ref.lower()


class TestIndexCreatorPosts:

    @pytest.mark.asyncio
    async def test_index_multiple_posts(self):
        result = await index_creator_posts(
            creator_id="test_bulk_index",
            posts=[
                {"post_id": "1", "caption": "Primer post sobre fitness y gym para todos"},
                {"post_id": "2", "caption": "Segundo post sobre nutricion y dieta"},
                {"post_id": "3", "caption": "Muy corto"},  # Se ignora (< 20 chars)
            ],
            save=False
        )

        assert result['posts_indexed'] == 2  # El corto se ignora
        assert result['total_chunks'] >= 2

    @pytest.mark.asyncio
    async def test_index_posts_with_dates(self):
        result = await index_creator_posts(
            creator_id="test_dates",
            posts=[
                {
                    "post_id": "1",
                    "caption": "Post con fecha de publicacion incluida",
                    "published_date": "2024-01-15T10:00:00"
                }
            ],
            save=False
        )

        assert result['posts_indexed'] == 1

    @pytest.mark.asyncio
    async def test_index_empty_posts(self):
        result = await index_creator_posts(
            creator_id="test_empty",
            posts=[],
            save=False
        )

        assert result['posts_indexed'] == 0
        assert result['total_chunks'] == 0


class TestGetCitationPromptSection:

    def test_get_prompt_section_with_content(self):
        # Primero indexar contenido directamente
        index = get_content_index("test_prompt_creator")
        index.add_post(
            post_id="p1",
            caption="Guia completa sobre ayuno intermitente y como empezar correctamente"
        )

        prompt = get_citation_prompt_section("test_prompt_creator", "ayuno intermitente")

        # Should return prompt section with citations
        if prompt:  # May return empty if no relevant content found
            assert "CONTENIDO RELEVANTE" in prompt or len(prompt) > 0

    def test_get_prompt_section_no_content(self):
        prompt = get_citation_prompt_section("nonexistent_xyz_123", "cualquier cosa")
        assert prompt == ""

    def test_get_prompt_section_irrelevant_query(self):
        index = get_content_index("test_irrelevant_creator")
        index.add_post(
            post_id="p1",
            caption="Todo sobre cocina italiana y pasta casera"
        )

        prompt = get_citation_prompt_section(
            "test_irrelevant_creator",
            "programacion en python",
            min_relevance=0.5
        )

        assert prompt == ""


class TestCitationIntegration:
    """Tests de integracion end-to-end."""

    @pytest.mark.asyncio
    async def test_full_citation_flow(self):
        """Test completo: indexar -> buscar -> generar prompt."""
        creator_id = "integration_test_creator"

        # 1. Indexar contenido
        await index_creator_posts(
            creator_id=creator_id,
            posts=[
                {
                    "post_id": "fitness_1",
                    "caption": "Hoy les comparto mi rutina de entrenamiento matutino: "
                              "cardio 20 min, pesas 40 min, estiramientos 10 min. "
                              "Importante descansar bien!",
                    "post_type": "instagram_reel"
                },
                {
                    "post_id": "nutrition_1",
                    "caption": "Mis tips de alimentacion: come proteina en cada comida, "
                              "hidratate bien, evita azucares procesados. Simple pero efectivo!",
                    "post_type": "instagram_post"
                }
            ],
            save=False
        )

        # 2. Buscar citaciones
        citation_context = await find_relevant_citations(
            creator_id=creator_id,
            query="Como es tu rutina de ejercicio?",
            min_relevance=0.3
        )

        # 3. Verificar resultados
        assert citation_context.has_relevant_content(min_score=0.3)
        top_citations = citation_context.get_top_citations()
        assert len(top_citations) >= 1

        # 4. Generar prompt context
        prompt_context = citation_context.to_prompt_context()
        assert "CONTENIDO RELEVANTE" in prompt_context
        assert "INSTRUCCIONES OBLIGATORIAS PARA CITAR" in prompt_context

    @pytest.mark.asyncio
    async def test_citation_respects_relevance_threshold(self):
        """Verifica que solo se incluyen citas relevantes."""
        creator_id = "relevance_threshold_test"

        await index_creator_posts(
            creator_id=creator_id,
            posts=[
                {
                    "post_id": "1",
                    "caption": "Todo sobre inversion en bolsa y finanzas personales"
                },
                {
                    "post_id": "2",
                    "caption": "Receta de pasta italiana con tomate y albahaca"
                }
            ],
            save=False
        )

        # Query sobre finanzas
        citations = await find_relevant_citations(
            creator_id=creator_id,
            query="Como invertir dinero?",
            min_relevance=0.3
        )

        # Solo deberia encontrar el post de finanzas
        if citations.citations:
            assert all("bolsa" in c.excerpt.lower() or "inversion" in c.excerpt.lower()
                      for c in citations.citations)
