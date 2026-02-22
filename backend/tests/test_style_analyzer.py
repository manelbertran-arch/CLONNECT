"""Tests for StyleAnalyzer with Spanish informal DM data.

Uses examples from multilingue_e_informal.md research document.
"""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# --- Test Data: Spanish informal DMs ---
STEFANO_MESSAGES = [
    {"content": "Hola! 🔥 Qué onda?", "created_at": datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc), "intent": "greeting", "copilot_action": None, "lead_status": "nuevo"},
    {"content": "Dale! Mira, el curso tiene 8 módulos", "created_at": datetime(2026, 2, 1, 10, 5, tzinfo=timezone.utc), "intent": "product_question", "copilot_action": "approved", "lead_status": "nuevo"},
    {"content": "Son 297€ y tienes acceso de por vida 💪", "created_at": datetime(2026, 2, 1, 10, 6, tzinfo=timezone.utc), "intent": "purchase_intent", "copilot_action": "edited", "lead_status": "caliente"},
    {"content": "jajaja tal cual! Es genial", "created_at": datetime(2026, 2, 1, 14, 0, tzinfo=timezone.utc), "intent": "casual", "copilot_action": None, "lead_status": "amigo"},
    {"content": "Claro! Acá te dejo el link: https://pay.hotmart.com/curso", "created_at": datetime(2026, 2, 1, 14, 10, tzinfo=timezone.utc), "intent": "purchase_intent", "copilot_action": "approved", "lead_status": "caliente"},
    {"content": "Crack! Ya te lo comparto", "created_at": datetime(2026, 2, 2, 9, 0, tzinfo=timezone.utc), "intent": "acknowledgment", "copilot_action": None, "lead_status": "cliente"},
    {"content": "Buenísimo 🔥❤️", "created_at": datetime(2026, 2, 2, 9, 30, tzinfo=timezone.utc), "intent": "reaction", "copilot_action": None, "lead_status": "amigo"},
    {"content": "Sí! Vamos con todo, el feedback del grupo fue espectacular", "created_at": datetime(2026, 2, 2, 15, 0, tzinfo=timezone.utc), "intent": "continuation", "copilot_action": None, "lead_status": "cliente"},
    {"content": "Ntp! Te cuento que sumamos 3 bonos nuevos esta semana", "created_at": datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc), "intent": "product_question", "copilot_action": None, "lead_status": "nuevo"},
    {"content": "Ey! Cómo vas? 😊", "created_at": datetime(2026, 2, 3, 11, 0, tzinfo=timezone.utc), "intent": "greeting", "copilot_action": None, "lead_status": "nuevo"},
    {"content": "Dale dale, te mando toda la info xq es clave", "created_at": datetime(2026, 2, 3, 11, 5, tzinfo=timezone.utc), "intent": "interest_soft", "copilot_action": None, "lead_status": "nuevo"},
    {"content": "Mira, básicamente es un programa de 3 meses donde...", "created_at": datetime(2026, 2, 3, 14, 0, tzinfo=timezone.utc), "intent": "product_question", "copilot_action": None, "lead_status": "caliente"},
    {"content": "💪", "created_at": datetime(2026, 2, 4, 10, 0, tzinfo=timezone.utc), "intent": "reaction", "copilot_action": None, "lead_status": "amigo"},
    {"content": "Genial! Cualquier duda me escribís", "created_at": datetime(2026, 2, 4, 10, 30, tzinfo=timezone.utc), "intent": "casual", "copilot_action": None, "lead_status": "nuevo"},
    {"content": "Vamos! El lunes arrancamos 🚀", "created_at": datetime(2026, 2, 4, 15, 0, tzinfo=timezone.utc), "intent": "encouragement", "copilot_action": None, "lead_status": "cliente"},
] * 3  # Repeat to get 45 messages (above MIN_MESSAGES_FOR_PROFILE=30)


