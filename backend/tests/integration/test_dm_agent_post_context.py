"""Tests for dm_agent integration with PostContext.

TDD: Tests written FIRST before implementation.
Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


class TestDMAgentPostContextIntegration:
    """Test suite for dm_agent + PostContext integration."""

    @pytest.mark.asyncio
    async def test_loads_post_context_for_response(self):
        """Should load post context when generating response."""
        from services.dm_agent_context_integration import get_full_context

        mock_post_context = {
            "creator_id": "stefan",
            "active_promotion": "Curso 20% dto",
            "context_instructions": "Menciona el curso",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=6),
        }

        with patch("services.dm_agent_context_integration.get_post_context") as mock_get:
            mock_get.return_value = mock_post_context

            context = await get_full_context("stefan", "lead123")

            assert "post_context" in context
            assert context["post_context"]["active_promotion"] == "Curso 20% dto"

    @pytest.mark.asyncio
    async def test_includes_post_context_in_prompt(self):
        """Should include post context in prompt assembly."""
        from services.dm_agent_context_integration import build_context_prompt

        mock_post_context = {
            "creator_id": "stefan",
            "active_promotion": "Lanzamiento curso meditación",
            "promotion_urgency": "48h",
            "recent_topics": ["meditación", "mindfulness"],
            "context_instructions": "Si preguntan por cursos, menciona el lanzamiento",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=6),
        }

        with patch("services.dm_agent_context_integration.get_post_context") as mock_get:
            mock_get.return_value = mock_post_context

            prompt = await build_context_prompt("stefan", "lead123")

            assert "Lanzamiento" in prompt or "meditación" in prompt
            assert "CONTEXTO" in prompt.upper() or "promoción" in prompt.lower()

    @pytest.mark.asyncio
    async def test_graceful_without_post_context(self):
        """Should work gracefully when no post context."""
        from services.dm_agent_context_integration import get_full_context

        with patch("services.dm_agent_context_integration.get_post_context") as mock_get:
            mock_get.return_value = None

            context = await get_full_context("stefan", "lead123")

            # Should still return valid context
            assert context is not None
            assert context.get("post_context") is None or context.get("post_context") == {}

    @pytest.mark.asyncio
    async def test_combines_with_relationship_dna(self):
        """Should combine post context with relationship DNA."""
        from services.dm_agent_context_integration import build_context_prompt

        mock_post_context = {
            "creator_id": "stefan",
            "active_promotion": "Flash Sale",
            "context_instructions": "Promoción activa",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=6),
        }

        mock_relationship_dna = {
            "relationship_type": "AMISTAD_CERCANA",
            "vocabulary_uses": ["hermano", "bro"],
            "bot_instructions": "Usa tono fraternal",
        }

        with patch("services.dm_agent_context_integration.get_post_context") as mock_post:
            mock_post.return_value = mock_post_context
            with patch("services.dm_agent_context_integration.get_relationship_dna") as mock_dna:
                mock_dna.return_value = mock_relationship_dna

                prompt = await build_context_prompt("stefan", "lead123")

                # Should include both contexts
                assert "Flash Sale" in prompt or "Promoción" in prompt
