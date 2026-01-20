"""
Tone Detector - Detecta el tono de comunicación y genera instrucciones para el bot.

Analiza el contenido para determinar:
- Estilo: amigo, mentor, vendedor, profesional
- Formalidad: tuteo vs usted
- Uso de emojis
- Instrucciones personalizadas
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ToneConfig:
    """Configuración de tono extraída."""

    tone: str  # "amigo", "mentor", "vendedor", "profesional"
    instructions: str  # Instrucciones para el bot
    emoji_usage: bool  # Si usa emojis
    formality: str  # "informal" (tuteo), "formal" (usted)
    vocabulary: list  # Palabras/frases características

    def to_dict(self) -> dict:
        return {
            "tone": self.tone,
            "instructions": self.instructions,
            "emoji_usage": self.emoji_usage,
            "formality": self.formality,
            "vocabulary": self.vocabulary,
        }


class ToneDetector:
    """
    Detecta el tono de comunicación del creador.

    Tonos disponibles:
    - amigo: Cercano, casual, usa emojis, tutea
    - mentor: Guía, empático, inspiracional, puede tutear
    - vendedor: Persuasivo, urgencia, beneficios, puede tutear
    - profesional: Formal, informativo, usa usted
    """

    TONES = {
        "amigo": {
            "keywords": ["amigo", "crack", "genial", "increíble", "brutal", "mola", "guay"],
            "patterns": [r"!", r"jaja", r"😊|😄|🎉|💪|❤️"],
        },
        "mentor": {
            "keywords": ["aprender", "crecer", "transformar", "consciencia", "proceso", "camino", "guía"],
            "patterns": [r"te\s+ayudo", r"juntos", r"acompañ"],
        },
        "vendedor": {
            "keywords": ["oferta", "descuento", "ahora", "último", "exclusivo", "limitado", "aprovecha"],
            "patterns": [r"solo\s+hoy", r"plazas\s+limitadas", r"no\s+te\s+lo\s+pierdas"],
        },
        "profesional": {
            "keywords": ["servicios", "empresa", "corporativo", "consultoría", "asesoramiento"],
            "patterns": [r"usted", r"le\s+ofrecemos", r"nuestra\s+empresa"],
        },
    }

    # Indicadores de formalidad
    INFORMAL_PATTERNS = [
        r"\btú\b", r"\bte\b", r"\btu\b", r"\btus\b",
        r"\btienes\b", r"\bquieres\b", r"\bpuedes\b",
        r"!", r"😊|😄|🎉|💪|❤️|✨|🔥",
    ]

    FORMAL_PATTERNS = [
        r"\busted\b", r"\ble\b", r"\bsu\b", r"\bsus\b",
        r"\btiene\b", r"\bdesea\b", r"\bpuede\b",
        r"estimado", r"atentamente",
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

    def _detect_emojis(self, text: str) -> bool:
        """Detecta si el texto usa emojis frecuentemente."""
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE,
        )
        matches = emoji_pattern.findall(text)
        # Si hay más de 3 emojis, consideramos que los usa
        return len(matches) >= 3

    def _detect_formality(self, text: str) -> str:
        """Detecta si el texto es formal o informal."""
        text_lower = text.lower()

        informal_score = 0
        formal_score = 0

        for pattern in self.INFORMAL_PATTERNS:
            matches = re.findall(pattern, text_lower)
            informal_score += len(matches)

        for pattern in self.FORMAL_PATTERNS:
            matches = re.findall(pattern, text_lower)
            formal_score += len(matches)

        if informal_score > formal_score * 2:
            return "informal"
        elif formal_score > informal_score:
            return "formal"
        else:
            return "informal"  # Default a informal

    def _detect_tone_from_patterns(self, text: str) -> tuple[str, int]:
        """Detecta el tono basado en patrones y palabras clave."""
        text_lower = text.lower()
        scores = {tone: 0 for tone in self.TONES}

        for tone, config in self.TONES.items():
            # Contar keywords
            for keyword in config["keywords"]:
                if keyword in text_lower:
                    scores[tone] += 2

            # Contar patterns
            for pattern in config["patterns"]:
                matches = re.findall(pattern, text_lower, re.IGNORECASE)
                scores[tone] += len(matches)

        # Encontrar el tono con mayor score
        max_tone = max(scores, key=scores.get)
        max_score = scores[max_tone]

        # Si el score es muy bajo, default a "mentor"
        if max_score < 3:
            return "mentor", max_score

        return max_tone, max_score

    def _extract_vocabulary(self, text: str, tone: str) -> list:
        """Extrae palabras/frases características del estilo."""
        text_lower = text.lower()
        vocabulary = []

        # Añadir keywords del tono detectado que aparecen en el texto
        if tone in self.TONES:
            for keyword in self.TONES[tone]["keywords"]:
                if keyword in text_lower:
                    vocabulary.append(keyword)

        # Buscar frases comunes
        common_phrases = [
            r"te\s+ayudo\s+a",
            r"juntos\s+\w+",
            r"mi\s+experiencia",
            r"lo\s+que\s+\w+\s+para\s+ti",
        ]

        for pattern in common_phrases:
            matches = re.findall(pattern, text_lower)
            vocabulary.extend(matches[:2])

        return list(set(vocabulary))[:10]

    def _generate_instructions(self, tone: str, formality: str, emoji_usage: bool, bio: Optional[object]) -> str:
        """Genera instrucciones para el bot basadas en el tono detectado."""

        base_instructions = {
            "amigo": (
                "Sé cercano y casual, como hablando con un amigo. "
                "Usa expresiones coloquiales y muestra entusiasmo genuino. "
                "Puedes usar humor ligero cuando sea apropiado."
            ),
            "mentor": (
                "Sé guía y empático. Muestra que entiendes el camino del cliente. "
                "Inspira confianza y ofrece apoyo. Usa un tono cálido pero sabio. "
                "Haz preguntas que inviten a la reflexión."
            ),
            "vendedor": (
                "Sé persuasivo pero no agresivo. Destaca beneficios claramente. "
                "Crea sentido de oportunidad sin presionar demasiado. "
                "Usa testimonios y casos de éxito cuando sea relevante."
            ),
            "profesional": (
                "Mantén un tono profesional y cortés. "
                "Sé claro y directo en las explicaciones. "
                "Ofrece información detallada y precisa."
            ),
        }

        instructions = base_instructions.get(tone, base_instructions["mentor"])

        # Añadir indicaciones de formalidad
        if formality == "informal":
            instructions += " Usa tuteo (tú, te, tu)."
        else:
            instructions += " Usa usted de manera respetuosa."

        # Añadir indicaciones de emojis
        if emoji_usage:
            instructions += " Puedes usar emojis ocasionalmente para dar calidez."
        else:
            instructions += " Evita usar emojis, mantén el texto limpio."

        # Añadir contexto del bio si existe
        if bio and hasattr(bio, 'specialties') and bio.specialties:
            specialties_str = ", ".join(bio.specialties[:3])
            instructions += f" El creador se especializa en: {specialties_str}."

        return instructions

    async def detect(self, scraped_pages: list, bio: Optional[object] = None) -> ToneConfig:
        """
        Detecta el tono de comunicación de las páginas scrapeadas.

        Args:
            scraped_pages: Lista de ScrapedPage del sitio web
            bio: CreatorBio extraído (opcional, para contexto)

        Returns:
            ToneConfig con el tono detectado
        """
        if not scraped_pages:
            logger.warning("[ToneDetector] No pages to analyze")
            return ToneConfig(
                tone="mentor",
                instructions="Sé amable y servicial con los clientes.",
                emoji_usage=False,
                formality="informal",
                vocabulary=[],
            )

        # Combinar contenido de las páginas
        combined_content = "\n".join([
            page.main_content[:2000] for page in scraped_pages[:5]
        ])

        # Detectar características básicas
        emoji_usage = self._detect_emojis(combined_content)
        formality = self._detect_formality(combined_content)
        tone, score = self._detect_tone_from_patterns(combined_content)
        vocabulary = self._extract_vocabulary(combined_content, tone)

        logger.info(f"[ToneDetector] Detected tone: {tone} (score: {score}), formality: {formality}")

        # Intentar refinar con LLM
        llm = self._get_llm_client()
        if llm and score < 5:  # Si el score es bajo, usar LLM para confirmar
            try:
                llm_result = await self._detect_with_llm(llm, combined_content)
                if llm_result:
                    tone = llm_result.get("tone", tone)
                    if llm_result.get("vocabulary"):
                        vocabulary = llm_result["vocabulary"]
            except Exception as e:
                logger.warning(f"[ToneDetector] LLM detection failed: {e}")

        # Generar instrucciones
        instructions = self._generate_instructions(tone, formality, emoji_usage, bio)

        return ToneConfig(
            tone=tone,
            instructions=instructions,
            emoji_usage=emoji_usage,
            formality=formality,
            vocabulary=vocabulary,
        )

    async def _detect_with_llm(self, llm, content: str) -> Optional[dict]:
        """Usa LLM para detectar el tono."""

        prompt = f"""Analiza el tono de comunicación de este contenido web:

{content[:3000]}

Determina:
1. Tono principal: "amigo" (casual, cercano), "mentor" (guía, inspiracional), "vendedor" (persuasivo, beneficios), o "profesional" (formal, corporativo)
2. Palabras/frases características del estilo

Responde SOLO en JSON:
{{"tone": "mentor", "vocabulary": ["palabra1", "frase característica"]}}"""

        try:
            import json

            response = await llm.generate(prompt)
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"[ToneDetector] LLM parsing error: {e}")

        return None
