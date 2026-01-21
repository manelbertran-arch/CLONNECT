"""
Tone Detector - Intelligent tone detection using LLM.

Analyzes website content to understand the creator's unique communication style.
Works for ANY type of creator in ANY language.
No fixed categories - each creator is unique.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ..deterministic_scraper import ScrapedPage
    from .bio_extractor import ExtractedBio

logger = logging.getLogger(__name__)

# Timeout for LLM calls
LLM_TIMEOUT = 30


@dataclass
class DetectedTone:
    """Detected tone profile from website - flexible, not fixed categories."""

    # Core tone (open-ended, not limited to fixed options)
    style: str  # e.g., "cercano", "inspirador", "técnico", "divertido", "motivacional"
    formality: str  # "formal", "informal", "mixto"

    # Language detection
    language: str  # Detected primary language (e.g., "es", "en", "pt")

    # Communication patterns
    emoji_usage: str  # "none", "light", "heavy"
    personality_traits: List[str] = field(default_factory=list)  # 3-5 traits

    # Summaries for chatbot
    communication_summary: str = ""  # 1 sentence describing how they communicate
    suggested_bot_tone: str = ""  # Instructions for chatbot to mimic (max 200 chars)

    # Metadata
    confidence: float = 0.0


# LLM prompt for tone detection - multi-language, flexible output
TONE_DETECTION_PROMPT = """Analyze this creator's communication tone based on their website content.

CREATOR'S CONTENT:
{content}

---

Detect the UNIQUE tone and personality of this creator. DO NOT limit to fixed categories.

Respond ONLY with valid JSON:

{{
    "style": "How they communicate in 1-2 words (e.g., 'cercano', 'inspirador', 'técnico', 'divertido', 'serio', 'motivacional', 'empático', 'directo', 'poético', 'enérgico')",
    "formality": "formal" | "informal" | "mixto",
    "language": "Primary language code (es/en/pt/fr/de/it/etc.)",
    "emoji_usage": "none" | "light" | "heavy",
    "personality_traits": ["trait1", "trait2", "trait3"],
    "communication_summary": "One sentence describing how this creator communicates with their audience",
    "suggested_bot_tone": "Brief instructions for a chatbot to mimic this creator's tone (max 200 chars)"
}}

GUIDELINES:
- style: Describe THEIR unique style, don't force into generic categories
- personality_traits: 3-5 traits that define their communicative personality
- communication_summary: Be specific to THIS creator, not generic
- suggested_bot_tone: Actionable instructions (what TO do, not what to avoid)
- Detect the actual language used, don't assume Spanish

IMPORTANT:
- Each creator is unique - describe their actual tone
- Be specific, not generic
- Respond ONLY with JSON"""


class ToneDetector:
    """Detects communication tone using LLM for intelligent analysis."""

    def __init__(self, max_content_chars: int = 4000):
        self.max_content_chars = max_content_chars
        self._llm_client = None

    def _get_llm_client(self):
        """Lazy load LLM client."""
        if self._llm_client is None:
            from core.llm import get_llm_client

            self._llm_client = get_llm_client()
        return self._llm_client

    async def detect(
        self,
        pages: List["ScrapedPage"],
        bio: Optional["ExtractedBio"] = None,
    ) -> Optional[DetectedTone]:
        """
        Detect tone from website pages using LLM.

        Args:
            pages: Scraped website pages
            bio: Extracted bio for additional context

        Returns:
            DetectedTone or None if not enough content
        """
        # Combine content for analysis
        combined_content = self._prepare_content(pages, bio)

        if not combined_content or len(combined_content.strip()) < 200:
            logger.warning("Not enough content for tone detection")
            return None

        try:
            tone = await self._detect_with_llm(combined_content)
            if tone:
                logger.info(
                    f"Detected tone: style='{tone.style}', formality={tone.formality}, "
                    f"language={tone.language}, confidence={tone.confidence:.2f}"
                )
            return tone
        except Exception as e:
            logger.error(f"Error detecting tone: {e}")
            return None

    def _prepare_content(
        self,
        pages: List["ScrapedPage"],
        bio: Optional["ExtractedBio"],
    ) -> str:
        """Prepare content for LLM analysis."""
        parts = []

        # Add page content
        for page in pages[:5]:  # Limit to 5 pages
            content = page.main_content
            if content and len(content.strip()) > 100:
                parts.append(content[:1500])

        # Add bio if available
        if bio and bio.description:
            parts.append(f"\n[ABOUT THE CREATOR]\n{bio.description}")

        combined = "\n\n".join(parts)

        # Truncate if too long
        if len(combined) > self.max_content_chars:
            combined = combined[: self.max_content_chars] + "..."

        return combined

    async def _detect_with_llm(self, content: str) -> Optional[DetectedTone]:
        """Detect tone using LLM."""
        llm = self._get_llm_client()
        prompt = TONE_DETECTION_PROMPT.format(content=content)

        logger.info("Detecting tone using LLM...")

        # Call LLM with timeout
        response = await asyncio.wait_for(
            llm.generate(prompt, temperature=0.3, max_tokens=800),
            timeout=LLM_TIMEOUT,
        )

        # Parse response
        tone_data = self._parse_llm_response(response)

        if not tone_data:
            logger.warning("Failed to parse tone from LLM response")
            return None

        # Create DetectedTone
        tone = DetectedTone(
            style=tone_data.get("style", "neutral")[:50],
            formality=self._validate_formality(tone_data.get("formality", "neutral")),
            language=tone_data.get("language", "es")[:10],
            emoji_usage=self._validate_emoji_usage(tone_data.get("emoji_usage", "none")),
            personality_traits=tone_data.get("personality_traits", [])[:5],
            communication_summary=tone_data.get("communication_summary", "")[:300],
            suggested_bot_tone=tone_data.get("suggested_bot_tone", "")[:200],
            confidence=0.85 if tone_data.get("style") else 0.5,
        )

        return tone

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

    def _validate_formality(self, value: str) -> str:
        """Validate formality value."""
        valid = ["formal", "informal", "mixto"]
        return value.lower() if value.lower() in valid else "informal"

    def _validate_emoji_usage(self, value: str) -> str:
        """Validate emoji_usage value."""
        valid = ["none", "light", "heavy"]
        return value.lower() if value.lower() in valid else "none"

    def to_dict(self, tone: DetectedTone) -> dict:
        """Convert DetectedTone to dictionary."""
        return {
            "style": tone.style,
            "formality": tone.formality,
            "language": tone.language,
            "emoji_usage": tone.emoji_usage,
            "personality_traits": tone.personality_traits,
            "communication_summary": tone.communication_summary,
            "suggested_bot_tone": tone.suggested_bot_tone,
            "confidence": tone.confidence,
        }
