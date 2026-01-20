"""
Tests para Bio Extractor, FAQ Extractor y Tone Detector.

Ejecutar: pytest tests/test_bio_faq_tone.py -v
"""

import pytest
from dataclasses import dataclass
from typing import List


# Mock de ScrapedPage para tests
@dataclass
class MockScrapedPage:
    url: str
    title: str
    main_content: str
    sections: List[dict] = None
    links: List[str] = None

    def __post_init__(self):
        if self.sections is None:
            self.sections = []
        if self.links is None:
            self.links = []


class TestBioExtractor:
    """Tests para BioExtractor"""

    def test_find_bio_pages_by_url(self):
        """Debe encontrar páginas de bio por URL"""
        from ingestion.v2.bio_extractor import BioExtractor

        extractor = BioExtractor()

        pages = [
            MockScrapedPage(url="https://example.com/", title="Home", main_content="Welcome"),
            MockScrapedPage(url="https://example.com/about", title="About", main_content="About me"),
            MockScrapedPage(url="https://example.com/products", title="Products", main_content="Our products"),
        ]

        bio_pages = extractor._find_bio_pages(pages)
        urls = [p.url for p in bio_pages]

        assert "https://example.com/about" in urls
        assert "https://example.com/" in urls

    def test_extract_experience_years_from_text(self):
        """Debe extraer años de experiencia"""
        from ingestion.v2.bio_extractor import BioExtractor

        extractor = BioExtractor()

        test_cases = [
            ("Tengo 10 años de experiencia", 10),
            ("Más de 5 años en el sector", 5),
            ("Con 3 años de experiencia en coaching", 3),
        ]

        for text, expected in test_cases:
            result = extractor._extract_experience_years(text)
            assert result == expected, f"En '{text}' esperaba {expected}, encontró {result}"

    def test_extract_specialties_from_text(self):
        """Debe extraer especialidades del texto"""
        from ingestion.v2.bio_extractor import BioExtractor

        extractor = BioExtractor()

        text = "Soy coach de bienestar y meditación. También hago yoga y fitness."
        specialties = extractor._extract_specialties_from_text(text)

        assert len(specialties) > 0
        specialties_lower = [s.lower() for s in specialties]
        assert any("coach" in s or "coaching" in s for s in specialties_lower)

    @pytest.mark.asyncio
    async def test_extract_returns_creator_bio(self):
        """Debe retornar un CreatorBio válido"""
        from ingestion.v2.bio_extractor import BioExtractor, CreatorBio

        extractor = BioExtractor()

        pages = [
            MockScrapedPage(
                url="https://example.com/about",
                title="Sobre mí",
                main_content="Soy un coach con 5 años de experiencia en bienestar y meditación. "
                "Ayudo a personas a encontrar equilibrio en sus vidas.",
            )
        ]

        bio = await extractor.extract(pages)

        assert isinstance(bio, CreatorBio)
        assert bio.experience_years == 5


class TestFAQExtractor:
    """Tests para FAQExtractor"""

    def test_find_faq_pages_by_url(self):
        """Debe encontrar páginas de FAQ por URL"""
        from ingestion.v2.faq_extractor import FAQExtractor

        extractor = FAQExtractor()

        pages = [
            MockScrapedPage(url="https://example.com/", title="Home", main_content="Welcome"),
            MockScrapedPage(url="https://example.com/faq", title="FAQ", main_content="Questions"),
            MockScrapedPage(url="https://example.com/products", title="Products", main_content="Products"),
        ]

        faq_pages = extractor._find_faq_pages(pages)
        urls = [p.url for p in faq_pages]

        assert "https://example.com/faq" in urls

    def test_find_faq_pages_by_content(self):
        """Debe encontrar páginas de FAQ por contenido"""
        from ingestion.v2.faq_extractor import FAQExtractor

        extractor = FAQExtractor()

        pages = [
            MockScrapedPage(
                url="https://example.com/ayuda",
                title="Ayuda",
                main_content="Preguntas Frecuentes\n¿Cómo funciona? Es muy fácil...",
            ),
        ]

        faq_pages = extractor._find_faq_pages(pages)
        assert len(faq_pages) == 1

    def test_categorize_faq(self):
        """Debe categorizar FAQs correctamente"""
        from ingestion.v2.faq_extractor import FAQExtractor

        extractor = FAQExtractor()

        test_cases = [
            ("¿Qué incluye el producto?", "El producto incluye...", "producto"),
            ("¿Cómo puedo pagar?", "Aceptamos tarjeta y PayPal", "pago"),
            ("¿Cómo son las sesiones?", "Las sesiones de coaching...", "servicio"),
        ]

        for question, answer, expected_category in test_cases:
            category = extractor._categorize_faq(question, answer)
            assert category == expected_category, f"'{question}' debería ser '{expected_category}', fue '{category}'"

    def test_extract_faqs_from_text(self):
        """Debe extraer FAQs de texto estructurado"""
        from ingestion.v2.faq_extractor import FAQExtractor

        extractor = FAQExtractor()

        text = """
        ¿Qué incluye el programa?
        El programa incluye videos, guías y acceso a la comunidad durante 30 días.

        ¿Cuánto cuesta?
        El precio es de 99€ con acceso de por vida.
        """

        faqs = extractor._extract_faqs_from_text(text)
        assert len(faqs) >= 1

    @pytest.mark.asyncio
    async def test_extract_returns_faq_list(self):
        """Debe retornar una lista de FAQs"""
        from ingestion.v2.faq_extractor import FAQExtractor, FAQ

        extractor = FAQExtractor()

        pages = [
            MockScrapedPage(
                url="https://example.com/faq",
                title="FAQ",
                main_content="""
                ¿Qué incluye el curso?
                El curso incluye 10 módulos con videos y ejercicios prácticos.
                """,
            )
        ]

        faqs = await extractor.extract(pages)

        assert isinstance(faqs, list)
        for faq in faqs:
            assert isinstance(faq, FAQ)


