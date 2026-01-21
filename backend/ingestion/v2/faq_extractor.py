"""
FAQ Extractor - LITERAL FAQ extraction using LLM.

FILOSOFÍA CLONNECT: El sistema debe ser FIEL al contenido del creador.
NO parafrasear, NO reformular, NO inventar.

Extrae FAQs LITERALMENTE como aparecen en la web del creador.
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
LLM_TIMEOUT = 60  # Longer timeout for multiple pages


@dataclass
class ExtractedFAQ:
    """A single FAQ item."""

    question: str  # LITERAL question from the web
    answer: str  # LITERAL answer (or summarized if >500 chars)
    source_url: str
    source_type: str  # "extracted_literal" | "extracted_summarized" | "generated"
    category: str  # pricing|process|benefits|eligibility|getting_started|other
    context: str  # Product/service name this FAQ belongs to
    confidence: float


@dataclass
class FAQExtractionResult:
    """Result of FAQ extraction."""

    faqs: List[ExtractedFAQ] = field(default_factory=list)
    source_urls: List[str] = field(default_factory=list)


# LLM prompt for LITERAL FAQ extraction
FAQ_EXTRACTION_PROMPT = """Extrae LITERALMENTE todas las preguntas y respuestas de este contenido web.

CONTENIDO WEB:
{page_content}

---

INSTRUCCIONES CRÍTICAS - LEE CON ATENCIÓN:

1. EXTRACCIÓN LITERAL:
   - Copia la pregunta EXACTAMENTE como aparece en la web
   - Copia la respuesta EXACTAMENTE como aparece
   - NO parafrasees, NO reformules, NO cambies palabras
   - Si la respuesta es muy larga (>500 chars), resume MANTENIENDO la información clave

2. IDENTIFICA EL CONTEXTO:
   - Determina a qué producto/servicio pertenece cada FAQ
   - Usa el título de la sección o el nombre del producto
   - Si es FAQ general, usa "General"

3. BUSCA EN TODO EL CONTENIDO:
   - Secciones FAQ/Preguntas frecuentes
   - Patrones ¿...? seguido de explicación
   - Acordeones o listas pregunta-respuesta
   - Cualquier formato de duda + solución

Responde SOLO con JSON válido:

{{
    "faqs": [
        {{
            "source": "extracted_literal" | "extracted_summarized" | "generated",
            "question": "COPIA EXACTA de la pregunta",
            "answer": "COPIA EXACTA de la respuesta (o resumen si >500 chars)",
            "context": "Nombre del producto/servicio al que pertenece",
            "category": "pricing|process|benefits|eligibility|getting_started|other"
        }}
    ]
}}

CATEGORÍAS:
- pricing: precios, costos, pagos, descuentos
- process: cómo funciona, pasos, metodología, duración
- benefits: resultados, beneficios, qué obtengo
- eligibility: para quién es, requisitos
- getting_started: cómo empezar, primeros pasos
- other: otras preguntas

