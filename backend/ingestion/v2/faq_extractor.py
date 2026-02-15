"""
FAQ Extractor - HYBRID extraction (Regex + LLM)

FILOSOFÍA CLONNECT: El sistema debe ser FIEL al contenido del creador.

APPROACH:
1. REGEX: Extrae FAQs literalmente (patrones ¿...?)
2. FILTROS REGEX: Excluye ruido obvio (blog URLs, CTAs, retóricas)
3. FILTRO LLM: Clasifica REAL vs SKIP para eliminar ruido de blog
4. LLM CATEGORIZACIÓN: Categoriza las FAQs reales, NO reformula
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from core.metrics import record_faqs_extracted, observe_extract_duration, record_ingestion_error

if TYPE_CHECKING:
    from ..deterministic_scraper import ScrapedPage
    from .bio_extractor import ExtractedBio
    from .product_detector import DetectedProduct

logger = logging.getLogger(__name__)

# Timeout for LLM calls
LLM_TIMEOUT = 60

# =============================================================================
# NOISE FILTERS - Exclude blog posts, CTAs, and rhetorical questions
# =============================================================================

# URLs to EXCLUDE (blog posts, articles - not product/service pages)
EXCLUDE_URL_PATTERNS = [
    r"/blog/",
    r"/post/",
    r"/posts/",
    r"/articulo/",
    r"/articulos/",
    r"/article/",
    r"/articles/",
    r"/noticias/",
    r"/news/",
]

# Question patterns to EXCLUDE (CTAs and rhetorical)
EXCLUDE_QUESTION_PATTERNS = [
    # CTAs - calls to action disguised as questions
    r"^¿te gustaría\b",
    r"^¿listo para\b",
    r"^¿quieres\b",
    r"^¿te animas\b",
    r"^¿preparado para\b",
    r"^¿estás listo\b",
    r"^¿te atreves\b",
    # Rhetorical / About section
    r"^¿quién soy\b",
    r"^¿quiénes somos\b",
    r"^¿por qué\?$",  # Just "¿Por qué?" alone
    r"^¿y tú\b",
    r"^¿qué tal\b",
    r"^¿sabías que\b",
    # Blog-style reflective questions
    r"^¿y si\b",  # "¿Y si tu dolor fuera un mensaje?"
    r"^¿alguna vez\b",  # "¿Alguna vez te sentiste..."
    r"^¿cuántas veces\b",
    r"^¿qué pasaría si\b",
    r"^¿qué pasa cuando\b",
    r"^¿cómo sería\b",
    r"^¿te has preguntado\b",
]


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

# LLM prompt for CLASSIFICATION (REAL vs SKIP)
FAQ_CLASSIFICATION_PROMPT = """Analiza estas preguntas extraídas de un sitio web de un creador/coach.

Tu tarea es clasificar CADA pregunta como "REAL" o "SKIP".

CLASIFICAR COMO "REAL" (FAQs de producto/servicio):
- Preguntas sobre precio, costo, inversión
- Preguntas sobre qué incluye un programa/servicio
- Preguntas sobre cómo funciona, metodología, duración
- Preguntas sobre requisitos, para quién es
- Preguntas sobre horarios, acceso, formato
- Preguntas sobre cómo empezar, primer paso, inscripción
- Preguntas sobre por qué participar/unirse (beneficios)
- Preguntas sobre qué pasa si no puedo, cancelaciones, políticas
- Dudas frecuentes de clientes potenciales

EJEMPLOS DE "REAL" (NO son CTAs ni retóricas):
- "¿Cómo puedo dar mi primer paso?" → REAL (getting started)
- "¿Por qué participar en este taller?" → REAL (beneficios)
- "¿Qué sucede si no puedo completar?" → REAL (política)
- "¿Para quién está dirigido?" → REAL (elegibilidad)
- "¿Qué equipo necesito?" → REAL (requisitos)

CLASIFICAR COMO "SKIP" (NO son FAQs reales):
- Preguntas retóricas de blog SIN respuesta concreta ("¿Y si tu dolor fuera un mensaje?")
- Títulos de artículos en forma de pregunta ("¿Cómo la IA está transformando el mundo?")
- Preguntas filosóficas abstractas ("¿Qué es la consciencia?")
- Preguntas sobre temas generales NO relacionados con el servicio

REGLA CLAVE: Si la pregunta tiene una respuesta práctica sobre el producto/servicio → REAL.
ANTE LA DUDA: Clasificar como REAL (mejor incluir de más que perder FAQs importantes).

PREGUNTAS A CLASIFICAR:
{questions_list}

Responde SOLO con JSON válido:
{{"results": [{{"id": 1, "class": "REAL"}}, {{"id": 2, "class": "SKIP"}}, ...]}}

