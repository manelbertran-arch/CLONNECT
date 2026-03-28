"""
Text utility functions for DM Agent V2.

- Accent stripping for fuzzy matching
- Product name matching (fuzzy, accent-insensitive)
- Sentence-aware text truncation
- Smart context truncation preserving recent conversation
- Argentine voseo conversion
- Adaptive max_tokens based on message category
"""

import re
import unicodedata
from typing import Optional

from services.intent_service import Intent


# =============================================================================
# ADAPTIVE MAX TOKENS — calibrated from real creator response patterns
# =============================================================================

# Regex classifiers mirror the SQL categories used in mining
_GREETING_RE = re.compile(r"^(hola|hey|hi|bon dia|buenas|ey|ei|holi|holaa?)$", re.IGNORECASE)
_BOOKING_PRICE_RE = re.compile(
    r"(precio|cost[ao]?s?\b|cuesta|tarifa|preu|quant costa|cuanto vale|cuanto cuesta|reserv|book|cita\b|horari|dispo)",
    re.IGNORECASE,
)
_CANCEL_RE = re.compile(
    r"(cancel|anul|devoluc|reembols|no puedo|no puc)", re.IGNORECASE
)
_QUESTION_RE = re.compile(
    r"(\?|que |qué |como |cómo |cuando |cuándo |donde |dónde |quien |quién |cual |cuál |per que|com )",
    re.IGNORECASE,
)
_SHORT_AFFIRM_RE = re.compile(
    r"^(si+|ok+|vale|bien|genial|perfecto|gracias|gràcies|d acord|sí+|claro|ya|jaja)",
    re.IGNORECASE,
)


def _classify_user_message(message: str) -> str:
    """Classify a user message into a response-length category."""
    msg = message.strip()
    msg_len = len(msg)

    # Short affirmations first — "Si", "Ok", "Vale" etc. before greeting fallback
    if msg_len <= 15 and _SHORT_AFFIRM_RE.match(msg):
        return "short_affirmation"
    if _GREETING_RE.match(msg) or (msg_len <= 5 and not _BOOKING_PRICE_RE.search(msg)):
        return "greeting"
    if _BOOKING_PRICE_RE.search(msg):
        return "booking_price"
    if _CANCEL_RE.search(msg):
        return "cancel"
    if _QUESTION_RE.search(msg):
        return "question"
    if msg_len <= 20:
        return "short_casual"
    return "long_message"


def get_adaptive_max_tokens(
    message: str,
    calibration: Optional[dict] = None,
    fallback: int = 150,
) -> int:
    """Return max_tokens as a safety-net ceiling (not a guide).

    Always returns 150 — the model is guided by prompt-level length hints
    instead. This prevents mid-sentence truncation while still capping
    runaway generation.
    """
    return 150


# Length hints — natural language instructions injected into the prompt
# so the model generates the right length NATURALLY instead of being truncated.
_LENGTH_HINTS = {
    "short_affirmation": "Responde ultra-breve (1-3 palabras o emoji).",
    "greeting": "Saludo breve y cálido, 1 frase.",
    "cancel": "Respuesta empática muy breve.",
    "short_casual": "Respuesta corta y natural, 1 frase.",
    "booking_price": "Da el precio/info de reserva necesaria, sin rodeos.",
    "question": "Responde la pregunta de forma directa.",
    "long_message": "Responde proporcionalmente al mensaje del lead.",
}