REGLAS IMPORTANTES:
- Extrae TODAS las FAQs que encuentres (sin límite arbitrario)
- PRIORIZA "extracted_literal" sobre "generated"
- Solo genera FAQs si NO encuentras ninguna explícita
- Las FAQs generadas deben basarse SOLO en información del contenido
- Responde ÚNICAMENTE con el JSON, sin texto adicional"""


class FAQExtractor:
    """Extracts FAQs LITERALLY using LLM - faithful to creator's content."""

    def __init__(self, max_faqs: int = 100, max_content_chars: int = 12000):
        # max_faqs alto (100) - el límite real es el contexto del LLM, no un número arbitrario
        # Si el creador tiene 50 FAQs, extraemos 50
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
        Extract FAQs LITERALLY from ALL pages using LLM.

        Args:
            pages: Scraped website pages
            products: Detected products (for context)
            bio: Extracted bio (for context)

        Returns:
            FAQExtractionResult with list of FAQs
        """
        result = FAQExtractionResult()

        # Prepare content from ALL pages with FAQs
        combined_content, page_urls = self._prepare_content(pages, products, bio)

        if not combined_content or len(combined_content.strip()) < 100:
            logger.warning("Not enough content for FAQ extraction")
            return result

        # Extract FAQs using LLM
        try:
            faqs = await self._extract_with_llm(combined_content, page_urls)
            result.faqs = faqs[: self.max_faqs]
            result.source_urls = list(set(faq.source_url for faq in result.faqs))

            # Log extraction stats
            literal_count = sum(1 for f in result.faqs if f.source_type == "extracted_literal")
            summarized_count = sum(1 for f in result.faqs if f.source_type == "extracted_summarized")
            generated_count = sum(1 for f in result.faqs if f.source_type == "generated")
            logger.info(
                f"Extracted {len(result.faqs)} FAQs: "
                f"{literal_count} literal, {summarized_count} summarized, {generated_count} generated"
            )
        except Exception as e:
            logger.error(f"Error extracting FAQs: {e}")

        return result

    def _prepare_content(
        self,
        pages: List["ScrapedPage"],
        products: Optional[List["DetectedProduct"]],
        bio: Optional["ExtractedBio"],
    ) -> tuple[str, dict]:
        """
        Prepare combined content for LLM analysis.

        Returns:
            Tuple of (combined_content, {page_index: url} mapping)
        """
        parts = []
        page_urls = {}
        page_index = 0

        # FAQ section keywords to search for
        faq_keywords = [
            "preguntas frecuentes",
            "preguntas y respuestas",
            "faq",
            "dudas",
            "lo que debes saber",
            "frequently asked",
            "q&a",
            "preguntas",
            "respuestas",
        ]

        # Process ALL pages - no arbitrary limit
        for page in pages:
            content = page.main_content
            if not content:
                continue

            content_lower = content.lower()
            has_faq_section = False
            page_content_parts = []

            # Search for ALL FAQ sections in this page
            for keyword in faq_keywords:
                # Find all occurrences of this keyword
                start_pos = 0
                while True:
                    kw_pos = content_lower.find(keyword, start_pos)
                    if kw_pos < 0:
                        break

                    has_faq_section = True
                    # Extract FAQ section (3000 chars from that point for more complete extraction)
                    faq_section = content[kw_pos : kw_pos + 3000]

                    # Avoid duplicates
                    if faq_section not in "".join(page_content_parts):
                        page_content_parts.append(f"\n[SECCIÓN FAQ: {keyword.upper()}]\n{faq_section}")

                    start_pos = kw_pos + len(keyword) + 500  # Move past this section

            # If page has FAQ sections, include it with context
            if has_faq_section:
                page_header = f"\n{'='*50}\n[PÁGINA {page_index + 1}: {page.url}]\n{'='*50}\n"

                # Add page title/beginning for context (500 chars)
                context_intro = content[:500]
                page_content = page_header + f"[CONTEXTO DE PÁGINA]\n{context_intro}\n"
                page_content += "\n".join(page_content_parts)

                parts.append(page_content)
                page_urls[page_index] = page.url
                page_index += 1

        # If no FAQ sections found, include first 3 pages for general extraction
        if not parts:
            logger.info("No explicit FAQ sections found, using general content")
            for i, page in enumerate(pages[:3]):
                if page.main_content:
                    parts.append(f"\n[PÁGINA {i + 1}: {page.url}]\n{page.main_content[:2000]}")
                    page_urls[i] = page.url

        # Add product context for better FAQ grouping
        if products:
            product_info = "\n\n[PRODUCTOS/SERVICIOS DEL CREADOR - usar para contexto de FAQs]\n"
            for p in products:
                price_str = f" - {p.currency}{p.price}" if p.price else ""
                product_info += f"• {p.name}{price_str}\n"
            parts.append(product_info)

        # Add bio context
        if bio and bio.description:
            parts.append(f"\n[SOBRE EL CREADOR]\n{bio.description}")

        combined = "\n".join(parts)

        # Truncate if too long (increased limit for more complete extraction)
        if len(combined) > self.max_content_chars:
            combined = combined[: self.max_content_chars] + "\n...[contenido truncado]"

        logger.info(f"Prepared {len(parts)} content sections for FAQ extraction ({len(combined)} chars)")
        return combined, page_urls

    async def _extract_with_llm(self, content: str, page_urls: dict) -> List[ExtractedFAQ]:
        """Extract FAQs using LLM with LITERAL extraction."""
        llm = self._get_llm_client()
        prompt = FAQ_EXTRACTION_PROMPT.format(page_content=content)

        logger.info("Extracting FAQs LITERALLY using LLM...")

        # Call LLM with timeout
        response = await asyncio.wait_for(
            llm.generate(prompt, temperature=0.1, max_tokens=3000),  # Lower temp for more faithful extraction
            timeout=LLM_TIMEOUT,
        )

        # Parse response
        faq_data = self._parse_llm_response(response)

        if not faq_data or "faqs" not in faq_data:
            logger.warning("No FAQs found in LLM response")
            return []

        # Convert to ExtractedFAQ objects - preserve literal text
        faqs = []
        default_url = page_urls.get(0, "")

        for item in faq_data["faqs"]:
            if not item.get("question") or not item.get("answer"):
                continue

            # Determine source type
            source_type = item.get("source", "extracted_literal")
            if source_type not in ["extracted_literal", "extracted_summarized", "generated"]:
                source_type = "extracted_literal"

            # Preserve question exactly - only normalize whitespace
            question = " ".join(item["question"].split())

            # Preserve answer exactly - only normalize whitespace
            answer = " ".join(item["answer"].split())

            # Get context
            context = item.get("context", "General")
            if not context:
                context = "General"

            faq = ExtractedFAQ(
                question=question,
                answer=answer[:500] if len(answer) > 500 else answer,
                source_url=default_url,
                source_type=source_type,
                category=item.get("category", "other"),
                context=context,
                confidence=self._calculate_confidence(source_type),
            )
            faqs.append(faq)

        logger.info(f"Parsed {len(faqs)} FAQs from LLM response")
        return faqs

    def _calculate_confidence(self, source_type: str) -> float:
        """Calculate confidence based on source type."""
        confidence_map = {
            "extracted_literal": 0.95,
            "extracted_summarized": 0.85,
            "generated": 0.70,
        }
        return confidence_map.get(source_type, 0.75)

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

    def to_dict(self, faq: ExtractedFAQ) -> dict:
        """Convert FAQ to dictionary."""
        return {
            "question": faq.question,
            "answer": faq.answer,
            "source_url": faq.source_url,
            "source_type": faq.source_type,
            "category": faq.category,
            "context": faq.context,
            "confidence": faq.confidence,
        }