IMPORTANTE: Solo incluye el JSON, sin explicaciones."""


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
        creator_id: str = "unknown",
    ) -> FAQExtractionResult:
        """
        Extract FAQs using hybrid approach (Regex + LLM).

        Pipeline:
        1. Regex extraction → all questions with ¿...? pattern
        2. Regex filters → exclude obvious noise (blog URLs, CTAs)
        3. LLM classification → REAL vs SKIP to filter blog questions
        4. LLM categorization → add category and context
        """
        start_time = time.time()
        result = FAQExtractionResult()

        # PASO 1: Extracción LITERAL con regex + filtros básicos
        raw_faqs = self._extract_faqs_with_regex(pages)

        if not raw_faqs:
            logger.info("No FAQs found with regex extraction")
            return result

        logger.info(f"Regex extracted {len(raw_faqs)} literal FAQs (after basic filters)")

        # PASO 2: Clasificación con LLM (REAL vs SKIP)
        try:
            classified_faqs = await self._classify_faqs_with_llm(raw_faqs)
            logger.info(
                f"LLM classification: {len(classified_faqs)} REAL FAQs "
                f"(filtered {len(raw_faqs) - len(classified_faqs)} noise)"
            )
        except Exception as e:
            logger.warning(f"LLM classification failed, using all FAQs: {e}")
            classified_faqs = raw_faqs

        if not classified_faqs:
            logger.info("No FAQs passed LLM classification")
            return result

        # PASO 3: Categorización con LLM (sin reformular)
        try:
            categorized_faqs = await self._categorize_with_llm(classified_faqs, products)
            result.faqs = categorized_faqs[: self.max_faqs]
            result.source_urls = list(set(faq.source_url for faq in result.faqs))

            # Log stats
            logger.info(
                f"Final: {len(result.faqs)} FAQs categorized "
                f"(categories: {set(f.category for f in result.faqs)})"
            )
        except Exception as e:
            logger.error(f"Error categorizing FAQs: {e}")
            record_ingestion_error("faq_categorization_error")
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
                for faq in classified_faqs
            ]
            result.source_urls = list(set(faq.source_url for faq in result.faqs))

        # Record metrics
        duration = time.time() - start_time
        observe_extract_duration("faqs", duration)
        record_faqs_extracted(creator_id, len(result.faqs))

        return result

    def _extract_faqs_with_regex(self, pages: List["ScrapedPage"]) -> List[dict]:
        """
        PASO 1: Extract FAQs literally using regex.
        PASO 1.5: Filter out noise (blog posts, CTAs, rhetorical questions).

        Finds patterns like:
        - ¿Pregunta aquí?
        - Followed by answer text until next question or section
        """
        all_faqs = []

        for page in pages:
            content = page.main_content
            if not content:
                continue

            # FILTRO 1: Excluir páginas de blog/artículos
            url_lower = page.url.lower()
            is_blog_page = any(re.search(pattern, url_lower) for pattern in EXCLUDE_URL_PATTERNS)
            if is_blog_page:
                logger.debug(f"Skipping blog/article page: {page.url}")
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

                # FILTRO 2: Excluir CTAs y preguntas retóricas
                should_skip = any(
                    re.match(pattern, q["question"], re.I) for pattern in EXCLUDE_QUESTION_PATTERNS
                )
                if should_skip:
                    logger.debug(f"Skipping CTA/rhetorical: {q['question'][:50]}...")
                    continue

                # Get answer: text from end of question to start of next question (or +1000 chars)
                answer_start = q["end"]
                if i + 1 < len(questions_with_pos):
                    answer_end = questions_with_pos[i + 1]["start"]
                else:
                    answer_end = min(answer_start + 2000, len(content))

                answer = content[answer_start:answer_end].strip()

                # Clean answer
                answer = self._clean_answer(answer)

                # Skip if answer is too short or empty
                if len(answer) < 20:
                    continue

                all_faqs.append(
                    {
                        "question": q["question"],
                        "answer": answer[:1000] if len(answer) > 1000 else answer,
                        "source_url": page.url,
                        "was_truncated": len(answer) > 1000,
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

    async def _classify_faqs_with_llm(self, raw_faqs: List[dict]) -> List[dict]:
        """
        PASO 2: Use LLM to classify FAQs as REAL (product/service) or SKIP (blog/noise).

        Processes in batches of 30 to handle large numbers of FAQs.
        Returns only FAQs classified as REAL.
        """
        if not raw_faqs:
            return []

        llm = self._get_llm_client()
        real_faqs = []
        batch_size = 30

        # Process in batches
        for batch_start in range(0, len(raw_faqs), batch_size):
            batch = raw_faqs[batch_start : batch_start + batch_size]

            # Format questions for prompt
            questions_list = "\n".join(f"{i + 1}. {faq['question']}" for i, faq in enumerate(batch))

            prompt = FAQ_CLASSIFICATION_PROMPT.format(questions_list=questions_list)

            try:
                response = await asyncio.wait_for(
                    llm.generate(prompt, temperature=0.1, max_tokens=1000),
                    timeout=LLM_TIMEOUT,
                )

                # Parse response
                classification = self._parse_llm_response(response)

                if classification and "results" in classification:
                    for item in classification["results"]:
                        faq_id = item.get("id", 0) - 1  # Convert to 0-indexed
                        faq_class = item.get("class", "SKIP").upper()

                        if 0 <= faq_id < len(batch) and faq_class == "REAL":
                            real_faqs.append(batch[faq_id])
                else:
                    # If parsing fails, include all from this batch as fallback
                    logger.warning(
                        f"Could not parse LLM classification for batch {batch_start}, "
                        "including all as fallback"
                    )
                    real_faqs.extend(batch)

            except asyncio.TimeoutError:
                logger.warning(
                    f"LLM classification timeout for batch {batch_start}, "
                    "including all as fallback"
                )
                real_faqs.extend(batch)
            except Exception as e:
                logger.warning(
                    f"LLM classification error for batch {batch_start}: {e}, "
                    "including all as fallback"
                )
                real_faqs.extend(batch)

        return real_faqs

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

        # Stop patterns - cut text at common section markers
        # PROTECCIÓN: solo cortar si match.start() > 10 (evita bug de string vacío)
        # UNIVERSAL PATTERNS - funcionan para cualquier web
        stop_patterns = [
            # ═══ SECCIONES COMUNES ═══
            r"MÁS PREGUNTAS",
            r"PREGUNTAS FRECUENTES",
            r"SOBRE EL AUTOR",
            r"SOBRE NOSOTROS",
            r"CONOCE A TU",
            r"INSTRUCTOR:",
            r"TENGO OTRA PREGUNTA",
            r"NUESTRO EQUIPO",
            r"CONT[AÁ]CTANOS",
            # ═══ TESTIMONIOS / SOCIAL PROOF ═══
            r"\d+\s*(personas|usuarios|clientes|alumnos)\s+(que\s+)?(ya\s+)?(han|ya)\b",
            r"(personas|usuarios|clientes|alumnos)\s+que\s+(han|ya|aceptaron|probaron|completaron|eligieron|confiaron)",
            r"\b(testimonios?|opiniones|reseñas|reviews)\b",
            r"casos?\s+de\s+[eé]xito",
            r"lo\s+que\s+dicen",
            r"★{3,}",
            # ═══ CTAs GENÉRICOS ═══
            r"(inscr[íi]bete|reg[íi]strate|reserva\s+tu|únete)\s*(ahora|ya|hoy)?",
            r"(empieza|comienza|inicia)\s+(ahora|ya|hoy|tu)",
            r"(solicita|pide|agenda)\s+(tu|una)\s+(demo|prueba|cita|llamada|sesión)",
            # ═══ NAVEGACIÓN ═══
            r"(siguiente|anterior)\s*(pregunta|sección)",
            r"(mostrar|ocultar)\s*(más|menos)",
            r"\(\s*ejemplo\s*\)",
            # ═══ FECHAS / TIMESTAMPS ═══
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            r"\b\w{3}\s+\d{1,2},\s+\d{4}\b",
            r"(publicado|actualizado)\s*(el|en)?",
            # ═══ PROMOCIONAL / INTRO ═══
            r"(oferta|descuento|promoción)\s+(especial|limitada)",
            r"(solo|últimas)\s+\d+\s+(plazas|lugares|cupos)",
            r"por\s+(solo|sólo)\s+[€$£]\d+",
            r"(este|esta)\s+(taller|curso|programa|retiro)\s+es\s+una?\s+(experiencia|oportunidad)",
        ]
        for pattern in stop_patterns:
            match = re.search(pattern, answer, re.IGNORECASE)
            if match and match.start() > 10:
                answer = answer[: match.start()].strip()

        # Clean numeric noise at start/end (post-extraction cleanup)
        answer = re.sub(r"^\s*\d+\.\s*", "", answer)  # "4. texto" → "texto"
        answer = re.sub(r"\s+\d+\.\s*$", "", answer)  # "texto 2." → "texto"

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
                except json.JSONDecodeError as e:
                    logger.debug("Ignored json.JSONDecodeError in return json.loads(json_match.group()): %s", e)
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
