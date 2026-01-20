"""
Bio Extractor - Extrae información biográfica del creador desde su web.

Busca en páginas típicas: /about, /sobre-mi, /bio, página principal
Usa LLM para extraer información estructurada.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CreatorBio:
    """Información biográfica extraída del creador."""

    description: str = ""
    specialties: List[str] = field(default_factory=list)
    experience_years: Optional[int] = None
    target_audience: str = ""
    name: str = ""

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "specialties": self.specialties,
            "experience_years": self.experience_years,
            "target_audience": self.target_audience,
            "name": self.name,
        }

    def is_valid(self) -> bool:
        """Verifica que la bio tiene contenido útil."""
        return bool(self.description and len(self.description) > 50)


class BioExtractor:
    """
    Extrae información biográfica del creador desde páginas scrapeadas.

    Estrategia:
    1. Buscar páginas típicas de bio (/about, /sobre-mi, etc.)
    2. Extraer texto relevante
    3. Usar LLM para estructurar la información
    """

    # URLs típicas de páginas de bio
    BIO_URL_PATTERNS = [
        r"/about",
        r"/sobre-mi",
        r"/sobre-nosotros",
        r"/bio",
        r"/quien-soy",
        r"/mi-historia",
        r"/conoceme",
        r"/$",  # Página principal como fallback
    ]

    # Patrones para detectar años de experiencia
    EXPERIENCE_PATTERNS = [
        r"(\d+)\s*años?\s*de\s*experiencia",
        r"más\s*de\s*(\d+)\s*años",
        r"(\d+)\s*years?\s*of\s*experience",
        r"desde\s*(\d{4})",  # "desde 2018" -> calcular años
    ]

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

    def _find_bio_pages(self, pages: list) -> list:
        """Encuentra páginas que probablemente contengan bio."""
        bio_pages = []

        for page in pages:
            url_lower = page.url.lower()
            for pattern in self.BIO_URL_PATTERNS:
                if re.search(pattern, url_lower):
                    bio_pages.append(page)
                    break

        # Si no encontramos páginas específicas, usar las primeras páginas
        if not bio_pages and pages:
            bio_pages = pages[:3]

        return bio_pages

    def _extract_experience_years(self, text: str) -> Optional[int]:
        """Extrae años de experiencia del texto."""
        import datetime

        for pattern in self.EXPERIENCE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1)
                if len(value) == 4:  # Es un año (ej: 2018)
                    year = int(value)
                    current_year = datetime.datetime.now().year
                    return current_year - year
                else:
                    return int(value)
        return None

    def _extract_specialties_from_text(self, text: str) -> List[str]:
        """Extrae especialidades mencionadas en el texto."""
        # Palabras clave comunes de especialidades
        specialty_keywords = [
            "coach", "coaching", "mentor", "mentoring",
            "fitness", "bienestar", "wellness",
            "nutrición", "nutrition",
            "meditación", "meditation", "mindfulness",
            "yoga", "pilates",
            "business", "negocios", "emprendimiento",
            "marketing", "ventas", "sales",
            "desarrollo personal", "personal development",
            "liderazgo", "leadership",
            "productividad", "productivity",
            "finanzas", "finance",
            "programación", "programming", "coding",
            "diseño", "design",
            "fotografía", "photography",
            "escritura", "writing",
        ]

        text_lower = text.lower()
        found = []

        for keyword in specialty_keywords:
            if keyword in text_lower:
                # Capitalizar primera letra
                found.append(keyword.capitalize())

        return list(set(found))[:5]  # Máximo 5 especialidades

    async def extract(self, scraped_pages: list) -> CreatorBio:
        """
        Extrae información biográfica de las páginas scrapeadas.

        Args:
            scraped_pages: Lista de ScrapedPage del sitio web

        Returns:
            CreatorBio con la información extraída
        """
        bio = CreatorBio()

        if not scraped_pages:
            logger.warning("[BioExtractor] No pages to analyze")
            return bio

        # Encontrar páginas relevantes
        bio_pages = self._find_bio_pages(scraped_pages)
        logger.info(f"[BioExtractor] Found {len(bio_pages)} potential bio pages")

        # Combinar contenido de páginas de bio
        combined_content = "\n\n".join([
            f"=== {page.title} ===\n{page.main_content[:3000]}"
            for page in bio_pages[:3]
        ])

        # Extraer información básica sin LLM
        bio.experience_years = self._extract_experience_years(combined_content)
        bio.specialties = self._extract_specialties_from_text(combined_content)

        # Usar LLM para extraer información estructurada
        llm = self._get_llm_client()
        if llm:
            try:
                bio = await self._extract_with_llm(llm, combined_content, bio)
            except Exception as e:
                logger.warning(f"[BioExtractor] LLM extraction failed: {e}")
                # Fallback: usar primera página como descripción
                if bio_pages:
                    bio.description = bio_pages[0].main_content[:500]
        else:
            # Sin LLM, usar texto como descripción
            if bio_pages:
                bio.description = bio_pages[0].main_content[:500]

        logger.info(f"[BioExtractor] Extracted bio: {len(bio.description)} chars, {len(bio.specialties)} specialties")
        return bio

    async def _extract_with_llm(self, llm, content: str, existing_bio: CreatorBio) -> CreatorBio:
        """Usa LLM para extraer información estructurada."""

        prompt = f"""Analiza el siguiente contenido de una página web y extrae información sobre el creador/autor.

CONTENIDO:
{content[:4000]}

Responde SOLO en este formato JSON (sin explicaciones):
{{
    "name": "nombre del creador si se menciona",
    "description": "descripción breve del creador (2-3 oraciones, máximo 200 caracteres)",
    "specialties": ["especialidad1", "especialidad2", "especialidad3"],
    "target_audience": "descripción del público objetivo",
    "experience_years": número o null
}}

Si no encuentras información, deja el campo vacío o null."""

        try:
            response = await llm.generate(prompt)

            # Parsear JSON de la respuesta
            import json

            # Buscar JSON en la respuesta
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())

                return CreatorBio(
                    name=data.get("name", existing_bio.name) or "",
                    description=data.get("description", existing_bio.description) or "",
                    specialties=data.get("specialties", existing_bio.specialties) or [],
                    target_audience=data.get("target_audience", existing_bio.target_audience) or "",
                    experience_years=data.get("experience_years", existing_bio.experience_years),
                )
        except Exception as e:
            logger.error(f"[BioExtractor] LLM parsing error: {e}")

        return existing_bio