class TestQuantitativeMetrics:
    """Test quantitative metric extraction."""

    def setup_method(self):
        from core.style_analyzer import StyleAnalyzer
        self.analyzer = StyleAnalyzer()

    def test_length_distribution(self):
        metrics = self.analyzer.extract_quantitative_metrics(STEFANO_MESSAGES)
        length = metrics["length"]
        assert length["char_mean"] > 0
        assert length["char_median"] > 0
        assert length["char_p10"] <= length["char_median"] <= length["char_p90"]
        assert length["char_min"] >= 1
        assert length["word_mean"] > 0

    def test_emoji_extraction(self):
        metrics = self.analyzer.extract_quantitative_metrics(STEFANO_MESSAGES)
        emoji = metrics["emoji"]
        assert emoji["total_count"] > 0
        assert emoji["msgs_with_emoji_pct"] > 0
        assert emoji["avg_per_message"] > 0
        top_emoji_chars = [e[0] for e in emoji["top_20"]]
        assert "🔥" in top_emoji_chars

    def test_abbreviation_detection(self):
        metrics = self.analyzer.extract_quantitative_metrics(STEFANO_MESSAGES)
        abbrevs = dict(metrics["abbreviations_top_20"])
        assert "xq" in abbrevs

    def test_muletilla_detection(self):
        metrics = self.analyzer.extract_quantitative_metrics(STEFANO_MESSAGES)
        muletillas = dict(metrics["muletillas_top_20"])
        assert "dale" in muletillas
        assert "mira" in muletillas

    def test_punctuation_stats(self):
        metrics = self.analyzer.extract_quantitative_metrics(STEFANO_MESSAGES)
        punct = metrics["punctuation"]
        assert "exclamation_pct" in punct
        assert "question_pct" in punct
        assert "laugh_pct" in punct
        assert punct["exclamation_pct"] >= 0
        assert punct["laugh_pct"] >= 0

    def test_opening_patterns(self):
        metrics = self.analyzer.extract_quantitative_metrics(STEFANO_MESSAGES)
        openers = dict(metrics["openers_top_10"])
        assert len(openers) > 0

    def test_style_by_lead_status(self):
        metrics = self.analyzer.extract_quantitative_metrics(STEFANO_MESSAGES)
        by_status = metrics["style_by_lead_status"]
        assert "nuevo" in by_status
        assert "caliente" in by_status
        assert by_status["nuevo"]["count"] >= 3

    def test_empty_messages_returns_empty(self):
        metrics = self.analyzer.extract_quantitative_metrics([])
        assert metrics == {}

    def test_hourly_distribution(self):
        metrics = self.analyzer.extract_quantitative_metrics(STEFANO_MESSAGES)
        hourly = metrics["hourly_distribution"]
        assert len(hourly) > 0
        assert any(h in hourly for h in [9, 10, 14])


