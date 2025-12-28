"""
Chain of Thought Reasoning Module for Clonnect

Generates step-by-step reasoning for complex queries before providing an answer.
Particularly useful for:
- Health-related questions (lesiones, enfermedades, condiciones médicas)
- Complex product questions
- Multi-part queries

Based on: "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models"
(Wei et al., 2022)
"""

import logging
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Keywords that trigger Chain of Thought reasoning
COMPLEX_QUERY_KEYWORDS = [
    # Health-related (Spanish)
    "lesión", "lesion", "enfermedad", "médico", "medico", "embarazo",
    "diabetes", "alergia", "problema", "condición", "condicion",
    "dolor", "molestia", "síntoma", "sintoma", "tratamiento",
    "medicamento", "medicina", "doctor", "hospital", "salud",
    # Health-related (English)
    "injury", "disease", "doctor", "pregnancy", "diabetes",
    "allergy", "problem", "condition", "pain", "symptom",
    "treatment", "medication", "medicine", "health",
    # Complex product questions
    "comparar", "diferencia", "mejor opción", "qué incluye",
    "cuánto dura", "requisitos", "necesito saber",
    "compare", "difference", "best option", "what includes",
    "how long", "requirements", "need to know"
]

# Minimum word count to consider a query complex
MIN_WORDS_FOR_COMPLEX = 50


