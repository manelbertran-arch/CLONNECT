"""
Test dual-save functionality for bio/FAQs/tone.

Verifies that data is saved to BOTH:
1. RAG documents (for chatbot)
2. UI tables (KnowledgeBase, knowledge_about)
"""

from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@dataclass
class MockExtractedBio:
    """Mock bio matching the new LLM-based ExtractedBio interface."""

    name: Optional[str] = "María García"
    bio_summary: str = "Coach de negocios que ayuda a emprendedores a escalar."
    source_url: str = "https://example.com/about"
    specialties: List[str] = field(default_factory=lambda: ["coaching", "negocios"])
    years_experience: Optional[int] = 10
    target_audience: Optional[str] = "Emprendedores"
    confidence: float = 0.85
    raw_text: str = "raw"

    @property
    def description(self) -> str:
        """Backwards compatibility alias."""
        return self.bio_summary


@dataclass
class MockExtractedFAQ:
    question: str = "What services do you offer?"
    answer: str = "I offer consulting and coaching."
    source_url: str = "https://example.com/faq"
    source_type: str = "extracted_literal"
    category: str = "other"
    context: str = "General"
    confidence: float = 0.95


@dataclass
class MockDetectedTone:
    style: str = "cercano y motivador"
    formality: str = "informal"
    language: str = "es"
    emoji_usage: str = "light"
    personality_traits: list = None
    communication_summary: str = "Se comunica de forma cercana y motivadora con su audiencia"
    suggested_bot_tone: str = "Tutea al usuario, usa tono motivador, incluye algún emoji ocasional"
    confidence: float = 0.85

    def __post_init__(self):
        if self.personality_traits is None:
            self.personality_traits = ["motivador", "cercano", "experto"]


class TestDualSave:
    """Test that _save_creator_knowledge saves to both RAG and UI tables."""

    def test_bio_saved_to_both_locations(self):
        """Bio should be saved to knowledge_about AND RAGDocument."""
        from ingestion.v2.pipeline import IngestionV2Pipeline

        # Mock DB session and models
        mock_db = MagicMock()
        mock_creator = MagicMock()
        mock_creator.id = "test-uuid"
        mock_creator.name = "testcreator"
        mock_creator.knowledge_about = {}

        # Setup query to return mock creator
        mock_db.query.return_value.filter.return_value.first.return_value = mock_creator

        pipeline = IngestionV2Pipeline(db_session=mock_db)
        bio = MockExtractedBio()

        # Call the method
        result = pipeline._save_creator_knowledge(
            creator_id="testcreator",
            bio=bio,
            faqs=[],
            tone=None,
        )

        assert result is True

        # Verify knowledge_about was updated with bio
        assert "bio" in mock_creator.knowledge_about
        assert mock_creator.knowledge_about["bio"] == bio.description
        assert mock_creator.knowledge_about["bio_source_url"] == bio.source_url

        # Verify RAGDocument was created (via db.merge)
        mock_db.merge.assert_called()

        # Verify commit was called
        mock_db.commit.assert_called_once()

    def test_faqs_saved_to_knowledgebase_and_rag(self):
        """FAQs should be saved to KnowledgeBase table AND RAGDocument."""
        from ingestion.v2.pipeline import IngestionV2Pipeline

        mock_db = MagicMock()
        mock_creator = MagicMock()
        mock_creator.id = "test-uuid"
        mock_creator.name = "testcreator"
        mock_creator.knowledge_about = {}

        mock_db.query.return_value.filter.return_value.first.return_value = mock_creator
        mock_db.query.return_value.filter.return_value.delete.return_value = 0

        pipeline = IngestionV2Pipeline(db_session=mock_db)
        faqs = [MockExtractedFAQ(), MockExtractedFAQ(question="How much?", answer="€97")]

        result = pipeline._save_creator_knowledge(
            creator_id="testcreator",
            bio=None,
            faqs=faqs,
            tone=None,
        )

        assert result is True

        # Verify db.add was called for each KnowledgeBase entry
        assert mock_db.add.call_count >= 2

        # Verify db.merge was called for RAG docs
        assert mock_db.merge.call_count >= 2

    def test_tone_saved_to_knowledge_about(self):
        """Tone should be saved to knowledge_about JSON field."""
        from ingestion.v2.pipeline import IngestionV2Pipeline

        mock_db = MagicMock()
        mock_creator = MagicMock()
        mock_creator.id = "test-uuid"
        mock_creator.name = "testcreator"
        mock_creator.knowledge_about = {}

        mock_db.query.return_value.filter.return_value.first.return_value = mock_creator

        pipeline = IngestionV2Pipeline(db_session=mock_db)
        tone = MockDetectedTone()

        result = pipeline._save_creator_knowledge(
            creator_id="testcreator",
            bio=None,
            faqs=[],
            tone=tone,
        )

        assert result is True

        # Verify tone was added to knowledge_about
        assert "tone" in mock_creator.knowledge_about
        assert mock_creator.knowledge_about["tone"]["style"] == "cercano y motivador"
        assert mock_creator.knowledge_about["tone"]["formality"] == "informal"
        assert mock_creator.knowledge_about["tone"]["language"] == "es"
        assert mock_creator.knowledge_about["tone"]["emoji_usage"] == "light"
        assert "personality_traits" in mock_creator.knowledge_about["tone"]
        assert "suggested_bot_tone" in mock_creator.knowledge_about["tone"]

    def test_no_db_returns_false(self):
        """Without DB session, should return False."""
        from ingestion.v2.pipeline import IngestionV2Pipeline

        pipeline = IngestionV2Pipeline(db_session=None)

        result = pipeline._save_creator_knowledge(
            creator_id="testcreator",
            bio=MockExtractedBio(),
            faqs=[],
            tone=None,
        )

        assert result is False

    def test_creator_not_found_returns_false(self):
        """If creator not found, should return False."""
        from ingestion.v2.pipeline import IngestionV2Pipeline

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        pipeline = IngestionV2Pipeline(db_session=mock_db)

        result = pipeline._save_creator_knowledge(
            creator_id="nonexistent",
            bio=MockExtractedBio(),
            faqs=[],
            tone=None,
        )

        assert result is False


