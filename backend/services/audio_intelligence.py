"""Audio Intelligence Pipeline — 4-Layer Processing.

Whisper → Clean → Extract → Synthesize

Replaces the simple 1-layer audio_transcription_processor with a structured
pipeline that extracts entities, intent, action items, and generates
zero-data-loss summaries.

Feature flag: ENABLE_AUDIO_INTELLIGENCE (default OFF).
When OFF, returns raw Whisper text without LLM processing.
"""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

ENABLE_AUDIO_INTELLIGENCE = (
    os.getenv("ENABLE_AUDIO_INTELLIGENCE", "false").lower() == "true"
)
MIN_WORDS_FOR_PROCESSING = 30
LAYER_TIMEOUT_SECONDS = 12  # per-layer LLM timeout


# ═══════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════


@dataclass
class AudioEntities:
    """Structured entities extracted from audio."""

    people: List[str] = field(default_factory=list)
    places: List[str] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    numbers: List[str] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    products: List[str] = field(default_factory=list)


@dataclass
class AudioIntelligence:
    """Complete processed output for an audio message."""

    # Layer 1: Raw transcription
    raw_text: str = ""

    # Layer 2: Cleaned text
    clean_text: str = ""

    # Layer 3: Structured extraction
    intent: str = ""
    entities: AudioEntities = field(default_factory=AudioEntities)
    action_items: List[str] = field(default_factory=list)
    emotional_tone: str = ""
    topics: List[str] = field(default_factory=list)

    # Layer 4: Smart summary
    summary: str = ""

    # Metadata
    duration_seconds: int = 0
    language: str = "es"
    source: str = "whisper"
    processed_at: str = ""
    processing_time_ms: int = 0

    def to_metadata(self) -> dict:
        """Format for msg_metadata.audio_intel field."""
        return {
            "raw_text": self.raw_text,
            "clean_text": self.clean_text,
            "summary": self.summary,
            "intent": self.intent,
            "entities": asdict(self.entities),
            "action_items": self.action_items,
            "emotional_tone": self.emotional_tone,
            "topics": self.topics,
            "duration_seconds": self.duration_seconds,
            "language": self.language,
            "source": self.source,
            "processed_at": self.processed_at,
            "processing_time_ms": self.processing_time_ms,
        }

    def to_legacy_fields(self) -> dict:
        """Return old-format fields for backward compatibility."""
        return {
            "transcript_raw": self.raw_text,
            "transcript_full": self.clean_text or self.raw_text,
            "transcript_summary": self.summary or self.raw_text,
            "transcription": self.summary or self.raw_text,
        }


# ═══════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════

CLEAN_PROMPT = """Tu tarea es ESTRUCTURAR esta transcripción de audio para que sea legible.

REGLAS ESTRICTAS:
1. MANTÉN todas las palabras y expresiones del hablante — es SU voz
2. NO reescribas frases — solo añade puntuación y párrafos
3. NO elimines expresiones coloquiales ("bueno", "vale", "o sea", "pues")
4. NO hagas el texto más formal — mantén el registro exacto
5. AÑADE: puntos, comas, signos de interrogación donde correspondan
6. AÑADE: saltos de párrafo cada 2-4 oraciones o cuando cambie de tema
7. CORRIGE: mayúsculas después de punto, nombres propios (WhatsApp, Clonet, Instagram)
8. ELIMINA SOLO: repeticiones LITERALES inmediatas (cuando dice exactamente lo mismo dos veces seguidas)
9. ELIMINA SOLO: muletillas vacías sin contenido ("eh", "um", "este este este", "mmm")
10. El resultado debe tener entre 85-95% de las palabras del original

El resultado debe sonar EXACTAMENTE como la persona, solo que con puntuación y estructura.

Transcripción cruda:
\"\"\"
{raw_text}
\"\"\"

Transcripción estructurada:"""