@dataclass
class ChainOfThoughtResult:
    """Result of Chain of Thought reasoning"""
    answer: str
    reasoning_steps: List[str]
    is_complex: bool
    query_type: str  # "health", "product", "general"
    confidence: float
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ChainOfThoughtReasoner:
    """
    Generates step-by-step reasoning for complex queries.

    How it works:
    1. Detect if query is complex (keywords or length)
    2. Generate reasoning steps
    3. Synthesize final answer from reasoning
    4. Include safety disclaimers for health topics
    """

    def __init__(self, llm_client):
        self.llm = llm_client

    def _is_complex_query(self, message: str) -> tuple:
        """
        Determine if a query requires Chain of Thought reasoning.

        Returns:
            (is_complex, query_type)
        """
        if not message:
            return False, "general"

        msg_lower = message.lower()
        word_count = len(message.split())

        # Check for health keywords
        health_keywords = [
            "lesión", "lesion", "enfermedad", "médico", "medico",
            "embarazo", "diabetes", "alergia", "dolor", "síntoma",
            "tratamiento", "medicamento", "salud", "injury", "disease",
            "doctor", "pregnancy", "pain", "symptom", "treatment", "health"
        ]
        if any(kw in msg_lower for kw in health_keywords):
            return True, "health"

        # Check for complex product questions
        product_keywords = [
            "comparar", "diferencia", "mejor opción", "qué incluye",
            "requisitos", "compare", "difference", "requirements"
        ]
        if any(kw in msg_lower for kw in product_keywords):
            return True, "product"

        # Check word count
        if word_count >= MIN_WORDS_FOR_COMPLEX:
            return True, "general"

        # Check for any complex keywords
        if any(kw in msg_lower for kw in COMPLEX_QUERY_KEYWORDS):
            return True, "general"

        return False, "general"

    def _get_cot_prompt(self, query: str, query_type: str, context: Dict[str, Any]) -> str:
        """
        Generate Chain of Thought prompt.
        """
        creator_name = context.get("creator_name", "el creador")
        products = context.get("products", [])
        product_names = [p.get("name", "") for p in products]

        base_prompt = f"""Eres el asistente de IA de {creator_name}. Un usuario ha hecho una pregunta compleja.

IMPORTANTE: Piensa paso a paso antes de responder.

Pregunta del usuario: {query}

"""

        if query_type == "health":
            base_prompt += """
CONTEXTO: Esta es una pregunta relacionada con salud.

Pasos a seguir:
1. ANALIZA: ¿Qué está preguntando exactamente el usuario?
2. CONSIDERA: ¿Es algo que puedo responder con información general o requiere atención médica?
3. EVALÚA: ¿Hay algún producto relevante que pueda ayudar (sin hacer claims médicos)?
4. RESPONDE: Formula una respuesta empática y responsable.

REGLAS PARA TEMAS DE SALUD:
- NUNCA dar consejos médicos específicos
- SIEMPRE recomendar consultar con un profesional de salud
- SÍ puedes hablar de bienestar general y hábitos saludables
- SÍ puedes mencionar productos si son relevantes (sin claims médicos)

"""
        elif query_type == "product":
            base_prompt += f"""
CONTEXTO: Esta es una pregunta sobre productos.

Productos disponibles: {', '.join(product_names) if product_names else 'Consultar catálogo'}

Pasos a seguir:
1. IDENTIFICA: ¿Qué producto(s) está preguntando?
2. ANALIZA: ¿Qué información específica necesita?
3. COMPARA: Si pide comparación, analiza pros y contras
4. RESPONDE: Da información clara y útil

"""
        else:
            base_prompt += """
Pasos a seguir:
1. ANALIZA: ¿Cuál es la pregunta principal?
2. DESGLOSA: Si hay múltiples partes, identifícalas
3. RESPONDE: Aborda cada parte de forma clara

"""

        base_prompt += """
FORMATO DE RESPUESTA:
Primero, escribe tu razonamiento interno (esto NO se mostrará al usuario):
[RAZONAMIENTO]
- Paso 1: ...
- Paso 2: ...
- Paso 3: ...
[/RAZONAMIENTO]

Luego, escribe la respuesta final para el usuario:
[RESPUESTA]
Tu respuesta aquí (máximo 3-4 frases, tono cercano)
[/RESPUESTA]
"""

        return base_prompt

    def _parse_cot_response(self, raw_response: str) -> tuple:
        """
        Parse Chain of Thought response to extract reasoning and answer.

        Returns:
            (reasoning_steps, final_answer)
        """
        reasoning_steps = []
        final_answer = raw_response.strip()

        # Try to extract reasoning
        reasoning_match = re.search(
            r'\[RAZONAMIENTO\](.*?)\[/RAZONAMIENTO\]',
            raw_response,
            re.DOTALL | re.IGNORECASE
        )
        if reasoning_match:
            reasoning_text = reasoning_match.group(1).strip()
            # Split into steps
            steps = re.findall(r'(?:Paso \d+:|[-•])\s*(.+?)(?=(?:Paso \d+:|[-•]|$))', reasoning_text, re.DOTALL)
            reasoning_steps = [s.strip() for s in steps if s.strip()]

        # Try to extract final answer
        answer_match = re.search(
            r'\[RESPUESTA\](.*?)\[/RESPUESTA\]',
            raw_response,
            re.DOTALL | re.IGNORECASE
        )
        if answer_match:
            final_answer = answer_match.group(1).strip()
        else:
            # If no tags, try to find answer after reasoning
            if reasoning_match:
                after_reasoning = raw_response[reasoning_match.end():].strip()
                if after_reasoning:
                    final_answer = after_reasoning

        return reasoning_steps, final_answer

    async def generate(
        self,
        query: str,
        context: Dict[str, Any] = None
    ) -> ChainOfThoughtResult:
        """
        Generate a response using Chain of Thought reasoning.

        Args:
            query: User's message
            context: Additional context (products, creator info, etc.)

        Returns:
            ChainOfThoughtResult with reasoning steps and final answer
        """
        context = context or {}
        is_complex, query_type = self._is_complex_query(query)

        if not is_complex:
            # Not complex enough, return simple result
            return ChainOfThoughtResult(
                answer="",
                reasoning_steps=[],
                is_complex=False,
                query_type=query_type,
                confidence=1.0,
                metadata={"skipped": True, "reason": "not_complex"}
            )

        logger.info(f"Using Chain of Thought for {query_type} query")

        try:
            # Generate CoT prompt
            cot_prompt = self._get_cot_prompt(query, query_type, context)

            # Call LLM with CoT prompt
            messages = [
                {"role": "system", "content": "Eres un asistente que razona paso a paso."},
                {"role": "user", "content": cot_prompt}
            ]

            raw_response = await self.llm.chat(
                messages,
                max_tokens=500,
                temperature=0.5  # Lower temperature for more focused reasoning
            )

            # Parse response
            reasoning_steps, final_answer = self._parse_cot_response(raw_response)

            # Add health disclaimer if needed
            if query_type == "health" and final_answer:
                # Check if disclaimer already present
                if "consulta" not in final_answer.lower() and "médico" not in final_answer.lower():
                    final_answer += " Recuerda siempre consultar con un profesional de salud para temas médicos específicos."

            logger.info(f"CoT completed: {len(reasoning_steps)} steps, answer length: {len(final_answer)}")

            return ChainOfThoughtResult(
                answer=final_answer,
                reasoning_steps=reasoning_steps,
                is_complex=True,
                query_type=query_type,
                confidence=0.85 if reasoning_steps else 0.6,
                metadata={
                    "raw_response_length": len(raw_response),
                    "steps_found": len(reasoning_steps)
                }
            )

        except Exception as e:
            logger.error(f"Chain of Thought generation failed: {e}")
            return ChainOfThoughtResult(
                answer="",
                reasoning_steps=[],
                is_complex=True,
                query_type=query_type,
                confidence=0.0,
                metadata={"error": str(e)}
            )

    def is_complex_query(self, message: str) -> bool:
        """Public method to check if query is complex"""
        is_complex, _ = self._is_complex_query(message)
        return is_complex


# Singleton instance
_chain_of_thought: Optional[ChainOfThoughtReasoner] = None


def get_chain_of_thought_reasoner(llm_client=None) -> ChainOfThoughtReasoner:
    """
    Get singleton instance of ChainOfThoughtReasoner.

    Args:
        llm_client: LLM client to use (required on first call)

    Returns:
        ChainOfThoughtReasoner instance
    """
    global _chain_of_thought

    if _chain_of_thought is None:
        if llm_client is None:
            from core.llm import get_llm_client
            llm_client = get_llm_client()
        _chain_of_thought = ChainOfThoughtReasoner(llm_client)

    return _chain_of_thought


def reset_chain_of_thought():
    """Reset singleton (for testing)"""
    global _chain_of_thought
    _chain_of_thought = None
