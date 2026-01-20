"""
Bio Extractor - Intelligent extraction using LLM.

Extracts structured creator information from /about pages.
Works for any type of creator: coaches, traders, photographers, etc.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ..deterministic_scraper import ScrapedPage

logger = logging.getLogger(__name__)

# Timeout for LLM calls
LLM_TIMEOUT = 30


@dataclass
class ExtractedBio:
    """Extracted creator information."""

    # Core info
    name: Optional[str] = None  # Creator's name
    bio_summary: str = ""  # 1-2 sentence summary of what they do
    source_url: str = ""  # Where it was found

    # Additional structured info
    specialties: List[str] = field(default_factory=list)  # Keywords/expertise
    years_experience: Optional[int] = None  # Years of experience if mentioned
    target_audience: Optional[str] = None  # Who they help

    # Metadata
    confidence: float = 0.0
    raw_text: str = ""  # Original text for reference

    @property
    def description(self) -> str:
        """Alias for bio_summary for backwards compatibility."""
        return self.bio_summary


# Patterns to identify about pages
ABOUT_URL_PATTERNS = [
    r"/about",
    r"/sobre",
    r"/quien-soy",
    r"/who-am-i",
    r"/bio",
    r"/me$",
    r"/yo$",
    r"/conoceme",
    r"/mi-historia",
]

# LLM prompt for extraction
EXTRACTION_PROMPT = """Analiza esta página /about de un creador de contenido y extrae información estructurada.

TEXTO DE LA PÁGINA:
{page_content}

---

Extrae la siguiente información y responde SOLO con JSON válido:

{{
    "name": "Nombre del creador (si se menciona, sino null)",
    "bio_summary": "Resumen de 1-2 frases de QUÉ HACE y PARA QUIÉN. Máximo 250 caracteres. No copies el texto, RESUME.",
    "specialties": ["keyword1", "keyword2", ...],
    "years_experience": número o null si no se menciona,
    "target_audience": "A quién ayuda/para quién trabaja (1 frase corta)"
}}

REGLAS:
- bio_summary debe ser CORTO (máx 250 chars) - solo qué hace y para quién
- specialties: máximo 5 keywords relevantes
- Si no puedes extraer algo con certeza, pon null
- NO inventes información que no esté en el texto
- Responde SOLO con el JSON, sin explicaciones"""


class BioExtractor:
    """Extracts creator bio using LLM for intelligent parsing."""

    def __init__(self, max_content_chars: int = 4000):
        self.max_content_chars = max_content_chars
        self._llm_client = None

    def _get_llm_client(self):
        """Lazy load LLM client."""
        if self._llm_client is None:
            from core.llm import get_llm_client

            self._llm_client = get_llm_client()
        return self._llm_client

    async def extract(self, pages: List["ScrapedPage"]) -> Optional[ExtractedBio]:
        """
        Extract bio from list of scraped pages using LLM.

        Args:
            pages: List of ScrapedPage objects from scraper

        Returns:
            ExtractedBio if found, None otherwise
        """
        # First, find about pages
        about_pages = self._find_about_pages(pages)

        if about_pages:
            logger.info(f"Found {len(about_pages)} about pages")
            for page in about_pages:
                bio = await self._extract_with_llm(page)
                if bio and bio.bio_summary:
                    return bio

        # Fallback: try homepage or other pages
        logger.info("No about page found, trying other pages...")
        for page in pages[:3]:  # Try first 3 pages
            if page not in about_pages:
                bio = await self._extract_with_llm(page)
                if bio and bio.bio_summary:
                    return bio

        logger.warning("No bio found in any page")
        return None

    def _find_about_pages(self, pages: List["ScrapedPage"]) -> List["ScrapedPage"]:
        """Find pages that are likely about/bio pages."""
        about_pages = []

        for page in pages:
            url_lower = page.url.lower()
            for pattern in ABOUT_URL_PATTERNS:
                if re.search(pattern, url_lower):
                    about_pages.append(page)
                    break

        # Sort by URL specificity (shorter = more likely main about page)
        about_pages.sort(key=lambda p: len(p.url))
        return about_pages

    async def _extract_with_llm(self, page: "ScrapedPage") -> Optional[ExtractedBio]:
        """Extract bio from a single page using LLM."""
        content = page.main_content

        if not content or len(content.strip()) < 100:
            return None

        # Truncate content if too long
        if len(content) > self.max_content_chars:
            content = content[: self.max_content_chars] + "..."

        # Clean content
        content = self._clean_content(content)

        try:
            llm = self._get_llm_client()
            prompt = EXTRACTION_PROMPT.format(page_content=content)

            logger.info(f"Extracting bio from {page.url} using LLM...")

            # Call LLM with timeout
            response = await asyncio.wait_for(
                llm.generate(prompt, temperature=0.3, max_tokens=500),
                timeout=LLM_TIMEOUT,
            )

            # Parse JSON response
            bio_data = self._parse_llm_response(response)

            if not bio_data:
                return None

            # Create ExtractedBio
            bio = ExtractedBio(
                name=bio_data.get("name"),
                bio_summary=bio_data.get("bio_summary", "")[:250],  # Ensure max length
                source_url=page.url,
                specialties=bio_data.get("specialties", [])[:5],  # Max 5
                years_experience=bio_data.get("years_experience"),
                target_audience=bio_data.get("target_audience"),
                confidence=0.85 if bio_data.get("bio_summary") else 0.3,
                raw_text=content[:500],
            )

            logger.info(
                f"Bio extracted: name={bio.name}, summary={len(bio.bio_summary)} chars"
            )
            return bio

        except asyncio.TimeoutError:
            logger.warning(f"LLM timeout extracting bio from {page.url}")
            return None
        except Exception as e:
            logger.error(f"Error extracting bio: {e}")
            return None

    def _clean_content(self, content: str) -> str:
        """Clean page content for LLM processing."""
        # Remove excessive whitespace
        content = re.sub(r"\s+", " ", content)
        # Remove common navigation/footer text
        content = re.sub(
            r"(copyright|all rights reserved|privacy policy|terms of service).*",
            "",
            content,
            flags=re.IGNORECASE,
        )
        return content.strip()

    def _parse_llm_response(self, response: str) -> Optional[dict]:
        """Parse JSON from LLM response."""
        try:
            # Clean markdown code blocks if present
            response = response.strip()
            if response.startswith("```"):
                response = re.sub(r"^```json?\n?", "", response)
                response = re.sub(r"\n?```$", "", response)

            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            # Try to extract JSON from response
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            return None

    def to_dict(self, bio: ExtractedBio) -> dict:
        """Convert ExtractedBio to dictionary for storage."""
        return {
            "name": bio.name,
            "description": bio.bio_summary,  # Keep 'description' for compatibility
            "bio_summary": bio.bio_summary,
            "source_url": bio.source_url,
            "specialties": bio.specialties,
            "years_experience": bio.years_experience,
            "target_audience": bio.target_audience,
            "confidence": bio.confidence,
        }