EXTRACT_PROMPT = """Analiza esta transcripción de un mensaje de audio en una conversación por DM.

Extrae SOLO lo que está explícitamente presente. NO inventes ni infieras.

Responde en JSON exacto (sin markdown, sin backticks):
{{
  "intent": "qué quiere comunicar el hablante, en 1 frase corta",
  "people": ["nombres de personas mencionadas"],
  "places": ["lugares mencionados"],
  "dates": ["fechas, plazos o referencias temporales mencionadas"],
  "numbers": ["cifras, cantidades, precios mencionados"],
  "events": ["eventos o actividades mencionadas"],
  "products": ["productos, servicios o marcas mencionadas"],
  "action_items": ["propuestas, peticiones, acuerdos, cosas pendientes"],
  "emotional_tone": "una o dos palabras describiendo el tono",
  "topics": ["2-5 tags temáticos cortos"]
}}

Si un campo no tiene datos, usa lista vacía [] o string vacío "".

Transcripción:
\"\"\"
{clean_text}
\"\"\"

JSON:"""

SUMMARY_PROMPT = """Sintetiza este audio en 1-3 frases que capturen TODA la información clave.
El resultado debe ser tan útil que el lector NO necesite escuchar el audio.

DATOS EXTRAÍDOS (úsalos TODOS en tu síntesis):
- Intención: {intent}
- Personas: {people}
- Lugares: {places}
- Fechas: {dates}
- Cifras: {numbers}
- Eventos: {events}
- Acciones pendientes: {action_items}
- Tono: {emotional_tone}

REGLAS:
1. Cada nombre propio, fecha, lugar y cifra DEBE aparecer en la síntesis
2. Si hay propuesta o acuerdo → incluirlo obligatoriamente
3. Máximo 3 frases. Si el audio es simple, usa 1 frase
4. Escribe en el MISMO idioma que el audio
5. Es un mensaje {role_desc} — escribe en {person_perspective}
6. NO uses bullet points ni etiquetas — solo texto fluido natural
7. NO empieces con "El hablante" ni "El usuario" — ve directo al contenido

TRANSCRIPCIÓN:
\"\"\"
{clean_text}
\"\"\"

Síntesis (1-3 frases):"""


# ═══════════════════════════════════════════════════════
# SERVICE
# ═══════════════════════════════════════════════════════


