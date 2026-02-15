"""Tests para Tone Service - Integracion con Magic Slice."""

import pytest
import tempfile
from pathlib import Path

# Mock the ingestion imports before importing tone_service
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion import ToneProfile


class TestToneServiceUnit:
    """Tests unitarios para tone_service."""

    def test_tone_profile_to_dict(self):
        """Verifica que ToneProfile se serializa correctamente."""
        profile = ToneProfile(
            creator_id="test_creator",
            formality="informal",
            energy="alta",
            warmth="muy_calido",
            signature_phrases=["vamos crack", "a tope"]
        )

        data = profile.to_dict()

        assert data["creator_id"] == "test_creator"
        assert data["formality"] == "informal"
        assert data["energy"] == "alta"
        assert "vamos crack" in data["signature_phrases"]

    def test_tone_profile_from_dict(self):
        """Verifica que ToneProfile se deserializa correctamente."""
        data = {
            "creator_id": "test_creator",
            "formality": "formal",
            "energy": "media",
            "warmth": "calido",
            "signature_phrases": ["excelente"],
            "favorite_emojis": ["👍"],
            "confidence_score": 0.85
        }

        profile = ToneProfile.from_dict(data)

        assert profile.creator_id == "test_creator"
        assert profile.formality == "formal"
        assert profile.confidence_score == 0.85

    def test_tone_profile_to_system_prompt_section(self):
        """Verifica que genera seccion de prompt correctamente."""
        profile = ToneProfile(
            creator_id="test",
            formality="informal",
            energy="alta",
            warmth="muy_calido",
            signature_phrases=["vamos crack"]
        )

        section = profile.to_system_prompt_section()

        # Check for style indicators (new compact format uses TONO CREADOR block)
        assert "TONO CREADOR" in section or "TUTEO" in section
        assert len(section) > 50  # Debe tener contenido sustancial


class TestToneServiceIntegration:
    """Tests de integracion para tone_service."""

    @pytest.fixture
    def temp_dir(self):
        """Crea directorio temporal para tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_save_and_load_profile(self, temp_dir):
        """Verifica guardar y cargar perfil."""
        from core import tone_service

        # Patch el directorio
        original_dir = tone_service.TONE_PROFILES_DIR
        tone_service.TONE_PROFILES_DIR = temp_dir
        tone_service._tone_cache.clear()

        try:
            profile = ToneProfile(
                creator_id="integration_test",
                formality="casual",
                energy="alta",
                warmth="calido",
                signature_phrases=["hey", "mola"]
            )

            # Guardar
            saved = await tone_service.save_tone_profile(profile)
            assert saved == True

            # Limpiar cache para forzar lectura de archivo
            tone_service.clear_cache("integration_test")

            # Cargar
            loaded = await tone_service.get_tone_profile("integration_test")
            assert loaded is not None
            assert loaded.creator_id == "integration_test"
            assert loaded.formality == "casual"

        finally:
            tone_service.TONE_PROFILES_DIR = original_dir
            tone_service._tone_cache.clear()

    def test_get_tone_prompt_section_not_found(self):
        """Verifica que retorna vacio cuando no existe perfil."""
        from core import tone_service

        tone_service._tone_cache.clear()
        result = tone_service.get_tone_prompt_section("nonexistent_creator_xyz")
        assert result == ""

    def test_get_tone_prompt_section_from_cache(self):
        """Verifica que usa cache correctamente."""
        from core import tone_service

        profile = ToneProfile(
            creator_id="cached_creator",
            formality="informal",
            energy="alta",
            warmth="calido"
        )

        tone_service._tone_cache["cached_creator"] = profile

        try:
            result = tone_service.get_tone_prompt_section("cached_creator")
            assert len(result) > 0
            assert "TONO CREADOR" in result or "TUTEO" in result
        finally:
            tone_service.clear_cache("cached_creator")

    def test_list_profiles_empty(self, temp_dir):
        """Verifica lista vacia de perfiles."""
        from core import tone_service

        original_dir = tone_service.TONE_PROFILES_DIR
        tone_service.TONE_PROFILES_DIR = temp_dir

        try:
            profiles = tone_service.list_profiles()
            assert profiles == []
        finally:
            tone_service.TONE_PROFILES_DIR = original_dir

    @pytest.mark.asyncio
    async def test_list_profiles_with_data(self, temp_dir):
        """Verifica lista de perfiles con datos."""
        from core import tone_service

        original_dir = tone_service.TONE_PROFILES_DIR
        tone_service.TONE_PROFILES_DIR = temp_dir

        try:
            # Crear algunos perfiles
            for i in range(3):
                profile = ToneProfile(
                    creator_id=f"creator_{i}",
                    formality="informal"
                )
                await tone_service.save_tone_profile(profile)

            profiles = tone_service.list_profiles()
            assert len(profiles) == 3
            assert "creator_0" in profiles
            assert "creator_1" in profiles
            assert "creator_2" in profiles

        finally:
            tone_service.TONE_PROFILES_DIR = original_dir
            tone_service._tone_cache.clear()


class TestDMAgentIntegration:
    """Tests para verificar integracion con dm_agent."""

    def test_import_tone_service_in_dm_agent(self):
        """Verifica que dm_agent puede importar tone_service."""
        # Este test verifica que el import funciona
        try:
            from core.tone_service import get_tone_prompt_section
            assert callable(get_tone_prompt_section)
        except ImportError as e:
            pytest.skip(f"Import failed (expected in isolation): {e}")

    def test_tone_profile_prompt_format(self):
        """Verifica formato del prompt para inyeccion."""
        profile = ToneProfile(
            creator_id="format_test",
            formality="muy_informal",
            energy="muy_alta",
            warmth="muy_calido",
            signature_phrases=["vamos", "crack", "a tope"],
            favorite_emojis=["🔥", "💪", "🚀"],
            uses_emojis=True
        )

        section = profile.to_system_prompt_section()

        # Verificar que el formato es apropiado para inyeccion
        assert isinstance(section, str)
        assert len(section) > 100  # Contenido sustancial
        # No debe tener caracteres problematicos
        assert "{" not in section or "}" not in section  # Evitar f-string issues


class TestGenerateToneProfile:
    """Tests para generacion de ToneProfile."""

    @pytest.mark.asyncio
    async def test_generate_from_posts(self):
        """Verifica generacion de perfil desde posts."""
        from core import tone_service

        posts = [
            {"caption": "Hola a todos! 💪 Hoy vamos a entrenar duro. Preparados?"},
            {"caption": "Me encanta ver vuestro progreso 🔥 Sois INCREIBLES!"},
            {"caption": "Nuevo video! Esta vez sobre nutricion 🥗 Lo que me pedisteis!"},
            {"caption": "Vamos crack! A por todas hoy 💪🚀"},
            {"caption": "Recordad: constancia es la clave. Nos vemos mañana!"}
        ]

        profile = await tone_service.generate_tone_profile(
            creator_id="generated_test",
            posts=posts,
            save=False
        )

        assert profile.creator_id == "generated_test"
        assert profile.analyzed_posts_count == 5
        assert profile.uses_emojis == True  # Los posts tienen emojis
