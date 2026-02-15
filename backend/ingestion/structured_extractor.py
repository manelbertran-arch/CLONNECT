"""
Structured Content Extractor - Extract structured data using REGEX patterns.

NO LLM, NO HALLUCINATIONS - Only deterministic pattern matching.

Extracts:
- Products/Services with prices (regex-verified)
- Testimonials with attribution
- FAQs (question/answer pairs)
- Contact information
- Structured sections

Anti-hallucination principles:
1. Only extract what we can VERIFY exists on the page
2. Use regex for price extraction (not interpretation)
3. Track source_url for every extracted item
4. confidence field indicates how reliable the extraction is
"""

import re
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExtractedProduct:
    """A product/service extracted from a page."""
    name: str
    description: str
    price: Optional[float] = None
    currency: str = "EUR"
    source_url: str = ""
    price_verified: bool = False  # True if price was found via regex
    confidence: float = 0.0  # 0.0-1.0 extraction confidence


@dataclass
class ExtractedTestimonial:
    """A testimonial extracted from a page."""
    content: str
    author: str = "Anonymous"
    role: Optional[str] = None
    source_url: str = ""


@dataclass
class ExtractedFAQ:
    """A FAQ pair extracted from a page."""
    question: str
    answer: str
    source_url: str = ""


@dataclass
class ExtractedContent:
    """All structured content extracted from scraped pages."""
    products: List[ExtractedProduct] = field(default_factory=list)
    testimonials: List[ExtractedTestimonial] = field(default_factory=list)
    faqs: List[ExtractedFAQ] = field(default_factory=list)
    about_sections: List[Dict[str, str]] = field(default_factory=list)
    raw_chunks: List[Dict[str, Any]] = field(default_factory=list)  # For RAG indexing
    contact_info: Dict[str, str] = field(default_factory=dict)


