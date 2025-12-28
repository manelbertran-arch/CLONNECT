"""
Reflexion Module for Clonnect

Iteratively improves responses by self-critique and refinement.
Used for personalizing generic messages (like nurturing templates).

Based on: "Reflexion: Language Agents with Verbal Reinforcement Learning"
(Shinn et al., 2023)
"""

import logging
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ReflexionResult:
    """Result of Reflexion improvement"""
    final_answer: str
    original_response: str
    improvements_made: List[str]
    iterations: int
    quality_score: float  # 0.0 - 1.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ReflexionImprover:
    """
    Improves responses through self-critique and refinement.

    How it works:
    1. Take original response
    2. Critique it against target quality
    3. Generate improved version
    4. Optionally iterate for further improvement
    """

    def __init__(self, llm_client, max_iterations: int = 2):
        self.llm = llm_client
        self.max_iterations = max_iterations

    def _get_critique_prompt(
        self,
        response: str,
        target_quality: str,
        context: Dict[str, Any]
    ) -> str:
        """Generate prompt for critiquing the response"""
        follower_name = context.get("follower_name", "")
        follower_interests = context.get("interests", [])
        products_discussed = context.get("products_discussed", [])
        language = context.get("language", "es")

        prompt = f"""Analiza este mensaje y sugiere mejoras.

MENSAJE ACTUAL:
{response}

OBJETIVO DE CALIDAD: {target_quality}

CONTEXTO DEL USUARIO:
- Nombre: {follower_name if follower_name else "No conocido"}
- Intereses: {", ".join(follower_interests) if follower_interests else "No especificados"}
- Productos discutidos: {", ".join(products_discussed) if products_discussed else "Ninguno"}
- Idioma preferido: {language}

CRITERIOS DE EVALUACIÓN:
1. ¿Es personalizado? (usa el nombre si lo conoce, referencia intereses)
2. ¿Es empático? (muestra comprensión, no es robótico)
3. ¿Es natural? (suena como una persona real, no un bot)
4. ¿Es apropiado? (longitud adecuada, tono correcto)
5. ¿Es efectivo? (cumple su objetivo sin ser agresivo)

FORMATO DE RESPUESTA:
[CRITICA]
- Punto 1: ...
- Punto 2: ...
[/CRITICA]

[PUNTUACION]
X/10
[/PUNTUACION]

[MEJORAS_SUGERIDAS]
- Mejora 1: ...
- Mejora 2: ...
[/MEJORAS_SUGERIDAS]
"""
        return prompt

    def _get_improvement_prompt(
        self,
        original: str,
        critique: str,
        improvements: List[str],
        context: Dict[str, Any]
    ) -> str:
        """Generate prompt for improving the response"""
        follower_name = context.get("follower_name", "")
        language = context.get("language", "es")

        prompt = f"""Mejora este mensaje basándote en la crítica.

MENSAJE ORIGINAL:
{original}

CRÍTICA RECIBIDA:
{critique}

MEJORAS A APLICAR:
{chr(10).join(f"- {m}" for m in improvements)}

CONTEXTO:
- Nombre del usuario: {follower_name if follower_name else "No usar nombre"}
- Idioma: {language}

INSTRUCCIONES:
1. Aplica las mejoras sugeridas
2. Mantén el mensaje conciso (2-3 frases máximo)
3. Hazlo sonar natural y personal
4. NO uses frases genéricas como "espero que estés bien"
5. SÉ específico y directo

Escribe SOLO el mensaje mejorado, sin explicaciones:
"""
        return prompt

    def _parse_critique(self, raw_critique: str) -> tuple:
        """
        Parse critique response.

        Returns:
            (critique_text, score, improvements)
        """
        critique_text = raw_critique
        score = 5.0
        improvements = []

        # Extract critique
        critique_match = re.search(
            r'\[CRITICA\](.*?)\[/CRITICA\]',
            raw_critique,
            re.DOTALL | re.IGNORECASE
        )
        if critique_match:
            critique_text = critique_match.group(1).strip()

        # Extract score
        score_match = re.search(
            r'\[PUNTUACION\]\s*(\d+(?:\.\d+)?)\s*/\s*10',
            raw_critique,
            re.IGNORECASE
        )
        if score_match:
            score = float(score_match.group(1))

        # Extract improvements
        improvements_match = re.search(
            r'\[MEJORAS_SUGERIDAS\](.*?)\[/MEJORAS_SUGERIDAS\]',
            raw_critique,
            re.DOTALL | re.IGNORECASE
        )
        if improvements_match:
            improvements_text = improvements_match.group(1)
            improvements = re.findall(r'[-•]\s*(.+?)(?=[-•]|$)', improvements_text, re.DOTALL)
            improvements = [i.strip() for i in improvements if i.strip()]

        return critique_text, score / 10.0, improvements

    async def improve_response(
        self,
        response: str,
        target_quality: str = "personalizado y empático",
        context: Dict[str, Any] = None,
        min_quality: float = 0.7
    ) -> ReflexionResult:
        """
        Improve a response through iterative self-critique.

        Args:
            response: Original response to improve
            target_quality: Description of desired quality
            context: User context (name, interests, etc.)
            min_quality: Minimum quality score to accept (0.0-1.0)

        Returns:
            ReflexionResult with improved response
        """
        context = context or {}
        current_response = response
        all_improvements = []
        iterations = 0
        quality_score = 0.0

        logger.info(f"Starting Reflexion improvement for response of {len(response)} chars")

        for iteration in range(self.max_iterations):
            iterations = iteration + 1

            try:
                # Step 1: Critique current response
                critique_prompt = self._get_critique_prompt(
                    current_response, target_quality, context
                )

                critique_raw = await self.llm.chat(
                    [{"role": "user", "content": critique_prompt}],
                    max_tokens=400,
                    temperature=0.5
                )

                critique_text, quality_score, improvements = self._parse_critique(critique_raw)
                all_improvements.extend(improvements)

                logger.info(f"Iteration {iterations}: quality={quality_score:.2f}, improvements={len(improvements)}")

                # Check if quality is good enough
                if quality_score >= min_quality:
                    logger.info(f"Quality threshold met ({quality_score:.2f} >= {min_quality})")
                    break

                # Check if no improvements suggested
                if not improvements:
                    logger.info("No improvements suggested, stopping")
                    break

                # Step 2: Apply improvements
                improvement_prompt = self._get_improvement_prompt(
                    current_response, critique_text, improvements, context
                )

                improved_response = await self.llm.chat(
                    [{"role": "user", "content": improvement_prompt}],
                    max_tokens=200,
                    temperature=0.6
                )

                # Update current response
                improved_response = improved_response.strip()
                if improved_response and improved_response != current_response:
                    current_response = improved_response
                else:
                    logger.info("No change in response, stopping")
                    break

            except Exception as e:
                logger.error(f"Reflexion iteration {iterations} failed: {e}")
                break

        # Ensure we don't return empty response
        if not current_response.strip():
            current_response = response

        return ReflexionResult(
            final_answer=current_response,
            original_response=response,
            improvements_made=all_improvements,
            iterations=iterations,
            quality_score=quality_score,
            metadata={
                "target_quality": target_quality,
                "context_provided": bool(context)
            }
        )

    async def personalize_message(
        self,
        template: str,
        follower_context: Dict[str, Any]
    ) -> str:
        """
        Convenience method to personalize a template message.

        Args:
            template: Template message to personalize
            follower_context: Context about the follower

        Returns:
            Personalized message string
        """
        result = await self.improve_response(
            response=template,
            target_quality="personalizado, empático y natural",
            context=follower_context,
            min_quality=0.6
        )
        return result.final_answer


# Singleton instance
_reflexion: Optional[ReflexionImprover] = None


def get_reflexion_improver(llm_client=None) -> ReflexionImprover:
    """
    Get singleton instance of ReflexionImprover.

    Args:
        llm_client: LLM client to use (required on first call)

    Returns:
        ReflexionImprover instance
    """
    global _reflexion

    if _reflexion is None:
        if llm_client is None:
            from core.llm import get_llm_client
            llm_client = get_llm_client()
        _reflexion = ReflexionImprover(llm_client)

    return _reflexion


def reset_reflexion():
    """Reset singleton (for testing)"""
    global _reflexion
    _reflexion = None
