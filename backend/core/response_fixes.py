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


def apply_all_response_fixes(
    response: str,
    creator_name: str = None,
    products: List[Dict[str, Any]] = None
) -> str:
    """
    Apply all v1.5.2 technical fixes to a response.

    Args:
        response: The LLM-generated response text
        creator_name: Optional creator name for identity fix
        products: Optional products list (not used for response text, but logged)

    Returns:
        Fixed response text
    """
    if not response:
        return response

    # Apply fixes in order
    response = fix_price_typo(response)
    response = fix_broken_links(response)
    response = fix_identity_claim(response, creator_name)
    response = clean_raw_ctas(response)
    response = hide_technical_errors(response)

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
