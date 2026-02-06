"""
CreatorDMStyle - Patrones de estilo de DM del creador.

A diferencia de RelationshipDNA (per-lead), esto captura el estilo GENERAL
del creador basado en análisis de TODOS sus mensajes de DM.

Datos basados en análisis real de 3,054 mensajes de Stefan:
- Mediana: 22 chars
- 65% respuestas < 30 chars
- 85% respuestas < 50 chars
- Solo 5% > 100 chars
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class ResponseLengthContext(Enum):
    """Contextos que determinan la longitud de respuesta."""

    GREETING = "greeting"  # Saludos -> muy corto
    CONFIRMATION = "confirmation"  # Confirmaciones -> muy corto
    EMOJI_REACTION = "emoji"  # Reacciones -> muy corto
    SIMPLE_QUESTION = "simple_q"  # Preguntas simples -> corto
    PRICE_QUESTION = "price_q"  # Preguntas de precio -> corto-medio
    SERVICE_EXPLANATION = "service"  # Explicar servicios -> medio-largo
    ADVICE = "advice"  # Dar consejos -> largo si necesario


@dataclass
class LengthPattern:
    """Patrón de longitud para un contexto específico."""

    context: ResponseLengthContext
    median_chars: int
    typical_range: tuple  # (min, max)
    percentage_under_30: float
    examples: List[str]


@dataclass
class CreatorDMStyle:
    """Estilo de DM del creador basado en datos reales."""

    creator_id: str
    creator_name: str

    # Distribución general de longitud
    overall_median_chars: int = 22
    overall_avg_chars: int = 38
    pct_under_30: float = 0.65
    pct_under_50: float = 0.85
    pct_under_100: float = 0.95
    pct_over_100: float = 0.05

    # Patrones por contexto
    length_patterns: Optional[Dict[str, LengthPattern]] = None

    # Emojis más usados (global)
    top_emojis: List[str] = field(default_factory=list)
    emoji_frequency: float = 0.0  # % de mensajes con emoji

    # Frases características
    common_openers: List[str] = field(default_factory=list)
    common_closers: List[str] = field(default_factory=list)
    signature_phrases: List[str] = field(default_factory=list)

    # Anti-patterns (lo que NUNCA hace)
    never_uses: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.length_patterns is None:
            self.length_patterns = {}


# Datos hardcodeados de Stefan basados en análisis real
STEFAN_DM_STYLE = CreatorDMStyle(
    creator_id="5e5c2364-c99a-4484-b986-741bb84a11cf",
    creator_name="stefano_bonanno",
    # Distribución real (de nuestro análisis)
    overall_median_chars=22,
    overall_avg_chars=38,
    pct_under_30=0.65,
    pct_under_50=0.85,
    pct_under_100=0.95,
    pct_over_100=0.05,
    # Patrones por contexto
    length_patterns={
        "greeting": LengthPattern(
            context=ResponseLengthContext.GREETING,
            median_chars=13,
            typical_range=(5, 25),
            percentage_under_30=0.71,
            examples=["Hola! 😊", "Qué tal!", "Hey!", "Buenas!"],
        ),
        "confirmation": LengthPattern(
            context=ResponseLengthContext.CONFIRMATION,
            median_chars=21,
            typical_range=(5, 30),
            percentage_under_30=0.68,
            examples=["Dale!", "Perfecto! ❤️", "Genial!", "Hecho!"],
        ),
        "emoji_reaction": LengthPattern(
            context=ResponseLengthContext.EMOJI_REACTION,
            median_chars=13,
            typical_range=(1, 20),
            percentage_under_30=0.81,
            examples=["😊", "❤️", "💪", "Jajaja"],
        ),
        "price_question": LengthPattern(
            context=ResponseLengthContext.PRICE_QUESTION,
            median_chars=18,
            typical_range=(15, 50),
            percentage_under_30=1.0,
            examples=["90 min", "97€ el programa"],
        ),
    },
    # Emojis
    top_emojis=["😊", "❤️", "💪", "🙏", "😄", "🔥"],
    emoji_frequency=0.45,  # 45% de mensajes tienen emoji
    # Frases características
    common_openers=["Hola!", "Qué tal!", "Hey!", "Genial!"],
    common_closers=["Un abrazo!", "❤️", "💪", "Dale!"],
    signature_phrases=["crack", "bro", "hermano", "amigo", "tío", "te quiero"],
    # Lo que Stefan NUNCA dice
    never_uses=[
        "¿En qué puedo ayudarte?",
        "Gracias por contactarnos",
        "Será un placer asistirte",
        "Quedo a tu disposición",
        "No dudes en consultarnos",
        "Estimado/a",
        "Atentamente",
    ],
)
