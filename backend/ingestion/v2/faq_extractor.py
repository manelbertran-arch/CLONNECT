"""
FAQ Extractor - Extracts FAQs from website pages.

Looks for explicit FAQ sections and generates common FAQs from products/bio.
Saves to both RAG documents AND KnowledgeBase table.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ..deterministic_scraper import ScrapedPage
    from .bio_extractor import ExtractedBio
    from .product_detector import DetectedProduct

logger = logging.getLogger(__name__)


@dataclass
class ExtractedFAQ:
    """A single FAQ item."""

    question: str
    answer: str
    source_url: str
    source_type: str  # "explicit" (from page) or "generated" (from products/bio)
    confidence: float


@dataclass
class FAQExtractionResult:
    """Result of FAQ extraction."""

    faqs: List[ExtractedFAQ] = field(default_factory=list)
    source_urls: List[str] = field(default_factory=list)


# Patterns for FAQ page detection
FAQ_URL_PATTERNS = [
    r"/faq",
    r"/preguntas",
    r"/dudas",
    r"/ayuda",
    r"/help",
    r"/support",
]

# Patterns to identify Q&A structure
QA_PATTERNS = [
    # Spanish patterns
    r"\?[\s\n]+([A-Z][^?]+)",  # Question mark followed by answer
    r"(?:P|Pregunta)[:\.]?\s*([^?]+\?)\s*(?:R|Respuesta)[:\.]?\s*([^P]+?)(?=(?:P|Pregunta)|$)",
    # English patterns
    r"(?:Q|Question)[:\.]?\s*([^?]+\?)\s*(?:A|Answer)[:\.]?\s*([^Q]+?)(?=(?:Q|Question)|$)",
]


class FAQExtractor:
    """Extracts FAQs from website and generates common ones."""

    def __init__(self, max_faqs: int = 20, min_answer_length: int = 20):
        self.max_faqs = max_faqs
        self.min_answer_length = min_answer_length

    async def extract(
        self,
        pages: List["ScrapedPage"],
        products: Optional[List["DetectedProduct"]] = None,
        bio: Optional["ExtractedBio"] = None,
    ) -> FAQExtractionResult:
        """
        Extract FAQs from pages and generate common ones.

        Args:
            pages: Scraped website pages
            products: Detected products (for generating FAQs)
            bio: Extracted bio (for context)

        Returns:
            FAQExtractionResult with list of FAQs
        """
        result = FAQExtractionResult()

        # Step 1: Extract explicit FAQs from FAQ pages
        faq_pages = self._find_faq_pages(pages)
        for page in faq_pages:
            explicit_faqs = self._extract_faqs_from_page(page)
            result.faqs.extend(explicit_faqs)
            if explicit_faqs:
                result.source_urls.append(page.url)

        logger.info(f"Extracted {len(result.faqs)} explicit FAQs from {len(faq_pages)} pages")

        # Step 2: Generate common FAQs from products if we don't have enough
        if len(result.faqs) < 5 and products:
            generated = self._generate_product_faqs(products)
            result.faqs.extend(generated)
            logger.info(f"Generated {len(generated)} FAQs from products")

        # Step 3: Deduplicate and limit
        result.faqs = self._deduplicate_faqs(result.faqs)
        result.faqs = result.faqs[: self.max_faqs]

        return result

    def _find_faq_pages(self, pages: List["ScrapedPage"]) -> List["ScrapedPage"]:
        """Find pages that are likely FAQ pages."""
        faq_pages = []

        for page in pages:
            url_lower = page.url.lower()

            # Check URL patterns
            for pattern in FAQ_URL_PATTERNS:
                if re.search(pattern, url_lower):
                    faq_pages.append(page)
                    break

            # Check if content has FAQ-like structure
            if page not in faq_pages:
                content_lower = page.main_content.lower()
                if "preguntas frecuentes" in content_lower or "faq" in content_lower:
                    faq_pages.append(page)

        return faq_pages

    def _extract_faqs_from_page(self, page: "ScrapedPage") -> List[ExtractedFAQ]:
        """Extract Q&A pairs from a page."""
        faqs = []
        content = page.main_content

        # Try different patterns
        for pattern in QA_PATTERNS:
            matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                if isinstance(match, tuple) and len(match) >= 2:
                    question = match[0].strip()
                    answer = match[1].strip()
                elif isinstance(match, str):
                    # Single group match (answer after question mark)
                    continue  # Skip, need both Q and A

                if self._is_valid_faq(question, answer):
                    faqs.append(
                        ExtractedFAQ(
                            question=self._clean_question(question),
                            answer=self._clean_answer(answer),
                            source_url=page.url,
                            source_type="explicit",
                            confidence=0.9,
                        )
                    )

        # Also try to find question marks followed by content
        lines = content.split("\n")
        i = 0
        while i < len(lines) - 1:
            line = lines[i].strip()
            if line.endswith("?") and len(line) > 15:
                # Next non-empty lines might be the answer
                answer_lines = []
                j = i + 1
                while j < len(lines) and len(answer_lines) < 5:
                    next_line = lines[j].strip()
                    if next_line.endswith("?"):
                        break  # Next question
                    if next_line:
                        answer_lines.append(next_line)
                    j += 1

                if answer_lines:
                    answer = " ".join(answer_lines)
                    if self._is_valid_faq(line, answer):
                        faqs.append(
                            ExtractedFAQ(
                                question=self._clean_question(line),
                                answer=self._clean_answer(answer),
                                source_url=page.url,
                                source_type="explicit",
                                confidence=0.8,
                            )
                        )
                i = j
            else:
                i += 1

        return faqs

    def _generate_product_faqs(self, products: List["DetectedProduct"]) -> List[ExtractedFAQ]:
        """Generate common FAQs from product information."""
        faqs = []

        # Get products with prices
        priced_products = [p for p in products if p.price and p.price > 0]

        if priced_products:
            # FAQ about pricing
            if len(priced_products) == 1:
                p = priced_products[0]
                faqs.append(
                    ExtractedFAQ(
                        question=f"What is the price of {p.name}?",
                        answer=f"The price of {p.name} is {p.currency}{p.price}.",
                        source_url=p.source_url,
                        source_type="generated",
                        confidence=0.95,
                    )
                )
            else:
                price_range = f"{min(p.price for p in priced_products)}-{max(p.price for p in priced_products)}"
                currency = priced_products[0].currency or "EUR"
                faqs.append(
                    ExtractedFAQ(
                        question="What are the prices?",
                        answer=f"Prices range from {currency}{price_range} depending on the product/service.",
                        source_url=priced_products[0].source_url,
                        source_type="generated",
                        confidence=0.85,
                    )
                )

        # FAQ about what services are offered
        if products:
            services = [p.name for p in products[:5]]
            faqs.append(
                ExtractedFAQ(
                    question="What services do you offer?",
                    answer=f"I offer: {', '.join(services)}.",
                    source_url=products[0].source_url,
                    source_type="generated",
                    confidence=0.9,
                )
            )

        return faqs

    def _is_valid_faq(self, question: str, answer: str) -> bool:
        """Check if Q&A pair is valid."""
        if not question or not answer:
            return False
        if len(question) < 10 or len(answer) < self.min_answer_length:
            return False
        if len(question) > 300 or len(answer) > 1000:
            return False
        return True

    def _clean_question(self, question: str) -> str:
        """Clean question text."""
        question = question.strip()
        if not question.endswith("?"):
            question += "?"
        return question

    def _clean_answer(self, answer: str) -> str:
        """Clean answer text."""
        answer = re.sub(r"\s+", " ", answer)
        return answer.strip()

    def _deduplicate_faqs(self, faqs: List[ExtractedFAQ]) -> List[ExtractedFAQ]:
        """Remove duplicate FAQs based on question similarity."""
        seen_questions = set()
        unique_faqs = []

        for faq in faqs:
            # Normalize question for comparison
            normalized = re.sub(r"[^\w\s]", "", faq.question.lower())
            normalized = " ".join(normalized.split())

            if normalized not in seen_questions:
                seen_questions.add(normalized)
                unique_faqs.append(faq)

        return unique_faqs

    def to_dict(self, faq: ExtractedFAQ) -> dict:
        """Convert FAQ to dictionary."""
        return {
            "question": faq.question,
            "answer": faq.answer,
            "source_url": faq.source_url,
            "source_type": faq.source_type,
            "confidence": faq.confidence,
        }
