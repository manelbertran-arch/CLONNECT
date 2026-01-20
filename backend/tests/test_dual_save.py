"""
Test dual-save functionality for bio/FAQs/tone.

Verifies that data is saved to BOTH:
1. RAG documents (for chatbot)
2. UI tables (KnowledgeBase, knowledge_about)
"""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest


@dataclass
class MockExtractedBio:
    description: str = "I'm a test creator who helps people."
    source_url: str = "https://example.com/about"
    confidence: float = 0.9
    raw_text: str = "raw"


@dataclass
class MockExtractedFAQ:
    question: str = "What services do you offer?"
    answer: str = "I offer consulting and coaching."
    source_url: str = "https://example.com/faq"
    source_type: str = "explicit"
    confidence: float = 0.9


@dataclass
class MockDetectedTone:
    style: str = "mentor"
    formality: str = "informal"
    energy: str = "alta"
    confidence: float = 0.85
    indicators: list = None

    def __post_init__(self):
        if self.indicators is None:
            self.indicators = ["descubre", "aprende"]


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
        assert mock_creator.knowledge_about["tone"]["style"] == "mentor"
        assert mock_creator.knowledge_about["tone"]["formality"] == "informal"

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
    async def test_extracts_from_about_page(self):
        """Should extract bio from /about page."""
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

        extractor = BioExtractor()
        bio = await extractor.extract([mock_page])

        assert bio is not None
        assert len(bio.description) > 50
        assert "example.com/about" in bio.source_url


class TestFAQExtractor:
    """Test FAQ extraction."""

    @pytest.mark.asyncio
    async def test_extracts_explicit_faqs(self):
        """Should extract FAQs from FAQ page."""
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

        extractor = FAQExtractor()
        result = await extractor.extract([mock_page])

        assert result is not None
        assert len(result.faqs) >= 1


class TestToneDetector:
    """Test tone detection."""

    @pytest.mark.asyncio
    async def test_detects_mentor_tone(self):
        """Should detect mentor tone from teaching content."""
        from ingestion.v2.tone_detector import ToneDetector

        mock_page = MagicMock()
        mock_page.url = "https://example.com"
        mock_page.main_content = """
        Te enseño paso a paso cómo construir tu negocio online.
        Descubre mi metodología probada. Te guío en cada etapa.
        Mi experiencia de 10 años te ayudará a evitar errores comunes.
        """

        detector = ToneDetector()
        tone = await detector.detect([mock_page])

        assert tone is not None
        assert tone.style in ["mentor", "profesional"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
