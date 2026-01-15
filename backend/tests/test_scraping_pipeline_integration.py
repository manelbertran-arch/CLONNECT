"""
Tests de Integración: Scraping Pipeline + RAG + Anti-Alucinación

Verifica:
1. OAuth scraper selection (MetaGraphAPI vs Instaloader)
2. Scraping → PostgreSQL (instagram_posts)
3. Posts → RAG Chunks (content_chunks + embeddings)
4. RAG Search funciona
5. Anti-Alucinación End-to-End
"""

import pytest
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Optional

# Set test environment before imports
os.environ["DATABASE_URL"] = ""
os.environ["TESTING"] = "true"


# =============================================================================
# Mock Classes
# =============================================================================

@dataclass
class MockInstagramPost:
    """Mock de un post de Instagram"""
    post_id: str
    caption: str
    permalink: str
    post_type: str = "IMAGE"
    media_url: str = "https://example.com/image.jpg"
    thumbnail_url: str = None
    timestamp: datetime = None
    likes_count: int = 100
    comments_count: int = 10
    hashtags: List[str] = None
    mentions: List[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        if self.hashtags is None:
            self.hashtags = []
        if self.mentions is None:
            self.mentions = []


@dataclass
class MockCreator:
    """Mock de un Creator con/sin OAuth"""
    id: str = "test-creator-uuid"
    name: str = "test_creator"
    instagram_token: Optional[str] = None
    instagram_user_id: Optional[str] = None
    instagram_page_id: Optional[str] = None


def create_mock_posts(count: int = 5, with_empty_caption: bool = False) -> List[MockInstagramPost]:
    """Crea posts de prueba"""
    posts = []
    for i in range(count):
        caption = "" if (i == 0 and with_empty_caption) else f"Este es el post número {i+1} con contenido útil sobre fitness y entrenamiento personal."
        posts.append(MockInstagramPost(
            post_id=f"post_{i+1}",
            caption=caption,
            permalink=f"https://instagram.com/p/ABC{i+1}",
            post_type="IMAGE" if i % 2 == 0 else "VIDEO",
            likes_count=100 + i * 10,
            comments_count=10 + i,
            hashtags=["fitness", "training"] if i % 2 == 0 else [],
            mentions=["@user1"] if i % 3 == 0 else []
        ))
    return posts


# =============================================================================
# TEST GROUP 1: OAuth Scraper Selection
# =============================================================================

class TestOAuthScraperSelection:
    """Tests para verificar que se selecciona el scraper correcto"""

    @pytest.mark.asyncio
    async def test_uses_meta_api_when_token_exists(self):
        """Si creator tiene instagram_token → MetaGraphAPIScraper"""
        from ingestion.v2.instagram_ingestion import InstagramIngestionV2

        # Create ingestion with OAuth credentials
        pipeline = InstagramIngestionV2(
            access_token="valid_access_token_123",
            instagram_business_id="17841407135263418"
        )

        # Verify credentials are stored
        assert pipeline.access_token == "valid_access_token_123"
        assert pipeline.instagram_business_id == "17841407135263418"

        # Mock the Meta API scraper
        mock_posts = create_mock_posts(3)

        with patch('ingestion.instagram_scraper.MetaGraphAPIScraper') as MockMetaScraper:
            mock_instance = Mock()
            mock_instance.get_posts = AsyncMock(return_value=mock_posts)
            MockMetaScraper.return_value = mock_instance

            # Call the internal scrape method
            posts = await pipeline._scrape_instagram("test_user", 10)

            # Verify Meta API was called (not Instaloader)
            MockMetaScraper.assert_called_once_with(
                access_token="valid_access_token_123",
                instagram_business_id="17841407135263418"
            )
            assert len(posts) == 3

    @pytest.mark.asyncio
    async def test_falls_back_to_instaloader_without_token(self):
        """Si creator NO tiene token → InstaloaderScraper"""
        from ingestion.v2.instagram_ingestion import InstagramIngestionV2

        # Create ingestion WITHOUT OAuth credentials
        pipeline = InstagramIngestionV2(
            access_token=None,
            instagram_business_id=None
        )

        mock_posts = create_mock_posts(3)

        with patch('ingestion.instagram_scraper.InstaloaderScraper') as MockInstaloader:
            mock_instance = Mock()
            mock_instance.get_posts = Mock(return_value=mock_posts)
            MockInstaloader.return_value = mock_instance

            posts = await pipeline._scrape_instagram("test_user", 10)

            # Verify Instaloader was called
            MockInstaloader.assert_called_once()
            mock_instance.get_posts.assert_called_once()
            assert len(posts) == 3

    @pytest.mark.asyncio
    async def test_falls_back_when_meta_api_fails(self):
        """Si Meta API falla → Fallback a Instaloader"""
        from ingestion.v2.instagram_ingestion import InstagramIngestionV2

        pipeline = InstagramIngestionV2(
            access_token="valid_token",
            instagram_business_id="12345"
        )

        mock_posts = create_mock_posts(2)

        with patch('ingestion.instagram_scraper.MetaGraphAPIScraper') as MockMetaScraper:
            # Meta API fails
            mock_meta = Mock()
            mock_meta.get_posts = AsyncMock(side_effect=Exception("API Error"))
            MockMetaScraper.return_value = mock_meta

            with patch('ingestion.instagram_scraper.InstaloaderScraper') as MockInstaloader:
                # Instaloader works
                mock_insta = Mock()
                mock_insta.get_posts = Mock(return_value=mock_posts)
                MockInstaloader.return_value = mock_insta

                posts = await pipeline._scrape_instagram("test_user", 10)

                # Should fallback to Instaloader
                MockInstaloader.assert_called_once()
                assert len(posts) == 2


# =============================================================================
# TEST GROUP 2: Scraping → PostgreSQL
# =============================================================================

class TestScrapingToPostgreSQL:
    """Tests para verificar que los posts se guardan correctamente"""

    def test_sanity_check_rejects_empty_caption(self):
        """Caption vacío = post rechazado"""
        from ingestion.v2.instagram_ingestion import InstagramPostSanityChecker

        checker = InstagramPostSanityChecker()

        # Post con caption vacío
        empty_post = MockInstagramPost(
            post_id="empty_1",
            caption="",
            permalink="https://instagram.com/p/empty"
        )

        result = checker.check_post(empty_post)

        assert result.passed is False
        assert result.checks['caption_not_empty'] is False
        assert "vacío" in result.rejection_reason.lower() or "corto" in result.rejection_reason.lower()

    def test_sanity_check_rejects_short_caption(self):
        """Caption muy corto (<10 chars) = rechazado"""
        from ingestion.v2.instagram_ingestion import InstagramPostSanityChecker

        checker = InstagramPostSanityChecker()

        short_post = MockInstagramPost(
            post_id="short_1",
            caption="Hey!",  # Solo 4 chars
            permalink="https://instagram.com/p/short"
        )

        result = checker.check_post(short_post)

        assert result.passed is False
        assert result.checks['caption_not_empty'] is False

    def test_sanity_check_rejects_duplicate_post_id(self):
        """Post duplicado no se guarda 2 veces"""
        from ingestion.v2.instagram_ingestion import InstagramPostSanityChecker

        checker = InstagramPostSanityChecker()

        post1 = MockInstagramPost(
            post_id="duplicate_123",
            caption="Este es un post válido con contenido suficiente",
            permalink="https://instagram.com/p/dup1"
        )

        post2 = MockInstagramPost(
            post_id="duplicate_123",  # Mismo ID
            caption="Este es otro post válido con contenido diferente",
            permalink="https://instagram.com/p/dup2"
        )

        # Primer post pasa
        result1 = checker.check_post(post1)
        assert result1.passed is True

        # Segundo post (duplicado) falla
        result2 = checker.check_post(post2)
        assert result2.passed is False
        assert result2.checks['not_duplicate'] is False
        assert "duplicado" in result2.rejection_reason.lower()

    def test_sanity_check_rejects_only_hashtags(self):
        """Post con solo hashtags = rechazado (no útil)"""
        from ingestion.v2.instagram_ingestion import InstagramPostSanityChecker

        checker = InstagramPostSanityChecker()

        hashtag_only = MockInstagramPost(
            post_id="hashtag_1",
            caption="#fitness #gym #workout #training #motivation",
            permalink="https://instagram.com/p/hashtag"
        )

        result = checker.check_post(hashtag_only)

        assert result.passed is False
        assert result.checks['useful_content'] is False

    def test_sanity_check_accepts_valid_post(self):
        """Post válido pasa todos los checks"""
        from ingestion.v2.instagram_ingestion import InstagramPostSanityChecker

        checker = InstagramPostSanityChecker()

        valid_post = MockInstagramPost(
            post_id="valid_123",
            caption="Hoy quiero compartir con ustedes mi rutina de entrenamiento favorita para ganar fuerza y masa muscular.",
            permalink="https://instagram.com/p/valid123"
        )

        result = checker.check_post(valid_post)

        assert result.passed is True
        assert all(result.checks.values())
        assert result.rejection_reason is None

    def test_convert_posts_to_db_format(self):
        """Posts se convierten correctamente al formato de DB"""
        from ingestion.v2.instagram_ingestion import InstagramIngestionV2

        pipeline = InstagramIngestionV2()
        posts = create_mock_posts(2)

        db_format = pipeline._convert_posts_to_db_format(posts)

        assert len(db_format) == 2

        for i, post_data in enumerate(db_format):
            assert 'post_id' in post_data
            assert 'caption' in post_data
            assert 'permalink' in post_data
            assert 'media_type' in post_data
            assert post_data['permalink'].startswith('https://instagram.com')


# =============================================================================
# TEST GROUP 3: Posts → RAG Chunks
# =============================================================================

class TestPostsToRAGChunks:
    """Tests para verificar conversión a chunks RAG"""

    def test_posts_converted_to_content_chunks(self):
        """Posts → chunks en content_chunks format"""
        from ingestion.v2.instagram_ingestion import InstagramIngestionV2

        pipeline = InstagramIngestionV2()
        posts = create_mock_posts(3)

        chunks = pipeline._create_content_chunks("test_creator", posts)

        assert len(chunks) == 3

        for chunk in chunks:
            assert 'chunk_id' in chunk
            assert 'creator_id' in chunk
            assert 'content' in chunk
            assert 'source_type' in chunk
            assert 'source_url' in chunk
            assert chunk['source_type'] == 'instagram_post'

    def test_chunk_has_source_url(self):
        """Anti-alucinación: cada chunk tiene source_url"""
        from ingestion.v2.instagram_ingestion import InstagramIngestionV2

        pipeline = InstagramIngestionV2()
        posts = create_mock_posts(2)

        chunks = pipeline._create_content_chunks("test_creator", posts)

        for chunk in chunks:
            # CRÍTICO: source_url debe existir para citas
            assert 'source_url' in chunk
            assert chunk['source_url'] is not None
            assert chunk['source_url'].startswith('https://instagram.com')

    def test_chunk_has_metadata(self):
        """Chunks tienen metadata para contexto"""
        from ingestion.v2.instagram_ingestion import InstagramIngestionV2

        pipeline = InstagramIngestionV2()
        posts = create_mock_posts(1)

        chunks = pipeline._create_content_chunks("test_creator", posts)

        chunk = chunks[0]
        assert 'metadata' in chunk
        assert 'post_type' in chunk['metadata']
        assert 'likes' in chunk['metadata']
        assert 'hashtags' in chunk['metadata']

    def test_chunk_id_is_deterministic(self):
        """Chunk ID es determinístico (mismo input → mismo ID)"""
        from ingestion.v2.instagram_ingestion import InstagramIngestionV2

        pipeline = InstagramIngestionV2()
        posts = create_mock_posts(1)

        chunks1 = pipeline._create_content_chunks("test_creator", posts)
        chunks2 = pipeline._create_content_chunks("test_creator", posts)

        # Mismo input debe generar mismo chunk_id
        assert chunks1[0]['chunk_id'] == chunks2[0]['chunk_id']


# =============================================================================
# TEST GROUP 4: RAG Search
# =============================================================================

class TestRAGSearch:
    """Tests para verificar búsqueda RAG"""

    def test_semantic_rag_fallback_search(self):
        """Fallback search funciona sin embeddings"""
        from core.rag.semantic import SemanticRAG

        rag = SemanticRAG()

        # Add documents
        rag.add_document(
            doc_id="doc1",
            text="Rutina de entrenamiento para ganar masa muscular con ejercicios compuestos",
            metadata={"creator_id": "test_creator"}
        )
        rag.add_document(
            doc_id="doc2",
            text="Consejos de nutrición para deportistas y atletas",
            metadata={"creator_id": "test_creator"}
        )
        rag.add_document(
            doc_id="doc3",
            text="Recetas de cocina vegana fáciles",
            metadata={"creator_id": "other_creator"}
        )

        # Search (without OpenAI key, uses fallback)
        results = rag._fallback_search("entrenamiento muscular", top_k=5, creator_id="test_creator")

        assert len(results) >= 1
        assert results[0]['doc_id'] == 'doc1'  # Most relevant
        # Should filter out other_creator's docs
        for r in results:
            assert r['metadata']['creator_id'] == 'test_creator'

    def test_citation_service_keyword_search(self):
        """Citation service puede buscar por keywords"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex(creator_id="test_creator")

        # Add posts
        index.add_post(
            post_id="post1",
            caption="Hoy vamos a hablar sobre proteina whey y sus beneficios para el entrenamiento",
            post_type="instagram_post",
            url="https://instagram.com/p/ABC123"
        )
        index.add_post(
            post_id="post2",
            caption="Rutina de piernas para principiantes en el gimnasio",
            post_type="instagram_post",
            url="https://instagram.com/p/DEF456"
        )

        # Search (uses normalized keywords without accents)
        results = index.search("proteina whey", max_results=5)

        assert len(results) >= 1
        # First result should be about protein
        assert "proteina" in results[0]['content'].lower() or "whey" in results[0]['content'].lower()

    def test_search_returns_source_url(self):
        """Resultados incluyen source_url para citas"""
        from core.citation_service import CreatorContentIndex

        index = CreatorContentIndex(creator_id="test_creator")

        index.add_post(
            post_id="post1",
            caption="Contenido sobre entrenamiento funcional y ejercicios compuestos",
            post_type="instagram_post",
            url="https://instagram.com/p/TEST123"
        )

        results = index.search("entrenamiento funcional", max_results=5)

        assert len(results) >= 1
        # CRÍTICO: source_url debe existir para anti-alucinación
        assert 'source_url' in results[0]
        assert results[0]['source_url'] == "https://instagram.com/p/TEST123"


# =============================================================================
# TEST GROUP 5: Anti-Alucinación End-to-End
# =============================================================================

class TestAntiHallucination:
    """Tests para verificar sistema anti-alucinación"""

    def test_ingestion_result_tracks_all_stats(self):
        """IngestionResult trackea todas las estadísticas"""
        from ingestion.v2.instagram_ingestion import InstagramIngestionResult

        result = InstagramIngestionResult(
            success=True,
            creator_id="test",
            instagram_username="test_user"
        )

        result.posts_scraped = 10
        result.posts_passed_sanity = 8
        result.posts_rejected = 2
        result.posts_saved_db = 8
        result.rag_chunks_created = 8

        result_dict = result.to_dict()

        assert result_dict['success'] is True
        assert result_dict['posts_scraped'] == 10
        assert result_dict['posts_passed_sanity'] == 8
        assert result_dict['posts_rejected'] == 2
        assert result_dict['rag_chunks_created'] == 8

    @pytest.mark.asyncio
    async def test_full_ingestion_pipeline_creates_chunks(self):
        """Pipeline completo crea chunks con source_url"""
        from ingestion.v2.instagram_ingestion import InstagramIngestionV2

        pipeline = InstagramIngestionV2()
        mock_posts = create_mock_posts(3)

        # Mock the scraper
        with patch.object(pipeline, '_scrape_instagram', new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = mock_posts

            # Mock DB saves
            with patch.object(pipeline, '_clean_previous_data', new_callable=AsyncMock):
                with patch.object(pipeline, '_save_posts_to_db', new_callable=AsyncMock) as mock_save_posts:
                    mock_save_posts.return_value = 3
                    with patch.object(pipeline, '_save_chunks_to_db', new_callable=AsyncMock) as mock_save_chunks:
                        mock_save_chunks.return_value = 3

                        result = await pipeline.ingest(
                            creator_id="test_creator",
                            instagram_username="test_user",
                            max_posts=10,
                            clean_before=True
                        )

                        assert result.success is True
                        assert result.posts_scraped == 3
                        assert result.posts_passed_sanity == 3
                        assert result.rag_chunks_created == 3

    def test_empty_caption_not_indexed(self):
        """Posts con caption vacío no se indexan (previene chunks vacíos)"""
        from ingestion.v2.instagram_ingestion import InstagramPostSanityChecker

        checker = InstagramPostSanityChecker()

        # Posts mixtos
        posts = [
            MockInstagramPost(post_id="1", caption="", permalink="url1"),
            MockInstagramPost(post_id="2", caption="Contenido válido sobre fitness", permalink="url2"),
            MockInstagramPost(post_id="3", caption="   ", permalink="url3"),  # Solo espacios
        ]

        valid_posts = [p for p in posts if checker.check_post(p).passed]

        # Solo 1 post debería pasar
        assert len(valid_posts) == 1
        assert valid_posts[0].post_id == "2"


# =============================================================================
# TEST GROUP 6: Auto Configurator Integration
# =============================================================================

class TestAutoConfiguratorIntegration:
    """Tests para verificar que AutoConfigurator pasa credenciales OAuth"""

    @pytest.mark.asyncio
    async def test_auto_configurator_fetches_oauth_credentials(self):
        """AutoConfigurator obtiene credenciales OAuth del Creator"""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()

        # Mock the database query - patch where it's imported, not where it's defined
        mock_creator = MockCreator(
            id="uuid-123",
            name="test_creator",
            instagram_token="oauth_token_abc",
            instagram_user_id="17841407135263418",
            instagram_page_id="17841407135263418"
        )

        # Patch at the api.database level since that's where it's imported from
        with patch('api.database.get_db_session') as mock_db_session:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = mock_creator
            mock_db_session.return_value = mock_db

            with patch('ingestion.v2.instagram_ingestion.ingest_instagram_v2', new_callable=AsyncMock) as mock_ingest:
                mock_ingest.return_value = MagicMock(
                    to_dict=lambda: {"success": True, "posts_scraped": 5}
                )

                result = await configurator._scrape_instagram(
                    creator_id="test_creator",
                    instagram_username="test_user",
                    max_posts=10
                )

                # Verify ingest was called with OAuth credentials
                mock_ingest.assert_called_once()
                call_kwargs = mock_ingest.call_args.kwargs
                assert call_kwargs.get('access_token') == "oauth_token_abc"
                assert call_kwargs.get('instagram_business_id') == "17841407135263418"

    @pytest.mark.asyncio
    async def test_auto_configurator_passes_none_without_oauth(self):
        """Si Creator no tiene OAuth, pasa None al pipeline"""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()

        # Creator sin OAuth
        mock_creator = MockCreator(
            id="uuid-456",
            name="no_oauth_creator",
            instagram_token=None,
            instagram_user_id=None,
            instagram_page_id=None
        )

        with patch('api.database.get_db_session') as mock_db_session:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = mock_creator
            mock_db_session.return_value = mock_db

            with patch('ingestion.v2.instagram_ingestion.ingest_instagram_v2', new_callable=AsyncMock) as mock_ingest:
                mock_ingest.return_value = MagicMock(
                    to_dict=lambda: {"success": True, "posts_scraped": 3}
                )

                result = await configurator._scrape_instagram(
                    creator_id="no_oauth_creator",
                    instagram_username="test_user",
                    max_posts=10
                )

                # Verify ingest was called with None credentials
                mock_ingest.assert_called_once()
                call_kwargs = mock_ingest.call_args.kwargs
                assert call_kwargs.get('access_token') is None
                assert call_kwargs.get('instagram_business_id') is None


# =============================================================================
# TEST GROUP 7: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests para casos extremos"""

    def test_sanity_checker_reset(self):
        """Sanity checker se puede resetear para nueva ingestion"""
        from ingestion.v2.instagram_ingestion import InstagramPostSanityChecker

        checker = InstagramPostSanityChecker()

        post1 = MockInstagramPost(
            post_id="same_id",
            caption="Contenido válido número uno",
            permalink="url1"
        )

        # Primera vez pasa
        assert checker.check_post(post1).passed is True

        # Segunda vez falla (duplicado)
        assert checker.check_post(post1).passed is False

        # Reset
        checker.reset()

        # Después de reset, pasa de nuevo
        assert checker.check_post(post1).passed is True

    def test_future_date_rejected(self):
        """Posts con fecha futura son rechazados"""
        from ingestion.v2.instagram_ingestion import InstagramPostSanityChecker
        from datetime import timedelta

        checker = InstagramPostSanityChecker()

        future_post = MockInstagramPost(
            post_id="future_1",
            caption="Este post tiene una fecha futura inválida",
            permalink="url",
            timestamp=datetime.now(timezone.utc) + timedelta(days=30)
        )

        result = checker.check_post(future_post)

        assert result.passed is False
        assert result.checks['valid_date'] is False

    def test_very_old_post_rejected(self):
        """Posts muy antiguos (>3 años) son rechazados"""
        from ingestion.v2.instagram_ingestion import InstagramPostSanityChecker
        from datetime import timedelta

        checker = InstagramPostSanityChecker()

        old_post = MockInstagramPost(
            post_id="old_1",
            caption="Este post es muy antiguo y no debería indexarse",
            permalink="url",
            timestamp=datetime.now(timezone.utc) - timedelta(days=365 * 4)  # 4 años
        )

        result = checker.check_post(old_post)

        assert result.passed is False
        assert result.checks['valid_date'] is False


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
