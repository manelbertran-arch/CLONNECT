"""Audit tests for core/auto_configurator.py."""

from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test 1: init / import
# ---------------------------------------------------------------------------
class TestAutoConfiguratorImports:
    """Verify module imports and dataclass construction."""

    def test_imports_and_dataclass_defaults(self):
        from core.auto_configurator import AutoConfigResult

        result = AutoConfigResult(success=False, creator_id="test", status="failed")

        assert result.success is False
        assert result.creator_id == "test"
        assert result.status == "failed"
        assert result.steps_completed == []
        assert result.errors == []
        assert result.warnings == []
        assert result.instagram_posts_scraped == 0
        assert result.tone_profile_generated is False
        assert result.dms_conversations_found == 0
        assert result.bio_loaded is False
        assert result.faqs_generated == 0
        assert result.duration_seconds == 0.0

    def test_auto_configurator_init(self):
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator(db_session=None)
        assert configurator.db is None

        sentinel = object()
        configurator2 = AutoConfigurator(db_session=sentinel)
        assert configurator2.db is sentinel


# ---------------------------------------------------------------------------
# Test 2: happy path - to_dict and _analyze_tone
# ---------------------------------------------------------------------------
class TestAutoConfiguratorHappyPath:
    """Test data conversion and tone analysis on valid data."""

    def test_to_dict_structure(self):
        from core.auto_configurator import AutoConfigResult

        result = AutoConfigResult(
            success=True,
            creator_id="creator1",
            status="success",
        )
        result.instagram_posts_scraped = 50
        result.tone_profile_generated = True
        result.tone_confidence = 0.85
        result.steps_completed = ["instagram_scraping", "tone_profile"]
        result.duration_seconds = 12.5

        d = result.to_dict()

        assert d["success"] is True
        assert d["creator_id"] == "creator1"
        assert d["status"] == "success"
        assert d["instagram"]["posts_scraped"] == 50
        assert d["tone_profile"]["generated"] is True
        assert d["tone_profile"]["confidence"] == 0.85
        assert d["duration_seconds"] == 12.5
        assert "instagram_scraping" in d["steps_completed"]

    def test_analyze_tone_returns_expected_keys(self):
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()
        captions = [
            "Hoy fue un gran dia de entreno! Fuerza y disciplina siempre",
            "Nuevo video donde les cuento mi rutina de ejercicio para mantenerse fit",
            "La mente lo es todo. Sin mentalidad ganadora no hay progreso",
            "Proteina despues del gym, siempre. Buena alimentacion es clave",
            "Gracias por el apoyo! Los quiero mucho a todos mis seguidores",
        ]

        profile = configurator._analyze_tone(captions)

        assert "emoji_style" in profile
        assert "avg_message_length" in profile
        assert "formality" in profile
        assert "frequent_words" in profile
        assert "topics" in profile
        assert "confidence_score" in profile
        assert isinstance(profile["confidence_score"], float)
        assert 0 <= profile["confidence_score"] <= 1.0

    def test_analyze_tone_detects_fitness_topic(self):
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()
        captions = [
            "Vamos al gym a entrenar piernas hoy! Fuerza!",
            "Dia de ejercicio intenso, no hay excusas",
            "El fitness es un estilo de vida, no solo un hobby",
            "Entreno de fuerza para principiantes disponible",
            "Nuevo programa de deporte para todos los niveles",
        ]
        profile = configurator._analyze_tone(captions)
        assert "fitness" in profile["topics"]


# ---------------------------------------------------------------------------
# Test 3: edge case - invalid / minimal inputs
# ---------------------------------------------------------------------------
class TestAutoConfiguratorEdgeCases:
    """Edge cases in tone analysis and result serialisation."""

    def test_analyze_tone_single_word_captions(self):
        """Very short captions should still produce a valid profile dict."""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()
        captions = ["Hola", "Vamos", "Si", "Dale", "Ok"]
        profile = configurator._analyze_tone(captions)

        assert "confidence_score" in profile
        assert profile["avg_message_length"] >= 1

    def test_to_dict_truncates_errors(self):
        """Errors list in to_dict is capped at 10."""
        from core.auto_configurator import AutoConfigResult

        result = AutoConfigResult(success=False, creator_id="x", status="failed")
        result.errors = [f"error_{i}" for i in range(25)]
        result.warnings = [f"warn_{i}" for i in range(25)]
        result.transcription_errors = [f"t_err_{i}" for i in range(10)]

        d = result.to_dict()
        assert len(d["errors"]) == 10
        assert len(d["warnings"]) == 10
        assert len(d["transcription"]["errors"]) == 5

    def test_analyze_tone_all_caps_text(self):
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()
        captions = [
            "TODO EN MAYUSCULAS PORQUE SI AMIGOS",
            "ESTO ES UN CAPTION EN CAPS",
            "HOLA A TODOS MIS SEGUIDORES QUERIDOS",
            "GRACIAS POR EL APOYO INCONDICIONAL",
            "VAMOS QUE SE PUEDE CON TODO",
        ]
        profile = configurator._analyze_tone(captions)
        assert isinstance(profile["formality"], float)

    def test_analyze_tone_empty_emoji_list(self):
        """Captions without emojis should return empty emoji_style list."""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()
        captions = [
            "Post sin emoji, solo texto plano aqui",
            "Otro post bastante sencillo la verdad",
            "Esto es un contenido limpio sin adornos",
            "Publicacion profesional y seria",
            "Contenido de valor para la comunidad",
        ]
        profile = configurator._analyze_tone(captions)
        assert profile["emoji_style"] == []


