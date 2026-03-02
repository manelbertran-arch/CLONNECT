"""
Prompt Builder — Calibration-driven helpers (v9+).

Contains get_calibration_soft_max, build_length_hint, build_vocabulary_hint,
and build_question_hint.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# CALIBRATION-DRIVEN HELPERS (v9+)
# =============================================================================


def get_calibration_soft_max(
    calibration: Optional[dict] = None,
    context: Optional[str] = None,
    creator_id: Optional[str] = None,
) -> int:
    """
    Get soft_max from calibration, per-context if available (v9.2).

    v12: If a personality extraction exists, uses max_message_length_chars
    as the soft_max override (highest priority).

    Falls back to baseline soft_max, then to 60.
    """
    # v12: Personality extraction override (highest priority)
    if creator_id:
        try:
            from core.personality_loader import get_calibration_override

            override = get_calibration_override(creator_id)
            if override and "max_message_length_chars" in override:
                return override["max_message_length_chars"]
        except Exception as e:
            logger.debug(f"[CALIBRATION] error: {e}")

    if not calibration:
        return 60

    # Try per-context first
    if context and "context_soft_max" in calibration:
        ctx_max = calibration["context_soft_max"].get(context)
        if ctx_max is not None:
            return ctx_max

    # Fall back to baseline
    return calibration.get("baseline", {}).get("soft_max", 60)


def build_length_hint(
    calibration: Optional[dict] = None,
    context: Optional[str] = None,
) -> str:
    """
    Build a length guidance hint for the LLM prompt (v9.2).

    Returns a short instruction string to append to the system prompt.
    """
    soft_max = get_calibration_soft_max(calibration, context)

    context_labels = {
        "saludo": "greeting - short and warm",
        "agradecimiento": "thanks - brief acknowledgment",
        "casual": "casual chat - relaxed",
        "humor": "funny reaction - keep it light",
        "interes": "interest signal - just acknowledge",
        "pregunta_precio": "price question - be clear",
        "pregunta_producto": "product question - concise but informative",
        "pregunta_general": "general question - quick answer",
        "objecion": "objection - explain value",
        "otro": "normal conversation",
    }

    label = context_labels.get(context or "", "normal conversation")

    return (
        f"[Length: {label}. "
        f"Target ~{soft_max} chars max. Keep it natural and concise.]"
    )


def build_vocabulary_hint(
    calibration: Optional[dict] = None,
    creator_name: str = "",
) -> str:
    """
    Build a vocabulary hint from calibration data (v10.3).

    Injects the creator's most-used words so the LLM integrates them naturally.
    """
    if not calibration:
        return ""

    vocab = calibration.get("creator_vocabulary", [])
    if not vocab:
        return ""

    name = creator_name or "el creador"
    words_str = ", ".join(vocab[:15])
    return (
        f"Palabras que {name} usa frecuentemente: {words_str}. "
        "Intégralas naturalmente en tus respuestas."
    )


def build_question_hint(
    calibration: Optional[dict] = None,
) -> str:
    """
    Build a question frequency hint for LLM (v9.3).

    If creator asks questions in ~12% of responses, hint the LLM to do the same.
    """
    if not calibration:
        return ""

    q_pct = calibration.get("baseline", {}).get("question_frequency_pct", 0)
    if q_pct >= 8:
        return (
            f"Pregunta naturalmente en ~{int(q_pct)}% de respuestas. "
            "Ejemplos: '¿Cómo estás?', '¿En serio?', '¿Todo bien?'"
        )

    return ""

