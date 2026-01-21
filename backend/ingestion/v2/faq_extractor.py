"""
FAQ Extractor - HYBRID extraction (Regex + LLM)

FILOSOFÍA CLONNECT: El sistema debe ser FIEL al contenido del creador.

APPROACH:
1. REGEX: Extrae FAQs literalmente (patrones ¿...?)
2. LLM: Solo categoriza las FAQs ya extraídas, NO reformula
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
LLM_TIMEOUT = 60


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


# LLM prompt for CATEGORIZATION ONLY (not extraction)
FAQ_CATEGORIZATION_PROMPT = """Categoriza las siguientes FAQs que ya fueron extraídas de una web.

IMPORTANTE: NO cambies las preguntas ni respuestas. Solo añade categoría y contexto.

FAQs A CATEGORIZAR:
{faqs_json}

---

PRODUCTOS/SERVICIOS DEL CREADOR (para identificar contexto):
{products_info}

---

Para cada FAQ, determina:
1. category: pricing|process|benefits|eligibility|getting_started|other
2. context: nombre del producto/servicio al que pertenece (o "General" si aplica a todo)

CATEGORÍAS:
- pricing: precios, costos, pagos, descuentos
- process: cómo funciona, pasos, metodología, duración
- benefits: resultados, beneficios, qué obtengo
- eligibility: para quién es, requisitos
- getting_started: cómo empezar, primeros pasos
- other: otras preguntas

Responde SOLO con JSON:

{{
    "categorized_faqs": [
        {{
            "question": "COPIA EXACTA de la pregunta original",
            "answer": "COPIA EXACTA de la respuesta original",
            "category": "pricing|process|benefits|etc",
            "context": "Nombre del producto o General"
        }}
    ]
}}

