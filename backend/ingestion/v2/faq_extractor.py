"""
FAQ Extractor - Intelligent FAQ extraction using LLM.

Detects ANY FAQ-like content regardless of how it's labeled:
- "FAQ", "Preguntas frecuentes", "Preguntas y respuestas", "Dudas", etc.
- Question-answer patterns anywhere in the content
- Generates useful FAQs if none found explicitly
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
    from .product_detector import DetectedProduct

logger = logging.getLogger(__name__)

# Timeout for LLM calls
LLM_TIMEOUT = 45  # Longer timeout for FAQ extraction


@dataclass
class ExtractedFAQ:
    """A single FAQ item."""

    question: str
    answer: str
    source_url: str
    source_type: str  # "extracted" (found in web) or "generated" (created by LLM)
    category: str  # pricing|process|benefits|eligibility|getting_started|other
    confidence: float


@dataclass
class FAQExtractionResult:
    """Result of FAQ extraction."""

    faqs: List[ExtractedFAQ] = field(default_factory=list)
    source_urls: List[str] = field(default_factory=list)


# LLM prompt for FAQ extraction
FAQ_EXTRACTION_PROMPT = """Analiza este contenido web y extrae TODAS las preguntas y respuestas que encuentres.

CONTENIDO WEB:
{page_content}

---

BUSCA:
- Secciones de FAQ/Preguntas frecuentes (cualquier nombre: "Dudas", "Q&A", "Lo que debes saber", etc.)
- Patrones de pregunta-respuesta (¿...? seguido de explicación)
- Acordeones o listas con formato pregunta + respuesta
- Cualquier contenido estructurado como duda + solución

Si NO encuentras FAQs explícitas, genera 5-8 FAQs ÚTILES basadas en el contenido.

Responde SOLO con JSON válido:

{{
    "faqs": [
        {{
            "source": "extracted" o "generated",
            "question": "La pregunta (máx 150 chars)",
            "answer": "La respuesta (máx 500 chars, resumir si es muy larga)",
            "category": "pricing|process|benefits|eligibility|getting_started|other"
        }}
    ]
}}

CATEGORÍAS:
- pricing: precios, costos, pagos, descuentos
- process: cómo funciona, pasos, metodología
- benefits: resultados, beneficios, qué obtengo
- eligibility: para quién es, requisitos
- getting_started: cómo empezar, primeros pasos
- other: otras preguntas

