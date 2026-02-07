"""Audit tests for services/dm_agent_context_integration.py."""

from unittest.mock import patch

import pytest

# We test synchronous helpers directly and async functions with pytest-asyncio.


class TestContextBuilderInit:
    """Test 1: init/import - Module imports and core functions exist."""

    def test_module_imports_successfully(self):
        import services.dm_agent_context_integration as mod

        assert hasattr(mod, "get_full_context")
        assert hasattr(mod, "build_context_prompt")
        assert hasattr(mod, "get_context_for_dm_agent")

    def test_format_dna_for_prompt_exists(self):
        from services.dm_agent_context_integration import _format_dna_for_prompt

        assert callable(_format_dna_for_prompt)

    def test_format_post_context_for_prompt_exists(self):
        from services.dm_agent_context_integration import _format_post_context_for_prompt

        assert callable(_format_post_context_for_prompt)

    def test_conversation_memory_helpers_exist(self):
        from services.dm_agent_context_integration import (
            get_conversation_memory,
            get_memory_context_for_prompt,
            save_conversation_memory,
            update_memory_after_response,
        )

        assert callable(get_conversation_memory)
        assert callable(save_conversation_memory)
        assert callable(update_memory_after_response)
        assert callable(get_memory_context_for_prompt)

    def test_orchestrator_helpers_exist(self):
        from services.dm_agent_context_integration import (
            process_with_orchestrator,
            send_orchestrated_response,
        )

        assert callable(process_with_orchestrator)
        assert callable(send_orchestrated_response)


class TestContextAssembly:
    """Test 2: happy path - Context is assembled correctly from sources."""

    @pytest.mark.asyncio
    async def test_build_context_prompt_with_all_sources(self):
        from services.dm_agent_context_integration import build_context_prompt

        with patch(
            "services.dm_agent_context_integration.get_creator_dm_style_for_prompt",
            return_value="STYLE: casual",
        ), patch(
            "services.dm_agent_context_integration.format_writing_patterns_for_prompt",
            return_value="PATTERNS: short messages",
        ), patch(
            "services.dm_agent_context_integration.get_relationship_dna",
            return_value={
                "relationship_type": "AMISTAD_CERCANA",
                "depth_level": 3,
                "trust_score": 0.8,
            },
        ), patch(
            "services.dm_agent_context_integration.get_post_context",
            return_value={
                "creator_id": "c1",
                "active_promotion": "20% off",
                "recent_topics": ["yoga"],
                "context_instructions": "Mention promo",
                "expires_at": "2030-01-01T00:00:00",
            },
        ):
            result = await build_context_prompt("c1", "l1")

        assert "STYLE: casual" in result
        assert "PATTERNS: short messages" in result
        assert "AMISTAD_CERCANA" in result

    @pytest.mark.asyncio
    async def test_get_full_context_populates_both_layers(self):
        from services.dm_agent_context_integration import get_full_context

        fake_dna = {"relationship_type": "CLIENTE", "trust_score": 0.5}
        fake_post = {"creator_id": "c1", "recent_topics": ["fitness"]}

        with patch(
            "services.dm_agent_context_integration.get_relationship_dna",
            return_value=fake_dna,
        ), patch(
            "services.dm_agent_context_integration.get_post_context",
            return_value=fake_post,
        ):
            ctx = await get_full_context("c1", "l1")

        assert ctx["relationship_dna"] == fake_dna
        assert ctx["post_context"] == fake_post
        assert ctx["creator_id"] == "c1"
        assert ctx["lead_id"] == "l1"

    def test_format_dna_includes_relationship_type(self):
        from services.dm_agent_context_integration import _format_dna_for_prompt

        dna = {
            "relationship_type": "INTIMA",
            "depth_level": 4,
            "trust_score": 0.9,
        }
        result = _format_dna_for_prompt(dna)
        assert "INTIMA" in result
        assert "Comunicación muy cercana y personal" in result

    def test_format_dna_includes_vocabulary(self):
        from services.dm_agent_context_integration import _format_dna_for_prompt

        dna = {
            "relationship_type": "AMISTAD_CASUAL",
            "depth_level": 0,
            "trust_score": 0.0,
            "vocabulary_uses": ["crack", "tio"],
            "vocabulary_avoids": ["hermano"],
        }
        result = _format_dna_for_prompt(dna)
        assert "crack" in result
        assert "hermano" in result

    def test_format_dna_includes_golden_examples(self):
        from services.dm_agent_context_integration import _format_dna_for_prompt

        dna = {
            "relationship_type": "CLIENTE",
            "depth_level": 0,
            "trust_score": 0.0,
            "golden_examples": [
                {"user": "Hola!", "assistant": "Hey! Que tal?"},
            ],
        }
        result = _format_dna_for_prompt(dna)
        assert "Hola!" in result
        assert "Hey! Que tal?" in result