class TestQualitativeProfile:
    """Test LLM-based qualitative analysis."""

    @pytest.mark.asyncio
    async def test_qualitative_profile_structure(self):
        """Mock LLM and verify output structure."""
        from core.style_analyzer import StyleAnalyzer

        mock_llm_response = json.dumps({
            "tone": "informal",
            "energy_level": "alto",
            "humor_usage": "frecuente",
            "sales_style": "consultivo",
            "empathy_level": "alto",
            "formality_markers": ["tuteo", "usa_emojis"],
            "signature_phrases": ["dale!", "vamos con todo 🔥"],
            "vocabulary_preferences": ["crack", "genial"],
            "avoids": ["estimado"],
            "greeting_style": "Informal con emoji",
            "closing_style": "CTA sutil",
            "sales_patterns": "Consulta primero, link después",
            "per_lead_type_differences": {
                "nuevo": "Cálido sin presión",
                "caliente": "Directo con links"
            },
            "dialect": "rioplatense",
            "code_switching": "Español/inglés ocasional",
            "overall_summary": "Energético e informal."
        })

        with patch(
            "core.providers.gemini_provider.generate_simple",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            analyzer = StyleAnalyzer()
            profile = await analyzer.extract_qualitative_profile(
                STEFANO_MESSAGES, "stefano_bonanno"
            )

            assert profile["tone"] == "informal"
            assert profile["energy_level"] == "alto"
            assert "dale!" in profile["signature_phrases"]
            assert profile["dialect"] == "rioplatense"


class TestProfileBuilder:
    """Test full profile building."""

    @pytest.mark.asyncio
    async def test_full_profile_generation(self):
        from core.style_analyzer import StyleAnalyzer

        mock_llm_response = json.dumps({
            "tone": "informal",
            "energy_level": "alto",
            "humor_usage": "frecuente",
            "sales_style": "consultivo",
            "empathy_level": "alto",
            "formality_markers": ["tuteo"],
            "signature_phrases": ["dale!"],
            "vocabulary_preferences": ["crack"],
            "avoids": ["estimado"],
            "greeting_style": "Informal",
            "closing_style": "CTA",
            "sales_patterns": "Consultivo",
            "per_lead_type_differences": {},
            "dialect": "rioplatense",
            "code_switching": "",
            "overall_summary": "Energético e informal."
        })

        with patch(
            "core.providers.gemini_provider.generate_simple",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            analyzer = StyleAnalyzer()
            analyzer._load_creator_messages = MagicMock(
                return_value=STEFANO_MESSAGES
            )

            profile = await analyzer.analyze_creator(
                "stefano_bonanno", "uuid-123", force=True
            )

            assert profile is not None
            assert profile["version"] == 1
            assert profile["creator_id"] == "stefano_bonanno"
            assert profile["confidence"] >= 0.5
            assert "quantitative" in profile
            assert "qualitative" in profile
            assert "prompt_injection" in profile
            assert len(profile["prompt_injection"]) > 50

    def test_insufficient_messages_returns_none(self):
        from core.style_analyzer import StyleAnalyzer
        analyzer = StyleAnalyzer()
        analyzer._load_creator_messages = MagicMock(return_value=[
            {"content": "Hola", "created_at": datetime.now(timezone.utc),
             "intent": "greeting", "copilot_action": None, "lead_status": "nuevo"}
        ] * 5)  # Only 5 messages, below MIN_MESSAGES_FOR_PROFILE

        import asyncio
        loop = asyncio.new_event_loop()
        try:
            profile = loop.run_until_complete(
                analyzer.analyze_creator("test", "uuid-test")
            )
            assert profile is None
        finally:
            loop.close()


class TestPromptInjection:
    """Test the generated prompt section."""

    def test_prompt_contains_length_info(self):
        from core.style_analyzer import StyleAnalyzer
        analyzer = StyleAnalyzer()
        quant = {
            "length": {"char_mean": 40, "char_p10": 8, "char_p90": 95, "word_mean": 7},
            "emoji": {"avg_per_message": 0.5, "top_20": [["🔥", 10]], "msgs_with_emoji_pct": 40},
            "punctuation": {"exclamation_pct": 35, "laugh_pct": 20, "ellipsis_pct": 5},
        }
        qual = {
            "tone": "informal",
            "dialect": "rioplatense",
            "overall_summary": "Energético e informal.",
            "signature_phrases": ["dale!"],
            "vocabulary_preferences": ["crack"],
            "avoids": ["estimado"],
            "sales_style": "consultivo",
            "sales_patterns": "Consulta primero",
            "formality_markers": ["tuteo"],
        }
        prompt = analyzer._generate_prompt_section(quant, qual, "stefano")

        assert "40" in prompt
        assert "🔥" in prompt
        assert "informal" in prompt
        assert "dale!" in prompt
        assert "estimado" in prompt


class TestRepresentativeSample:
    """Test message sampling for LLM analysis."""

    def test_sample_respects_n_limit(self):
        from core.style_analyzer import StyleAnalyzer
        analyzer = StyleAnalyzer()
        sample = analyzer._select_representative_sample(STEFANO_MESSAGES, n=10)
        assert len(sample) <= 10

    def test_sample_includes_recent(self):
        from core.style_analyzer import StyleAnalyzer
        analyzer = StyleAnalyzer()
        sample = analyzer._select_representative_sample(STEFANO_MESSAGES, n=10)
        assert sample[0] == STEFANO_MESSAGES[0]

    def test_sample_returns_all_if_under_limit(self):
        from core.style_analyzer import StyleAnalyzer
        analyzer = StyleAnalyzer()
        small_batch = STEFANO_MESSAGES[:5]
        sample = analyzer._select_representative_sample(small_batch, n=30)
        assert len(sample) == 5


class TestPercentile:
    """Test percentile utility."""

    def test_basic_percentile(self):
        from core.style_analyzer import _percentile
        data = list(range(1, 101))
        assert _percentile(data, 50) == pytest.approx(50.5, abs=1)
        assert _percentile(data, 90) == pytest.approx(90.1, abs=1)

    def test_empty_returns_zero(self):
        from core.style_analyzer import _percentile
        assert _percentile([], 50) == 0.0

    def test_single_element(self):
        from core.style_analyzer import _percentile
        assert _percentile([42], 50) == 42
