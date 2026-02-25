"""
DM Agent helper/utility functions.

Pure functions for text processing, product matching,
voseo conversion, and response strategy determination.
"""

import re
import unicodedata

from services.intent_service import Intent

# =============================================================================
# PRODUCT NAME MATCHING (fuzzy, accent-insensitive)
# =============================================================================

_PRODUCT_STOPWORDS = frozenset({
    "para", "como", "hacia", "entre", "sobre", "desde", "hasta",
    "este", "esta", "estos", "estas", "todo", "toda", "todos",
    "cada", "otro", "otra", "otros", "dias", "donde", "bien",
    "mejor", "mucho", "poco", "mas", "menos", "muy", "que",
    "con", "del", "los", "las", "una", "uno",
})


def _strip_accents(text: str) -> str:
    """Remove accents/diacritics for fuzzy matching."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _message_mentions_product(product_name: str, msg_lower: str) -> bool:
    """Check if a message mentions a product using fuzzy matching.

    Handles long DB names like 'Fitpack Challenge de 11 días: Transforma...'
    by matching on the short-name segment or >=2 significant brand words.
    """
    pname = _strip_accents(product_name.lower().strip())
    msg = _strip_accents(msg_lower)

    if not pname or len(pname) <= 3:
        return False

    # 1. Exact substring (works for short names like "Círculo de Hombres")
    if pname in msg:
        return True

    # 2. First segment before ':' or '—' delimiter
    for sep in [":", "\u2014", " - "]:
        if sep in pname:
            short = pname.split(sep)[0].strip()
            if short and len(short) > 3 and short in msg:
                return True
            break

    # 3. Brand-word matching: >=2 significant words found in message
    words = [w for w in pname.split() if len(w) >= 4 and w not in _PRODUCT_STOPWORDS]
    if len(words) >= 2:
        matches = sum(1 for w in words if w in msg)
        if matches >= 2:
            return True

    return False


# =============================================================================
# TEXT TRUNCATION (sentence-aware)
# =============================================================================


def _truncate_at_boundary(text: str, max_chars: int) -> str:
    """Truncate text at a sentence or word boundary to avoid corrupting LLM input."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # Try to cut at last sentence boundary (don't lose more than 20%)
    last_period = truncated.rfind('. ')
    if last_period > max_chars * 0.8:
        return truncated[:last_period + 1]
    # Fallback: cut at last newline
    last_newline = truncated.rfind('\n')
    if last_newline > max_chars * 0.9:
        return truncated[:last_newline]
    # Fallback: cut at last word boundary
    last_space = truncated.rfind(' ')
    if last_space > max_chars * 0.9:
        return truncated[:last_space]
    return truncated


def _smart_truncate_context(system_prompt: str, max_chars: int) -> str:
    """Truncate context preserving recent conversation and key sections.

    Priority order (highest first):
    1. System instructions (persona, rules) — never truncated
    2. Recent conversation history (last messages)
    3. RAG context
    4. Older conversation history
    """
    if len(system_prompt) <= max_chars:
        return system_prompt

    # Find the conversation history section (usually marked by a header)
    history_markers = [
        "Historial de conversación",
        "Conversation history",
        "Últimos mensajes",
        "Recent messages",
        "<user_message>",
    ]

    history_start = -1
    for marker in history_markers:
        idx = system_prompt.find(marker)
        if idx > 0:
            history_start = idx
            break

    if history_start > 0:
        # Split into pre-history (instructions + RAG) and history
        pre_history = system_prompt[:history_start]
        history = system_prompt[history_start:]

        # Allocate: 60% for instructions+RAG, 40% for conversation history
        pre_budget = int(max_chars * 0.6)
        history_budget = max_chars - min(len(pre_history), pre_budget)

        # Truncate pre-history from the middle (keep start + end)
        if len(pre_history) > pre_budget:
            keep_start = int(pre_budget * 0.7)
            keep_end = pre_budget - keep_start
            pre_history = pre_history[:keep_start] + "\n...[context truncated]...\n" + pre_history[-keep_end:]

        # Truncate history from the START (keep recent messages at the end)
        if len(history) > history_budget:
            history = "...[older messages truncated]...\n" + history[-(history_budget - 40):]

        return pre_history + history

    # Fallback: simple truncation at sentence boundary
    return _truncate_at_boundary(system_prompt, max_chars)


# =============================================================================
# NON-CACHEABLE INTENTS
# =============================================================================