class TestToneDetector:
    """Tests para ToneDetector"""

    def test_detect_emojis(self):
        """Debe detectar uso de emojis"""
        from ingestion.v2.tone_detector import ToneDetector

        detector = ToneDetector()

        text_with_emojis = "¡Hola! 😊 Bienvenido 🎉 Esto es genial 💪 ❤️"
        text_without = "Hola. Bienvenido. Esto es profesional."

        assert detector._detect_emojis(text_with_emojis) is True
        assert detector._detect_emojis(text_without) is False

    def test_detect_formality_informal(self):
        """Debe detectar tono informal (tuteo)"""
        from ingestion.v2.tone_detector import ToneDetector

        detector = ToneDetector()

        text = "Hola! ¿Cómo estás? Te cuento que puedes inscribirte ya. Tienes acceso inmediato."
        formality = detector._detect_formality(text)

        assert formality == "informal"

    def test_detect_formality_formal(self):
        """Debe detectar tono formal (usted)"""
        from ingestion.v2.tone_detector import ToneDetector

        detector = ToneDetector()

        text = "Estimado cliente, le ofrecemos nuestros servicios. Usted puede contactarnos cuando desee."
        formality = detector._detect_formality(text)

        assert formality == "formal"

    def test_detect_tone_mentor(self):
        """Debe detectar tono mentor"""
        from ingestion.v2.tone_detector import ToneDetector

        detector = ToneDetector()

        text = "Te ayudo a transformar tu vida. Juntos recorreremos este camino de consciencia y crecimiento personal."
        tone, score = detector._detect_tone_from_patterns(text)

        assert tone == "mentor"

    def test_detect_tone_vendedor(self):
        """Debe detectar tono vendedor"""
        from ingestion.v2.tone_detector import ToneDetector

        detector = ToneDetector()

        text = "¡Oferta exclusiva! Solo hoy, plazas limitadas. Aprovecha este descuento único."
        tone, score = detector._detect_tone_from_patterns(text)

        assert tone == "vendedor"

    @pytest.mark.asyncio
    async def test_detect_returns_tone_config(self):
        """Debe retornar ToneConfig válido"""
        from ingestion.v2.tone_detector import ToneDetector, ToneConfig

        detector = ToneDetector()

        pages = [
            MockScrapedPage(
                url="https://example.com/",
                title="Home",
                main_content="¡Hola! 😊 Te ayudo a transformar tu bienestar. Juntos podemos lograr tus metas.",
            )
        ]

        tone = await detector.detect(pages)

        assert isinstance(tone, ToneConfig)
        assert tone.tone in ["amigo", "mentor", "vendedor", "profesional"]
        assert tone.formality in ["informal", "formal"]
        assert isinstance(tone.emoji_usage, bool)
        assert len(tone.instructions) > 0


class TestFullExtraction:
    """Tests de integración completa"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_full_extraction_stefanobonanno(self):
        """
        Test completo con stefanobonanno.com

        NOTA: Este test hace requests reales a la web.
        Marcado como 'slow' para ejecutar solo cuando se necesite.
        """
        from ingestion.v2.bio_extractor import BioExtractor
        from ingestion.v2.faq_extractor import FAQExtractor
        from ingestion.v2.tone_detector import ToneDetector
        from ingestion.deterministic_scraper import DeterministicScraper

        # Scrapear la web
        scraper = DeterministicScraper(max_pages=10)
        pages = await scraper.scrape_website("https://www.stefanobonanno.com")

        assert len(pages) > 0, "Debe scrapear páginas"

        # Extraer bio
        bio_extractor = BioExtractor()
        bio = await bio_extractor.extract(pages)
        assert bio is not None
        # La bio puede estar vacía si no hay LLM configurado

        # Extraer FAQs
        faq_extractor = FAQExtractor()
        faqs = await faq_extractor.extract(pages)
        assert isinstance(faqs, list)

        # Detectar tono
        tone_detector = ToneDetector()
        tone = await tone_detector.detect(pages, bio)
        assert tone is not None
        assert tone.tone in ["amigo", "mentor", "vendedor", "profesional"]

        # Log resultados
        print(f"\n=== RESULTADOS EXTRACCIÓN ===")
        print(f"Bio: {bio.to_dict() if hasattr(bio, 'to_dict') else bio}")
        print(f"FAQs: {len(faqs)} encontradas")
        print(f"Tone: {tone.tone}, formality: {tone.formality}")
