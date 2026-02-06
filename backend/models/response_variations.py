"""
ResponseVariations - Pools de respuestas para variedad natural.

El bot no debe responder siempre igual al mismo input.
Basado en respuestas reales de Stefan extraídas de 3056 mensajes.
"""
from dataclasses import dataclass, field
from typing import Dict, List
import random


@dataclass
class ResponsePool:
    """Pool de respuestas posibles para un tipo de mensaje."""

    trigger_type: str
    responses: List[str]
    weights: List[float] = field(default_factory=list)

    def __post_init__(self):
        if not self.weights:
            # Pesos iguales si no se especifican
            self.weights = [1.0 / len(self.responses)] * len(self.responses)

    def select(self, exclude: List[str] = None) -> str:
        """Selecciona respuesta aleatoria según pesos, evitando las excluidas."""
        exclude = exclude or []

        # Filtrar respuestas excluidas
        available = [
            (r, w) for r, w in zip(self.responses, self.weights) if r not in exclude
        ]

        if not available:
            # Si todas están excluidas, usar cualquiera
            return random.choice(self.responses)

        responses, weights = zip(*available)
        return random.choices(responses, weights=weights, k=1)[0]


# ═══════════════════════════════════════════════════════════════════════════════
# POOLS DE STEFAN - Basados en análisis de 3056 mensajes reales
# ═══════════════════════════════════════════════════════════════════════════════

STEFAN_RESPONSE_POOLS: Dict[str, ResponsePool] = {
    # ─────────────────────────────────────────────────────────────────────────
    # SALUDOS
    # ─────────────────────────────────────────────────────────────────────────
    "greeting": ResponsePool(
        trigger_type="greeting",
        responses=[
            "Hey! 😊",
            "Qué tal!",
            "Hola! 😊",
            "Buenas!",
            "Ey!",
            "Hola 😀",
            "Hey 😊",
            "Qué pasa!",
            "Hola! Cómo estás?",
            "Buenas! Qué tal?",
        ],
        weights=[0.15, 0.15, 0.15, 0.1, 0.1, 0.1, 0.08, 0.07, 0.05, 0.05],
    ),
    # ─────────────────────────────────────────────────────────────────────────
    # AGRADECIMIENTOS
    # ─────────────────────────────────────────────────────────────────────────
    "thanks": ResponsePool(
        trigger_type="thanks",
        responses=[
            "A ti! 😊",
            "De nada! 💙",
            "A ti!",
            "Gracias a ti!",
            "💙",
            "😊",
            "Nada!",
            "De nada!",
            "A ti 😊",
        ],
        weights=[0.15, 0.15, 0.12, 0.12, 0.1, 0.1, 0.1, 0.08, 0.08],
    ),
    # ─────────────────────────────────────────────────────────────────────────
    # CONFIRMACIONES
    # ─────────────────────────────────────────────────────────────────────────
    "confirmation": ResponsePool(
        trigger_type="confirmation",
        responses=[
            "Perfecto! 😊",
            "Genial!",
            "Dale!",
            "Ok!",
            "Perfecto!",
            "Genial 😊",
            "Vale!",
            "👍",
            "💙",
            "Bien!",
        ],
        weights=[0.15, 0.12, 0.12, 0.1, 0.1, 0.1, 0.1, 0.08, 0.07, 0.06],
    ),
    # ─────────────────────────────────────────────────────────────────────────
    # REACCIONES A EMOJIS
    # ─────────────────────────────────────────────────────────────────────────
    "emoji_reaction": ResponsePool(
        trigger_type="emoji_reaction",
        responses=[
            "❤",
            "💙",
            "😊",
            "😀",
            "🙏🏽",
            "☺",
            "💪",
        ],
        weights=[0.2, 0.2, 0.15, 0.15, 0.1, 0.1, 0.1],
    ),
    # ─────────────────────────────────────────────────────────────────────────
    # RESPUESTAS SECAS (cuando Stefan es muy breve)
    # ─────────────────────────────────────────────────────────────────────────
    "dry_response": ResponsePool(
        trigger_type="dry_response",
        responses=[
            "Ok",
            "Vale",
            "Bien",
            "👍",
            "Sí",
            "Ya",
        ],
        weights=[0.25, 0.2, 0.15, 0.15, 0.15, 0.1],
    ),
    # ─────────────────────────────────────────────────────────────────────────
    # RISAS
    # ─────────────────────────────────────────────────────────────────────────
    "laugh": ResponsePool(
        trigger_type="laugh",
        responses=[
            "Jajaja",
            "Jaja",
            "Jajaja 😀",
            "😀",
            "Jaja sí",
            "Jajajaja",
        ],
        weights=[0.3, 0.25, 0.15, 0.1, 0.1, 0.1],
    ),
    # ─────────────────────────────────────────────────────────────────────────
    # DESPEDIDAS
    # ─────────────────────────────────────────────────────────────────────────
    "farewell": ResponsePool(
        trigger_type="farewell",
        responses=[
            "Un abrazo! 😊",
            "Un abrazo!",
            "Abrazo! 💙",
            "💙",
            "Cuídate!",
            "Hablamos!",
            "Un abrazo grande!",
        ],
        weights=[0.2, 0.18, 0.15, 0.12, 0.12, 0.12, 0.11],
    ),
    # ─────────────────────────────────────────────────────────────────────────
    # INTERÉS / ENTUSIASMO
    # ─────────────────────────────────────────────────────────────────────────
    "enthusiasm": ResponsePool(
        trigger_type="enthusiasm",
        responses=[
            "Genial!! 😀",
            "Qué bien! 😊",
            "Me encanta!",
            "Qué bueno!",
            "Genial!",
            "Increíble!",
            "Wow!",
        ],
        weights=[0.2, 0.18, 0.15, 0.15, 0.12, 0.1, 0.1],
    ),
    # ─────────────────────────────────────────────────────────────────────────
    # PREGUNTAS DE SEGUIMIENTO
    # ─────────────────────────────────────────────────────────────────────────
    "follow_up_question": ResponsePool(
        trigger_type="follow_up_question",
        responses=[
            "Y tú qué tal?",
            "Cómo estás?",
            "Qué tal todo?",
            "Y tú?",
            "Cómo vas?",
            "Qué me cuentas?",
        ],
        weights=[0.2, 0.2, 0.18, 0.15, 0.14, 0.13],
    ),
    # ─────────────────────────────────────────────────────────────────────────
    # PROPUESTAS DE QUEDAR (RECHAZAR)
    # Stefan no puede quedar en persona - siempre rechaza amablemente
    # ─────────────────────────────────────────────────────────────────────────
    "meeting_request": ResponsePool(
        trigger_type="meeting_request",
        responses=[
            "Imposible bro, me explota la agenda jaja",
            "Uf imposible, tengo la agenda llena 😅",
            "Me es imposible ahora mismo, hermano",
            "Ahora no puedo, bro. Quizás más adelante! 😊",
            "Difícil ahora, tengo todo el mes pillado jaja",
        ],
        weights=[0.3, 0.25, 0.2, 0.15, 0.1],
    ),
}