NON_CACHEABLE_INTENTS = {
    Intent.OBJECTION_PRICE,
    Intent.OBJECTION_TIME,
    Intent.OBJECTION_DOUBT,
    Intent.OBJECTION_LATER,
    Intent.OBJECTION_WORKS,
    Intent.OBJECTION_NOT_FOR_ME,
    Intent.INTEREST_STRONG,
    Intent.ESCALATION,
    Intent.SUPPORT,
    Intent.OTHER,
}


# =============================================================================
# VOSEO CONVERSION
# =============================================================================

def apply_voseo(text: str) -> str:
    """Convert Spanish tuteo to Argentine voseo.

    Transforms: tu->vos, tienes->tenes, puedes->podes, etc.
    """
    conversions = [
        # Pronouns
        (r"\btú\b", "vos"),
        (r"\bTú\b", "Vos"),
        # Common present tense verbs (2nd person singular)
        (r"\btienes\b", "tenés"),
        (r"\bTienes\b", "Tenés"),
        (r"\bpuedes\b", "podés"),
        (r"\bPuedes\b", "Podés"),
        (r"\bquieres\b", "querés"),
        (r"\bQuieres\b", "Querés"),
        (r"\bsabes\b", "sabés"),
        (r"\bSabes\b", "Sabés"),
        (r"\beres\b", "sos"),
        (r"\bEres\b", "Sos"),
        (r"\bvienes\b", "venís"),
        (r"\bpiensas\b", "pensás"),
        (r"\bsientes\b", "sentís"),
        (r"\bprefieres\b", "preferís"),
        (r"\bnecesitas\b", "necesitás"),
        (r"\bestás\b", "estás"),
        (r"\bvas\b", "vas"),
        # Imperatives
        (r"\bcuéntame\b", "contame"),
        (r"\bCuéntame\b", "Contame"),
        (r"\bescríbeme\b", "escribime"),
        (r"\bEscríbeme\b", "Escribime"),
        (r"\bdime\b", "decime"),
        (r"\bDime\b", "Decime"),
        (r"\bmira\b", "mirá"),
        (r"\bMira\b", "Mirá"),
        (r"\bpiensa\b", "pensá"),
        (r"\bPiensa\b", "Pensá"),
        (r"\bespera\b", "esperá"),
        (r"\bEspera\b", "Esperá"),
        (r"\bescucha\b", "escuchá"),
        (r"\bEscucha\b", "Escuchá"),
        (r"\bfíjate\b", "fijate"),
        (r"\bFíjate\b", "Fijate"),
        (r"\bpregunta\b", "preguntá"),
        # Common phrases (same in voseo)
        (r"\bte respondo\b", "te respondo"),
        (r"\bte cuento\b", "te cuento"),
        (r"\bte paso\b", "te paso"),
        (r"\bte gustaría\b", "te gustaría"),
    ]

    result = text
    for pattern, replacement in conversions:
        result = re.sub(pattern, replacement, result)

    return result


# =============================================================================
# RESPONSE STRATEGY
# =============================================================================

def _determine_response_strategy(
    message: str,
    intent_value: str,
    relationship_type: str,
    is_first_message: bool,
    is_friend: bool,
    follower_interests: list,
    lead_stage: str,
) -> str:
    """Determine response strategy to inject as LLM guidance."""
    msg_lower = message.lower().strip()

    # Priority 1: Family/close friends → personal mode, never sell
    if relationship_type in ("FAMILIA", "INTIMA"):
        return (
            "ESTRATEGIA: PERSONAL. Esta persona es cercana (familia/íntimo). "
            "Responde con cariño y naturalidad. Si pide ayuda, ayúdale. "
            "NUNCA vendas ni ofrezcas productos."
        )

    if is_friend:
        return (
            "ESTRATEGIA: PERSONAL. Esta persona es amigo/a. "
            "Responde relajado y natural. No vendas."
        )

    # Priority 2: Detect concrete help requests
    help_signals = [
        "ayuda", "problema", "no funciona", "no puedo", "error",
        "cómo", "como hago", "necesito", "urgente", "no me deja",
        "no entiendo", "explícame", "explicame", "qué hago", "que hago",
    ]
    if any(signal in msg_lower for signal in help_signals):
        return (
            "ESTRATEGIA: AYUDA. El usuario tiene una necesidad concreta. "
            "Responde DIRECTAMENTE a lo que necesita. NO saludes genéricamente. "
            "Si no sabes la respuesta exacta, pregunta detalles específicos."
        )

    # Priority 3: Product interest → sales mode
    if intent_value in ("purchase", "pricing", "product_info"):
        return (
            "ESTRATEGIA: VENTA. El usuario muestra interés en productos/servicios. "
            "Da la información concreta que pide (precio, contenido, duración). "
            "Añade un CTA suave al final."
        )

    # Priority 4: First message → greeting (but check for embedded needs)
    if is_first_message:
        if "?" in message or any(s in msg_lower for s in help_signals):
            return (
                "ESTRATEGIA: BIENVENIDA + AYUDA. Es el primer mensaje y contiene una pregunta. "
                "Saluda brevemente y responde a su necesidad en la misma respuesta."
            )
        return (
            "ESTRATEGIA: BIENVENIDA. Primer mensaje del usuario. "
            "Saluda brevemente y pregunta en qué puedes ayudar. "
            "NO hagas un saludo genérico largo."
        )

    # Priority 5: Ghost/reactivation
    if lead_stage in ("fantasma",):
        return (
            "ESTRATEGIA: REACTIVACIÓN. El usuario vuelve después de mucho tiempo. "
            "Muestra que te alegra verle. No seas agresivo con la venta."
        )

    # Default: natural conversation
    return ""


