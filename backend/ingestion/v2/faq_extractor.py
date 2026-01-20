"""
FAQ Extractor - Extrae o genera FAQs desde el contenido de la web.

Estrategia:
1. Buscar FAQs existentes en la web
2. Si no hay suficientes, generar con LLM basado en contenido y productos
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FAQ:
    """Pregunta frecuente extraída o generada."""

    question: str
    answer: str
    category: str  # "producto", "servicio", "general", "pago", "proceso"

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "category": self.category,
        }

    def is_valid(self) -> bool:
        """Verifica que la FAQ tiene contenido útil."""
        return (
            bool(self.question)
            and bool(self.answer)
            and len(self.question) > 10
            and len(self.answer) > 20
        )


class FAQExtractor:
    """
    Extrae FAQs existentes o genera nuevas basadas en el contenido.

    Estrategia:
    1. Buscar páginas de FAQ (/faq, /preguntas-frecuentes)
    2. Detectar patrones de pregunta-respuesta
    3. Si no hay suficientes, generar con LLM
    """

    # URLs típicas de páginas de FAQ
    FAQ_URL_PATTERNS = [
        r"/faq",
        r"/faqs",
        r"/preguntas-frecuentes",
        r"/preguntas",
        r"/dudas",
        r"/ayuda",
        r"/help",
        r"/q-?a",
    ]

    # Patrones para detectar preguntas
    QUESTION_PATTERNS = [
        r"¿[^?]+\?",  # Preguntas en español
        r"\?[^?]+\?",  # Preguntas con ? al inicio y final
        r"(?:cómo|qué|cuándo|dónde|por qué|cuál|quién)[^.?]+\?",  # Preguntas interrogativas
    ]

    # Categorías de FAQ
    CATEGORIES = {
        "producto": ["producto", "incluye", "contenido", "acceso", "material"],
        "servicio": ["sesión", "consulta", "acompañamiento", "coaching", "mentoría"],
        "pago": ["pago", "precio", "costo", "tarjeta", "transferencia", "paypal", "factura"],
        "proceso": ["cómo funciona", "proceso", "pasos", "empezar", "inscribir"],
        "general": [],  # Default
    }

    MIN_FAQS = 5

    def __init__(self):
        self.llm_client = None

    def _get_llm_client(self):
        """Obtiene cliente LLM lazy."""
        if self.llm_client is None:
            try:
                from core.llm import get_llm_client
                self.llm_client = get_llm_client()
            except Exception as e:
                logger.warning(f"Could not get LLM client: {e}")
        return self.llm_client

    def _find_faq_pages(self, pages: list) -> list:
        """Encuentra páginas que probablemente contengan FAQs."""
        faq_pages = []

        for page in pages:
            url_lower = page.url.lower()
            content_lower = page.main_content.lower()

            # Buscar por URL
            for pattern in self.FAQ_URL_PATTERNS:
                if re.search(pattern, url_lower):
                    faq_pages.append(page)
                    break

            # Buscar por contenido (títulos de FAQ)
            if "preguntas frecuentes" in content_lower or "faq" in content_lower:
                if page not in faq_pages:
                    faq_pages.append(page)

        return faq_pages

    def _categorize_faq(self, question: str, answer: str) -> str:
        """Determina la categoría de una FAQ."""
        combined = (question + " " + answer).lower()

        for category, keywords in self.CATEGORIES.items():
            if category == "general":
                continue
            for keyword in keywords:
                if keyword in combined:
                    return category

        return "general"

    def _extract_faqs_from_text(self, text: str) -> List[FAQ]:
        """Extrae FAQs de texto usando patrones."""
        faqs = []

        # Buscar patrones de Q&A
        # Patrón: Pregunta seguida de respuesta
        lines = text.split("\n")
        current_question = None

        for i, line in enumerate(lines):
            line = line.strip()

            # Detectar pregunta
            if "?" in line and len(line) > 15:
                # Limpiar la pregunta
                question = re.sub(r"^[•\-\d.)\s]+", "", line).strip()
                if question.startswith("¿") or "?" in question:
                    current_question = question

            # Si hay pregunta pendiente, buscar respuesta
            elif current_question and len(line) > 30:
                answer = line
                faq = FAQ(
                    question=current_question,
                    answer=answer[:500],
                    category=self._categorize_faq(current_question, answer),
                )
                if faq.is_valid():
                    faqs.append(faq)
                current_question = None

        return faqs

    async def extract(
        self,
        scraped_pages: list,
        products: Optional[list] = None,
        bio: Optional[object] = None,
    ) -> List[FAQ]:
        """
        Extrae o genera FAQs desde el contenido.

        Args:
            scraped_pages: Lista de ScrapedPage del sitio web
            products: Lista de productos detectados (opcional)
            bio: CreatorBio extraído (opcional)

        Returns:
            Lista de FAQs (mínimo 5)
        """
        faqs = []

        if not scraped_pages:
            logger.warning("[FAQExtractor] No pages to analyze")
            return faqs

        # 1. Buscar FAQs existentes en páginas de FAQ
        faq_pages = self._find_faq_pages(scraped_pages)
        logger.info(f"[FAQExtractor] Found {len(faq_pages)} FAQ pages")

        for page in faq_pages:
            extracted = self._extract_faqs_from_text(page.main_content)
            faqs.extend(extracted)

        logger.info(f"[FAQExtractor] Extracted {len(faqs)} FAQs from pages")

        # 2. Si no hay suficientes, generar con LLM
        if len(faqs) < self.MIN_FAQS:
            llm = self._get_llm_client()
            if llm:
                try:
                    generated = await self._generate_faqs_with_llm(
                        llm, scraped_pages, products, bio, existing_count=len(faqs)
                    )
                    faqs.extend(generated)
                except Exception as e:
                    logger.warning(f"[FAQExtractor] LLM generation failed: {e}")

        # Eliminar duplicados
        seen = set()
        unique_faqs = []
        for faq in faqs:
            key = faq.question.lower()[:50]
            if key not in seen:
                seen.add(key)
                unique_faqs.append(faq)

        logger.info(f"[FAQExtractor] Final FAQ count: {len(unique_faqs)}")
        return unique_faqs[:10]  # Máximo 10 FAQs

    async def _generate_faqs_with_llm(
        self,
        llm,
        pages: list,
        products: Optional[list],
        bio: Optional[object],
        existing_count: int,
    ) -> List[FAQ]:
        """Genera FAQs usando LLM basado en el contenido."""

        # Preparar contexto
        content_summary = "\n".join([
            f"- {page.title}: {page.main_content[:500]}..."
            for page in pages[:5]
        ])

        products_info = ""
        if products:
            products_info = "\nPRODUCTOS/SERVICIOS:\n" + "\n".join([
                f"- {p.get('name', 'Producto')}: {p.get('price', 'N/A')}€ - {p.get('description', '')[:100]}"
                for p in products[:5]
            ])

        bio_info = ""
        if bio and hasattr(bio, 'description'):
            bio_info = f"\nSOBRE EL CREADOR:\n{bio.description}"

        needed = max(self.MIN_FAQS - existing_count, 3)

        prompt = f"""Genera {needed} preguntas frecuentes (FAQs) para un negocio basándote en esta información:

CONTENIDO DEL SITIO WEB:
{content_summary}
{products_info}
{bio_info}

Genera FAQs útiles que un cliente potencial preguntaría.
Incluye FAQs sobre: productos/servicios, precios, proceso de compra, y dudas generales.

Responde SOLO en este formato JSON (array de objetos):
[
    {{"question": "¿Pregunta 1?", "answer": "Respuesta detallada...", "category": "producto"}},
    {{"question": "¿Pregunta 2?", "answer": "Respuesta detallada...", "category": "pago"}}
]

Categorías válidas: producto, servicio, pago, proceso, general"""

        try:
            response = await llm.generate(prompt)

            # Parsear JSON
            import json

            # Buscar array JSON en la respuesta
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                data = json.loads(json_match.group())

                faqs = []
                for item in data:
                    if isinstance(item, dict):
                        faq = FAQ(
                            question=item.get("question", ""),
                            answer=item.get("answer", ""),
                            category=item.get("category", "general"),
                        )
                        if faq.is_valid():
                            faqs.append(faq)

                return faqs

        except Exception as e:
            logger.error(f"[FAQExtractor] LLM parsing error: {e}")

        return []
