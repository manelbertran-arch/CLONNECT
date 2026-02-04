"""Tests for PostContext model.

TDD: Tests written FIRST before implementation.
Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

from datetime import datetime, timedelta, timezone

import pytest


class TestPostContext:
    """Test suite for PostContext dataclass."""

    def test_create_minimal(self):
        """Should create PostContext with minimal required fields."""
        from models.post_context import PostContext

        ctx = PostContext(
            creator_id="stefan",
            context_instructions="No special context",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )

        assert ctx.creator_id == "stefan"
        assert ctx.active_promotion is None
        assert ctx.recent_topics == []
        assert ctx.recent_products == []

    def test_create_with_promotion(self):
        """Should create PostContext with promotion details."""
        from models.post_context import PostContext

        ctx = PostContext(
            creator_id="stefan",
            active_promotion="Curso meditación 20% dto",
            promotion_urgency="48h restantes",
            context_instructions="Mencionar el curso en promoción",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )

        assert ctx.active_promotion == "Curso meditación 20% dto"
        assert ctx.promotion_urgency == "48h restantes"

    def test_create_with_topics(self):
        """Should create PostContext with recent topics."""
        from models.post_context import PostContext

        ctx = PostContext(
            creator_id="stefan",
            recent_topics=["meditación", "retiro Bali", "mindfulness"],
            recent_products=["Curso Meditación"],
            context_instructions="Temas recientes del creador",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )

        assert "meditación" in ctx.recent_topics
        assert "Curso Meditación" in ctx.recent_products

    def test_is_expired_true(self):
        """Should return True when context has expired."""
        from models.post_context import PostContext

        ctx = PostContext(
            creator_id="stefan",
            context_instructions="Test",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        assert ctx.is_expired() is True

    def test_is_expired_false(self):
        """Should return False when context is still valid."""
        from models.post_context import PostContext

        ctx = PostContext(
            creator_id="stefan",
            context_instructions="Test",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )

        assert ctx.is_expired() is False

    def test_has_active_promotion_true(self):
        """Should return True when promotion exists."""
        from models.post_context import PostContext

        ctx = PostContext(
            creator_id="stefan",
            active_promotion="Flash Sale!",
            context_instructions="Test",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )

        assert ctx.has_active_promotion() is True

    def test_has_active_promotion_false(self):
        """Should return False when no promotion."""
        from models.post_context import PostContext

        ctx = PostContext(
            creator_id="stefan",
            context_instructions="Test",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )

        assert ctx.has_active_promotion() is False

    def test_to_prompt_addition_with_promotion(self):
        """Should generate prompt text including promotion."""
        from models.post_context import PostContext

        ctx = PostContext(
            creator_id="stefan",
            active_promotion="Curso meditación 20% dto",
            promotion_urgency="48h",
            recent_topics=["meditación", "mindfulness"],
            context_instructions="Menciona el curso si preguntan",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )

        prompt = ctx.to_prompt_addition()

        assert "Curso meditación" in prompt
        assert "48h" in prompt
        assert "meditación" in prompt

    def test_to_prompt_addition_minimal(self):
        """Should generate minimal prompt when no special context."""
        from models.post_context import PostContext

        ctx = PostContext(
            creator_id="stefan",
            context_instructions="Sin contexto especial",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )

        prompt = ctx.to_prompt_addition()

        assert "Sin contexto especial" in prompt

    def test_to_prompt_addition_with_availability(self):
        """Should include availability hint in prompt."""
        from models.post_context import PostContext

        ctx = PostContext(
            creator_id="stefan",
            availability_hint="De viaje por Bali hasta el 15",
            context_instructions="Mencionar que está de viaje",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )

        prompt = ctx.to_prompt_addition()

        assert "Bali" in prompt or "viaje" in prompt.lower()