# =============================================================================
# HISTORY & AUDIO CONTEXT
# =============================================================================


def get_history_from_follower(follower) -> list:
    """Extract conversation history from follower memory."""
    history = []
    for msg in follower.last_messages[-20:]:
        if isinstance(msg, dict):
            history.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })
    return history


def build_audio_context(metadata: dict, cognitive_metadata: dict) -> str:
    """Build audio context if message comes from audio intelligence."""
    audio_intel = metadata.get("audio_intel")
    if not audio_intel or not isinstance(audio_intel, dict):
        return ""

    parts = []
    if audio_intel.get("intent"):
        parts.append(f"Intención del audio: {audio_intel['intent']}")
    entities = audio_intel.get("entities", {})
    entity_parts = []
    for key, label in [
        ("people", "Personas"), ("places", "Lugares"),
        ("dates", "Fechas"), ("numbers", "Cifras"),
        ("products", "Productos/servicios"),
    ]:
        vals = entities.get(key, [])
        if vals:
            entity_parts.append(f"{label}: {', '.join(vals)}")
    if entity_parts:
        parts.append("Datos mencionados: " + ". ".join(entity_parts))
    actions = audio_intel.get("action_items", [])
    if actions:
        parts.append("Acciones pendientes: " + "; ".join(actions))
    if audio_intel.get("emotional_tone"):
        parts.append(f"Tono: {audio_intel['emotional_tone']}")
    if parts:
        cognitive_metadata["audio_enriched"] = True
        return "CONTEXTO DE AUDIO (mensaje de voz transcrito):\n" + "\n".join(parts)
    return ""


# =============================================================================
# FACT TRACKING
# =============================================================================


def track_facts(follower, message: str, formatted_content: str, products: list) -> None:
    """Track conversation facts in the last message."""
    import logging
    _logger = logging.getLogger(__name__)
    try:
        facts = []
        if re.search(r"\d+\s*€|\d+\s*euros?|\$\d+", formatted_content, re.IGNORECASE):
            facts.append("PRICE_GIVEN")
        if "https://" in formatted_content or "http://" in formatted_content:
            facts.append("LINK_SHARED")
        if products:
            for prod in products:
                prod_name = prod.get("name", "").lower()
                if prod_name and len(prod_name) > 3 and prod_name in formatted_content.lower():
                    facts.append("PRODUCT_EXPLAINED")
                    break
        if re.search(r"entiendo tu (duda|preocupación)|es normal|no te preocupes|garantía|devolución", formatted_content, re.IGNORECASE):
            facts.append("OBJECTION_RAISED")
        if re.search(r"me interesa|quiero saber|cuéntame|suena bien|me gusta", message, re.IGNORECASE):
            facts.append("INTEREST_EXPRESSED")
        if re.search(r"reserva|agenda|cita|llamada|reunión|calendly|cal\.com", formatted_content, re.IGNORECASE):
            facts.append("APPOINTMENT_MENTIONED")
        if re.search(r"@\w{3,}|[\w.-]+@[\w.-]+\.\w+|\+?\d{9,}|wa\.me|whatsapp", formatted_content, re.IGNORECASE):
            facts.append("CONTACT_SHARED")
        if "?" in formatted_content:
            facts.append("QUESTION_ASKED")
        if follower.name and len(follower.name) > 2 and follower.name.lower() in formatted_content.lower():
            facts.append("NAME_USED")
        if facts:
            follower.last_messages[-1]["facts"] = facts
    except Exception as e:
        _logger.debug(f"Fact tracking failed: {e}")
