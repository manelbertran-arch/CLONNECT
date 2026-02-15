"""
Response Variation Engine v1.8.0
Evita repeticiones manteniendo naturalidad.

Estrategias:
1. Sinónimos de conectores: "Además" → "También" → "Por otro lado"
2. Variación de saludos: "Hola!" → "Hey!" → "Qué tal!"
3. CTAs alternativos: "Te paso el link" → "Aquí tienes" → "Mira esto"
4. Estructura de precio: "cuesta X€" → "son X€" → "X€ con todo incluido"
"""

import logging
import re
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class VariationEngine:
    """
    Varía respuestas para evitar repetición.

    Trackea qué variantes se han usado por conversación
    y selecciona la menos usada para mantener frescura.
    """

    # ==========================================================================
    # MAPAS DE VARIACIÓN
    # ==========================================================================

    # Conectores y sus variantes (case-insensitive matching)
    CONNECTOR_VARIANTS = {
        "además": ["también", "por otro lado", "y además", "aparte de eso"],
        "también": ["además", "igualmente", "asimismo", "de igual forma"],
        "pero": ["aunque", "sin embargo", "eso sí", "no obstante"],
        "porque": ["ya que", "dado que", "es que", "puesto que"],
        "entonces": ["así que", "por lo tanto", "en ese caso", "pues"],
        "por eso": ["por esa razón", "debido a eso", "por lo cual"],
    }

    # Saludos al inicio de mensaje
    GREETING_VARIANTS = [
        "¡Hola!",
        "¡Hey!",
        "¡Qué tal!",
        "¡Buenas!",
        "¡Hola hola!",
        "¡Ey!",
    ]

    # Patrones de saludo para detectar
    GREETING_PATTERNS = [
        r'^¡?[Hh]ola!?\s*',
        r'^¡?[Hh]ey!?\s*',
        r'^¡?[Qq]ué tal!?\s*',
        r'^¡?[Bb]uenas!?\s*',
        r'^¡?[Ee]y!?\s*',
    ]

    # Variantes de formato de precio
    PRICE_FORMATS = [
        "{price}€",
        "son {price}€",
        "{price} euros",
        "{price}€ con todo incluido",
        "solo {price}€",
        "{price} euritos",
    ]

    # CTAs y sus variantes
    CTA_VARIANTS = {
        "te paso el link": ["aquí lo tienes", "te lo dejo aquí", "mira esto", "este es el enlace"],
        "aquí tienes": ["te lo paso", "míralo aquí", "échale un ojo", "aquí está"],
        "si quieres": ["cuando quieras", "si te interesa", "si te apetece"],
        "no dudes en": ["siéntete libre de", "puedes", "anímate a"],
        "escríbeme": ["cuéntame", "dime", "háblame", "avísame"],
    }

    # Frases de cierre
    CLOSING_VARIANTS = [
        "¿Alguna duda?",
        "¿Qué te parece?",
        "¿Te cuento más?",
        "¿Tienes alguna pregunta?",
        "¡Cuéntame!",
        "¿Qué opinas?",
    ]

    def __init__(self):
        # Track usage per conversation: {conv_id: {category: {variant: count}}}
        self._usage_history: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(int))
        )
        # Compile greeting patterns
        self._greeting_compiled = [re.compile(p, re.IGNORECASE) for p in self.GREETING_PATTERNS]

    def vary_response(self, response: str, conversation_id: str) -> str:
        """
        Aplica variaciones a la respuesta para evitar repetición.

        Args:
            response: Respuesta original del LLM
            conversation_id: ID único de la conversación (creator:follower)

        Returns:
            Respuesta con variaciones aplicadas
        """
        if not response:
            return response

        original = response

        # 1. Variar saludos
        response = self._vary_greeting(response, conversation_id)

        # 2. Variar conectores
        response = self._vary_connectors(response, conversation_id)

        # 3. Variar formato de precio
        response = self._vary_price_format(response, conversation_id)

        # 4. Variar CTAs
        response = self._vary_ctas(response, conversation_id)

        # 5. Variar cierres
        response = self._vary_closing(response, conversation_id)

        if response != original:
            logger.info("[VARIATION] Applied variations to response")
            logger.debug(f"[VARIATION] Original: {original[:100]}...")
            logger.debug(f"[VARIATION] Varied: {response[:100]}...")

        return response

    def _vary_greeting(self, response: str, conv_id: str) -> str:
        """Varía el saludo inicial si existe."""
        for pattern in self._greeting_compiled:
            match = pattern.match(response)
            if match:
                # Found a greeting at the start
                _current_greeting = match.group(0).strip()
                new_greeting = self._get_least_used_variant(
                    self.GREETING_VARIANTS, conv_id, "greeting"
                )
                # Replace and track
                response = pattern.sub(new_greeting + " ", response, count=1)
                self._track_usage(conv_id, "greeting", new_greeting)
                break

        return response

    def _vary_connectors(self, response: str, conv_id: str) -> str:
        """Varía conectores en el texto."""
        for connector, variants in self.CONNECTOR_VARIANTS.items():
            # Case-insensitive search for connector as whole word
            pattern = re.compile(rf'\b{re.escape(connector)}\b', re.IGNORECASE)

            if pattern.search(response):
                # Get least used variant (including original)
                all_variants = [connector] + variants
                new_connector = self._get_least_used_variant(
                    all_variants, conv_id, f"connector_{connector}"
                )

                # Only replace if different
                if new_connector.lower() != connector.lower():
                    # Preserve case of first letter
                    def replace_preserving_case(match):
                        original = match.group(0)
                        if original[0].isupper():
                            return new_connector.capitalize()
                        return new_connector.lower()

                    response = pattern.sub(replace_preserving_case, response, count=1)

                self._track_usage(conv_id, f"connector_{connector}", new_connector)

        return response

    def _vary_price_format(self, response: str, conv_id: str) -> str:
        """Varía el formato de presentación de precios."""
        # Pattern to find prices like "297€", "cuesta 297€", "son 297 euros"
        price_pattern = re.compile(
            r'(?:cuesta\s+|son\s+|solo\s+)?(\d+(?:[.,]\d{2})?)\s*(?:€|euros?|euritos)',
            re.IGNORECASE
        )

        match = price_pattern.search(response)
        if match:
            price = match.group(1)
            full_match = match.group(0)

            # Get least used price format
            format_template = self._get_least_used_variant(
                self.PRICE_FORMATS, conv_id, "price_format"
            )

            new_price_str = format_template.format(price=price)

            # Replace only if format is different
            if new_price_str.lower() != full_match.lower():
                response = response[:match.start()] + new_price_str + response[match.end():]

            self._track_usage(conv_id, "price_format", format_template)

        return response

    def _vary_ctas(self, response: str, conv_id: str) -> str:
        """Varía llamadas a la acción."""
        response_lower = response.lower()

        for cta, variants in self.CTA_VARIANTS.items():
            if cta in response_lower:
                all_variants = [cta] + variants
                new_cta = self._get_least_used_variant(
                    all_variants, conv_id, f"cta_{cta}"
                )

                if new_cta.lower() != cta:
                    # Case-insensitive replace, preserving sentence case
                    pattern = re.compile(re.escape(cta), re.IGNORECASE)

                    def replace_preserving_case(match):
                        original = match.group(0)
                        if original[0].isupper():
                            return new_cta.capitalize()
                        return new_cta.lower()

                    response = pattern.sub(replace_preserving_case, response, count=1)

                self._track_usage(conv_id, f"cta_{cta}", new_cta)
                break  # Only vary one CTA per response

        return response

    def _vary_closing(self, response: str, conv_id: str) -> str:
        """Varía frases de cierre si termina con una pregunta común."""
        for closing in self.CLOSING_VARIANTS:
            if response.rstrip().endswith(closing) or response.rstrip().endswith(closing.rstrip('?')):
                new_closing = self._get_least_used_variant(
                    self.CLOSING_VARIANTS, conv_id, "closing"
                )

                if new_closing != closing:
                    # Replace at the end
                    pattern = re.compile(re.escape(closing) + r'\s*$', re.IGNORECASE)
                    if pattern.search(response):
                        response = pattern.sub(new_closing, response)

                self._track_usage(conv_id, "closing", new_closing)
                break

        return response

    def _get_least_used_variant(self, variants: List[str], conv_id: str, category: str) -> str:
        """
        Retorna la variante menos usada en esta conversación.

        Args:
            variants: Lista de variantes posibles
            conv_id: ID de conversación
            category: Categoría de variación (greeting, connector, etc.)

        Returns:
            La variante con menor uso
        """
        if not variants:
            return ""

        usage = self._usage_history[conv_id][category]

        # Find variant with minimum usage
        min_usage = float('inf')
        least_used = variants[0]

        for variant in variants:
            variant_usage = usage.get(variant.lower(), 0)
            if variant_usage < min_usage:
                min_usage = variant_usage
                least_used = variant

        return least_used

    def _track_usage(self, conv_id: str, category: str, variant: str) -> None:
        """
        Registra uso de una variante.

        Args:
            conv_id: ID de conversación
            category: Categoría de variación
            variant: Variante usada
        """
        self._usage_history[conv_id][category][variant.lower()] += 1

        # Limit history size per conversation (prevent memory bloat)
        if len(self._usage_history) > 10000:
            # Remove oldest conversations (simple FIFO)
            oldest = list(self._usage_history.keys())[:1000]
            for key in oldest:
                del self._usage_history[key]

    def get_usage_stats(self, conv_id: str) -> Dict[str, Dict[str, int]]:
        """Get usage statistics for a conversation (for debugging)."""
        return dict(self._usage_history.get(conv_id, {}))

    def clear_conversation(self, conv_id: str) -> None:
        """Clear history for a conversation."""
        if conv_id in self._usage_history:
            del self._usage_history[conv_id]


# =============================================================================
# SINGLETON
# =============================================================================

_variation_engine: Optional[VariationEngine] = None


def get_variation_engine() -> VariationEngine:
    """Get singleton VariationEngine instance."""
    global _variation_engine
    if _variation_engine is None:
        _variation_engine = VariationEngine()
    return _variation_engine
