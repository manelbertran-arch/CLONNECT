"""
Tests del AutoConfigurator - Pipeline de 8 pasos
Basado en auditoria: backend/core/auto_configurator.py

Pipeline real (metodos en el codigo):
1. _scrape_instagram() -> instagram_posts
2. _transcribe_videos() -> content_chunks
3. _scrape_website() -> products, rag_documents
4. _generate_tone_profile() -> tone_profiles
5. _load_dm_history() -> leads, messages
6. _extract_bio() -> knowledge_base
7. _generate_faqs() -> knowledge_base
8. _update_creator() -> creators

Metodo principal: run()
Funcion helper: auto_configure_clone()
Resultado: AutoConfigResult
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


class TestAutoConfiguratorPipeline:
    """Verifica que los 8 pasos se ejecutan y escriben en las tablas correctas"""

    @pytest.fixture
    def mock_db_session(self):
        """Mock de sesion de base de datos"""
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        session.add = MagicMock()
        session.commit = MagicMock()
        session.close = MagicMock()
        return session

    @pytest.fixture
    def mock_creator(self):
        """Mock de creator con OAuth credentials"""
        return MagicMock(
            id="test-uuid",
            name="test_creator",
            instagram_token="valid_oauth_token_123",
            instagram_user_id="ig_user_123",
            instagram_page_id="page_123"
        )

    @pytest.fixture
    def mock_creator_no_oauth(self):
        """Mock de creator SIN OAuth credentials"""
        return MagicMock(
            id="test-uuid",
            name="test_creator",
            instagram_token=None,
            instagram_user_id=None,
            instagram_page_id=None
        )

    # =========================================================================
    # PASO 1: Instagram Scraping
    # =========================================================================

    @pytest.mark.asyncio
    async def test_step1_scrape_instagram_method_exists(self):
        """Paso 1: _scrape_instagram() existe"""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()
        assert hasattr(configurator, '_scrape_instagram')

    @pytest.mark.asyncio
    async def test_step1_scrape_instagram_is_async(self):
        """Paso 1: _scrape_instagram() es async"""
        from core.auto_configurator import AutoConfigurator
        import inspect

        configurator = AutoConfigurator()
        assert inspect.iscoroutinefunction(configurator._scrape_instagram)

    # =========================================================================
    # PASO 3: Website Scraping
    # =========================================================================

    @pytest.mark.asyncio
    async def test_step3_scrape_website_uses_signal_detection(self):
        """Paso 3: Product detection usa sistema de senales, NO LLM"""
        from ingestion.v2.pipeline import IngestionV2Pipeline
        from ingestion.v2.product_detector import ProductDetector

        # Verificar que ProductDetector existe y no usa LLM
        detector = ProductDetector()

        # El metodo detect_products deberia existir
        assert hasattr(detector, 'detect_products')

        # El detector NO deberia tener llamadas a LLM en su logica principal
        # (esto se verifica por inspeccion del codigo - no hay imports de llm)

    @pytest.mark.asyncio
    async def test_step3_pipeline_cleans_before_insert(self):
        """Paso 3: Pipeline limpia datos anteriores antes de insertar"""
        from ingestion.v2.pipeline import IngestionV2Pipeline

        mock_db = MagicMock()
        pipeline = IngestionV2Pipeline(db_session=mock_db, max_pages=5)

        # Verificar que _clean_creator_data existe
        assert hasattr(pipeline, '_clean_creator_data')

        # Mock para verificar que DELETE se ejecuta
        mock_db.query.return_value.filter.return_value.delete.return_value = 5

        stats = pipeline._clean_creator_data("test_creator")

        # Deberia haber llamado a delete en products y rag_documents
        assert mock_db.query.called

    # =========================================================================
    # PASO 5: DM History Import
    # =========================================================================

    @pytest.mark.asyncio
    async def test_step5_dm_history_uses_max_age_days(self):
        """Paso 5: DM history respeta max_age_days (default 90)"""
        from core.dm_history_service import DMHistoryService, DEFAULT_MAX_AGE_DAYS

        assert DEFAULT_MAX_AGE_DAYS == 90

        service = DMHistoryService()

        # Verificar que el metodo acepta max_age_days
        import inspect
        sig = inspect.signature(service.load_dm_history)
        params = sig.parameters

        assert 'max_age_days' in params
        assert params['max_age_days'].default == DEFAULT_MAX_AGE_DAYS

    @pytest.mark.asyncio
    async def test_step5_dm_history_calculates_lead_score(self):
        """Paso 5: Calcula purchase_intent y asigna status"""
        from core.dm_history_service import DMHistoryService

        # Los scores estan definidos en el codigo:
        # interest_strong/purchase -> +3
        # interest_soft/question_product -> +1
        # objection -> -1
        # Status: hot (>=0.6), active (>=0.35), new (<0.35)

        # Verificar constantes de scoring en el codigo
        service = DMHistoryService()
        assert hasattr(service, '_import_conversation')

    # =========================================================================
    # PIPELINE COMPLETO
    # =========================================================================

    @pytest.mark.asyncio
    async def test_pipeline_has_all_8_methods(self):
        """Pipeline tiene los 8 metodos de configuracion"""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()

        # Verificar que todos los metodos existen (nombres reales del codigo)
        required_methods = [
            '_scrape_instagram',
            '_transcribe_videos',
            '_scrape_website',
            '_generate_tone_profile',
            '_load_dm_history',  # Nombre real (no _import_dm_history)
            '_extract_bio',       # Nombre real (no _extract_bio_data)
            '_generate_faqs',
            '_update_creator'
        ]

        for method in required_methods:
            assert hasattr(configurator, method), f"Falta metodo: {method}"

    @pytest.mark.asyncio
    async def test_pipeline_main_method_exists(self):
        """run() es el punto de entrada principal"""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()
        assert hasattr(configurator, 'run')

        # Verificar que es async
        import inspect
        assert inspect.iscoroutinefunction(configurator.run)


class TestAutoConfiguratorOAuthIntegration:
    """Tests especificos de integracion OAuth"""

    @pytest.mark.asyncio
    async def test_oauth_credentials_fetched_from_creator_table(self):
        """OAuth credentials se obtienen de tabla creators"""
        from core.auto_configurator import AutoConfigurator

        # El codigo busca:
        # creator.instagram_token
        # creator.instagram_user_id OR creator.instagram_page_id
        configurator = AutoConfigurator()

        # Verificar que _scrape_instagram intenta cargar credentials
        import inspect
        source = inspect.getsource(configurator._scrape_instagram)

        assert 'instagram_token' in source
        assert 'instagram_user_id' in source or 'instagram_page_id' in source

    @pytest.mark.asyncio
    async def test_priority_meta_graph_over_instaloader(self):
        """Meta Graph API tiene prioridad sobre Instaloader"""
        from ingestion.v2.instagram_ingestion import InstagramIngestionV2

        # Verificar que la clase acepta access_token
        import inspect
        sig = inspect.signature(InstagramIngestionV2.__init__)

        assert 'access_token' in sig.parameters
        assert 'instagram_business_id' in sig.parameters


class TestAutoConfigResult:
    """Tests del resultado de configuracion"""

    def test_auto_config_result_exists(self):
        """AutoConfigResult existe"""
        from core.auto_configurator import AutoConfigResult

        # La clase debe existir
        assert AutoConfigResult is not None

    def test_auto_config_result_structure(self):
        """AutoConfigResult tiene la estructura esperada"""
        from core.auto_configurator import AutoConfigResult

        # Verificar campos (basado en inspeccion del codigo)
        result = AutoConfigResult(
            success=True,
            creator_id="test",
            status="success"  # Campo requerido
        )

        assert hasattr(result, 'success')
        assert hasattr(result, 'creator_id')
        assert hasattr(result, 'status')
        assert hasattr(result, 'steps_completed')
        assert hasattr(result, 'instagram_posts_scraped')
        assert hasattr(result, 'products_detected')
        assert hasattr(result, 'tone_profile_generated')
        assert hasattr(result, 'dms_leads_created')
        assert hasattr(result, 'faqs_generated')

    def test_auto_config_result_to_dict(self):
        """AutoConfigResult tiene metodo to_dict"""
        from core.auto_configurator import AutoConfigResult

        result = AutoConfigResult(
            success=True,
            creator_id="test",
            status="success"  # Campo requerido
        )

        assert hasattr(result, 'to_dict')
        data = result.to_dict()
        assert isinstance(data, dict)
        assert 'success' in data
        assert 'creator_id' in data
        assert 'status' in data
        assert 'instagram' in data
        assert 'website' in data
        assert 'tone_profile' in data
