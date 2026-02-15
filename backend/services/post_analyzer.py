"""Post Analyzer - LLM-powered analysis of Instagram posts.

Analyzes creator's recent posts to extract:
- Active promotions/launches
- Recent topics discussed
- Availability hints
- Context instructions for the bot

Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Default result when no analysis is possible
DEFAULT_RESULT = {
    "active_promotion": None,
    "promotion_deadline": None,
    "promotion_urgency": None,
    "recent_topics": [],
    "recent_products": [],
    "availability_hint": None,
    "context_instructions": "Sin contexto especial de posts recientes.",
}


class PostAnalyzer:
    """Analyzes posts with LLM to extract context."""

    ANALYSIS_PROMPT_TEMPLATE = """Analiza estos posts recientes de un creador de contenido de Instagram.

POSTS RECIENTES:
{posts}

Extrae la siguiente información:
1. ¿Hay alguna promoción o lanzamiento activo? (producto, descuento, deadline)
2. ¿Cuáles son los temas principales mencionados?
3. ¿Hay alguna indicación de disponibilidad? (viaje, ocupado, retiro, etc)
4. ¿Qué productos o servicios se mencionan?

IMPORTANTE: Responde SOLO con un JSON válido, sin texto adicional.

Formato de respuesta JSON:
{{
    "active_promotion": "descripción de la promoción activa o null si no hay",
    "promotion_deadline": "deadline de la promoción o null",
    "promotion_urgency": "baja/media/alta o null",
    "recent_topics": ["tema1", "tema2", "tema3"],
    "recent_products": ["producto1", "producto2"],
    "availability_hint": "indicación de disponibilidad o null",
    "context_instructions": "instrucciones claras para el bot sobre cómo usar este contexto"
}}"""

    def __init__(self):
        """Initialize the analyzer."""

    async def analyze_posts(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze posts with LLM and extract context.

        Args:
            posts: List of post dicts with caption, timestamp

        Returns:
            Dict with analysis results
        """
        # Handle empty posts
        if not posts:
            return {
                **DEFAULT_RESULT,
                "context_instructions": "Sin posts recientes para analizar.",
            }

        try:
            # Format posts for prompt
            posts_text = self._format_posts_for_prompt(posts)

            # Build prompt
            prompt = self._build_analysis_prompt(posts_text)

            # Call LLM
            response = await self._call_llm(prompt)

            # Parse response
            result = self._parse_llm_response(response)

            logger.info(f"Analyzed {len(posts)} posts successfully")
            return result

        except Exception as e:
            logger.error(f"Error analyzing posts: {e}")
            return {
                **DEFAULT_RESULT,
                "context_instructions": f"Error al analizar posts: {str(e)[:100]}",
            }

    def _format_posts_for_prompt(self, posts: List[Dict[str, Any]]) -> str:
        """Format posts list into text for LLM prompt.

        Args:
            posts: List of post dicts

        Returns:
            Formatted string with posts
        """
        formatted_parts = []

        for i, post in enumerate(posts, 1):
            timestamp = post.get("timestamp", "fecha desconocida")
            caption = post.get("caption", "(sin texto)")
            media_type = post.get("media_type", "POST")

            formatted_parts.append(
                f"---\n[Post {i} - {timestamp} - {media_type}]\n{caption}\n"
            )

        return "\n".join(formatted_parts)

    def _build_analysis_prompt(self, posts_text: str) -> str:
        """Build the analysis prompt.

        Args:
            posts_text: Formatted posts text

        Returns:
            Complete prompt for LLM
        """
        return self.ANALYSIS_PROMPT_TEMPLATE.format(posts=posts_text)

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM to analyze posts.

        Args:
            prompt: Analysis prompt

        Returns:
            LLM response string
        """
        try:
            from core.llm import get_llm_client

            llm = get_llm_client()

            messages = [
                {
                    "role": "system",
                    "content": "Eres un asistente que analiza posts de Instagram. Responde SOLO con JSON válido.",
                },
                {"role": "user", "content": prompt},
            ]

            response = await llm.chat(messages, max_tokens=500)
            return response

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response JSON.

        Args:
            response: Raw LLM response

        Returns:
            Parsed dict with analysis results
        """
        try:
            # Try to extract JSON from response
            # Sometimes LLM adds extra text before/after JSON
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start == -1 or json_end == 0:
                logger.warning("No JSON found in LLM response")
                return {
                    **DEFAULT_RESULT,
                    "context_instructions": "No se pudo extraer contexto de los posts.",
                }

            json_str = response[json_start:json_end]
            result = json.loads(json_str)

            # Ensure all expected fields exist
            return {
                "active_promotion": result.get("active_promotion"),
                "promotion_deadline": result.get("promotion_deadline"),
                "promotion_urgency": result.get("promotion_urgency"),
                "recent_topics": result.get("recent_topics", []),
                "recent_products": result.get("recent_products", []),
                "availability_hint": result.get("availability_hint"),
                "context_instructions": result.get(
                    "context_instructions", "Contexto extraído de posts recientes."
                ),
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return {
                **DEFAULT_RESULT,
                "context_instructions": "Error al parsear respuesta del análisis.",
            }


# Module-level function for convenience
async def analyze_creator_posts(posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convenience function to analyze posts.

    Args:
        posts: List of post dicts

    Returns:
        Analysis result dict
    """
    analyzer = PostAnalyzer()
    return await analyzer.analyze_posts(posts)
