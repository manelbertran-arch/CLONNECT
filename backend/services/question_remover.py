"""
Question Remover - Removes unnecessary questions from responses.

Loads creator's question_rate from baseline profile. If no data available,
skips question removal entirely (zero hardcoding).
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Generic questions that should ALWAYS be removed (these are bot artifacts,
# not creator-specific — they appear across all creators as LLM muletillas)
BANNED_QUESTIONS = [
    r"¿qué tal\?",
    r"¿cómo estás\?",
    r"¿cómo vas\?",
    r"¿todo bien\?",
    r"¿y tú\?",
    r"¿y vos\?",
    r"¿qué cuentas\?",
    r"¿cómo te va\?",
    r"¿qué hay\?",
    r"¿qué onda\?",
    # Muletilla #1 del copiloto — appears across multiple creators
    r"¿qué te llamó la atención\?",
    r"¿qué fue lo que te llamó la atención\?",
    r"¿qué te llamó más la atención\?",
    r"¿qué fue lo que más te llamó la atención\?",
    r"¿algo en particular que te llamó la atención\?",
    # Muletilla #2 — generic assistant pattern
    r"¿en qué puedo ayudarte\?",
    r"¿hay algo en lo que pueda ayudarte\?",
    r"¿te puedo ayudar en algo\?",
    r"¿en qué te puedo ayudar\?",
    # Generic follow-up catchphrases (accent-insensitive)
    r"¿?qu[eé]\s+te\s+trajo\s+por\s+ac[aá][^?]*\??",
    r"contame\s+qu[eé]\s+te\s+trae\s+por\s+ac[aá][^?]*\??",
    r"contame\s+(?:de\s+lo\s+que\s+comparto|qu[eé]\s+te\s+llam[oó])[^?]*\??",
]

# Standalone filler responses (entire response = just this phrase)
FILLER_EXACT = {
    "contame mas", "contame más",
    "cuentame mas", "cuéntame más",
}

# Replacements for removed questions (empty string = remove entirely)
QUESTION_REPLACEMENTS = {
    "¿qué tal?": "",
    "¿cómo estás?": "",
    "¿todo bien?": "",
    "¿y tú?": "",
    "¿y vos?": "",
    "¿qué cuentas?": "",
    "¿cómo te va?": "",
    "¿qué te llamó la atención?": "",
    "¿qué fue lo que te llamó la atención?": "",
    "¿qué te llamó más la atención?": "",
    "¿qué fue lo que más te llamó la atención?": "",
    "¿algo en particular que te llamó la atención?": "",
    "¿en qué puedo ayudarte?": "",
    "¿hay algo en lo que pueda ayudarte?": "",
    "¿te puedo ayudar en algo?": "",
    "¿en qué te puedo ayudar?": "",
}


def _load_creator_question_rate(creator_id: str) -> Optional[float]:
    """Load creator's question_rate from baseline profile.

    Returns rate as fraction (0-1), or None if no data available.
    """
    try:
        from services.creator_profile_service import get_baseline
        baseline = get_baseline(creator_id)
        if baseline:
            punct = baseline.get("metrics", {}).get("punctuation", {})
            rate_pct = punct.get("has_question_msg_pct", punct.get("question_rate_pct"))
            if rate_pct is not None:
                return float(rate_pct) / 100.0
    except Exception as e:
        logger.debug("question_remover: failed to load profile for %s: %s", creator_id, e)

    # Fallback: try calibration data
    try:
        from services.calibration_loader import load_calibration
        cal = load_calibration(creator_id)
        if cal:
            rate_pct = cal.get("baseline", {}).get("question_frequency_pct")
            if rate_pct is not None:
                return float(rate_pct) / 100.0
    except Exception as e:
        logger.debug("question_remover: calibration load failed for %s: %s", creator_id, e)

    return None


def _load_creator_question_rate_std(creator_id: str) -> Optional[float]:
    """Load creator's question_rate standard deviation from profile.

    Returns std as fraction (0-1), or None if not available.
    """
    try:
        from services.creator_profile_service import get_baseline
        baseline = get_baseline(creator_id)
        if baseline:
            punct = baseline.get("metrics", {}).get("punctuation", {})
            std_pct = punct.get("question_rate_std_pct")
            if std_pct is not None:
                return float(std_pct) / 100.0
    except Exception:
        pass
    return None


def contains_banned_question(text: str) -> bool:
    """Check if text contains a banned question."""
    text_lower = text.lower()
    for pattern in BANNED_QUESTIONS:
        if re.search(pattern, text_lower):
            return True
    return False


def remove_banned_questions(text: str) -> str:
    """Remove banned questions from text."""
    result = text

    for question, replacement in QUESTION_REPLACEMENTS.items():
        result = re.sub(re.escape(question), replacement, result, flags=re.IGNORECASE)

    # Clean multiple spaces
    result = re.sub(r"\s+", " ", result).strip()

    return result


def should_allow_question(lead_message: str, response: str) -> bool:
    """
    Determine if a question in the response is justified.

    Allow questions when:
    1. Lead asked a question first
    2. Information is needed to complete an action
    3. It's sales/service follow-up
    """
    response_lower = response.lower()

    # If lead asked, we can respond with question
    if "?" in lead_message:
        return True

    # Necessary clarification questions
    clarification_patterns = [
        r"qué (día|hora|fecha)",
        r"cuándo (puedes|te va)",
        r"dónde (nos vemos|quedamos)",
        r"cuál (prefieres|quieres)",
    ]
    for pattern in clarification_patterns:
        if re.search(pattern, response_lower):
            return True

    # Sales follow-up
    sales_patterns = [
        r"te interesa",
        r"quieres (que te|reservar|agendar)",
        r"te paso (el link|info)",
    ]
    for pattern in sales_patterns:
        if re.search(pattern, response_lower):
            return True

    return False


def _normalize_for_filler(text: str) -> str:
    """Strip emojis and punctuation for filler check."""
    return re.sub(r"[^\w\s]", "", text).strip().lower()


def convert_question_to_statement(text: str) -> str:
    """Convert a question to a statement using pattern matching."""
    # Conversion patterns — these are structural transforms, not creator-specific
    conversions = [
        (r"¿cómo te fue\?", ""),
        (r"¿qué te pareció\?", ""),
        (r"¿cómo te sientes\?", ""),
        (r"¿qué tal te fue\?", ""),
        (r"¿pudiste\?", ""),
        (r"¿te gustó\?", ""),
    ]

    for pattern, replacement in conversions:
        if re.search(pattern, text, re.IGNORECASE):
            result = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
            result = re.sub(r"\s+", " ", result).strip()
            return result if result else text

    # Fallback: keep the response as-is with its questions
    return text


def process_questions(
    response: str,
    lead_message: str,
    question_rate: Optional[float] = None,
    creator_id: Optional[str] = None,
) -> str:
    """
    Process and remove unnecessary questions from response.

    Args:
        response: Generated response
        lead_message: Lead's message
        question_rate: Creator's question rate (0-1 fraction). If None, loaded from profile.
        creator_id: Creator ID for loading profile data.

    Returns:
        Response without unnecessary questions
    """
    # Check for standalone filler responses
    if _normalize_for_filler(response) in FILLER_EXACT:
        return response  # Return as-is — caller should regenerate

    # If no question, return as-is
    if "?" not in response:
        return response

    # If question is justified, allow it
    if should_allow_question(lead_message, response):
        return response

    # Remove banned questions (always — these are bot artifacts, not creator-specific)
    result = remove_banned_questions(response)

    # Determine question_rate from profile if not provided
    if question_rate is None and creator_id:
        question_rate = _load_creator_question_rate(creator_id)

    if question_rate is None:
        logger.warning("question_remover: no question_rate in profile for %s, skipping conversion", creator_id or "unknown")
        return result

    # Load std for band-based decision
    question_rate_std = None
    if creator_id:
        question_rate_std = _load_creator_question_rate_std(creator_id)

    # Band-based: if bot is above the creator's natural band, convert question
    if "?" in result:
        if question_rate_std is not None:
            upper_band = question_rate + question_rate_std
            if question_rate < upper_band:
                # Bot over-questions → convert
                result = convert_question_to_statement(result)
        else:
            # No std available — use question_rate alone as threshold
            if question_rate < result.count("?") / max(len(result.split()), 1):
                result = convert_question_to_statement(result)

    return result