class TestBioExtractor:
    """Test bio extraction from pages."""

    @pytest.mark.asyncio
    async def test_extracts_from_about_page_with_llm(self):
        """Should extract bio from /about page using LLM."""
        from ingestion.v2.bio_extractor import BioExtractor

        # Mock page
        mock_page = MagicMock()
        mock_page.url = "https://example.com/about"
        mock_page.main_content = """
        Sobre mí

        Soy María, coach de negocios con más de 10 años de experiencia.
        Ayudo a emprendedores a escalar sus negocios de forma sostenible.
        Mi metodología combina estrategia, mentalidad y sistemas probados.
        """

        # Mock LLM response
        mock_llm_response = """{
            "name": "María",
            "bio_summary": "Coach de negocios con 10 años de experiencia que ayuda a emprendedores a escalar sus negocios.",
            "specialties": ["coaching", "negocios", "estrategia"],
            "years_experience": 10,
            "target_audience": "Emprendedores"
        }"""

        with patch("ingestion.v2.bio_extractor.BioExtractor._get_llm_client") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.generate = AsyncMock(return_value=mock_llm_response)
            mock_get_llm.return_value = mock_llm

            extractor = BioExtractor()
            bio = await extractor.extract([mock_page])

            assert bio is not None
            assert bio.name == "María"
            assert len(bio.bio_summary) > 20
            assert "example.com/about" in bio.source_url
            assert "coaching" in bio.specialties
            assert bio.years_experience == 10

    @pytest.mark.asyncio
    async def test_finds_about_pages(self):
        """Should correctly identify about pages by URL pattern."""
        from ingestion.v2.bio_extractor import BioExtractor

        # Create mock pages
        home_page = MagicMock()
        home_page.url = "https://example.com/"

        about_page = MagicMock()
        about_page.url = "https://example.com/about"

        sobre_page = MagicMock()
        sobre_page.url = "https://example.com/sobre-mi"

        faq_page = MagicMock()
        faq_page.url = "https://example.com/faq"

        extractor = BioExtractor()
        about_pages = extractor._find_about_pages([home_page, about_page, sobre_page, faq_page])

        assert len(about_pages) == 2
        assert about_page in about_pages
        assert sobre_page in about_pages
        assert home_page not in about_pages
        assert faq_page not in about_pages