class TestMissingDataHandling:
    """Test 3: edge case - Graceful handling of missing data."""

    @pytest.mark.asyncio
    async def test_build_context_prompt_with_no_sources(self):
        from services.dm_agent_context_integration import build_context_prompt

        with patch(
            "services.dm_agent_context_integration.get_creator_dm_style_for_prompt",
            return_value=None,
        ), patch(
            "services.dm_agent_context_integration.format_writing_patterns_for_prompt",
            return_value=None,
        ), patch(
            "services.dm_agent_context_integration.get_relationship_dna",
            return_value=None,
        ), patch(
            "services.dm_agent_context_integration.get_post_context",
            return_value=None,
        ):
            result = await build_context_prompt("c1", "l1")

        assert result == "Sin contexto especial disponible."

    def test_format_dna_with_none_returns_none(self):
        from services.dm_agent_context_integration import _format_dna_for_prompt

        assert _format_dna_for_prompt(None) is None

    def test_format_dna_with_empty_dict_returns_none(self):
        """Empty dict is falsy so _format_dna_for_prompt returns None."""
        from services.dm_agent_context_integration import _format_dna_for_prompt

        result = _format_dna_for_prompt({})
        assert result is None

    def test_format_post_context_with_none_returns_none(self):
        from services.dm_agent_context_integration import _format_post_context_for_prompt

        assert _format_post_context_for_prompt(None) is None

    def test_format_post_context_with_empty_dict_returns_none(self):
        from services.dm_agent_context_integration import _format_post_context_for_prompt

        assert _format_post_context_for_prompt({}) is None


class TestContextSizeLimits:
    """Test 4: error handling - Errors in sources do not crash assembly."""

    @pytest.mark.asyncio
    async def test_dna_error_does_not_crash_full_context(self):
        from services.dm_agent_context_integration import get_full_context

        with patch(
            "services.dm_agent_context_integration.get_relationship_dna",
            side_effect=RuntimeError("DB down"),
        ), patch(
            "services.dm_agent_context_integration.get_post_context",
            return_value=None,
        ):
            ctx = await get_full_context("c1", "l1")

        assert ctx["relationship_dna"] is None
        assert ctx["creator_id"] == "c1"

    @pytest.mark.asyncio
    async def test_post_context_error_does_not_crash_full_context(self):
        from services.dm_agent_context_integration import get_full_context

        with patch(
            "services.dm_agent_context_integration.get_relationship_dna",
            return_value=None,
        ), patch(
            "services.dm_agent_context_integration.get_post_context",
            side_effect=RuntimeError("network error"),
        ):
            ctx = await get_full_context("c1", "l1")

        assert ctx["post_context"] is None

    @pytest.mark.asyncio
    async def test_build_prompt_handles_style_error(self):
        from services.dm_agent_context_integration import build_context_prompt

        with patch(
            "services.dm_agent_context_integration.get_creator_dm_style_for_prompt",
            side_effect=Exception("oops"),
        ), patch(
            "services.dm_agent_context_integration.format_writing_patterns_for_prompt",
            return_value=None,
        ), patch(
            "services.dm_agent_context_integration.get_relationship_dna",
            return_value=None,
        ), patch(
            "services.dm_agent_context_integration.get_post_context",
            return_value=None,
        ):
            result = await build_context_prompt("c1", "l1")

        assert result == "Sin contexto especial disponible."

    @pytest.mark.asyncio
    async def test_build_prompt_handles_writing_patterns_error(self):
        from services.dm_agent_context_integration import build_context_prompt

        with patch(
            "services.dm_agent_context_integration.get_creator_dm_style_for_prompt",
            return_value="style ok",
        ), patch(
            "services.dm_agent_context_integration.format_writing_patterns_for_prompt",
            side_effect=Exception("patterns error"),
        ), patch(
            "services.dm_agent_context_integration.get_relationship_dna",
            return_value=None,
        ), patch(
            "services.dm_agent_context_integration.get_post_context",
            return_value=None,
        ):
            result = await build_context_prompt("c1", "l1")

        assert "style ok" in result

    def test_format_dna_truncates_vocabulary_lists(self):
        """Vocabulary lists are capped at 8 (uses) and 5 (avoids)."""
        from services.dm_agent_context_integration import _format_dna_for_prompt

        dna = {
            "relationship_type": "CLIENTE",
            "depth_level": 0,
            "trust_score": 0.0,
            "vocabulary_uses": [f"word{i}" for i in range(20)],
            "vocabulary_avoids": [f"avoid{i}" for i in range(20)],
        }
        result = _format_dna_for_prompt(dna)
        # Only first 8 words should appear in vocabulary uses
        assert "word7" in result
        assert "word8" not in result
        # Only first 5 avoids
        assert "avoid4" in result
        assert "avoid5" not in result