REGLAS:
- Máximo 15 FAQs
- Respuestas concisas (máx 500 chars)
- NO inventes información que no esté en el contenido
- Si generas FAQs, básalas en lo que el creador ofrece
- Responde SOLO con el JSON"""


class FAQExtractor:
    """Extracts FAQs using LLM for intelligent detection."""

    def __init__(self, max_faqs: int = 15, max_content_chars: int = 6000):
        self.max_faqs = max_faqs
        self.max_content_chars = max_content_chars
        self._llm_client = None

    def _get_llm_client(self):
        """Lazy load LLM client."""
        if self._llm_client is None:
            from core.llm import get_llm_client

            self._llm_client = get_llm_client()
        return self._llm_client

    async def extract(
        self,
        pages: List["ScrapedPage"],
        products: Optional[List["DetectedProduct"]] = None,
        bio: Optional["ExtractedBio"] = None,
    ) -> FAQExtractionResult:
        """
        Extract FAQs from pages using LLM.

        Args:
            pages: Scraped website pages
            products: Detected products (for context)
            bio: Extracted bio (for context)

        Returns:
            FAQExtractionResult with list of FAQs
        """
        result = FAQExtractionResult()

        # Combine relevant page content
        combined_content = self._prepare_content(pages, products, bio)

        if not combined_content or len(combined_content.strip()) < 100:
            logger.warning("Not enough content for FAQ extraction")
            return result

        # Extract FAQs using LLM
        try:
            faqs = await self._extract_with_llm(combined_content, pages[0].url if pages else "")
            result.faqs = faqs[: self.max_faqs]
            result.source_urls = list(set(faq.source_url for faq in result.faqs))
            logger.info(f"Extracted {len(result.faqs)} FAQs using LLM")
        except Exception as e:
            logger.error(f"Error extracting FAQs: {e}")

        return result

    def _prepare_content(
        self,
        pages: List["ScrapedPage"],
        products: Optional[List["DetectedProduct"]],
        bio: Optional["ExtractedBio"],
    ) -> str:
        """Prepare combined content for LLM analysis."""
        parts = []

        # FAQ section keywords to search for
        faq_keywords = [
            "preguntas frecuentes",
            "preguntas y respuestas",
            "faq",
            "dudas",
            "lo que debes saber",
            "frequently asked",
            "q&a",
        ]

        # Add page content - SMART extraction for FAQs
        for page in pages[:5]:  # Limit to 5 pages
            content = page.main_content
            if content:
                page_content = ""
                content_lower = content.lower()

                # First, add beginning of page for context (1000 chars)
                page_content = content[:1000]

                # Then, search for FAQ sections and include them
                for keyword in faq_keywords:
                    kw_pos = content_lower.find(keyword)
                    if kw_pos >= 0:
                        # Found FAQ section - extract it (2000 chars from that point)
                        faq_section = content[kw_pos : kw_pos + 2000]
                        if faq_section not in page_content:
                            page_content += f"\n\n[SECCIÓN FAQ ENCONTRADA]\n{faq_section}"
                        break  # Only include first FAQ section found

                parts.append(f"[Página: {page.url}]\n{page_content}")

        # Add product context
        if products:
            product_info = "\n[PRODUCTOS/SERVICIOS OFRECIDOS]\n"
            for p in products[:5]:
                price_str = f" - {p.currency}{p.price}" if p.price else ""
                product_info += f"- {p.name}{price_str}\n"
            parts.append(product_info)

        # Add bio context
        if bio and bio.description:
            parts.append(f"\n[SOBRE EL CREADOR]\n{bio.description}")

        combined = "\n\n".join(parts)

        # Truncate if too long
        if len(combined) > self.max_content_chars:
            combined = combined[: self.max_content_chars] + "..."

        return combined

    async def _extract_with_llm(self, content: str, default_url: str) -> List[ExtractedFAQ]:
        """Extract FAQs using LLM."""
        llm = self._get_llm_client()
        prompt = FAQ_EXTRACTION_PROMPT.format(page_content=content)

        logger.info("Extracting FAQs using LLM...")

        # Call LLM with timeout
        response = await asyncio.wait_for(
            llm.generate(prompt, temperature=0.3, max_tokens=2000),
            timeout=LLM_TIMEOUT,
        )

        # Parse response
        faq_data = self._parse_llm_response(response)

        if not faq_data or "faqs" not in faq_data:
            logger.warning("No FAQs found in LLM response")
            return []

        # Convert to ExtractedFAQ objects
        faqs = []
        for item in faq_data["faqs"]:
            if not item.get("question") or not item.get("answer"):
                continue

            faq = ExtractedFAQ(
                question=self._clean_question(item["question"][:150]),
                answer=self._clean_answer(item["answer"][:500]),
                source_url=default_url,
                source_type=item.get("source", "extracted"),
                category=item.get("category", "other"),
                confidence=0.9 if item.get("source") == "extracted" else 0.75,
            )
            faqs.append(faq)

        logger.info(f"Parsed {len(faqs)} FAQs from LLM response")
        return faqs

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

    def _clean_question(self, question: str) -> str:
        """Clean question text."""
        question = re.sub(r"\s+", " ", question).strip()
        if not question.endswith("?"):
            question += "?"
        return question

    def _clean_answer(self, answer: str) -> str:
        """Clean answer text."""
        answer = re.sub(r"\s+", " ", answer)
        return answer.strip()

    def to_dict(self, faq: ExtractedFAQ) -> dict:
        """Convert FAQ to dictionary."""
        return {
            "question": faq.question,
            "answer": faq.answer,
            "source_url": faq.source_url,
            "source_type": faq.source_type,
            "category": faq.category,
            "confidence": faq.confidence,
        }
