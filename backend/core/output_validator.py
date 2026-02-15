"""
Output Validator Module

Validates LLM responses BEFORE sending to prevent:
- Hallucinated prices
- Unauthorized/fabricated URLs
- Invented products
- Missing required links (booking, payment, lead magnet)

This is the last line of defense against hallucinations.

Part of refactor/context-injection-v2
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.context_detector import DetectedContext
from core.creator_data_loader import CreatorData
from core.intent_classifier import Intent

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class ValidationIssue:
    """A single validation issue found in a response."""

    type: str  # hallucinated_price, hallucinated_link, unknown_product, missing_link, etc.
    severity: str  # error, warning
    details: str
    auto_fix: Optional[str] = None  # Automatic correction if possible

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "details": self.details,
            "auto_fix": self.auto_fix,
        }


@dataclass
class ValidationResult:
    """Result of validating an LLM response."""

    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    corrected_response: str = ""
    original_response: str = ""
    should_escalate: bool = False  # True if hallucination is too severe to fix
    was_truncated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "issues": [i.to_dict() for i in self.issues],
            "corrected_response": self.corrected_response,
            "original_response": self.original_response,
            "should_escalate": self.should_escalate,
            "was_truncated": self.was_truncated,
        }

    def add_issue(
        self,
        issue_type: str,
        severity: str,
        details: str,
        auto_fix: Optional[str] = None,
    ):
        """Add a validation issue."""
        self.issues.append(
            ValidationIssue(
                type=issue_type,
                severity=severity,
                details=details,
                auto_fix=auto_fix,
            )
        )
        if severity == "error":
            self.is_valid = False


# =============================================================================
# PRICE VALIDATION
# =============================================================================


def extract_prices_from_text(text: str) -> List[Tuple[str, float]]:
    """
    Extract prices from text.

    Returns list of (original_match, float_value) tuples.
    Deduplicates by value to avoid counting same price multiple times.
    """
    if not text:
        return []

    prices = []
    seen_values = set()

    # Price patterns: 297€, €297, 297 euros, 297 EUR, $297
    patterns = [
        r"(\d+(?:[.,]\d{1,2})?)\s*€",
        r"€\s*(\d+(?:[.,]\d{1,2})?)",
        r"(\d+(?:[.,]\d{1,2})?)\s*euros?",
        r"(\d+(?:[.,]\d{1,2})?)\s*EUR\b",
        r"\$\s*(\d+(?:[.,]\d{1,2})?)",
        r"(\d+(?:[.,]\d{1,2})?)\s*USD",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                # Normalize decimal separator
                normalized = match.replace(",", ".")
                float_val = float(normalized)
                # Dedupe by value
                if float_val not in seen_values:
                    seen_values.add(float_val)
                    prices.append((match, float_val))
            except ValueError:
                continue

    return prices


def validate_prices(
    response: str,
    known_prices: Dict[str, float],
    tolerance: float = 1.0,
) -> List[ValidationIssue]:
    """
    Validate that prices in response match known prices.

    Args:
        response: LLM response text
        known_prices: Dict of {product_name: price} from CreatorData.get_known_prices()
        tolerance: Allowed difference for rounding (default ±1€)

    Returns:
        List of ValidationIssue for any hallucinated prices
    """
    issues = []

    if not known_prices:
        # No known prices = can't validate, skip
        logger.debug("No known prices to validate against")
        return issues

    # Get set of known price values
    known_values = set(known_prices.values())

    # Extract prices from response
    found_prices = extract_prices_from_text(response)

    for original, value in found_prices:
        # Check if this price is within tolerance of any known price
        is_valid = False
        for known in known_values:
            if abs(value - known) <= tolerance:
                is_valid = True
                break

        if not is_valid:
            logger.warning(
                f"Hallucinated price detected: {original} ({value}€) "
                f"not in known prices {known_values}"
            )
            issues.append(
                ValidationIssue(
                    type="hallucinated_price",
                    severity="error",
                    details=f"Price {original}€ not found in known products. Known prices: {list(known_values)}",
                    auto_fix=None,  # Can't auto-fix prices - too risky
                )
            )

    return issues


# =============================================================================
# LINK VALIDATION
# =============================================================================


def extract_urls_from_text(text: str) -> List[str]:
    """Extract URLs from text."""
    if not text:
        return []

    # URL pattern
    pattern = r"https?://[^\s<>\"')\]]+(?:\([^\s]*\))?[^\s<>\"')\]]?"
    urls = re.findall(pattern, text)

    # Clean up trailing punctuation that might be captured
    cleaned = []
    for url in urls:
        # Remove trailing punctuation that's likely not part of URL
        url = url.rstrip(".,;:!?")
        if url:
            cleaned.append(url)

    return cleaned


# Default allowed domains (trusted payment/booking platforms)
DEFAULT_ALLOWED_DOMAINS = [
    "stripe.com",
    "pay.hotmart.com",
    "hotmart.com",
    "gumroad.com",
    "calendly.com",
    "cal.com",
    "tidycal.com",
    "instagram.com",
    "wa.me",
    "whatsapp.com",
    "t.me",
    "telegram.me",
    "youtube.com",
    "youtu.be",
    "www.clonnectapp.com",
    "clonnectapp.com",
    "revolut.me",
    "paypal.me",
    "paypal.com",
]


def validate_links(
    response: str,
    known_links: List[str],
    allowed_domains: Optional[List[str]] = None,
) -> Tuple[List[ValidationIssue], str]:
    """
    Validate that URLs in response are authorized.

    Args:
        response: LLM response text
        known_links: List of known links from CreatorData.get_known_links()
        allowed_domains: Additional allowed domains

    Returns:
        Tuple of (issues, corrected_response)
    """
    issues = []
    corrected = response

    # Combine default and custom allowed domains
    domains = set(DEFAULT_ALLOWED_DOMAINS)
    if allowed_domains:
        domains.update(allowed_domains)

    # Also allow domains from known links
    for link in known_links:
        try:
            # Extract domain from URL
            match = re.search(r"https?://([^/]+)", link)
            if match:
                domain = match.group(1).lower()
                # Add domain and its parent
                domains.add(domain)
                parts = domain.split(".")
                if len(parts) >= 2:
                    domains.add(".".join(parts[-2:]))
        except Exception as e:
            logger.warning("Suppressed error in match = re.search(r'https?://([^/]+)', link): %s", e)

    # Extract URLs from response
    found_urls = extract_urls_from_text(response)

    for url in found_urls:
        # Check if URL is a known link (exact or prefix match)
        is_known = any(
            url.startswith(known) or known.startswith(url)
            for known in known_links
        )

        if is_known:
            continue

        # Check if URL domain is allowed
        url_lower = url.lower()
        is_allowed_domain = any(domain in url_lower for domain in domains)

        if not is_allowed_domain:
            logger.warning(f"Hallucinated/unauthorized URL detected: {url}")
            issues.append(
                ValidationIssue(
                    type="hallucinated_link",
                    severity="error",
                    details=f"URL {url[:50]}... is not authorized",
                    auto_fix="removed",
                )
            )
            # Remove the hallucinated URL from response
            corrected = corrected.replace(url, "[enlace removido]")

    return issues, corrected


# =============================================================================
# PRODUCT VALIDATION
# =============================================================================


def validate_products(
    response: str,
    product_names: List[str],
) -> List[ValidationIssue]:
    """
    Validate that products mentioned in response exist.

    This is a soft check - only flags obvious fabrications.

    Args:
        response: LLM response text
        product_names: List of known product names

    Returns:
        List of ValidationIssue for unknown products
    """
    issues = []

    if not product_names:
        return issues

    # Normalize product names for matching
    normalized_products = {name.lower(): name for name in product_names}

    # Look for product mention patterns
    # "el curso X", "el programa X", "mi servicio X", etc.
    product_patterns = [
        r"(?:el|mi|nuestro)\s+(?:curso|programa|servicio|pack|producto)\s+[\"']?([A-Za-záéíóúñÁÉÍÓÚÑ\s]+)[\"']?",
        r"[\"']([A-Za-záéíóúñÁÉÍÓÚÑ\s]{3,30})[\"']\s+(?:cuesta|vale|tiene un precio)",
    ]

    for pattern in product_patterns:
        matches = re.findall(pattern, response, re.IGNORECASE)
        for match in matches:
            match_clean = match.strip().lower()

            # Check if this matches any known product
            is_known = any(
                match_clean in prod or prod in match_clean
                for prod in normalized_products.keys()
            )

            if not is_known and len(match_clean) > 3:
                # Only flag if it looks like a specific product name
                # Avoid flagging generic words
                generic_words = {"curso", "programa", "servicio", "producto", "pack", "el", "un", "una"}
                words = set(match_clean.split())
                if not words.issubset(generic_words):
                    issues.append(
                        ValidationIssue(
                            type="unknown_product",
                            severity="warning",
                            details=f"Product '{match}' not found in known products",
                            auto_fix=None,
                        )
                    )

    return issues


# =============================================================================
# ACTION VERIFICATION
# =============================================================================


def verify_action_completed(
    response: str,
    detected_context: DetectedContext,
    creator_data: CreatorData,
) -> Tuple[List[ValidationIssue], str]:
    """
    Verify that required actions were completed (links included).

    If intent requires a link but it's missing, auto-add it.

    Args:
        response: LLM response text
        detected_context: Detected context with intent
        creator_data: Creator data with links

    Returns:
        Tuple of (issues, corrected_response)
    """
    issues = []
    corrected = response

    # Check if response already has URLs
    existing_urls = extract_urls_from_text(response)
    has_url = len(existing_urls) > 0

    intent = detected_context.intent
    interest = detected_context.interest_level

    # BOOKING: If user wants to book and no booking link
    if intent == Intent.INTEREST_STRONG or "reserv" in response.lower() or "agend" in response.lower():
        if not has_url and creator_data.booking_links:
            # Find best booking link
            booking = creator_data.booking_links[0]
            if booking.url:
                issues.append(
                    ValidationIssue(
                        type="missing_link",
                        severity="warning",
                        details="Booking context detected but no booking link provided",
                        auto_fix=f"Added booking link: {booking.url}",
                    )
                )
                # Add booking link to response
                corrected = _append_link_to_response(corrected, booking.url, "reservar")
                has_url = True

    # PAYMENT: If user wants to buy and no payment link
    if (
        intent == Intent.INTEREST_STRONG
        and interest == "strong"
        and not has_url
    ):
        # Find featured product payment link
        featured = creator_data.get_featured_product()
        if featured and featured.payment_link:
            issues.append(
                ValidationIssue(
                    type="missing_link",
                    severity="warning",
                    details="Strong purchase intent but no payment link provided",
                    auto_fix=f"Added payment link: {featured.payment_link}",
                )
            )
            corrected = _append_link_to_response(corrected, featured.payment_link, "comprar")
            has_url = True

    # LEAD MAGNET: If user asks for free content and no lead magnet link
    free_keywords = ["gratis", "free", "gratuito", "probar", "prueba"]
    mentions_free = any(kw in response.lower() for kw in free_keywords)

    if mentions_free and not has_url and creator_data.lead_magnets:
        magnet = creator_data.lead_magnets[0]
        if magnet.payment_link:
            issues.append(
                ValidationIssue(
                    type="missing_link",
                    severity="warning",
                    details="Free content mentioned but no lead magnet link provided",
                    auto_fix=f"Added lead magnet link: {magnet.payment_link}",
                )
            )
            corrected = _append_link_to_response(corrected, magnet.payment_link, "acceder gratis")
            has_url = True

    return issues, corrected


def _append_link_to_response(response: str, url: str, action: str) -> str:
    """Append a link to the response naturally."""
    response = response.rstrip()

    # Remove trailing emoji if present, we'll add our own
    if response and response[-1] in "😊🙌👍💪🚀✨🔥":
        response = response[:-1].rstrip()

    # Ensure ends with punctuation
    if response and response[-1] not in ".!?":
        response += "."

    # Add the link
    response += f"\n\nAquí puedes {action}: {url} 👍"

    return response


# =============================================================================
# SMART TRUNCATE
# =============================================================================


def smart_truncate(
    response: str,
    max_chars: int = 400,
) -> Tuple[str, bool]:
    """
    Intelligently truncate response while preserving important content.

    Rules:
    - Never truncate if contains URLs (http)
    - Never truncate if contains prices (€)
    - Never truncate if contains key action words
    - If truncating, cut at sentence boundary
    - Max 400 characters (not 2 sentences)

    Args:
        response: Response to potentially truncate
        max_chars: Maximum characters (default 400)

    Returns:
        Tuple of (truncated_response, was_truncated)
    """
    if not response:
        return response, False

    response = response.strip()

    # If already short enough, return as-is
    if len(response) <= max_chars:
        return response, False

    # Check for content that should NOT be truncated
    protected_patterns = [
        r"https?://",  # URLs
        r"\d+\s*€",  # Prices
        r"€\s*\d+",
        r"\d+\s*euros?",
        r"\breserva\b",  # Action words
        r"\bpago\b",
        r"\blink\b",
        r"\benlace\b",
        r"\bcompra\b",
        r"\bbizum\b",
        r"\biban\b",
        r"\btransferencia\b",
    ]

    for pattern in protected_patterns:
        if re.search(pattern, response, re.IGNORECASE):
            logger.debug(f"Not truncating - protected content: {pattern}")
            return response, False

    # Safe to truncate - cut at sentence boundary
    # Split by sentence endings
    sentences = re.split(r"(?<=[.!?])\s+", response)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return response[:max_chars], True

    # Build truncated response sentence by sentence
    truncated = ""
    for sentence in sentences:
        if len(truncated) + len(sentence) + 1 <= max_chars:
            truncated = (truncated + " " + sentence).strip() if truncated else sentence
        else:
            break

    if not truncated:
        # First sentence alone is too long - take it anyway
        truncated = sentences[0]

    # Ensure ends with punctuation
    if truncated and truncated[-1] not in ".!?":
        truncated += "."

    was_truncated = len(truncated) < len(response)

    if was_truncated:
        logger.info(
            f"Truncated response from {len(response)} to {len(truncated)} chars"
        )

    return truncated, was_truncated


# =============================================================================
# MAIN VALIDATION FUNCTION
# =============================================================================


def validate_response(
    response: str,
    creator_data: CreatorData,
    detected_context: Optional[DetectedContext] = None,
    auto_correct: bool = True,
    max_chars: int = 400,
) -> ValidationResult:
    """
    Validate LLM response and optionally auto-correct issues.

    This is the main entry point for response validation.

    Steps:
    1. Validate prices against known prices
    2. Validate links against known links
    3. Validate products against known products
    4. Verify required actions completed (links added)
    5. Apply smart truncate

    Args:
        response: LLM response to validate
        creator_data: Creator data with known prices, links, products
        detected_context: Optional detected context for intent-aware validation
        auto_correct: Whether to auto-correct issues when possible
        max_chars: Max characters for truncation

    Returns:
        ValidationResult with is_valid, issues, corrected_response
    """
    result = ValidationResult(
        is_valid=True,
        original_response=response,
        corrected_response=response,
    )

    if not response:
        return result

    corrected = response

    # 1. Validate prices
    known_prices = creator_data.get_known_prices()
    price_issues = validate_prices(corrected, known_prices)
    result.issues.extend(price_issues)

    # Price hallucination is severe - should escalate
    if price_issues:
        result.is_valid = False
        result.should_escalate = True
        logger.warning("Price hallucination detected - should escalate")

    # 2. Validate links
    known_links = creator_data.get_known_links()
    link_issues, link_corrected = validate_links(corrected, known_links)
    result.issues.extend(link_issues)

    if link_issues:
        result.is_valid = False
        if auto_correct:
            # Apply link corrections (removed hallucinated links)
            corrected = link_corrected

    # 3. Validate products
    product_names = [p.name for p in creator_data.products]
    product_names.extend([p.name for p in creator_data.lead_magnets])
    product_issues = validate_products(corrected, product_names)
    result.issues.extend(product_issues)
    # Product issues are warnings, don't fail validation

    # 4. Verify actions completed (add missing links)
    if detected_context and auto_correct:
        action_issues, corrected = verify_action_completed(
            corrected, detected_context, creator_data
        )
        result.issues.extend(action_issues)

    # 5. Smart truncate
    if auto_correct:
        corrected, was_truncated = smart_truncate(corrected, max_chars)
        result.was_truncated = was_truncated

    result.corrected_response = corrected

    # Log summary
    error_count = sum(1 for i in result.issues if i.severity == "error")
    warning_count = sum(1 for i in result.issues if i.severity == "warning")

    if error_count > 0:
        logger.warning(
            f"Validation failed: {error_count} errors, {warning_count} warnings"
        )
    elif warning_count > 0:
        logger.info(f"Validation passed with {warning_count} warnings")
    else:
        logger.debug("Validation passed - no issues")

    return result


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def get_safe_response(
    response: str,
    creator_data: CreatorData,
    detected_context: Optional[DetectedContext] = None,
    fallback_response: Optional[str] = None,
) -> str:
    """
    Get a safe response, using fallback if validation fails severely.

    Args:
        response: LLM response
        creator_data: Creator data for validation
        detected_context: Optional context
        fallback_response: Optional custom fallback

    Returns:
        Safe response string
    """
    result = validate_response(
        response=response,
        creator_data=creator_data,
        detected_context=detected_context,
        auto_correct=True,
    )

    if result.should_escalate:
        # Severe hallucination - use fallback
        if fallback_response:
            return fallback_response

        creator_name = creator_data.profile.name or "el creador"
        return (
            "Déjame verificar esa información y te respondo correctamente. "
            f"Si prefieres, puedo pasarte con {creator_name} directamente 🙌"
        )

    return result.corrected_response


def quick_validate(response: str, creator_data: CreatorData) -> bool:
    """
    Quick validation check - returns True if response is safe.

    Args:
        response: LLM response
        creator_data: Creator data

    Returns:
        True if response passes validation
    """
    result = validate_response(
        response=response,
        creator_data=creator_data,
        auto_correct=False,
    )
    return result.is_valid
