"""
Sistema de Prompt Universal para Clonación de Estilo de Comunicación.

Basado en análisis de 131 turnos reales con los siguientes problemas detectados:
- PREGUNTA_INNECESARIA: 35.1%
- DEMASIADO_LARGO: 29.8%
- DEMASIADO_CORTO: 12.2%
- RESPUESTA_GENERICA: 6.1%
- EXCESO_EMOJIS: 4.6%
- USA_PUNTO_FINAL: 3.8%
- POOL_INADECUADO: 2.3%

Este prompt es UNIVERSAL - funciona con cualquier creador inyectando sus métricas.
"""

from dataclasses import dataclass
from typing import List

from core.emoji_utils import count_emojis as _count_emojis


@dataclass
class CreatorMetrics:
    """Métricas extraídas del análisis de mensajes del creador."""

    name: str
    avg_length: float  # Longitud promedio de sus mensajes
    median_length: float  # Mediana de longitud
    question_rate: float  # % de mensajes que son preguntas (0-1)
    emoji_rate: float  # % de mensajes con emoji (0-1)
    avg_emojis_per_msg: float  # Promedio de emojis por mensaje
    uses_period: bool  # Si usa punto final frecuentemente
    period_rate: float  # % de mensajes que terminan en punto
    exclamation_rate: float  # % de mensajes que terminan en !
    common_phrases: List[str]  # Frases típicas del creador
    vocabulary: List[str]  # Palabras características
    tone_words: List[str]  # Palabras de tono (bro, hermano, crack, etc)

    # Patrones de respuesta
    elaborates_on_emotion: bool  # Si elabora cuando el lead comparte emociones
    elaborates_on_questions: bool  # Si da respuestas largas a preguntas
    uses_dry_responses: bool  # Si a veces responde muy seco (ok, dale, etc)
    dry_response_rate: float  # % de respuestas secas


def build_clone_system_prompt(metrics: CreatorMetrics, relationship_context: str = "") -> str:
    """
    Construye el prompt del sistema para clonar el estilo del creador.

    Args:
        metrics: Métricas del creador extraídas de su historial
        relationship_context: Contexto de la relación con el lead específico

    Returns:
        Prompt del sistema optimizado
    """

    # Calcular límites de longitud - MÁS ESTRICTOS
    min_length = int(metrics.avg_length * 0.3)  # Más bajo
    max_length = int(metrics.avg_length * 1.2)  # Más estricto (era 1.5)
    target_length = int(metrics.median_length * 0.9)  # Apuntar más bajo

    # Determinar política de preguntas
    if metrics.question_rate < 0.10:
        question_policy = "CASI NUNCA preguntes. Solo si es absolutamente necesario para continuar."
    elif metrics.question_rate < 0.20:
        question_policy = "Pregunta MUY POCO. Máximo 1 de cada 5 respuestas puede tener pregunta."
    else:
        question_policy = "Puedes preguntar ocasionalmente, pero no en cada mensaje."

    # Determinar política de emojis
    if metrics.emoji_rate < 0.15:
        emoji_policy = "USA MUY POCOS EMOJIS. Máximo 1 emoji cada 3-4 mensajes."
    elif metrics.emoji_rate < 0.30:
        emoji_policy = (
            f"Usa emojis moderadamente. Promedio: {metrics.avg_emojis_per_msg:.1f} por mensaje."
        )
    else:
        emoji_policy = f"Puedes usar emojis frecuentemente. Promedio: {metrics.avg_emojis_per_msg:.1f} por mensaje."

    # Determinar política de puntuación
    if metrics.period_rate < 0.05:
        punctuation_policy = "NUNCA termines con punto (.). Usa ! o emoji o nada."
    elif metrics.period_rate < 0.15:
        punctuation_policy = "CASI NUNCA uses punto final. Prefiere ! o terminar sin puntuación."
    else:
        punctuation_policy = "Puedes usar punto final ocasionalmente."

    # Construir lista de frases prohibidas
    banned_phrases = [
        "¿Qué tal?",
        "¿Cómo estás?",
        "¿Todo bien?",
        "¿En qué puedo ayudarte?",
        "¿Necesitas algo?",
    ]

    prompt = f"""Eres {metrics.name}. Responde EXACTAMENTE como lo haría {metrics.name} en Instagram DM.

═══════════════════════════════════════════════════════════════════════════════
REGLAS CRÍTICAS - SEGUIR AL PIE DE LA LETRA
═══════════════════════════════════════════════════════════════════════════════

1. LONGITUD ESTRICTA
   - Tu longitud OBJETIVO es {target_length} caracteres
   - MÍNIMO: {min_length} caracteres
   - MÁXIMO: {max_length} caracteres
   - Si tu respuesta excede {max_length} chars, ACÓRTALA
   - Respuestas cortas son MEJORES que respuestas largas

2. PREGUNTAS - {question_policy}
   - PROHIBIDO usar estas frases: {', '.join(banned_phrases)}
   - Si el lead hace una pregunta, RESPONDE, no preguntes de vuelta
   - Si el lead saluda, SALUDA DE VUELTA, no preguntes "¿qué tal?"
   - Solo pregunta si REALMENTE necesitas información para continuar

3. EMOJIS - {emoji_policy}
   - NO pongas emoji al final de CADA mensaje
   - Si usas emoji, que sea NATURAL, no forzado

4. PUNTUACIÓN - {punctuation_policy}
   - NO escribas como asistente virtual, escribe como PERSONA REAL

5. TONO Y VOCABULARIO
   - Palabras características: {', '.join(metrics.tone_words) if metrics.tone_words else 'casual, natural'}
   - Frases típicas: {', '.join(metrics.common_phrases[:3]) if metrics.common_phrases else 'naturales'}
   - NUNCA uses lenguaje corporativo o de servicio al cliente

6. CONTEXTO Y COHERENCIA
   - LEE el mensaje del lead COMPLETO antes de responder
   - Si el lead comparte algo personal/emocional: {"ELABORA y muestra empatía" if metrics.elaborates_on_emotion else "responde breve pero cálido"}
   - Si el lead pregunta algo específico: RESPONDE A ESO, no cambies de tema

7. RESPUESTAS SECAS ({"PERMITIDAS" if metrics.uses_dry_responses else "EVITAR"})
   - {"A veces responde solo 'Dale', 'Ok', 'Jaja', etc." if metrics.uses_dry_responses else "Siempre elabora un poco"}

═══════════════════════════════════════════════════════════════════════════════
EJEMPLOS DE QUÉ NO HACER
═══════════════════════════════════════════════════════════════════════════════

❌ MALO: Lead: "Heeeyy" → Bot: "Hola!! 😊 ¿Qué tal?"
✅ BIEN: "Ey! 😊" o "Buenas!"

❌ MALO: Lead: "Todo bien vos?" → Bot: "Hola! Todo bien, gracias! 😊 ¿Y tú?"
✅ BIEN: "Bien y vos??"

❌ MALO: Lead: "Me mudé a Barcelona" → Bot: "¡Qué bien! 😊 ¿Qué tal te está yendo?"
✅ BIEN: "Bienvenido hermano!!" o "Barcelona es genial!"

❌ MALO: Lead: "Gracias" → Bot: "De nada. Un abrazo."
✅ BIEN: "De nada! 💙"

═══════════════════════════════════════════════════════════════════════════════
RECUERDA: Eres {metrics.name}, NO un asistente. CORTO > largo. NATURAL > correcto.
═══════════════════════════════════════════════════════════════════════════════

{relationship_context}
"""

    return prompt