# ---------------------------------------------------------------------------
# Test 4: error handling - run pipeline with mocked failing steps
# ---------------------------------------------------------------------------
class TestAutoConfiguratorErrorHandling:
    """Ensure pipeline handles step failures gracefully."""

    @pytest.mark.asyncio
    async def test_run_returns_failed_when_all_steps_fail(self):
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()

        # Mock every internal step to fail
        configurator._scrape_instagram = AsyncMock(
            return_value={"success": False, "posts_scraped": 0, "errors": ["IG error"]}
        )
        configurator._transcribe_videos = AsyncMock(side_effect=Exception("no whisper"))
        configurator._scrape_website = AsyncMock(side_effect=Exception("no site"))
        configurator._generate_tone_profile = AsyncMock(side_effect=Exception("no llm"))
        configurator._load_dm_history = AsyncMock(side_effect=Exception("no dm"))
        configurator._extract_bio = AsyncMock(side_effect=Exception("no bio"))
        configurator._generate_faqs = AsyncMock(side_effect=Exception("no faq"))
        configurator._update_creator = AsyncMock(side_effect=Exception("no db"))

        result = await configurator.run(
            creator_id="test_creator",
            instagram_username="testuser",
        )

        assert result.success is False
        assert result.status == "failed"
        assert len(result.steps_completed) == 0

    @pytest.mark.asyncio
    async def test_run_partial_success(self):
        """If some steps succeed, status should be partial or success."""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()

        configurator._scrape_instagram = AsyncMock(
            return_value={
                "success": True,
                "posts_scraped": 10,
                "posts_saved_db": 10,
                "posts_passed_sanity": 10,
                "rag_chunks_created": 5,
            }
        )
        configurator._transcribe_videos = AsyncMock(
            return_value={
                "videos_found": 0,
                "videos_transcribed": 0,
                "chunks_created": 0,
                "errors": [],
            }
        )
        configurator._generate_tone_profile = AsyncMock(
            return_value={
                "success": True,
                "confidence": 0.7,
            }
        )
        configurator._load_dm_history = AsyncMock(
            return_value={
                "success": True,
                "conversations_found": 5,
                "messages_imported": 20,
                "leads_created": 3,
            }
        )
        configurator._extract_bio = AsyncMock(return_value={"success": True})
        configurator._generate_faqs = AsyncMock(return_value={"faqs_created": 3})
        configurator._update_creator = AsyncMock()

        result = await configurator.run(
            creator_id="creator1",
            instagram_username="creator1ig",
            transcribe_videos=False,
        )

        assert result.success is True
        assert result.status == "success"
        assert "instagram_scraping" in result.steps_completed
        assert result.instagram_posts_scraped == 10


# ---------------------------------------------------------------------------
# Test 5: integration check - convenience function and config validation
# ---------------------------------------------------------------------------
class TestAutoConfiguratorIntegration:
    """End-to-end integration of the convenience wrapper."""

    @pytest.mark.asyncio
    async def test_auto_configure_clone_calls_run(self):
        from core.auto_configurator import AutoConfigurator, auto_configure_clone

        with patch.object(AutoConfigurator, "run", new_callable=AsyncMock) as mock_run:
            from core.auto_configurator import AutoConfigResult

            mock_run.return_value = AutoConfigResult(
                success=True, creator_id="c1", status="success"
            )

            result = await auto_configure_clone(
                creator_id="c1",
                instagram_username="c1ig",
                website_url="https://example.com",
                max_posts=25,
                transcribe_videos=False,
            )

            mock_run.assert_awaited_once_with(
                creator_id="c1",
                instagram_username="c1ig",
                website_url="https://example.com",
                max_posts=25,
                transcribe_videos=False,
            )
            assert result.success is True

    def test_auto_config_result_default_factory_isolation(self):
        """Ensure mutable defaults are not shared between instances."""
        from core.auto_configurator import AutoConfigResult

        r1 = AutoConfigResult(success=False, creator_id="a", status="failed")
        r2 = AutoConfigResult(success=False, creator_id="b", status="failed")

        r1.steps_completed.append("step1")
        r1.errors.append("err1")

        assert r2.steps_completed == []
        assert r2.errors == []

    def test_to_dict_contains_all_sections(self):
        from core.auto_configurator import AutoConfigResult

        result = AutoConfigResult(success=True, creator_id="x", status="success")
        d = result.to_dict()

        expected_keys = {
            "success",
            "creator_id",
            "status",
            "steps_completed",
            "instagram",
            "transcription",
            "website",
            "tone_profile",
            "rag",
            "dms",
            "bio",
            "faqs",
            "errors",
            "warnings",
            "duration_seconds",
        }
        assert expected_keys == set(d.keys())