def get_length_hint(message: str) -> str:
    """Return a natural-language length hint for the given user message.

    The hint is injected into the system prompt so the model self-regulates
    output length instead of relying on max_tokens truncation.

    Returns empty string for categories that don't need guidance.
    """
    category = _classify_user_message(message)
    return _LENGTH_HINTS.get(category, "")

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
    by matching on the short-name segment or >=1 significant brand word.

    BUG-09 fix: lowercases msg internally (caller may pass mixed case),
    and lowers word-match threshold to 1 for better partial-name detection.
    """
    pname = _strip_accents(product_name.lower().strip())
    msg = _strip_accents(msg_lower.lower())  # ensure lowercase regardless of caller

    if not pname or len(pname) <= 3:
        return False

    # 1. Exact substring (works for short names like "Círculo de Hombres")
    if pname in msg:
        return True

    # 2. First segment before ':' or '—' delimiter (e.g., "Fitpack Challenge")
    for sep in [":", "\u2014", " - "]:
        if sep in pname:
            short = pname.split(sep)[0].strip()
            if short and len(short) > 3 and short in msg:
                return True
            break

    # 3. Brand-word matching: >=1 significant word found in message
    # Strip non-alphanumeric chars (handles "1:1" -> "1" which is too short)
    cleaned_pname = re.sub(r'[^a-z0-9\s]', ' ', pname)
    words = [w for w in cleaned_pname.split() if len(w) >= 4 and w not in _PRODUCT_STOPWORDS]
    if words:
        matches = sum(1 for w in words if w in msg)
        if matches >= 1:
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
# NON-CACHEABLE INTENTS (backward compatibility)
# =============================================================================
# Intents that should NOT be cached (require fresh responses)
NON_CACHEABLE_INTENTS = {
    Intent.OBJECTION_PRICE,
    Intent.OBJECTION_TIME,
    Intent.OBJECTION_DOUBT,
    Intent.OBJECTION_LATER,
    Intent.OBJECTION_WORKS,
    Intent.OBJECTION_NOT_FOR_ME,
    Intent.INTEREST_STRONG,  # Active conversions
    Intent.ESCALATION,
    Intent.SUPPORT,  # Support needs personalized responses
    Intent.OTHER,  # Fallback - always regenerate
}


# =============================================================================
# VOSEO CONVERSION (backward compatibility)
# =============================================================================
def apply_voseo(text: str) -> str:
    """
    Convert Spanish tuteo to Argentine voseo.
    Transforms: tu->vos, tienes->tenes, puedes->podes, etc.
    """
    # Conversion patterns tuteo -> voseo
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
        (r"\bestás\b", "estás"),  # Same in voseo
        (r"\bvas\b", "vas"),  # Same in voseo
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
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    return result


# =============================================================================
# MESSAGE SPLITTER (word- and URL-aware)
# =============================================================================

def split_message(text: str, max_length: int = 160) -> list:
    """
    Split a long message into parts of at most max_length chars.

    Rules:
    - Never splits mid-word (parts end at space boundaries)
    - Never splits a URL across two parts (URL always kept intact, even if > max_length)
    - Non-last parts end with a trailing space to mark word boundary

    Args:
        text: The message text to split
        max_length: Maximum characters per part (URLs may exceed this limit)

    Returns:
        List of message parts
    """
    if len(text) <= max_length:
        return [text]

    # Build a set of (start, end) for all URLs in the text
    url_pattern = re.compile(r'https?://\S+')
    url_spans = [(m.start(), m.end()) for m in url_pattern.finditer(text)]

    def _url_covering(pos: int):
        """Return (start, end) of URL that contains pos, or None."""
        for start, end in url_spans:
            if start <= pos < end:
                return (start, end)
        return None

    parts = []
    pos = 0

    while pos < len(text):
        remaining = text[pos:]
        if len(remaining) <= max_length:
            parts.append(remaining.rstrip())
            break

        target = pos + max_length

        # Check if target lands inside a URL — if so, extend to include full URL
        url_span = _url_covering(target)
        if url_span:
            url_end = url_span[1]
            # Find the next space after the URL to split there
            next_space = text.find(' ', url_end)
            if next_space != -1:
                parts.append(text[pos:next_space + 1])  # include trailing space
                pos = next_space + 1
            else:
                parts.append(text[pos:])
                break
            continue

        # Walk back from target to find a space that isn't inside a URL
        split_at = None
        for i in range(target - 1, pos, -1):
            if text[i] == ' ' and _url_covering(i) is None:
                split_at = i
                break

        if split_at is not None:
            # Split at this space; keep the space so the part ends with ' '
            parts.append(text[pos:split_at + 1])
            pos = split_at + 1
        else:
            # No valid space — check if we're at the start of a URL
            url_span_here = _url_covering(pos)
            if url_span_here:
                url_end = url_span_here[1]
                next_space = text.find(' ', url_end)
                if next_space != -1:
                    parts.append(text[pos:next_space + 1])
                    pos = next_space + 1
                else:
                    parts.append(text[pos:])
                    break
            else:
                # Force-split at max_length
                parts.append(text[pos:target])
                pos = target

    # Strip only trailing whitespace from last part; keep inner spaces intact
    return [p for p in parts if p.strip()]