REGLA CRÍTICA: Las preguntas y respuestas deben ser IDÉNTICAS a las originales."""


class FAQExtractor:
    """
    Extracts FAQs using HYBRID approach:
    1. Regex for literal extraction
    2. LLM for categorization only
    """

    def __init__(self, max_faqs: int = 100, max_content_chars: int = 12000):
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
        Extract FAQs using hybrid approach (Regex + LLM).
        """
        result = FAQExtractionResult()

        # PASO 1: Extracción LITERAL con regex
        raw_faqs = self._extract_faqs_with_regex(pages)

        if not raw_faqs:
            logger.info("No FAQs found with regex extraction")
            return result

        logger.info(f"Regex extracted {len(raw_faqs)} literal FAQs")

        # PASO 2: Categorización con LLM (sin reformular)
        try:
            categorized_faqs = await self._categorize_with_llm(raw_faqs, products)
            result.faqs = categorized_faqs[: self.max_faqs]
            result.source_urls = list(set(faq.source_url for faq in result.faqs))

            # Log stats
            logger.info(
                f"Final: {len(result.faqs)} FAQs categorized "
                f"(categories: {set(f.category for f in result.faqs)})"
            )
        except Exception as e:
            logger.error(f"Error categorizing FAQs: {e}")
            # Fallback: return uncategorized FAQs
            result.faqs = [
                ExtractedFAQ(
                    question=faq["question"],
                    answer=faq["answer"],
                    source_url=faq["source_url"],
                    source_type="extracted_literal",
                    category="other",
                    context="General",
                    confidence=0.9,
                )
                for faq in raw_faqs
            ]
            result.source_urls = list(set(faq.source_url for faq in result.faqs))

        return result

    def _extract_faqs_with_regex(self, pages: List["ScrapedPage"]) -> List[dict]:
        """
        PASO 1: Extract FAQs literally using regex.

        Finds patterns like:
        - ¿Pregunta aquí?
        - Followed by answer text until next question or section
        """
        all_faqs = []

        for page in pages:
            content = page.main_content
            if not content:
                continue

            # Find all questions (¿...?)
            # Pattern: ¿ followed by text until ?
            question_pattern = r"¿([^?]+)\?"

            # Find all question positions
            questions_with_pos = []
            for match in re.finditer(question_pattern, content):
                question = f"¿{match.group(1)}?"
                start_pos = match.start()
                end_pos = match.end()
                questions_with_pos.append(
                    {"question": question, "start": start_pos, "end": end_pos}
                )

            # Extract answer for each question (text until next question or limit)
            for i, q in enumerate(questions_with_pos):
                # Skip very short questions (likely not real FAQs)
                if len(q["question"]) < 10:
                    continue

                # Skip common non-FAQ questions
                skip_patterns = [
                    r"^¿(te|quién|cómo|qué tal|y tú|sabías)",  # Greetings/rhetorical
                    r"^¿[^?]{0,15}\?$",  # Too short
                ]
                should_skip = False
                for pattern in skip_patterns:
                    if re.match(pattern, q["question"], re.I):
                        should_skip = True
                        break
                if should_skip:
                    continue

                # Get answer: text from end of question to start of next question (or +1000 chars)
                answer_start = q["end"]
                if i + 1 < len(questions_with_pos):
                    answer_end = questions_with_pos[i + 1]["start"]
                else:
                    answer_end = min(answer_start + 1000, len(content))

                answer = content[answer_start:answer_end].strip()

                # Clean answer
                answer = self._clean_answer(answer)

                # Skip if answer is too short or empty
                if len(answer) < 20:
                    continue

                all_faqs.append(
                    {
                        "question": q["question"],
                        "answer": answer[:500] if len(answer) > 500 else answer,
                        "source_url": page.url,
                        "was_truncated": len(answer) > 500,
                    }
                )

        # Deduplicate by question
        seen_questions = set()
        unique_faqs = []
        for faq in all_faqs:
            q_normalized = faq["question"].lower().strip()
            if q_normalized not in seen_questions:
                seen_questions.add(q_normalized)
                unique_faqs.append(faq)

        return unique_faqs

    def _clean_answer(self, answer: str) -> str:
        """Clean extracted answer text."""
        # Normalize whitespace
        answer = re.sub(r"\s+", " ", answer)

        # Remove common noise at start
        answer = re.sub(r"^[\s\-:]+", "", answer)

        # Remove common CTAs at end
        cta_patterns = [
            r"\s*(Leer más|Ver más|Más información|Click aquí|Haz click).*$",
            r"\s*(QUIERO|RESERVAR|COMPRAR|APÚNTATE).*$",
        ]
        for pattern in cta_patterns:
            answer = re.sub(pattern, "", answer, flags=re.I)

        return answer.strip()

    async def _categorize_with_llm(
        self, raw_faqs: List[dict], products: Optional[List["DetectedProduct"]]
    ) -> List[ExtractedFAQ]:
        """
        PASO 2: Use LLM to categorize pre-extracted FAQs.
        Does NOT modify questions or answers.
        """
        llm = self._get_llm_client()

        # Prepare FAQs for LLM
        faqs_for_llm = [{"question": f["question"], "answer": f["answer"]} for f in raw_faqs]

        # Prepare products info
        products_info = "No hay productos específicos identificados."
        if products:
            products_info = "\n".join(
                f"• {p.name}" + (f" ({p.currency}{p.price})" if p.price else "") for p in products
            )

        prompt = FAQ_CATEGORIZATION_PROMPT.format(
            faqs_json=json.dumps(faqs_for_llm, ensure_ascii=False, indent=2),
            products_info=products_info,
        )

        logger.info(f"Categorizing {len(raw_faqs)} FAQs with LLM...")

        # Call LLM
        response = await asyncio.wait_for(
            llm.generate(prompt, temperature=0.1, max_tokens=3000),
            timeout=LLM_TIMEOUT,
        )

        # Parse response
        categorized_data = self._parse_llm_response(response)

        if not categorized_data or "categorized_faqs" not in categorized_data:
            logger.warning("LLM categorization failed, using defaults")
            # Return with default categories
            return [
                ExtractedFAQ(
                    question=faq["question"],
                    answer=faq["answer"],
                    source_url=faq["source_url"],
                    source_type=(
                        "extracted_literal"
                        if not faq.get("was_truncated")
                        else "extracted_summarized"
                    ),
                    category="other",
                    context="General",
                    confidence=0.9,
                )
                for faq in raw_faqs
            ]

        # Build FAQ objects with categorization
        # Create lookup for original FAQ data
        original_lookup = {f["question"].lower().strip(): f for f in raw_faqs}

        categorized_faqs = []
        for item in categorized_data["categorized_faqs"]:
            question = item.get("question", "")

            # Find original FAQ data
            q_key = question.lower().strip()
            original = original_lookup.get(q_key)

            if not original:
                # LLM might have slightly modified - try fuzzy match
                for orig_q, orig_data in original_lookup.items():
                    if orig_q in q_key or q_key in orig_q:
                        original = orig_data
                        break

            if original:
                # Use ORIGINAL question/answer, only take category/context from LLM
                faq = ExtractedFAQ(
                    question=original["question"],  # LITERAL from regex
                    answer=original["answer"],  # LITERAL from regex
                    source_url=original["source_url"],
                    source_type=(
                        "extracted_literal"
                        if not original.get("was_truncated")
                        else "extracted_summarized"
                    ),
                    category=item.get("category", "other"),
                    context=item.get("context", "General"),
                    confidence=0.95,
                )
                categorized_faqs.append(faq)
            else:
                logger.warning(f"Could not match LLM FAQ to original: {question[:50]}...")

        return categorized_faqs

    def _parse_llm_response(self, response: str) -> Optional[dict]:
        """Parse JSON from LLM response."""
        try:
            response = response.strip()
            if response.startswith("```"):
                response = re.sub(r"^```json?\n?", "", response)
                response = re.sub(r"\n?```$", "", response)

            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
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
