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
# Test 2: happy path - to_dict and _generate_tone_profile
# ---------------------------------------------------------------------------
class TestAutoConfiguratorHappyPath:
    """Test data conversion and tone profile generation on valid data."""

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

    @pytest.mark.asyncio
    async def test_generate_tone_profile_returns_expected_keys(self):
        """_generate_tone_profile returns dict with 'success' and 'confidence' keys."""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()

        posts = [
            {"id": str(i), "caption": f"Caption text that is long enough for processing number {i}"}
            for i in range(10)
        ]

        mock_profile = object()  # any truthy value

        with patch("core.tone_profile_db.get_instagram_posts_db", new_callable=AsyncMock, return_value=posts), \
             patch("core.tone_service.save_tone_profile", new_callable=AsyncMock), \
             patch("ingestion.tone_analyzer.ToneAnalyzer") as MockAnalyzer:
            MockAnalyzer.return_value.analyze = AsyncMock(return_value=mock_profile)

            result = await configurator._generate_tone_profile("creator1")

        assert "success" in result
        assert "confidence" in result
        assert isinstance(result["confidence"], float)
        assert result["success"] is True
        assert result["confidence"] == 0.8

    @pytest.mark.asyncio
    async def test_generate_tone_profile_calls_tone_analyzer(self):
        """_generate_tone_profile delegates to ToneAnalyzer.analyze when enough posts exist."""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()

        posts = [
            {"id": str(i), "caption": f"This is a sufficiently long caption for post number {i}"}
            for i in range(10)
        ]

        mock_profile = {"some": "profile"}

        with patch("core.tone_profile_db.get_instagram_posts_db", new_callable=AsyncMock, return_value=posts), \
             patch("core.tone_service.save_tone_profile", new_callable=AsyncMock) as mock_save, \
             patch("ingestion.tone_analyzer.ToneAnalyzer") as MockAnalyzer:
            mock_analyze = AsyncMock(return_value=mock_profile)
            MockAnalyzer.return_value.analyze = mock_analyze

            result = await configurator._generate_tone_profile("creator1")

        mock_analyze.assert_awaited_once()
        mock_save.assert_awaited_once_with(mock_profile)
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Test 3: edge case - invalid / minimal inputs
# ---------------------------------------------------------------------------
class TestAutoConfiguratorEdgeCases:
    """Edge cases in tone profile generation and result serialisation."""

    @pytest.mark.asyncio
    async def test_generate_tone_profile_not_enough_posts(self):
        """When fewer than 5 valid posts exist, should return failure."""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()

        # Only 3 posts with short captions (< 20 chars) — will be filtered out
        posts = [
            {"id": "1", "caption": "Hola"},
            {"id": "2", "caption": "Vamos"},
            {"id": "3", "caption": "Si"},
        ]

        with patch("core.tone_profile_db.get_instagram_posts_db", new_callable=AsyncMock, return_value=posts):
            result = await configurator._generate_tone_profile("creator1")

        assert result["success"] is False
        assert result["confidence"] == 0.0

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

    @pytest.mark.asyncio
    async def test_generate_tone_profile_handles_analyzer_exception(self):
        """If ToneAnalyzer raises an exception, should return failure gracefully."""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()

        posts = [
            {"id": str(i), "caption": f"A sufficiently long caption for post number {i} here"}
            for i in range(10)
        ]

        with patch("core.tone_profile_db.get_instagram_posts_db", new_callable=AsyncMock, return_value=posts), \
             patch("ingestion.tone_analyzer.ToneAnalyzer") as MockAnalyzer:
            MockAnalyzer.return_value.analyze = AsyncMock(side_effect=Exception("LLM unavailable"))

            result = await configurator._generate_tone_profile("creator1")

        assert result["success"] is False
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_generate_tone_profile_no_posts(self):
        """When no posts exist at all, should return failure."""
        from core.auto_configurator import AutoConfigurator

        configurator = AutoConfigurator()

        with patch("core.tone_profile_db.get_instagram_posts_db", new_callable=AsyncMock, return_value=[]):
            result = await configurator._generate_tone_profile("creator1")

        assert result["success"] is False
        assert result["confidence"] == 0.0


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
