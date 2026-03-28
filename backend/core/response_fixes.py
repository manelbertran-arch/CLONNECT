"""
Response Fixes v1.5.2 - Technical fixes for bot responses.

Fixes included:
- FIX 1: Price "22?" -> "22€" (regex typo fix)
- FIX 2: Deduplicate products by name
- FIX 3: Broken links ://www -> https://www
- FIX 4: "Soy Stefano" -> "Soy el asistente de Stefano"
- FIX 5: Clean RAG of raw CTAs ("QUIERO SER PARTE")
- FIX 6: Hide technical errors (never show "ERROR:")
"""

import logging
import re
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


# =============================================================================
# FIX 1: Price typo fix - "22?" -> "22€"
# =============================================================================


def fix_price_typo(response: str) -> str:
    """
    Fix price typos where '?' was used instead of '€'.
    Examples: "22?" -> "22€", "297?" -> "297€"
    """
    if not response:
        return response

    # Pattern: number followed by ? that looks like a price typo
    # Match: "297?" or "22?" but not "¿tienes 22?" (question about the number)
    # The ? should be at end of number, not followed by more question text
    pattern = r'(\d+(?:[.,]\d{1,2})?)\s*\?(?=\s|$|[,.]|\sy\s)'

    def replace_price(match):
        price = match.group(1)
        logger.info(f"[FIX 1] Price typo fixed: {price}? -> {price}€")
        return f"{price}€"

    fixed = re.sub(pattern, replace_price, response)
    return fixed


# =============================================================================
# FIX 2: Deduplicate products by name
# =============================================================================


