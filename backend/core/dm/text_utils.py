"""
Text utility functions for DM Agent V2.

- Accent stripping for fuzzy matching
- Product name matching (fuzzy, accent-insensitive)
- Sentence-aware text truncation
- Smart context truncation preserving recent conversation
- Argentine voseo conversion
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
        result = re.sub(pattern, replacement, result)

    return result
