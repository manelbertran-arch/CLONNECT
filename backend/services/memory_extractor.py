"""
Memory Extractor — ARC2 A2.2 unified extractor.

Replaces 3 legacy systems at Phase 5:
  - services/memory_extraction.py (LLM-based, 6 old types, CC-faithful guards)
  - services/memory_engine.py (delegates extraction to memory_extraction.py)
  - models/conversation_memory.py (bot-centric FactTypes, Spanish-only regex)

Design: Hybrid Opción C (ARC2 §2.5):
  extract_from_message  → regex + heuristics only, NO LLM, <200ms budget
                          covers: identity + intent_signal (per-turn actionable)
  extract_deep          → LLM call with XML prompt, for nightly job
                          covers: all 5 types (objection/relationship_state
                          need multi-turn context)

Zero imports from the 3 legacy systems.
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any, Callable, Coroutine, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# TYPES + CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

MemoryType = Literal[
    "identity", "interest", "objection", "intent_signal", "relationship_state"
]

MEMORY_TYPES: tuple[str, ...] = (
    "identity",
    "interest",
    "objection",
    "intent_signal",
    "relationship_state",
)

CONFIDENCE_THRESHOLD: float = 0.7


# ─────────────────────────────────────────────────────────────────────────────
# PYDANTIC MODEL
# ─────────────────────────────────────────────────────────────────────────────

class ExtractedMemory(BaseModel):
    """Typed memory output from MemoryExtractor.

    Mirrors arc2_lead_memories schema (ARC2 §2.2):
      fact = content, why = why, how_to_apply = how_to_apply.
    """

    model_config = ConfigDict(frozen=True)

    type: MemoryType
    fact: str = Field(max_length=100)
    why: str
    how_to_apply: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in MEMORY_TYPES:
            raise ValueError(f"type must be one of {MEMORY_TYPES}, got {v!r}")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# REGEX PATTERNS — identity signals (multilingual: ES / CA / EN)
# ─────────────────────────────────────────────────────────────────────────────

_AGE_PATTERN = re.compile(
    r"(?:"
    r"tengo\s+(\d{1,2})\s*a[ñn]os?"
    r"|tinc\s+(\d{1,2})\s*anys?"
    r"|i['`]?m\s+(\d{1,2})\s*(?:years?\s*old)?"
    r"|(\d{1,2})\s*a[ñn]os?\s+de\s+edad"
    r"|(\d{1,2})\s*anys?\s+d'edat"
    r")",
    re.IGNORECASE,
)

_NAME_PATTERN = re.compile(
    r"(?:"
    r"me\s+llamo\s+([A-ZÁÉÍÓÚÑÇ][a-záéíóúñç]+(?:\s+[A-ZÁÉÍÓÚÑÇ][a-záéíóúñç]+)?)"
    r"|mi\s+nombre\s+es\s+([A-ZÁÉÍÓÚÑÇ][a-záéíóúñç]+)"
    r"|em\s+dic\s+([A-ZÁÉÍÓÚÀÈÍÏÒÓÚÜÇ][a-záéíóúàèíïòóúüç]+)"
    r"|my\s+name\s+is\s+([A-Z][a-z]+)"
    r"|i['`]?m\s+([A-Z][a-z]+)\s*(?:[,.]|$)"
    r")",
    re.IGNORECASE,
)

_LOCATION_PATTERN = re.compile(
    r"(?:"
    r"vivo\s+en\s+([A-ZÁÉÍÓÚÑÇ][a-záéíóúñç]+(?:\s+[A-ZÁÉÍÓÚÑÇ][a-záéíóúñç]+)?)"
    r"|soy\s+de\s+([A-ZÁÉÍÓÚÑÇ][a-záéíóúñç]+)"
    r"|estoy\s+en\s+([A-ZÁÉÍÓÚÑÇ][a-záéíóúñç]+)"
    r"|visc\s+a\s+([A-ZÁÉÍÓÚÀÈÍÏÒÓÚÜÇ][a-záéíóúàèíïòóúüç]+)"
    r"|soc\s+de\s+([A-ZÁÉÍÓÚÀÈÍÏÒÓÚÜÇ][a-záéíóúàèíïòóúüç]+)"
    r"|i\s+live\s+in\s+([A-Z][a-z]+)"
    r"|i['`]?m\s+from\s+([A-Z][a-z]+)"
    r")",
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# REGEX PATTERNS — intent_signal (purchase + abandon, multilingual)
# ─────────────────────────────────────────────────────────────────────────────

_INTENT_STRONG_PATTERN = re.compile(
    r"(?:"
    r"quiero\s+(?:empezar|comprar|contratar|apuntarme|unirme|participar)"
    r"|me\s+apunto\b"
    r"|c[oó]mo\s+(?:pago|contrato|me\s+apunto|me\s+registro)"
    r"|[¿?]cu[aá]nto\s+cuesta"
    r"|vull\s+(?:apuntar-me|comprar|contractar)"
    r"|i\s+want\s+to\s+(?:buy|start|sign\s+up|join|get\s+it)"
    r"|how\s+(?:do\s+i\s+)?(?:buy|pay|sign\s+up|get\s+started)"
    r"|let['`]?s\s+do\s+it"
    r")",
    re.IGNORECASE,
)

_INTENT_MEDIUM_PATTERN = re.compile(
    r"(?:"
    r"me\s+(?:lo|la)\s+(?:pienso|pensaré|estoy\s+pensando)"
    r"|me\s+interesa(?:r[íi]a)?\b"
    r"|[¿?]c[oó]mo\s+funciona"
    r"|cu[eé]ntame\s+m[aá]s"
    r"|qu[eé]\s+incluye"
    r"|m'interessa\b"
    r"|i['`]?m\s+interested\b"
    r"|tell\s+me\s+more\b"
    r"|how\s+does\s+(?:it\s+)?work\b"
    r"|quiero\s+(?:m[aá]s\s+)?informaci[oó]n"
    r")",
    re.IGNORECASE,
)

_INTENT_ABANDON_PATTERN = re.compile(
    r"(?:"
    r"(?:es\s+)?(?:muy\s+)?caro\b"
    r"|no\s+(?:tengo|me\s+lo\s+puedo)\s+(?:permitir|pagar|costear)"
    r"|d[eé]jame\s+pensarlo"
    r"|lo\s+dejo\s+para\s+(?:otro\s+)?(?:d[ií]a|momento)"
    r"|no\s+es\s+(?:para\s+m[íi]|el\s+momento)"
    r"|massa\s+car\b"
    r"|too\s+expensive\b"
    r"|can['`]?t\s+afford\b"
    r"|need\s+to\s+think\s+about\s+it\b"
    r")",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# LLM PROMPT TEMPLATE
# ─────────────────────────────────────────────────────────────────────────────

EXTRACTOR_PROMPT_TEMPLATE = """\
You are extracting durable memories about a LEAD from a DM conversation with a creator.

