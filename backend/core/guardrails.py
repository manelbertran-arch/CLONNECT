"""
Response Guardrails for Clonnect Creators.

Validates LLM responses before sending to users to prevent:
- Invented prices
- Unauthorized URLs
- Fabricated product information
- Off-brand responses

Enable/disable via ENABLE_GUARDRAILS environment variable.
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("clonnect-guardrails")


class ResponseGuardrail:
    """
    Guardrail simplificado para validar respuestas antes de enviar.
    Verifica consistencia con productos y configuración del creador.
    """

    def __init__(self):
        self.enabled = os.getenv("ENABLE_GUARDRAILS", "true").lower() == "true"
        logger.info(f"Guardrails {'enabled' if self.enabled else 'disabled'}")

    def validate_response(
        self,
        query: str,
        response: str,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Valida que la respuesta no contenga información inventada.

        Args:
            query: User's original message
            response: LLM-generated response
            context: Dict with products, allowed_urls, creator_config

        Returns:
            {"valid": bool, "reason": str, "issues": list, "corrected_response": str | None}
        """
        if not self.enabled:
            return {
                "valid": True,
                "reason": "guardrails_disabled",
                "issues": [],
                "corrected_response": None
            }

        context = context or {}
        issues = []

        # 1. Validate prices match known products
        price_issues = self._check_prices(response, context.get("products", []))
        issues.extend(price_issues)

        # 2. Validate URLs are authorized
        url_issues = self._check_urls(response, context.get("allowed_urls", []))
        issues.extend(url_issues)

        # 3. Check for common hallucination patterns
        hallucination_issues = self._check_hallucinations(response, context)
        issues.extend(hallucination_issues)

        # 4. Check response length isn't excessive
        if len(response) > 2000:
            issues.append("Response too long (>2000 chars)")

        if issues:
            logger.warning(f"Guardrail activated: {issues}")
            return {
                "valid": False,
                "reason": "; ".join(issues),
                "issues": issues,
                "corrected_response": None
            }

        return {
            "valid": True,
            "reason": "ok",
            "issues": [],
            "corrected_response": None
        }

    def _check_prices(self, response: str, products: List[Dict]) -> List[str]:
        """Check that prices in response match known products"""
        issues = []

        if not products:
            return issues

        # Extract known prices
        known_prices = set()
        for p in products:
            price = p.get("price")
            if price:
                # Add various formats
                known_prices.add(str(int(price)))
                known_prices.add(f"{price:.2f}".replace(".", ","))
                known_prices.add(f"{price:.2f}")
                known_prices.add(str(price))

        # Find prices in response (€, $, EUR patterns)
        price_patterns = [
            r'(\d+(?:[.,]\d{1,2})?)\s*€',
            r'€\s*(\d+(?:[.,]\d{1,2})?)',
            r'(\d+(?:[.,]\d{1,2})?)\s*euros?',
            r'(\d+(?:[.,]\d{1,2})?)\s*EUR',
            r'\$\s*(\d+(?:[.,]\d{1,2})?)',
            r'(\d+(?:[.,]\d{1,2})?)\s*USD',
        ]

        found_prices = set()
        for pattern in price_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            found_prices.update(matches)

        # Check if found prices are in known prices
        for price in found_prices:
            normalized = price.replace(",", ".")
            # Remove trailing zeros for comparison
            try:
                float_price = float(normalized)
                str_variants = [
                    str(int(float_price)),
                    f"{float_price:.2f}",
                    f"{float_price:.2f}".replace(".", ",")
                ]
                if not any(v in known_prices for v in str_variants):
                    issues.append(f"Unknown price mentioned: {price}")
            except ValueError:
                pass

        return issues

    def _check_urls(self, response: str, allowed_urls: List[str]) -> List[str]:
        """Check that URLs in response are authorized"""
        issues = []

        # Find URLs in response
        url_pattern = r'https?://[^\s<>"\')\]]+(?:\([^\s]*\))?[^\s<>"\')\]]?'
        found_urls = re.findall(url_pattern, response)

        if not found_urls:
            return issues

        # Default allowed domains if none specified
        default_allowed = [
            "stripe.com",
            "hotmart.com",
            "gumroad.com",
            "calendly.com",
            "cal.com",
            "instagram.com",
            "wa.me",
            "t.me",
            "youtube.com",
            "youtu.be",
        ]

        allowed = allowed_urls if allowed_urls else default_allowed

        for url in found_urls:
            # Check if URL contains any allowed domain
            is_allowed = any(domain in url.lower() for domain in allowed)
            if not is_allowed:
                issues.append(f"Unauthorized URL: {url[:50]}...")

        return issues

    def _check_hallucinations(self, response: str, context: Dict[str, Any]) -> List[str]:
        """Check for common hallucination patterns"""
        issues = []

        # Patterns that indicate potential hallucination
        hallucination_patterns = [
            (r'te?\s+llamo\s+en\s+\d+', "Promise to call back"),
            (r'te?\s+env[íi]o?\s+(un\s+)?email', "Promise to send email"),
            (r'nuestra?\s+direcci[oó]n\s+(f[íi]sica|postal)', "Physical address mentioned"),
            (r'horario\s+de\s+atenci[oó]n.*\d{1,2}:\d{2}', "Specific business hours"),
            (r'garant[íi]a\s+de\s+(\d+\s+(d[íi]as|meses|a[ñn]os))', "Specific guarantee period"),
        ]

        for pattern, description in hallucination_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                # Only flag if not in context
                creator_config = context.get("creator_config", {})
                if description not in str(creator_config):
                    issues.append(f"Potential hallucination: {description}")

        return issues

    def get_safe_response(
        self,
        query: str,
        response: str,
        context: Dict[str, Any] = None
    ) -> str:
        """
        Returns the original response if valid, or a fallback if issues found.

        Args:
            query: User's message
            response: LLM response
            context: Validation context

        Returns:
            Safe response string
        """
        validation = self.validate_response(query, response, context)

        if validation["valid"]:
            return response

        if validation.get("corrected_response"):
            return validation["corrected_response"]

        # Use fallback for serious issues
        logger.warning(f"Using fallback response due to: {validation['reason']}")
        return self._get_fallback_response(context)

    def _get_fallback_response(self, context: Dict[str, Any] = None) -> str:
        """Get a safe fallback response"""
        context = context or {}
        language = context.get("language", "es")

        fallbacks = {
            "es": [
                "¡Gracias por tu mensaje! Dame un momento para verificar esa información y te respondo correctamente. 🙌",
                "¡Hola! Déjame confirmar algunos detalles y te escribo enseguida. 😊",
                "Recibido! En un momento te cuento más sobre eso. 👍",
            ],
            "en": [
                "Thanks for your message! Let me verify that information and I'll get back to you. 🙌",
                "Hi! Let me check some details and I'll write back shortly. 😊",
                "Got it! I'll tell you more about that in a moment. 👍",
            ],
            "ca": [
                "Gràcies pel teu missatge! Deixa'm verificar aquesta informació i et responc correctament. 🙌",
                "Hola! Deixa'm confirmar alguns detalls i t'escric de seguida. 😊",
            ]
        }

        import random
        options = fallbacks.get(language, fallbacks["es"])
        return random.choice(options)


# Global instance
_guardrail: Optional[ResponseGuardrail] = None


def get_response_guardrail() -> ResponseGuardrail:
    """Get or create guardrail singleton"""
    global _guardrail
    if _guardrail is None:
        _guardrail = ResponseGuardrail()
    return _guardrail