def deduplicate_products(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate products based on name (case-insensitive).
    Keeps the first occurrence of each product.
    """
    if not products:
        return products

    seen_names = set()
    unique_products = []
    duplicates_removed = 0

    for product in products:
        name = product.get("name", "").lower().strip()
        if name and name not in seen_names:
            seen_names.add(name)
            unique_products.append(product)
        elif name:
            duplicates_removed += 1

    if duplicates_removed > 0:
        logger.info(f"[FIX 2] Removed {duplicates_removed} duplicate products")

    return unique_products


# =============================================================================
# FIX 3: Fix broken links - "://www" -> "https://www"
# =============================================================================


def fix_broken_links(response: str) -> str:
    """
    Fix broken links that are missing the protocol.
    Examples: "://www.example.com" -> "https://www.example.com"
    """
    if not response:
        return response

    # Pattern: "://www" at the start of a URL (missing https)
    pattern = r'(?<![a-zA-Z])://www\.'

    if re.search(pattern, response):
        logger.info("[FIX 3] Fixing broken link (missing https)")
        response = re.sub(pattern, 'https://www.', response)

    return response


# =============================================================================
# FIX 4: Identity fix - "Soy Stefano" -> "Soy el asistente de Stefano"
# =============================================================================


def fix_identity_claim(response: str, creator_name: str = None) -> str:
    """
    Prevent the bot from claiming to be the creator.
    Examples: "Soy Stefano" -> "Soy el asistente de Stefano"
    """
    if not response:
        return response

    # Pattern for common identity claims
    identity_patterns = [
        # Spanish patterns
        (r'\b[Ss]oy\s+([A-Z][a-záéíóúñ]+)\b(?!\s+(?:el|la|un|una)\s+asistente)', r'Soy el asistente de \1'),
        (r'\b[Mm]e\s+llamo\s+([A-Z][a-záéíóúñ]+)\b', r'Soy el asistente de \1'),
        # Catalan patterns
        (r'\b[Ss]óc\s+([A-Z][a-záéíóúàèìòùç]+)\b(?!\s+(?:el|la|un|una)\s+assistent)', r'Sóc l\'assistent de \1'),
        # English patterns
        (r'\bI\s+am\s+([A-Z][a-z]+)\b(?!\s+(?:the|an?)\s+assistant)', r"I'm the assistant of \1"),
        (r'\bI\'m\s+([A-Z][a-z]+)\b(?!\s+(?:the|an?)\s+assistant)', r"I'm the assistant of \1"),
    ]

    original = response
    for pattern, replacement in identity_patterns:
        response = re.sub(pattern, replacement, response)

    if response != original:
        logger.info("[FIX 4] Identity claim fixed")

    return response


# =============================================================================
# FIX 5: Clean RAG of raw CTAs
# =============================================================================


def clean_raw_ctas(response: str) -> str:
    """
    Remove raw Call-To-Action text that shouldn't appear in responses.
    Examples: "QUIERO SER PARTE", "COMPRA AHORA", "INSCRIBETE YA"
    """
    if not response:
        return response

    # List of raw CTAs that should be removed (usually in ALL CAPS)
    raw_ctas = [
        r'QUIERO\s+SER\s+PARTE',
        r'QUIERO\s+UNIRME',
        r'COMPRA\s+AHORA',
        r'INSCR[ÍI]BETE\s+(?:YA|AHORA)',
        r'APÚNTATE\s+(?:YA|AHORA)',
        r'RESERVA\s+TU\s+PLAZA',
        r'ÚNETE\s+(?:YA|AHORA)',
        r'HAGA?\s+CLIC\s+AQU[ÍI]',
        r'CLICK\s+HERE',
        r'BUY\s+NOW',
        r'SIGN\s+UP\s+NOW',
        r'JOIN\s+NOW',
        r'\[CTA\]',
        r'\[CALL\s+TO\s+ACTION\]',
        # Social media CTAs
        r'LINK\s+EN\s+(?:MI\s+)?BIO',
        r'SWIPE\s+UP',
        r'DM\s+(?:ME|FOR)\s+(?:INFO|MORE)',
        r'TAP\s+(?:THE\s+)?LINK',
    ]

    original = response
    for cta_pattern in raw_ctas:
        # Remove the CTA and any surrounding punctuation/whitespace
        pattern = rf'\s*["\'\[\(]?{cta_pattern}["\'\]\)]?\s*'
        response = re.sub(pattern, ' ', response, flags=re.IGNORECASE)

    # Clean up extra spaces
    response = re.sub(r'\s{2,}', ' ', response).strip()

    if response != original:
        logger.info("[FIX 5] Raw CTAs removed from response")

    return response


# =============================================================================
# FIX 6: Hide technical errors
# =============================================================================


def hide_technical_errors(response: str) -> str:
    """
    Remove technical error messages from responses.
    User should never see "ERROR:", "Exception:", stack traces, etc.
    """
    if not response:
        return response

    # Patterns for technical errors that should be hidden
    # Use [^.!?\n]* to stop at sentence boundaries, not consume entire line
    error_patterns = [
        r'ERROR:\s*[^.!?\n]*[.!?]?\s*',
        r'Error:\s*[^.!?\n]*[.!?]?\s*',
        r'Exception:\s*[^.!?\n]*[.!?]?\s*',
        r'Traceback\s*\([^\)]+\)[^.!?\n]*[.!?]?\s*',
        r'File\s+"[^"]+",\s+line\s+\d+[^.!?\n]*[.!?]?\s*',
        r'\[ERROR\][^.!?\n]*[.!?]?\s*',
        r'\[EXCEPTION\][^.!?\n]*[.!?]?\s*',
        r'NoneType\s+object[^.!?\n]*[.!?]?\s*',
        r'KeyError:\s*[^.!?\n]*[.!?]?\s*',
        r'ValueError:\s*[^.!?\n]*[.!?]?\s*',
        r'TypeError:\s*[^.!?\n]*[.!?]?\s*',
        r'IndexError:\s*[^.!?\n]*[.!?]?\s*',
        r'AttributeError:\s*[^.!?\n]*[.!?]?\s*',
        r'ConnectionError:\s*[^.!?\n]*[.!?]?\s*',
        r'TimeoutError:\s*[^.!?\n]*[.!?]?\s*',
        r'HTTP\s+\d{3}\s+Error[^.!?\n]*[.!?]?\s*',
        r'Internal\s+Server\s+Error[^.!?\n]*[.!?]?\s*',
        r'Database\s+error[^.!?\n]*[.!?]?\s*',
        r'API\s+error[^.!?\n]*[.!?]?\s*',
    ]

    original = response
    for pattern in error_patterns:
        response = re.sub(pattern, '', response, flags=re.IGNORECASE)

    # Clean up leftover whitespace
    response = re.sub(r'\n{2,}', '\n', response)
    response = re.sub(r'\s{2,}', ' ', response).strip()

    if response != original:
        logger.info("[FIX 6] Technical errors hidden from response")

        # If response is now empty or too short AFTER removing errors, use fallback
        if len(response.strip()) < 10:
            logger.warning("[FIX 6] Response empty after error removal, using fallback")
            return ""  # Let the caller handle the fallback

    return response


# =============================================================================
# MAIN FUNCTION: Apply all fixes
# =============================================================================


def apply_blacklist_filter(response: str, creator_id: str = None) -> str:
    """
    FIX 7: Remove blacklisted phrases from personality extraction (Doc D §4.2).

    Case-insensitive substring match. If the response contains a blacklisted
    phrase, it is removed. If the result is empty, returns original.
    """
    if not response or not creator_id:
        return response

    try:
        from core.personality_loader import load_extraction

        extraction = load_extraction(creator_id)
        if not extraction or not extraction.blacklist_phrases:
            return response
    except Exception:
        return response

    original = response
    for phrase in extraction.blacklist_phrases:
        if not phrase:
            continue
        # Case-insensitive removal, preserving surrounding whitespace
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        response = pattern.sub("", response)

    if response != original:
        # Clean up leftover whitespace
        response = re.sub(r"\s{2,}", " ", response).strip()
        removed = len(original) - len(response)
        logger.info("[FIX 7] Blacklist filter removed %d chars for %s", removed, creator_id)

    # Don't return empty response
    if not response.strip():
        return original

    return response


_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"  # supplemental
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"
    "]"
    "[\U0000FE0F\U0000200D\U0001F3FB-\U0001F3FF]*",  # optional modifiers (variation, ZWJ, skin tone)
    flags=re.UNICODE,
)


def apply_emoji_limit(response: str, creator_id: str = None) -> str:
    """
    FIX 8: Limit emoji count per message from Doc D §4.3 calibration.

    BUG-11 fix: applies a default limit of 5 when no calibration is available,
    so responses with 10+ emojis are trimmed even for uncalibrated creators.
    """
    if not response or not creator_id:
        return response

    DEFAULT_MAX_EMOJIS = 5  # BUG-11: default when no calibration
    max_emojis = DEFAULT_MAX_EMOJIS

    try:
        from core.personality_loader import get_calibration_override

        override = get_calibration_override(creator_id)
        if override:
            calibrated_max = override.get("max_emojis_per_message")
            if calibrated_max is not None:
                max_emojis = calibrated_max
    except Exception:
        pass  # use default

    emoji_matches = list(_EMOJI_RE.finditer(response))
    emoji_count = len(emoji_matches)

    if emoji_count <= max_emojis:
        return response

    # Remove excess emojis from the end
    to_remove = emoji_count - max_emojis
    for match in reversed(emoji_matches):
        if to_remove <= 0:
            break
        response = response[:match.start()] + response[match.end():]
        to_remove -= 1

    response = response.strip()
    logger.info("[FIX 8] Emoji limit applied: %d -> %d for %s", emoji_count, max_emojis, creator_id)
    return response


# =============================================================================
# FIX 9: Global catchphrase removal (accent-insensitive via unicode NFKD)
# =============================================================================

# Regex patterns for LLM-overused catchphrases.
# Matches the phrase + any trailing content up to the next sentence or end.
# Production variants found:
#   "Que te llamo la atencion?"
#   "Qué te llamó la atención? 😀"
#   "qué te llamó la atención de Menoutthebox?"
#   "Che, qué onda?? 😀 Qué te llamo la atención?"
#   "Daleee! Que te llamó la atención?"
_CATCHPHRASE_PATTERNS = [
    # "¿Qué te llamó la atención [de X]?" — matches the whole question including trailing content
    re.compile(
        r"[¿]?\s*qu[eé]\s+te\s+llam[oó]\s+la\s+atenci[oó]n[^.!?\n]*[?]?\s*",
        re.IGNORECASE,
    ),
    # "¿Qué te trajo por acá [...]?"
    re.compile(
        r"[¿]?\s*qu[eé]\s+te\s+trajo\s+por\s+ac[aá][^.!?\n]*[?]?\s*",
        re.IGNORECASE,
    ),
    # "Contame qué te trae por acá"
    re.compile(
        r"contame\s+qu[eé]\s+te\s+trae\s+por\s+ac[aá][^.!?\n]*[?]?\s*",
        re.IGNORECASE,
    ),
    # "Contame de lo que comparto" / "Contame qué te llamó"
    re.compile(
        r"contame\s+(?:de\s+lo\s+que\s+comparto|qu[eé]\s+te\s+llam[oó])[^.!?\n]*[?]?\s*",
        re.IGNORECASE,
    ),
]

# Standalone filler responses (complete response = just this phrase)
_FILLER_EXACT = {
    "contame mas",
    "contame más",
    "cuentame mas",
    "cuéntame más",
}


def _normalize_for_filler_check(text: str) -> str:
    """Normalize for filler check: lowercase, strip emojis and punctuation."""
    import unicodedata

    # Remove emojis and special chars, keep letters/spaces
    cleaned = ""
    for ch in text:
        if unicodedata.category(ch).startswith(("L", "Z")):
            cleaned += ch
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def remove_catchphrases(response: str) -> str:
    """FIX 9: Remove global catchphrases using accent-insensitive regex."""
    if not response:
        return response

    original = response

    # Check for standalone filler responses first
    normalized = _normalize_for_filler_check(response)
    if normalized in _FILLER_EXACT:
        logger.info("[FIX 9] Standalone filler detected: '%s'", normalized)
        return original  # Return original — caller should regenerate

    for pattern in _CATCHPHRASE_PATTERNS:
        response = pattern.sub(" ", response)

    if response != original:
        # Clean up: collapse whitespace, remove orphan emojis at start/end
        response = re.sub(r"\s{2,}", " ", response).strip()
        # Remove leading/trailing punctuation that became orphaned
        response = re.sub(r"^[,;:\s]+", "", response).strip()
        logger.info("[FIX 9] Catchphrase removed: %d chars removed", len(original) - len(response))

    # Don't return empty
    if not response.strip():
        return original

    return response


def apply_all_response_fixes(
    response: str,
    creator_name: str = None,
    products: List[Dict[str, Any]] = None,
    creator_id: str = None,
) -> str:
    """
    Apply all technical fixes to a response.

    Args:
        response: The LLM-generated response text
        creator_name: Optional creator name for identity fix
        products: Optional products list (not used for response text, but logged)
        creator_id: Optional creator ID for personality extraction blacklist

    Returns:
        Fixed response text
    """
    if not response:
        return response

    original = response  # preserve for empty-result fallback

    # Apply fixes in order
    response = fix_price_typo(response)
    response = fix_broken_links(response)
    # DISABLED: breaks first-person creators like Iris (audit 2026-03-26)
    # fix_identity_claim turns "Soy Iris" → "Soy el asistente de Iris" for all creators.
    # Re-enable conditionally if a creator ever needs bot_mode="assistant".
    # response = fix_identity_claim(response, creator_name)
    response = clean_raw_ctas(response)
    response = hide_technical_errors(response)

    # FIX 7: Personality extraction blacklist (after all other fixes)
    response = apply_blacklist_filter(response, creator_id)

    # FIX 8: Emoji limit — MOVED to postprocessing.py
    # FIX 9: Catchphrase removal — MERGED into question_remover.py

    # FIX 10: Strip markdown formatting — DMs don't render markdown, it looks broken.
    # **bold** → bold, *italic* → italic, `code` → code, ## headers stripped.
    response = re.sub(r'\*\*(.+?)\*\*', r'\1', response)
    response = re.sub(r'\*([^*\n]+?)\*', r'\1', response)
    response = re.sub(r'`([^`\n]+?)`', r'\1', response)
    response = re.sub(r'^#{1,3}\s+', '', response, flags=re.MULTILINE)

    # BUG-10 fix: if all fixes stripped the response to empty, return the
    # original pre-fix response (better than a hardcoded fallback).
    if not response.strip():
        logger.warning("[FIXES] All fixes resulted in empty response — using original")
        return original

    return response


def apply_product_fixes(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply product-level fixes (deduplication).

    Args:
        products: List of product dictionaries

    Returns:
        Deduplicated products list
    """
    return deduplicate_products(products)