Today's date: __TODAY__
Output language for fact/why/how_to_apply: __LANGUAGE__

## Closed memory types (use EXACTLY one of these)
- identity: Durable personal data (name, age, location, profession, family situation)
- interest: Product/topic the lead explicitly or implicitly shows interest in
- objection: Expressed resistance, price complaints, or explicit doubts
- intent_signal: Purchase or abandon signal ("I want to buy", "too expensive", "thinking about it")
- relationship_state: Lead status transition (new lead → warm → customer → cold/ghost → reactivation)

## What NOT to extract
- Bot messages or bot actions — only extract facts about the LEAD
- Generic greetings or filler with no factual content
- Facts already known (listed below)
- Speculation or inference without textual evidence

## Already known facts (do NOT re-extract)
__ALREADY_KNOWN__

## Conversation
__CONVERSATION__

## Output format — respond ONLY with this XML, no prose
<extracted_memories>
  <memory>
    <type>identity</type>
    <fact>Lead is 32 years old</fact>
    <why>Said "tengo 32 años" in turn 2</why>
    <how_to_apply>Use age-appropriate tone and examples when relevant</how_to_apply>
    <confidence>0.95</confidence>
  </memory>
</extracted_memories>

If nothing worth extracting: <extracted_memories></extracted_memories>

Rules:
- type: exactly one of identity / interest / objection / intent_signal / relationship_state
- fact: max 100 chars, in output language
- why: cite or paraphrase the exact evidence from conversation
- how_to_apply: actionable instruction for the clone to use this knowledge
- confidence: 0.0-1.0 (omit memory entirely if < 0.7)
- Convert relative dates to absolute using today's date\
"""


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