class AudioIntelligenceService:
    """4-layer audio processing pipeline."""

    async def process(
        self,
        raw_text: str = "",
        duration_seconds: int = 0,
        language: str = "es",
        role: str = "user",
    ) -> AudioIntelligence:
        """Process raw transcription through the 4-layer pipeline.

        Args:
            raw_text: Whisper transcription output
            duration_seconds: Audio duration
            language: Language code
            role: "user" (follower) or "assistant" (creator)

        Returns:
            AudioIntelligence with all layers populated.
            On failure/disabled, raw_text fills all text fields.
        """
        start = time.time()

        result = AudioIntelligence(
            raw_text=raw_text,
            duration_seconds=duration_seconds,
            language=language,
            source="whisper",
        )

        if not raw_text or not raw_text.strip():
            return result

        raw_text = raw_text.strip()
        result.raw_text = raw_text
        word_count = len(raw_text.split())

        # Skip LLM processing if disabled or text too short
        if not ENABLE_AUDIO_INTELLIGENCE or word_count < MIN_WORDS_FOR_PROCESSING:
            result.clean_text = raw_text
            result.summary = raw_text
            return result

        # ── Layer 2: Clean ──
        result.clean_text = await self._clean(raw_text)

        # ── Layer 3: Extract ──
        extraction = await self._extract(result.clean_text)
        result.intent = extraction.get("intent", "")
        result.entities = AudioEntities(
            people=extraction.get("people", []),
            places=extraction.get("places", []),
            dates=extraction.get("dates", []),
            numbers=extraction.get("numbers", []),
            events=extraction.get("events", []),
            products=extraction.get("products", []),
        )
        result.action_items = extraction.get("action_items", [])
        result.emotional_tone = extraction.get("emotional_tone", "")
        result.topics = extraction.get("topics", [])

        # ── Layer 4: Synthesize ──
        result.summary = await self._synthesize(result, role)

        result.processed_at = datetime.now(timezone.utc).isoformat()
        result.processing_time_ms = int((time.time() - start) * 1000)

        logger.info(
            "[AudioIntel] %ds audio in %dms. "
            "Raw:%d→Clean:%d→Summary:%d chars. "
            "Entities: %dppl %dplaces %dactions",
            duration_seconds,
            result.processing_time_ms,
            len(result.raw_text),
            len(result.clean_text),
            len(result.summary),
            len(result.entities.people),
            len(result.entities.places),
            len(result.action_items),
        )

        return result

    # ───────────────────────────────────────────────────
    # Layer implementations
    # ───────────────────────────────────────────────────

    async def _clean(self, raw_text: str) -> str:
        """Layer 2: Remove fillers, structure text."""
        if len(raw_text) < 100:
            return raw_text

        prompt = CLEAN_PROMPT.format(raw_text=raw_text)
        result = await self._call_llm(
            prompt=prompt,
            system="Estructurador de transcripciones. Añades puntuación y párrafos. NUNCA reescribes ni eliminas expresiones del hablante.",
            temperature=0.1,
            max_tokens=len(raw_text.split()) * 6,
        )
        return result or raw_text

    async def _extract(self, clean_text: str) -> dict:
        """Layer 3: Structured entity extraction."""
        prompt = EXTRACT_PROMPT.format(clean_text=clean_text)
        response = await self._call_llm(
            prompt=prompt,
            system="Extractor de datos. Responde SOLO en JSON válido.",
            temperature=0.1,
            max_tokens=600,
        )

        if not response:
            return self._empty_extraction()

        return self._parse_json(response)

    async def _synthesize(self, result: AudioIntelligence, role: str) -> str:
        """Layer 4: Smart summary using extracted entities."""
        entities = result.entities

        if role == "assistant":
            role_desc = "del creator (saliente)"
            person_perspective = "primera persona"
        else:
            role_desc = "de otra persona (entrante)"
            person_perspective = "tercera persona (ej: 'Comenta que...', 'Propone...')"

        prompt = SUMMARY_PROMPT.format(
            intent=result.intent or "no detectada",
            people=", ".join(entities.people) if entities.people else "ninguna",
            places=", ".join(entities.places) if entities.places else "ninguno",
            dates=", ".join(entities.dates) if entities.dates else "ninguna",
            numbers=", ".join(entities.numbers) if entities.numbers else "ninguna",
            events=", ".join(entities.events) if entities.events else "ninguno",
            action_items=(
                ", ".join(result.action_items)
                if result.action_items
                else "ninguna"
            ),
            emotional_tone=result.emotional_tone or "neutro",
            clean_text=result.clean_text[:2000],
            role_desc=role_desc,
            person_perspective=person_perspective,
        )

        summary = await self._call_llm(
            prompt=prompt,
            system="Sintetizador experto. Máxima info en mínimas palabras.",
            temperature=0.3,
            max_tokens=200,
        )

        # Validate: summary must be shorter than clean_text
        if summary and len(summary) < len(result.clean_text):
            return summary
        # If LLM returned something too long, truncate to first 3 sentences
        if summary:
            sentences = re.split(r'(?<=[.!?])\s+', summary)
            return " ".join(sentences[:3])
        return result.clean_text[:300]

    # ───────────────────────────────────────────────────
    # Helpers
    # ───────────────────────────────────────────────────

    async def _call_llm(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> Optional[str]:
        """Call LLM via existing generate_simple (Gemini → GPT-4o-mini)."""
        try:
            from core.providers.gemini_provider import generate_simple

            result = await asyncio.wait_for(
                generate_simple(
                    prompt=prompt,
                    system_prompt=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ),
                timeout=LAYER_TIMEOUT_SECONDS,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("[AudioIntel] LLM timeout after %ds", LAYER_TIMEOUT_SECONDS)
            return None
        except Exception as e:
            logger.error("[AudioIntel] LLM call failed: %s", e)
            return None

    def _parse_json(self, response: str) -> dict:
        """Parse JSON response, stripping markdown fences."""
        text = response.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning("[AudioIntel] JSON parse failed: %s — %s", e, text[:100])

        return self._empty_extraction()

    def _empty_extraction(self) -> dict:
        return {
            "intent": "",
            "people": [],
            "places": [],
            "dates": [],
            "numbers": [],
            "events": [],
            "products": [],
            "action_items": [],
            "emotional_tone": "",
            "topics": [],
        }


# ═══════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════

_service: Optional[AudioIntelligenceService] = None


def get_audio_intelligence() -> AudioIntelligenceService:
    global _service
    if _service is None:
        _service = AudioIntelligenceService()
    return _service