def build_response_guidelines(metrics: CreatorMetrics) -> str:
    """Construye guías adicionales por tipo de mensaje."""

    return f"""
═══════════════════════════════════════════════════════════════════════════════
GUÍA POR TIPO DE MENSAJE
═══════════════════════════════════════════════════════════════════════════════

SALUDO (hola, hey): → Saludo similar, 5-15 chars. "Ey!" "Buenas!"
PREGUNTA DIRECTA: → RESPONDE, no preguntes. Longitud según necesidad.
EMOCIONAL: → {"Empatía, 20-50 chars" if metrics.elaborates_on_emotion else "Breve y cálido"}
INFORMATIVO: → Reacciona. "Qué bien!" "Genial!"
EMOJI/REACCIÓN: → Emoji similar. 1-10 chars.
CONFIRMACIÓN: → "Dale!" "Perfecto" 3-15 chars.
DESPEDIDA: → "Un abrazo!" "Hablamos!" 5-20 chars.
"""


# ═══════════════════════════════════════════════════════════════════════════════
# MÉTRICAS DE STEFAN (default)
# ═══════════════════════════════════════════════════════════════════════════════

def extract_creator_metrics(creator_id: str, messages: list) -> CreatorMetrics:
    """Extrae métricas de los mensajes de un creador.

    Vocabulary is data-mined from real messages — zero hardcoding.
    """
    if not messages:
        raise ValueError(
            "No messages provided — cannot extract metrics without data"
        )

    from services.vocabulary_extractor import get_top_distinctive_words

    lengths = [len(m) for m in messages]
    avg_length = sum(lengths) / len(lengths)
    sorted_lengths = sorted(lengths)
    median_length = sorted_lengths[len(sorted_lengths) // 2]

    questions = sum(1 for m in messages if "?" in m)
    question_rate = questions / len(messages)

    count_emojis = _count_emojis

    msgs_with_emoji = sum(1 for m in messages if count_emojis(m) > 0)
    emoji_rate = msgs_with_emoji / len(messages)
    avg_emojis = sum(count_emojis(m) for m in messages) / len(messages)

    period_endings = sum(1 for m in messages if m.rstrip().endswith("."))
    period_rate = period_endings / len(messages)

    exclamation_endings = sum(1 for m in messages if m.rstrip().endswith("!"))
    exclamation_rate = exclamation_endings / len(messages)

    dry_responses = ["ok", "dale", "vale", "jaja", "jajaja", "sí", "si", "no", "bien"]
    dry_count = sum(1 for m in messages if m.lower().strip() in dry_responses or len(m) < 8)
    dry_rate = dry_count / len(messages)

    # Data-mined vocabulary: extract from real messages, not hardcoded lists
    found_words = get_top_distinctive_words(messages, top_n=8, min_freq=2)

    return CreatorMetrics(
        name="Creator",
        avg_length=avg_length,
        median_length=median_length,
        question_rate=question_rate,
        emoji_rate=emoji_rate,
        avg_emojis_per_msg=avg_emojis,
        uses_period=period_rate > 0.1,
        period_rate=period_rate,
        exclamation_rate=exclamation_rate,
        common_phrases=[],
        vocabulary=found_words,
        tone_words=found_words,
        elaborates_on_emotion=avg_length > 40,
        elaborates_on_questions=avg_length > 50,
        uses_dry_responses=dry_rate > 0.1,
        dry_response_rate=dry_rate,
    )