class MemoryExtractor:
    """
    Hybrid ARC2 extractor (§2.5 Opción C).

    extract_from_message  → regex, no LLM, <200ms per-turn sync
    extract_deep          → LLM XML output, nightly job only
    """

    def __init__(
        self,
        llm_caller: Optional[Callable[[str], Coroutine[Any, Any, str]]] = None,
    ) -> None:
        self._llm_caller = llm_caller

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: sync per-turn (no LLM, <200ms)
    # ─────────────────────────────────────────────────────────────────────

    async def extract_from_message(
        self,
        message: str,
        lead_id: UUID,
        language: str = "es",
    ) -> List[ExtractedMemory]:
        """Regex-only sync extractor — covers identity + intent_signal.

        No LLM call, stays within 200ms webhook budget.
        Returns only memories with confidence >= CONFIDENCE_THRESHOLD.
        """
        if not message or not self._classify_signal(message):
            return []

        memories: List[ExtractedMemory] = []
        memories.extend(self._extract_identity(message))
        memories.extend(self._extract_intent_signal(message))

        return [m for m in memories if m.confidence >= CONFIDENCE_THRESHOLD]

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: deep LLM (nightly job only)
    # ─────────────────────────────────────────────────────────────────────

    async def extract_deep(
        self,
        conversation: List[dict],
        lead_id: UUID,
        language: str = "es",
        already_known: Optional[List[ExtractedMemory]] = None,
    ) -> List[ExtractedMemory]:
        """LLM deep extractor — all 5 types, nightly job.

        Fails silent on LLM error (returns []).
        """
        if self._llm_caller is None:
            logger.warning("[MemoryExtractor] extract_deep called without llm_caller — skipping")
            return []

        if not conversation:
            return []

        already_known = already_known or []

        try:
            formatted = self._format_conversation(conversation)
            if not formatted:
                return []

            already_known_section = self._format_already_known(already_known) or "(none yet)"
            today = date.today().isoformat()

            prompt = (
                EXTRACTOR_PROMPT_TEMPLATE
                .replace("__TODAY__", today)
                .replace("__LANGUAGE__", language)
                .replace("__ALREADY_KNOWN__", already_known_section)
                .replace("__CONVERSATION__", formatted)
            )

            response = await self._llm_caller(prompt)
            if not response:
                return []

            memories = self._parse_xml_response(response)
            return [m for m in memories if m.confidence >= CONFIDENCE_THRESHOLD]

        except Exception as e:
            logger.warning("[MemoryExtractor] extract_deep failed silently: %s", e)
            return []

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE: quick pre-filter
    # ─────────────────────────────────────────────────────────────────────

    def _classify_signal(
        self,
        message: str,
        lead_context: Optional[dict] = None,
    ) -> bool:
        """Returns True if message likely has any extractable signal.

        Acts as a fast gate before the full regex pass.
        lead_context reserved for future use (e.g. skip already-known signals).
        """
        return bool(
            _AGE_PATTERN.search(message)
            or _NAME_PATTERN.search(message)
            or _LOCATION_PATTERN.search(message)
            or _INTENT_STRONG_PATTERN.search(message)
            or _INTENT_MEDIUM_PATTERN.search(message)
            or _INTENT_ABANDON_PATTERN.search(message)
        )

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE: identity extraction
    # ─────────────────────────────────────────────────────────────────────

    def _extract_identity(self, message: str) -> List[ExtractedMemory]:
        memories: List[ExtractedMemory] = []
        snippet = message[:80]

        m = _AGE_PATTERN.search(message)
        if m:
            age = next((g for g in m.groups() if g is not None), None)
            if age:
                memories.append(ExtractedMemory(
                    type="identity",
                    fact=f"Lead is {age} years old",
                    why=f"Said in message: '{snippet}'",
                    how_to_apply="Calibrate tone and examples to lead's age",
                    confidence=0.9,
                ))

        m = _NAME_PATTERN.search(message)
        if m:
            name = next((g for g in m.groups() if g is not None), None)
            if name:
                memories.append(ExtractedMemory(
                    type="identity",
                    fact=f"Lead's name is {name}",
                    why="Introduced themselves in message",
                    how_to_apply="Address lead by name for personalization",
                    confidence=0.95,
                ))

        m = _LOCATION_PATTERN.search(message)
        if m:
            location = next((g for g in m.groups() if g is not None), None)
            if location:
                memories.append(ExtractedMemory(
                    type="identity",
                    fact=f"Lead is from/in {location}",
                    why=f"Mentioned location in message",
                    how_to_apply="Use location context when discussing logistics or local events",
                    confidence=0.85,
                ))

        return memories

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE: intent_signal extraction
    # ─────────────────────────────────────────────────────────────────────

    def _extract_intent_signal(self, message: str) -> List[ExtractedMemory]:
        memories: List[ExtractedMemory] = []
        snippet = message[:80]

        if _INTENT_STRONG_PATTERN.search(message):
            memories.append(ExtractedMemory(
                type="intent_signal",
                fact="Lead shows strong purchase intent",
                why=f"Message: '{snippet}'",
                how_to_apply="Escalate to checkout or booking template immediately",
                confidence=0.9,
            ))
        elif _INTENT_ABANDON_PATTERN.search(message):
            # Abandon/price signal — also classify as intent_signal with lower confidence
            memories.append(ExtractedMemory(
                type="intent_signal",
                fact="Lead shows price or availability objection signal",
                why=f"Message: '{snippet}'",
                how_to_apply="Address value proposition before mentioning price again",
                confidence=0.8,
            ))
        elif _INTENT_MEDIUM_PATTERN.search(message):
            memories.append(ExtractedMemory(
                type="intent_signal",
                fact="Lead shows medium purchase interest",
                why=f"Message: '{snippet}'",
                how_to_apply="Send nurturing template with product details and social proof",
                confidence=0.75,
            ))

        return memories

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE: XML parser for deep LLM output
    # ─────────────────────────────────────────────────────────────────────

    def _parse_xml_response(self, response: str) -> List[ExtractedMemory]:
        """Parse LLM XML response into ExtractedMemory objects.

        Handles:
        - Missing XML block → []
        - Malformed XML → [] (logged as warning)
        - Unknown memory types → skipped (logged as debug)
        - Missing required fields → skipped
        """
        start = response.find("<extracted_memories>")
        end = response.find("</extracted_memories>")
        if start == -1 or end == -1:
            logger.warning("[MemoryExtractor] No <extracted_memories> block in LLM response")
            return []

        xml_block = response[start : end + len("</extracted_memories>")]

        try:
            root = ET.fromstring(xml_block)
        except ET.ParseError as exc:
            logger.warning("[MemoryExtractor] XML parse error: %s", exc)
            return []

        memories: List[ExtractedMemory] = []
        for mem_el in root.findall("memory"):
            try:
                mem_type = (mem_el.findtext("type") or "").strip()
                fact = (mem_el.findtext("fact") or "").strip()[:100]
                why = (mem_el.findtext("why") or "").strip()
                how_to_apply = (mem_el.findtext("how_to_apply") or "").strip()
                confidence_str = (mem_el.findtext("confidence") or "0.7").strip()

                if mem_type not in MEMORY_TYPES:
                    logger.debug("[MemoryExtractor] Skipping unknown type: %r", mem_type)
                    continue
                if not fact:
                    logger.debug("[MemoryExtractor] Skipping memory with empty fact")
                    continue

                try:
                    confidence = float(confidence_str)
                except ValueError:
                    confidence = 0.7

                confidence = max(0.0, min(1.0, confidence))

                memories.append(ExtractedMemory(
                    type=mem_type,  # type: ignore[arg-type]
                    fact=fact,
                    why=why or "Extracted from conversation",
                    how_to_apply=how_to_apply or "Use as context for personalization",
                    confidence=confidence,
                ))
            except Exception as exc:
                logger.debug("[MemoryExtractor] Skipping malformed memory element: %s", exc)
                continue

        return memories

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE: formatting helpers
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _format_conversation(conversation: List[dict]) -> str:
        lines: List[str] = []
        for i, msg in enumerate(conversation[-20:], 1):
            role = msg.get("role", "user")
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            label = "Lead" if role == "user" else "Bot"
            lines.append(f"Turn {i} [{label}]: {content}")
        return "\n".join(lines)

    @staticmethod
    def _format_already_known(already_known: List[ExtractedMemory]) -> str:
        if not already_known:
            return ""
        return "\n".join(
            f"- [{m.type}] {m.fact}"
            for m in already_known[:10]
        )


# ─────────────────────────────────────────────────────────────────────────────
# SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

_extractor: Optional[MemoryExtractor] = None


def get_memory_extractor(
    llm_caller: Optional[Callable[[str], Coroutine[Any, Any, str]]] = None,
) -> MemoryExtractor:
    """Return the global MemoryExtractor singleton.

    If llm_caller is provided and differs from the current instance,
    creates a new extractor (supports test fixtures with fresh callers).
    """
    global _extractor
    if _extractor is None or (
        llm_caller is not None and _extractor._llm_caller is not llm_caller
    ):
        _extractor = MemoryExtractor(llm_caller=llm_caller)
    return _extractor
