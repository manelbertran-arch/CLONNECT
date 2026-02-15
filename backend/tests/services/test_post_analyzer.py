"""Tests for Post Analyzer (LLM-powered).

TDD: Tests written FIRST before implementation.
Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

import json
from unittest.mock import AsyncMock, patch

import pytest


class TestPostAnalyzer:
    """Test suite for LLM-powered post analysis."""

    @pytest.mark.asyncio
    async def test_analyze_posts_with_promotion(self):
        """Should detect promotion from posts."""
        from services.post_analyzer import PostAnalyzer

        analyzer = PostAnalyzer()

        posts = [
            {
                "id": "1",
                "caption": "🚀 Lanzamos el curso de MEDITACIÓN! 20% descuento con código LAUNCH20. Solo 48h!",
                "timestamp": "2026-02-04T10:00:00+0000",
            }
        ]

        mock_llm_response = json.dumps({
            "active_promotion": "Curso de Meditación - 20% descuento código LAUNCH20",
            "promotion_deadline": "48 horas",
            "promotion_urgency": "alta",
            "recent_topics": ["meditación", "lanzamiento", "curso online"],
            "recent_products": ["Curso de Meditación"],
            "availability_hint": None,
            "context_instructions": "Menciona el lanzamiento del curso si preguntan por cursos.",
        })

        with patch.object(analyzer, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_response

            result = await analyzer.analyze_posts(posts)

            assert result["active_promotion"] is not None
            assert "Meditación" in result["active_promotion"]
            assert "meditación" in result["recent_topics"]

    @pytest.mark.asyncio
    async def test_analyze_posts_without_promotion(self):
        """Should handle posts without promotion."""
        from services.post_analyzer import PostAnalyzer

        analyzer = PostAnalyzer()

        posts = [
            {
                "id": "1",
                "caption": "Disfrutando de un café mientras leo 📚",
                "timestamp": "2026-02-04T10:00:00+0000",
            }
        ]

        mock_llm_response = json.dumps({
            "active_promotion": None,
            "promotion_deadline": None,
            "promotion_urgency": None,
            "recent_topics": ["lectura", "café", "lifestyle"],
            "recent_products": [],
            "availability_hint": None,
            "context_instructions": "Sin promoción activa. Temas recientes: lectura.",
        })

        with patch.object(analyzer, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_response

            result = await analyzer.analyze_posts(posts)

            assert result["active_promotion"] is None
            assert "lectura" in result["recent_topics"]

    @pytest.mark.asyncio
    async def test_analyze_posts_detects_availability(self):
        """Should detect availability hints."""
        from services.post_analyzer import PostAnalyzer

        analyzer = PostAnalyzer()

        posts = [
            {
                "id": "1",
                "caption": "¡De camino a Bali! Estaré de retiro las próximas 2 semanas 🏝️",
                "timestamp": "2026-02-04T10:00:00+0000",
            }
        ]

        mock_llm_response = json.dumps({
            "active_promotion": None,
            "promotion_deadline": None,
            "promotion_urgency": None,
            "recent_topics": ["viaje", "Bali", "retiro"],
            "recent_products": [],
            "availability_hint": "De retiro en Bali por 2 semanas",
            "context_instructions": "El creador está de viaje, puede demorar en responder.",
        })

        with patch.object(analyzer, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_response

            result = await analyzer.analyze_posts(posts)

            assert result["availability_hint"] is not None
            assert "Bali" in result["availability_hint"]

    @pytest.mark.asyncio
    async def test_analyze_empty_posts(self):
        """Should handle empty post list."""
        from services.post_analyzer import PostAnalyzer

        analyzer = PostAnalyzer()

        result = await analyzer.analyze_posts([])

        assert result["active_promotion"] is None
        assert result["recent_topics"] == []
        assert "Sin posts" in result["context_instructions"]

    @pytest.mark.asyncio
    async def test_analyze_handles_llm_error(self):
        """Should handle LLM errors gracefully."""
        from services.post_analyzer import PostAnalyzer

        analyzer = PostAnalyzer()

        posts = [{"id": "1", "caption": "Test", "timestamp": "2026-02-04T10:00:00+0000"}]

        with patch.object(analyzer, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("LLM Error")

            result = await analyzer.analyze_posts(posts)

            assert result["active_promotion"] is None
            assert "Error" in result["context_instructions"]

    @pytest.mark.asyncio
    async def test_analyze_handles_invalid_json(self):
        """Should handle invalid JSON from LLM."""
        from services.post_analyzer import PostAnalyzer

        analyzer = PostAnalyzer()

        posts = [{"id": "1", "caption": "Test", "timestamp": "2026-02-04T10:00:00+0000"}]

        with patch.object(analyzer, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "not valid json"

            result = await analyzer.analyze_posts(posts)

            assert result["active_promotion"] is None
            assert result["context_instructions"] is not None

    def test_format_posts_for_prompt(self):
        """Should format posts for LLM prompt."""
        from services.post_analyzer import PostAnalyzer

        analyzer = PostAnalyzer()

        posts = [
            {"id": "1", "caption": "Post 1 content", "timestamp": "2026-02-04T10:00:00+0000"},
            {"id": "2", "caption": "Post 2 content", "timestamp": "2026-02-03T10:00:00+0000"},
        ]

        formatted = analyzer._format_posts_for_prompt(posts)

        assert "Post 1 content" in formatted
        assert "Post 2 content" in formatted
        assert "---" in formatted  # Separator

    def test_build_analysis_prompt(self):
        """Should build proper analysis prompt."""
        from services.post_analyzer import PostAnalyzer

        analyzer = PostAnalyzer()

        posts_text = "Post content here"
        prompt = analyzer._build_analysis_prompt(posts_text)

        assert "JSON" in prompt
        assert "active_promotion" in prompt
        assert "recent_topics" in prompt
        assert "availability_hint" in prompt
