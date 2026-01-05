"""
Tests para OnboardingService - Pipeline de onboarding.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from backend.core.onboarding_service import (
    OnboardingService,
    OnboardingRequest,
    OnboardingResult,
    get_onboarding_service
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_posts():
    """Posts de ejemplo para testing."""
    return [
        {
            "caption": "Buenos dias! Hoy quiero hablarles de nutricion. Es super importante cuidar lo que comemos.",
            "post_id": "post_1",
            "post_type": "instagram_post",
            "likes_count": 150,
            "comments_count": 23
        },
        {
            "caption": "Mi rutina de ejercicios favorita. Siempre empiezo con cardio y termino con pesas.",
            "post_id": "post_2",
            "post_type": "instagram_reel",
            "likes_count": 280,
            "comments_count": 45
        },
        {
            "caption": "Pregunta del dia: Cual es su objetivo fitness para este ano?",
            "post_id": "post_3",
            "post_type": "instagram_post",
            "likes_count": 95,
            "comments_count": 67
        }
    ]


@pytest.fixture
def sample_tone_profile():
    """ToneProfile de ejemplo."""
    from backend.ingestion import ToneProfile
    return ToneProfile(
        creator_id="test_creator",
        formality="informal",
        energy="alta",
        warmth="calido",
        signature_phrases=["buenos dias", "super importante"],
        main_topics=["nutricion", "fitness", "bienestar"],
        confidence_score=0.8
    )


@pytest.fixture
def onboarding_service():
    """Instancia del servicio para testing."""
    return OnboardingService()


# ============================================================================
# TESTS - PARSING DE POSTS MANUALES
# ============================================================================

class TestManualPostParsing:
    """Tests para parsing de posts manuales."""

    def test_parse_manual_posts_basic(self, onboarding_service, sample_posts):
        """Parsea posts manuales correctamente."""
        result = onboarding_service._parse_manual_posts(sample_posts)

        assert len(result) == 3
        assert result[0]["caption"] == sample_posts[0]["caption"]
        assert result[0]["post_id"] == "post_1"

    def test_parse_manual_posts_without_caption_skipped(self, onboarding_service):
        """Posts sin caption son ignorados."""
        posts = [
            {"post_id": "1", "caption": "Con texto suficiente para ser indexado"},
            {"post_id": "2", "caption": ""},  # Sin texto
            {"post_id": "3"}  # Sin caption
        ]

        result = onboarding_service._parse_manual_posts(posts)

        assert len(result) == 1
        assert result[0]["post_id"] == "1"

    def test_parse_manual_posts_generates_ids(self, onboarding_service):
        """Genera IDs si no se proporcionan."""
        posts = [
            {"caption": "Post sin ID pero con contenido suficiente"},
            {"caption": "Otro post sin ID y tambien con contenido"}
        ]

        result = onboarding_service._parse_manual_posts(posts)

        assert result[0]["post_id"] == "manual_0"
        assert result[1]["post_id"] == "manual_1"

    def test_parse_manual_posts_short_captions_skipped(self, onboarding_service):
        """Posts con caption corto son ignorados."""
        posts = [
            {"post_id": "1", "caption": "Muy corto"},  # < 10 chars
            {"post_id": "2", "caption": "Este tiene contenido suficiente para ser indexado"}
        ]

        result = onboarding_service._parse_manual_posts(posts)

        assert len(result) == 1
        assert result[0]["post_id"] == "2"


# ============================================================================
# TESTS - PIPELINE COMPLETO
# ============================================================================

class TestOnboardingPipeline:
    """Tests para el pipeline completo de onboarding."""

    @pytest.mark.asyncio
    async def test_onboard_with_manual_posts(self, onboarding_service, sample_posts, sample_tone_profile):
        """Onboarding exitoso con posts manuales."""
        request = OnboardingRequest(
            creator_id="test_creator_123",
            manual_posts=sample_posts
        )

        with patch.object(onboarding_service, '_analyze_tone') as mock_tone, \
             patch.object(onboarding_service, '_index_content') as mock_index, \
             patch('backend.core.onboarding_service.save_tone_profile', new_callable=AsyncMock):

            mock_tone.return_value = sample_tone_profile
            mock_index.return_value = {"posts_indexed": 3, "total_chunks": 3}

            result = await onboarding_service.onboard_creator(request)

        assert result.success
        assert result.posts_processed == 3
        assert result.tone_profile_generated
        assert result.content_indexed

    @pytest.mark.asyncio
    async def test_onboard_fails_without_posts_or_username(self, onboarding_service):
        """Falla si no hay posts ni username."""
        request = OnboardingRequest(creator_id="test")

        result = await onboarding_service.onboard_creator(request)

        assert not result.success
        assert "Se requiere instagram_username o manual_posts" in result.errors

    @pytest.mark.asyncio
    async def test_onboard_fails_with_empty_posts(self, onboarding_service):
        """Falla si los posts estan vacios (lista vacia es falsy)."""
        request = OnboardingRequest(
            creator_id="test",
            manual_posts=[]  # Lista vacia es falsy, asi que falla validacion inicial
        )

        result = await onboarding_service.onboard_creator(request)

        assert not result.success
        # Lista vacia es falsy, asi que cae en la validacion de "se requiere..."
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_onboard_partial_success_no_tone(self, onboarding_service, sample_posts):
        """Exito parcial si falla analisis de tono."""
        request = OnboardingRequest(
            creator_id="test",
            manual_posts=sample_posts
        )

        with patch.object(onboarding_service, '_analyze_tone') as mock_tone, \
             patch.object(onboarding_service, '_index_content') as mock_index:

            mock_tone.return_value = None  # Falla el analisis
            mock_index.return_value = {"posts_indexed": 3, "total_chunks": 3}

            result = await onboarding_service.onboard_creator(request)

        assert result.success  # Aun es exitoso
        assert result.posts_processed == 3
        assert not result.tone_profile_generated
        assert "No se pudo generar ToneProfile" in result.errors


# ============================================================================
# TESTS - RESULT BUILDING
# ============================================================================

class TestResultBuilding:
    """Tests para construccion de resultados."""

    def test_build_result_with_tone_profile(self, onboarding_service, sample_tone_profile):
        """Resultado incluye resumen de tono."""
        request = OnboardingRequest(creator_id="test")

        result = onboarding_service._build_result(
            request=request,
            success=True,
            posts_count=10,
            errors=[],
            start_time=datetime.now(),
            tone_profile=sample_tone_profile,
            citation_stats={"posts_indexed": 10, "total_chunks": 10}
        )

        assert result.tone_summary is not None
        assert result.tone_summary["formality"] == "informal"
        assert "nutricion" in result.tone_summary["main_topics"]

    def test_build_result_without_tone_profile(self, onboarding_service):
        """Resultado sin tone_summary si no hay perfil."""
        request = OnboardingRequest(creator_id="test")

        result = onboarding_service._build_result(
            request=request,
            success=True,
            posts_count=10,
            errors=[],
            start_time=datetime.now(),
            tone_profile=None,
            citation_stats=None
        )

        assert result.tone_summary is None

    def test_build_result_calculates_duration(self, onboarding_service):
        """Calcula duracion correctamente."""
        from datetime import timedelta

        request = OnboardingRequest(creator_id="test")
        start = datetime.now() - timedelta(seconds=5)

        result = onboarding_service._build_result(
            request=request,
            success=True,
            posts_count=1,
            errors=[],
            start_time=start
        )

        assert result.duration_seconds >= 5

    def test_result_to_dict(self, onboarding_service, sample_tone_profile):
        """to_dict convierte correctamente."""
        request = OnboardingRequest(creator_id="test")

        result = onboarding_service._build_result(
            request=request,
            success=True,
            posts_count=5,
            errors=["warning1"],
            start_time=datetime.now(),
            tone_profile=sample_tone_profile
        )

        result_dict = result.to_dict()

        assert result_dict["creator_id"] == "test"
        assert result_dict["success"] is True
        assert result_dict["posts_processed"] == 5
        assert "warning1" in result_dict["errors"]


# ============================================================================
# TESTS - SINGLETON
# ============================================================================

class TestSingleton:
    """Tests para el patron singleton."""

    def test_get_onboarding_service_returns_same_instance(self):
        """Retorna la misma instancia."""
        # Reset singleton
        import backend.core.onboarding_service as module
        module._onboarding_service = None

        service1 = get_onboarding_service()
        service2 = get_onboarding_service()

        assert service1 is service2


# ============================================================================
# TESTS - ONBOARDING REQUEST
# ============================================================================

class TestOnboardingRequest:
    """Tests para OnboardingRequest."""

    def test_request_with_defaults(self):
        """Request con valores por defecto."""
        request = OnboardingRequest(creator_id="test")

        assert request.creator_id == "test"
        assert request.instagram_username is None
        assert request.manual_posts is None
        assert request.scraping_method == "manual"
        assert request.max_posts == 50

    def test_request_with_manual_posts(self):
        """Request con posts manuales."""
        posts = [{"caption": "test"}]
        request = OnboardingRequest(
            creator_id="test",
            manual_posts=posts
        )

        assert request.manual_posts == posts


# ============================================================================
# TESTS - INTEGRACION
# ============================================================================

class TestIntegration:
    """Tests de integracion con otros servicios."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_mocks(self, sample_posts):
        """Test de integracion completa del pipeline con mocks."""
        service = OnboardingService()

        request = OnboardingRequest(
            creator_id="integration_test_creator",
            manual_posts=sample_posts
        )

        # Mock de dependencias externas
        with patch('backend.core.onboarding_service.save_tone_profile', new_callable=AsyncMock), \
             patch('backend.core.onboarding_service.index_creator_posts', new_callable=AsyncMock) as mock_index, \
             patch('backend.core.onboarding_service.get_content_index') as mock_get_index:

            mock_index.return_value = {"posts_indexed": 3, "total_chunks": 3}
            mock_get_index.return_value = MagicMock(chunks=[1, 2, 3])

            # Mock del tone analyzer
            with patch.object(service.tone_analyzer, 'analyze', new_callable=AsyncMock) as mock_analyze:
                from backend.ingestion import ToneProfile
                mock_analyze.return_value = ToneProfile(
                    creator_id="integration_test_creator",
                    formality="informal",
                    energy="alta"
                )

                result = await service.onboard_creator(request)

        assert result.creator_id == "integration_test_creator"
        assert result.posts_processed == 3
        assert result.success


# ============================================================================
# TESTS - DELETE FUNCTIONS
# ============================================================================

class TestDeleteFunctions:
    """Tests para funciones de eliminacion."""

    def test_delete_tone_profile_nonexistent(self):
        """delete_tone_profile retorna False si no existe."""
        from backend.core.tone_service import delete_tone_profile

        result = delete_tone_profile("nonexistent_creator_xyz_123")

        assert result is False

    def test_delete_content_index_nonexistent(self):
        """delete_content_index retorna False si no existe."""
        from backend.core.citation_service import delete_content_index

        result = delete_content_index("nonexistent_creator_xyz_123")

        assert result is False