class StructuredExtractor:
    """
    Extract structured data from scraped pages using deterministic patterns.
    No LLM, no AI interpretation - just regex and heuristics.
    """

    # Price patterns for different currencies
    PRICE_PATTERNS = [
        # EUR: 150€, €150, 150 EUR, 1.497€, 1,497€
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*€',
        r'€\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*EUR',
        r'EUR\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
        # USD: $150, 150$, 150 USD
        r'\$\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*\$',
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*USD',
        # Generic: precio, price, coste, cost
        r'(?:precio|price|coste|cost)[:.\s]*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
    ]

    # Testimonial indicators
    TESTIMONIAL_PATTERNS = [
        r'testimonios?',
        r'opiniones?',
        r'reviews?',
        r'clientes?\s+dicen',
        r'what\s+(?:they|clients?|customers?)\s+say',
        r'"[^"]{50,}"',  # Quoted text that looks like a testimonial
    ]

    # FAQ indicators
    FAQ_PATTERNS = [
        r'(?:faq|preguntas?\s+frecuentes?)',
        r'\?\s*$',  # Ends with question mark
    ]

    # Service/Product indicators
    SERVICE_PATTERNS = [
        r'(?:servicios?|services?)',
        r'(?:programas?|programs?)',
        r'(?:cursos?|courses?)',
        r'(?:talleres?|workshops?)',
        r'(?:sesiones?|sessions?)',
        r'(?:coaching|mentoria|mentoring)',
        r'(?:consultor[ií]a|consulting)',
    ]

    def _normalize_price(self, price_str: str) -> Optional[float]:
        """Convert price string to float."""
        if not price_str:
            return None

        # Remove currency symbols and whitespace
        clean = re.sub(r'[€$\s]', '', price_str)

        # Handle different decimal/thousand separators
        # Spanish: 1.497,00 -> 1497.00
        # English: 1,497.00 -> 1497.00
        if ',' in clean and '.' in clean:
            # Determine which is decimal separator
            if clean.rfind(',') > clean.rfind('.'):
                # Spanish format: 1.497,00
                clean = clean.replace('.', '').replace(',', '.')
            else:
                # English format: 1,497.00
                clean = clean.replace(',', '')
        elif ',' in clean:
            # Could be decimal or thousand
            parts = clean.split(',')
            if len(parts[-1]) == 2:
                # Decimal separator
                clean = clean.replace(',', '.')
            else:
                # Thousand separator
                clean = clean.replace(',', '')
        elif '.' in clean:
            # Check if it's a thousand separator
            parts = clean.split('.')
            if len(parts[-1]) == 3 and len(parts) > 1:
                # It's a thousand separator
                clean = clean.replace('.', '')

        try:
            return float(clean)
        except ValueError:
            return None

    def _detect_currency(self, text: str) -> str:
        """Detect currency from text."""
        if '€' in text or 'EUR' in text.upper():
            return 'EUR'
        if '$' in text or 'USD' in text.upper():
            return 'USD'
        if '£' in text or 'GBP' in text.upper():
            return 'GBP'
        return 'EUR'  # Default

    def _extract_price_from_text(self, text: str) -> tuple[Optional[float], bool]:
        """
        Extract price from text using regex patterns.

        Returns:
            (price, verified): price as float or None, and whether it was verified by regex
        """
        for pattern in self.PRICE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price = self._normalize_price(match.group(1))
                if price is not None and price > 0:
                    return price, True
        return None, False

    def extract_products(self, pages: List['ScrapedPage']) -> List[ExtractedProduct]:
        """
        Extract products/services from scraped pages.
        """

        products = []
        seen_names = set()

        for page in pages:
            # Check if this is a services/products page
            is_service_page = any(
                re.search(p, page.url, re.I) or re.search(p, page.title, re.I)
                for p in self.SERVICE_PATTERNS
            )

            # Extract from sections
            for section in page.sections:
                heading = section.get('heading', '')
                content = section.get('content', '')

                # Skip if too short
                if len(content) < 20:
                    continue

                # Check if this looks like a service/product
                full_text = f"{heading} {content}"
                is_service = is_service_page or any(
                    re.search(p, full_text, re.I) for p in self.SERVICE_PATTERNS
                )

                if is_service and heading and heading.lower() not in seen_names:
                    # Try to extract price
                    price, verified = self._extract_price_from_text(full_text)
                    currency = self._detect_currency(full_text)

                    # Calculate confidence
                    confidence = 0.3  # Base confidence for structure
                    if verified:
                        confidence += 0.4  # Price verified
                    if is_service_page:
                        confidence += 0.2  # On services page
                    if len(content) > 100:
                        confidence += 0.1  # Good description

                    products.append(ExtractedProduct(
                        name=heading.strip(),
                        description=content[:500].strip(),
                        price=price,
                        currency=currency,
                        source_url=page.url,
                        price_verified=verified,
                        confidence=min(confidence, 1.0)
                    ))
                    seen_names.add(heading.lower())

        logger.info(f"Extracted {len(products)} products from {len(pages)} pages")
        return products

    def extract_testimonials(self, pages: List['ScrapedPage']) -> List[ExtractedTestimonial]:
        """
        Extract testimonials from scraped pages.
        """
        testimonials = []
        seen_content = set()

        for page in pages:
            # Check if this is a testimonials page
            _is_testimonial_page = any(
                re.search(p, page.url, re.I) or re.search(p, page.title, re.I)
                for p in self.TESTIMONIAL_PATTERNS
            )

            # Look for quoted text (testimonial pattern)
            # Pattern: "Quote here" - Author Name
            quote_pattern = r'"([^"]{30,500})"(?:\s*[-–—]\s*([^"<]+))?'

            for match in re.finditer(quote_pattern, page.main_content):
                quote = match.group(1).strip()
                author = match.group(2).strip() if match.group(2) else "Anonymous"

                if quote and quote.lower() not in seen_content:
                    testimonials.append(ExtractedTestimonial(
                        content=quote,
                        author=author,
                        source_url=page.url
                    ))
                    seen_content.add(quote.lower())

            # Also check sections that look like testimonials
            for section in page.sections:
                heading = section.get('heading', '').lower()
                content = section.get('content', '')

                if any(re.search(p, heading, re.I) for p in self.TESTIMONIAL_PATTERNS):
                    # This section is testimonials - extract content
                    # Split by common separators
                    parts = re.split(r'(?<=[.!?])\s*(?=[A-Z"])', content)
                    for part in parts:
                        if len(part) > 30 and part.lower() not in seen_content:
                            testimonials.append(ExtractedTestimonial(
                                content=part.strip()[:500],
                                source_url=page.url
                            ))
                            seen_content.add(part.lower())

        logger.info(f"Extracted {len(testimonials)} testimonials")
        return testimonials

    def extract_faqs(self, pages: List['ScrapedPage']) -> List[ExtractedFAQ]:
        """
        Extract FAQ pairs from scraped pages.
        """
        faqs = []
        seen_questions = set()

        for page in pages:
            # Check sections for FAQ-like content
            for i, section in enumerate(page.sections):
                heading = section.get('heading', '')
                content = section.get('content', '')

                # Is this a question?
                is_question = (
                    heading.endswith('?') or
                    heading.lower().startswith(('how', 'what', 'why', 'when', 'who', 'where', 'can', 'do', 'is', 'are')) or
                    heading.lower().startswith(('cómo', 'qué', 'por qué', 'cuándo', 'quién', 'dónde', 'puedo', 'es', 'son'))
                )

                if is_question and content and heading.lower() not in seen_questions:
                    faqs.append(ExtractedFAQ(
                        question=heading.strip(),
                        answer=content[:500].strip(),
                        source_url=page.url
                    ))
                    seen_questions.add(heading.lower())

        logger.info(f"Extracted {len(faqs)} FAQs")
        return faqs

    def extract_about_sections(self, pages: List['ScrapedPage']) -> List[Dict[str, str]]:
        """
        Extract about/bio sections.
        """
        about_patterns = [
            r'sobre\s+m[ií]',
            r'about\s+me',
            r'who\s+am\s+i',
            r'quién\s+soy',
            r'mi\s+historia',
            r'my\s+story',
            r'biograf[ií]a',
            r'biography',
        ]

        sections = []
        for page in pages:
            # Check if this is an about page
            is_about_page = any(
                re.search(p, page.url, re.I) or re.search(p, page.title, re.I)
                for p in about_patterns
            )

            if is_about_page:
                sections.append({
                    'title': page.title,
                    'content': page.main_content[:2000],
                    'source_url': page.url
                })
            else:
                # Check sections
                for section in page.sections:
                    heading = section.get('heading', '').lower()
                    if any(re.search(p, heading, re.I) for p in about_patterns):
                        sections.append({
                            'title': section.get('heading', ''),
                            'content': section.get('content', '')[:2000],
                            'source_url': page.url
                        })

        logger.info(f"Extracted {len(sections)} about sections")
        return sections

    def extract_contact_info(self, pages: List['ScrapedPage']) -> Dict[str, str]:
        """
        Extract contact information using regex.
        """
        contact = {}

        for page in pages:
            text = page.main_content

            # Email
            if 'email' not in contact:
                email_match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', text)
                if email_match:
                    contact['email'] = email_match.group()

            # Phone
            if 'phone' not in contact:
                phone_match = re.search(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}', text)
                if phone_match:
                    contact['phone'] = phone_match.group()

            # Instagram
            if 'instagram' not in contact:
                ig_match = re.search(r'@([a-zA-Z0-9_.]+)', text)
                if ig_match:
                    contact['instagram'] = ig_match.group(1)

        return contact

    def create_rag_chunks(self, pages: List['ScrapedPage'], chunk_size: int = 500) -> List[Dict[str, Any]]:
        """
        Create RAG-ready chunks from pages with source tracking.
        """
        chunks = []

        for page in pages:
            # Main content chunks
            content = page.main_content
            for i in range(0, len(content), chunk_size - 50):  # 50 char overlap
                chunk_text = content[i:i + chunk_size]
                if len(chunk_text.strip()) > 50:
                    chunks.append({
                        'content': chunk_text.strip(),
                        'source_url': page.url,
                        'source_type': 'website',
                        'content_type': 'page_content',
                        'title': page.title,
                        'chunk_index': len(chunks),
                    })

            # Section-based chunks
            for section in page.sections:
                section_text = f"{section.get('heading', '')}\n{section.get('content', '')}"
                if len(section_text.strip()) > 50:
                    chunks.append({
                        'content': section_text.strip()[:chunk_size],
                        'source_url': page.url,
                        'source_type': 'website',
                        'content_type': 'section',
                        'title': section.get('heading', page.title),
                        'chunk_index': len(chunks),
                    })

        logger.info(f"Created {len(chunks)} RAG chunks from {len(pages)} pages")
        return chunks

    def extract_all(self, pages: List['ScrapedPage']) -> ExtractedContent:
        """
        Extract all structured content from pages.
        """
        return ExtractedContent(
            products=self.extract_products(pages),
            testimonials=self.extract_testimonials(pages),
            faqs=self.extract_faqs(pages),
            about_sections=self.extract_about_sections(pages),
            raw_chunks=self.create_rag_chunks(pages),
            contact_info=self.extract_contact_info(pages)
        )


# Singleton
_extractor: Optional[StructuredExtractor] = None

def get_structured_extractor() -> StructuredExtractor:
    """Get or create extractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = StructuredExtractor()
    return _extractor