class TestFAQExtractor:
    """Test FAQ extraction."""

    @pytest.mark.asyncio
    async def test_extracts_explicit_faqs(self):
        """Should extract FAQs from FAQ page using LLM."""
        from ingestion.v2.faq_extractor import FAQExtractor

        mock_page = MagicMock()
        mock_page.url = "https://example.com/faq"
        mock_page.main_content = """
        Preguntas frecuentes

        ¿Cuánto cuesta el programa?
        El programa tiene un precio de €497 con opción de pago fraccionado.

        ¿Cuánto dura el programa?
        El programa dura 12 semanas con sesiones semanales de 90 minutos.
        """

        # Mock LLM response for CATEGORIZATION (hybrid approach)
        # LLM only categorizes, doesn't modify questions/answers
        mock_llm_response = """{
            "categorized_faqs": [
                {
                    "question": "¿Cuánto cuesta el programa?",
                    "answer": "El programa tiene un precio de €497 con opción de pago fraccionado.",
                    "category": "pricing",
                    "context": "Programa principal"
                },
                {
                    "question": "¿Cuánto dura el programa?",
                    "answer": "El programa dura 12 semanas con sesiones semanales de 90 minutos.",
                    "category": "process",
                    "context": "Programa principal"
                }
            ]
        }"""

        with patch("ingestion.v2.faq_extractor.FAQExtractor._get_llm_client") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.generate = AsyncMock(return_value=mock_llm_response)
            mock_get_llm.return_value = mock_llm

            extractor = FAQExtractor()
            result = await extractor.extract([mock_page])

            assert result is not None
            assert len(result.faqs) == 2
            assert result.faqs[0].question == "¿Cuánto cuesta el programa?"
            assert result.faqs[0].category == "pricing"
            assert result.faqs[1].category == "process"


class TestToneDetector:
    """Test tone detection."""

    @pytest.mark.asyncio
    async def test_detects_mentor_tone(self):
        """Should detect mentor tone from teaching content using LLM."""
        from ingestion.v2.tone_detector import ToneDetector

        mock_page = MagicMock()
        mock_page.url = "https://example.com"
        mock_page.main_content = """
        Te enseño paso a paso cómo construir tu negocio online desde cero.
        Descubre mi metodología probada que ha ayudado a cientos de emprendedores.
        Te guío en cada etapa del camino hacia el éxito empresarial.
        Mi experiencia de 10 años te ayudará a evitar los errores más comunes.
        Aprende las estrategias que realmente funcionan en el mundo digital.
        Transforma tu pasión en un negocio rentable con mi sistema comprobado.
        """

        # Mock LLM response
        mock_llm_response = """{
            "style": "mentor cercano",
            "formality": "informal",
            "language": "es",
            "emoji_usage": "none",
            "personality_traits": ["motivador", "experto", "cercano"],
            "communication_summary": "Se comunica como un mentor cercano que guía paso a paso",
            "suggested_bot_tone": "Tutea al usuario, usa tono motivador y cercano, menciona experiencia"
        }"""

        with patch("ingestion.v2.tone_detector.ToneDetector._get_llm_client") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.generate = AsyncMock(return_value=mock_llm_response)
            mock_get_llm.return_value = mock_llm

            detector = ToneDetector()
            tone = await detector.detect([mock_page])

            assert tone is not None
            assert tone.style == "mentor cercano"
            assert tone.formality == "informal"
            assert tone.language == "es"
            assert tone.emoji_usage == "none"
            assert len(tone.personality_traits) == 3
            assert "motivador" in tone.personality_traits
            assert len(tone.communication_summary) > 10
            assert len(tone.suggested_bot_tone) > 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
