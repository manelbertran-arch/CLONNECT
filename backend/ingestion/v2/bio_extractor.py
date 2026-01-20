"""
Bio Extractor - Extracts creator bio from website pages.

Focuses on /about, /sobre-mi, /who-am-i pages.
Returns structured bio data for knowledge_about field.
"""

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ..deterministic_scraper import ScrapedPage

logger = logging.getLogger(__name__)


@dataclass
class ExtractedBio:
    """Extracted bio information."""

    description: str  # Main bio text
    source_url: str  # Where it was found
    confidence: float  # 0-1 confidence score
    raw_text: str  # Original text before cleanup


# Patterns to identify about pages
ABOUT_URL_PATTERNS = [
    r"/about",
    r"/sobre",
    r"/quien-soy",
    r"/who-am-i",
    r"/bio",
    r"/me$",
    r"/yo$",
]

# Patterns to identify bio content in page
BIO_SECTION_PATTERNS = [
    r"(?:sobre\s+m[ií]|about\s+me|who\s+i\s+am|mi\s+historia)",
    r"(?:soy\s+\w+|my\s+name\s+is|i(?:'m|\s+am)\s+\w+)",
    r"(?:hola[,!]?\s+soy|hey[,!]?\s+i(?:'m|\s+am))",
]


class BioExtractor:
    """Extracts bio from scraped website pages."""

    def __init__(self, min_bio_length: int = 100, max_bio_length: int = 2000):
        self.min_bio_length = min_bio_length
        self.max_bio_length = max_bio_length

    async def extract(self, pages: List["ScrapedPage"]) -> Optional[ExtractedBio]:
        """
        Extract bio from list of scraped pages.

        Args:
            pages: List of ScrapedPage objects from scraper

        Returns:
            ExtractedBio if found, None otherwise
        """
        # First, look for dedicated about pages
        about_pages = self._find_about_pages(pages)

        if about_pages:
            logger.info(f"Found {len(about_pages)} about pages")
            for page in about_pages:
                bio = self._extract_bio_from_page(page)
                if bio:
                    return bio

        # Fallback: look for bio sections in homepage or other pages
        logger.info("No about page found, searching in other pages...")
        for page in pages:
            bio = self._extract_bio_from_page(page, strict=False)
            if bio:
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

    def _extract_bio_from_page(
        self, page: "ScrapedPage", strict: bool = True
    ) -> Optional[ExtractedBio]:
        """Extract bio text from a single page."""
        content = page.main_content

        if not content or len(content) < self.min_bio_length:
            return None

        # Clean content
        cleaned = self._clean_text(content)

        # For about pages, use more of the content
        if not strict:
            # Look for bio section markers
            bio_text = self._find_bio_section(cleaned)
            if not bio_text:
                return None
        else:
            # For about pages, use most of the content (it's likely all relevant)
            bio_text = cleaned

        # Truncate if too long
        if len(bio_text) > self.max_bio_length:
            # Try to cut at sentence boundary
            bio_text = self._truncate_at_sentence(bio_text, self.max_bio_length)

        # Validate minimum length
        if len(bio_text) < self.min_bio_length:
            return None

        # Calculate confidence
        confidence = self._calculate_confidence(page, bio_text, strict)

        return ExtractedBio(
            description=bio_text,
            source_url=page.url,
            confidence=confidence,
            raw_text=content[:500],  # Keep first 500 chars of raw
        )

    def _clean_text(self, text: str) -> str:
        """Clean text for bio extraction."""
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)
        # Remove common navigation text
        text = re.sub(
            r"(menu|nav|footer|header|copyright|all rights reserved).*?(?=\.|$)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        # Remove email addresses (will be extracted separately)
        text = re.sub(r"\S+@\S+\.\S+", "", text)
        # Remove URLs
        text = re.sub(r"https?://\S+", "", text)

        return text.strip()

    def _find_bio_section(self, text: str) -> Optional[str]:
        """Find the bio section in a larger text."""
        text_lower = text.lower()

        for pattern in BIO_SECTION_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                # Get text from match position
                start = match.start()
                # Get about 1000 chars or until end
                end = min(start + 1000, len(text))
                # Try to end at sentence boundary
                section = text[start:end]
                return self._truncate_at_sentence(section, 1000)

        return None

    def _truncate_at_sentence(self, text: str, max_length: int) -> str:
        """Truncate text at a sentence boundary."""
        if len(text) <= max_length:
            return text

        # Find last sentence end before max_length
        truncated = text[:max_length]
        last_period = truncated.rfind(".")
        last_exclaim = truncated.rfind("!")
        last_question = truncated.rfind("?")

        last_sentence_end = max(last_period, last_exclaim, last_question)

        if last_sentence_end > max_length * 0.5:  # At least 50% of max
            return text[: last_sentence_end + 1]

        return truncated + "..."

    def _calculate_confidence(
        self, page: "ScrapedPage", bio_text: str, from_about_page: bool
    ) -> float:
        """Calculate confidence score for extracted bio."""
        score = 0.5  # Base score

        # Higher confidence for about pages
        if from_about_page:
            score += 0.2

        # Higher confidence for longer bios
        if len(bio_text) > 300:
            score += 0.1
        if len(bio_text) > 500:
            score += 0.1

        # Lower confidence if contains too many special characters
        special_ratio = len(re.findall(r"[^\w\s.,!?]", bio_text)) / max(len(bio_text), 1)
        if special_ratio > 0.1:
            score -= 0.2

        # Cap at 0.95
        return min(0.95, max(0.1, score))

    def to_dict(self, bio: ExtractedBio) -> dict:
        """Convert ExtractedBio to dictionary for storage."""
        return {
            "description": bio.description,
            "source_url": bio.source_url,
            "confidence": bio.confidence,
        }