class TestMultiSourceMerge:
    """Test 5: integration check - Multiple sources merge correctly."""

    @pytest.mark.asyncio
    async def test_all_sections_appear_in_prompt(self):
        from services.dm_agent_context_integration import build_context_prompt

        with patch(
            "services.dm_agent_context_integration.get_creator_dm_style_for_prompt",
            return_value="CREATOR_STYLE_SECTION",
        ), patch(
            "services.dm_agent_context_integration.format_writing_patterns_for_prompt",
            return_value="WRITING_PATTERNS_SECTION",
        ), patch(
            "services.dm_agent_context_integration.get_relationship_dna",
            return_value={
                "relationship_type": "AMISTAD_CERCANA",
                "depth_level": 2,
                "trust_score": 0.6,
                "tone_description": "fraternal",
            },
        ), patch(
            "services.dm_agent_context_integration.get_post_context",
            return_value={
                "creator_id": "c1",
                "active_promotion": "Summer sale",
                "recent_topics": ["yoga", "meditation"],
                "context_instructions": "Push the sale",
                "expires_at": "2030-01-01T00:00:00",
            },
        ):
            result = await build_context_prompt("c1", "l1")

        assert "CREATOR_STYLE_SECTION" in result
        assert "WRITING_PATTERNS_SECTION" in result
        assert "AMISTAD_CERCANA" in result
        assert "fraternal" in result

    @pytest.mark.asyncio
    async def test_sections_separated_by_double_newline(self):
        from services.dm_agent_context_integration import build_context_prompt

        with patch(
            "services.dm_agent_context_integration.get_creator_dm_style_for_prompt",
            return_value="SECTION_A",
        ), patch(
            "services.dm_agent_context_integration.format_writing_patterns_for_prompt",
            return_value="SECTION_B",
        ), patch(
            "services.dm_agent_context_integration.get_relationship_dna",
            return_value=None,
        ), patch(
            "services.dm_agent_context_integration.get_post_context",
            return_value=None,
        ):
            result = await build_context_prompt("c1", "l1")

        assert "SECTION_A\n\nSECTION_B" in result

    def test_format_dna_all_fields_populated(self):
        from services.dm_agent_context_integration import _format_dna_for_prompt

        dna = {
            "relationship_type": "INTIMA",
            "depth_level": 4,
            "trust_score": 0.9,
            "vocabulary_uses": ["amor", "cielo"],
            "vocabulary_avoids": ["bro"],
            "emojis": ["heart", "fire"],
            "tone_description": "cariñoso",
            "recurring_topics": ["viajes", "cenas"],
            "private_references": ["aquella vez en Paris"],
            "bot_instructions": "Be warm and loving",
            "golden_examples": [
                {"user": "Te echo de menos", "assistant": "Yo también mi amor"},
            ],
        }
        result = _format_dna_for_prompt(dna)
        assert "amor" in result
        assert "cielo" in result
        assert "bro" in result
        assert "cariñoso" in result
        assert "viajes" in result
        assert "Paris" in result
        assert "Be warm and loving" in result
        assert "Te echo de menos" in result

    def test_format_dna_depth_description_mapping(self):
        from services.dm_agent_context_integration import _format_dna_for_prompt

        # depth=2 -> "confianza"
        dna = {
            "relationship_type": "CLIENTE",
            "depth_level": 2,
            "trust_score": 0.5,
        }
        result = _format_dna_for_prompt(dna)
        assert "confianza" in result

    def test_format_dna_high_trust_annotation(self):
        from services.dm_agent_context_integration import _format_dna_for_prompt

        dna = {
            "relationship_type": "AMISTAD_CERCANA",
            "depth_level": 3,
            "trust_score": 0.85,
        }
        result = _format_dna_for_prompt(dna)
        assert "alta confianza" in result
