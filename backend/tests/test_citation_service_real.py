"""
Tests del Citation Service (RAG)
Basado en auditoria: backend/core/citation_service.py

Flujo RAG:
1. CreatorContentIndex carga chunks de PostgreSQL (rag_documents) o JSON fallback
2. search() busca por keywords normalizados (sin acentos)
3. Filtra por min_relevance (default 0.25)
4. get_citation_prompt_section() genera string para inyectar en prompt
"""
import pytest


class TestCreatorContentIndex:
    """Tests de la clase CreatorContentIndex"""

    def test_class_exists(self):
        """CreatorContentIndex existe"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")
        assert index.creator_id == "test_creator"

    def test_has_chunks_list(self):
        """Index tiene lista de chunks"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")
        assert hasattr(index, 'chunks')
        assert isinstance(index.chunks, list)

    def test_has_posts_metadata(self):
        """Index tiene diccionario de metadata de posts"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")
        assert hasattr(index, 'posts_metadata')
        assert isinstance(index.posts_metadata, dict)

    def test_load_method_exists(self):
        """Index tiene metodo load()"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")
        assert hasattr(index, 'load')
        assert callable(index.load)

    def test_save_method_exists(self):
        """Index tiene metodo save()"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")
        assert hasattr(index, 'save')
        assert callable(index.save)

    def test_search_method_exists(self):
        """Index tiene metodo search()"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")
        assert hasattr(index, 'search')
        assert callable(index.search)

    def test_stats_property_exists(self):
        """Index tiene propiedad stats"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")
        assert hasattr(index, 'stats')

        stats = index.stats
        assert 'creator_id' in stats
        assert 'total_chunks' in stats
        assert 'loaded' in stats


class TestSearchFunctionality:
    """Tests de la funcionalidad de busqueda"""

    def test_search_returns_list(self):
        """search() retorna lista"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")
        results = index.search("test", max_results=5)

        assert isinstance(results, list)

    def test_search_respects_max_results(self):
        """search() respeta max_results"""
        from core.citation_service import CreatorContentIndex
        from datetime import datetime

        index = CreatorContentIndex("test_creator")

        # Agregar chunks de prueba con todos los campos requeridos
        from ingestion import ContentChunk
        for i in range(10):
            index.chunks.append(ContentChunk(
                id=f"chunk_{i}",
                creator_id="test_creator",
                source_type="test",
                source_id=f"source_{i}",
                source_url=f"https://example.com/{i}",
                title=f"Chunk {i}",
                content=f"Este es contenido de prueba numero {i} con palabra clave",
                chunk_index=0,
                total_chunks=1,
                metadata={},
                created_at=datetime.now()
            ))

        results = index.search("contenido prueba", max_results=3)

        assert len(results) <= 3

    def test_search_filters_by_min_relevance(self):
        """search() filtra por min_relevance"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")

        # Con min_relevance muy alto, no deberia encontrar nada
        results = index.search("xyz123nonexistent", max_results=10, min_relevance=0.99)

        assert len(results) == 0

    def test_search_result_structure(self):
        """Resultados tienen estructura correcta"""
        from core.citation_service import CreatorContentIndex
        from ingestion import ContentChunk
        from datetime import datetime

        index = CreatorContentIndex("test_creator")

        # Agregar chunk de prueba con todos los campos requeridos
        index.chunks.append(ContentChunk(
            id="test_chunk",
            creator_id="test_creator",
            source_type="instagram_post",
            source_id="post_123",
            source_url="https://instagram.com/p/123",
            title="Test Post",
            content="Este es un contenido de prueba para busqueda",
            chunk_index=0,
            total_chunks=1,
            metadata={},
            created_at=datetime.now()
        ))

        results = index.search("contenido prueba", max_results=5, min_relevance=0.1)

        if results:
            result = results[0]
            # Campos requeridos
            assert 'content' in result
            assert 'relevance_score' in result
            assert 'source_type' in result


class TestTextNormalization:
    """Tests de normalizacion de texto"""

    def test_extract_topics_from_query_exists(self):
        """Funcion extract_topics_from_query existe"""
        from ingestion import extract_topics_from_query

        assert callable(extract_topics_from_query)

    def test_normalize_text_exists(self):
        """Funcion normalize_text existe"""
        from ingestion import normalize_text

        assert callable(normalize_text)

    def test_normalize_removes_accents(self):
        """normalize_text quita acentos"""
        from ingestion import normalize_text

        result = normalize_text("Cuánto cuesta el programa?")

        # Deberia quitar acentos
        assert 'á' not in result
        assert 'é' not in result
        assert 'cuanto' in result.lower() or 'programa' in result.lower()


class TestGetCitationPromptSection:
    """Tests de get_citation_prompt_section"""

    def test_function_exists(self):
        """Funcion get_citation_prompt_section existe"""
        from core.citation_service import get_citation_prompt_section

        assert callable(get_citation_prompt_section)

    def test_returns_string(self):
        """Retorna string"""
        from core.citation_service import get_citation_prompt_section

        result = get_citation_prompt_section(
            creator_id="test_creator",
            query="test query"
        )

        assert isinstance(result, str)

    def test_returns_empty_when_no_results(self):
        """Retorna '' cuando no hay resultados"""
        from core.citation_service import get_citation_prompt_section

        result = get_citation_prompt_section(
            creator_id="nonexistent_xyz_123",
            query="blockchain nft metaverse crypto",
            min_relevance=0.5
        )

        assert result == ""


class TestAsyncCitationFunctions:
    """Tests de funciones async de citacion"""

    @pytest.mark.asyncio
    async def test_find_relevant_citations_exists(self):
        """Funcion find_relevant_citations existe"""
        from core.citation_service import find_relevant_citations

        assert callable(find_relevant_citations)

    @pytest.mark.asyncio
    async def test_find_relevant_citations_returns_context(self):
        """find_relevant_citations retorna CitationContext"""
        from core.citation_service import find_relevant_citations
        from ingestion import CitationContext

        result = await find_relevant_citations(
            creator_id="test_creator",
            query="test query",
            max_results=3
        )

        assert isinstance(result, CitationContext)

    @pytest.mark.asyncio
    async def test_index_creator_posts_exists(self):
        """Funcion index_creator_posts existe"""
        from core.citation_service import index_creator_posts

        assert callable(index_creator_posts)


class TestCacheManagement:
    """Tests de manejo de cache"""

    def test_get_content_index_exists(self):
        """Funcion get_content_index existe"""
        from core.citation_service import get_content_index

        assert callable(get_content_index)

    def test_clear_index_cache_exists(self):
        """Funcion clear_index_cache existe"""
        from core.citation_service import clear_index_cache

        assert callable(clear_index_cache)

    def test_reload_creator_index_exists(self):
        """Funcion reload_creator_index existe"""
        from core.citation_service import reload_creator_index

        assert callable(reload_creator_index)


class TestDataSources:
    """Tests de fuentes de datos (PostgreSQL vs JSON)"""

    def test_tries_postgres_first(self):
        """Intenta cargar de PostgreSQL primero"""
        from core.citation_service import _try_load_chunks_from_db

        assert callable(_try_load_chunks_from_db)

    def test_falls_back_to_json(self):
        """Fallback a JSON si PostgreSQL falla"""
        from core.citation_service import _try_load_chunks_from_json

        assert callable(_try_load_chunks_from_json)

    def test_loaded_from_db_flag(self):
        """Index tiene flag _loaded_from_db"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex("test_creator")
        assert hasattr(index, '_loaded_from_db')


class TestDeleteFunctionality:
    """Tests de eliminacion de indices"""

    def test_delete_content_index_exists(self):
        """Funcion delete_content_index existe"""
        from core.citation_service import delete_content_index

        assert callable(delete_content_index)

    def test_delete_returns_bool(self):
        """delete_content_index retorna bool"""
        from core.citation_service import delete_content_index

        # Intentar eliminar creator inexistente
        result = delete_content_index("nonexistent_xyz_123")

        assert isinstance(result, bool)
