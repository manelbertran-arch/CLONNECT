"""
Output Validator — validates LLM responses before sending.

Prevents unauthorized/fabricated URLs from reaching the user.
This is the last line of defense against link hallucinations.

Only validate_links() is used in the production DM pipeline
(core/dm/phases/postprocessing.py). All other validation functions
were removed in the dead code cleanup — they were defined but never
called from the pipeline.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """A single validation issue found in a response."""

    type: str  # hallucinated_link, etc.
    severity: str  # error, warning
    details: str
    auto_fix: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "details": self.details,
            "auto_fix": self.auto_fix,
        }


def extract_urls_from_text(text: str) -> List[str]:
    """Extract URLs from text."""
    if not text:
        return []

    pattern = r"https?://[^\s<>\"')\]]+(?:\([^\s]*\))?[^\s<>\"')\]]?"
    urls = re.findall(pattern, text)

    cleaned = []
    for url in urls:
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

    Removes hallucinated/unauthorized URLs and replaces them with
    "[enlace removido]". Authorized = in known_links OR in allowed domains.

    Args:
        response: LLM response text
        known_links: List of known links from creator products/booking
        allowed_domains: Additional allowed domains beyond defaults

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
            match = re.search(r"https?://([^/]+)", link)
            if match:
                domain = match.group(1).lower()
                domains.add(domain)
                parts = domain.split(".")
                if len(parts) >= 2:
                    domains.add(".".join(parts[-2:]))
        except Exception as e:
            logger.warning("Suppressed error parsing known link domain: %s", e)

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
