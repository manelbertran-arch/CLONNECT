"""
Nurturing Utilities - Helper functions for nurturing sequences.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.nurturing.models import NURTURING_SEQUENCES, SequenceType

logger = logging.getLogger(__name__)

# Base directory for data files (backend/)
_BASE_DIR = Path(__file__).resolve().parent.parent.parent

# =============================================================================
# TESTING MODE - Set to True to force default delays (bypass custom config)
# =============================================================================
TESTING_MODE = False  # Production mode - use custom config delays
# =============================================================================


def render_template(template: str, variables: Dict[str, Any]) -> str:
    """
    Render a nurturing template with variables.

    Args:
        template: Template string with {variable} placeholders
        variables: Dict with variable values

    Returns:
        Rendered message string
    """
    try:
        return template.format(**variables)
    except KeyError as e:
        logger.warning(f"Missing variable in template: {e}")
        # Return template with missing vars as-is
        return template


def _load_creator_nurturing_config(creator_id: str) -> Dict[str, Any]:
    """
    Load the nurturing sequence config for a creator.

    This reads from the config file saved by the dashboard.
    Uses absolute path based on _BASE_DIR to work regardless of CWD.
    """
    config_path = _BASE_DIR / "data" / "nurturing" / f"{creator_id}_sequences.json"
    logger.debug(f"[NURTURING] Loading config from: {config_path}")

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                # Ensure sequences is a dict
                sequences = config.get("sequences", {})
                if not isinstance(sequences, dict):
                    sequences = {}
                logger.info(f"[NURTURING] Loaded config for {creator_id}: {list(sequences.keys())}")
                return {"sequences": sequences}
        except Exception as e:
            logger.error(f"Error loading nurturing config for {creator_id}: {e}")
    else:
        logger.debug(f"[NURTURING] Config file not found: {config_path}")
    return {"sequences": {}}


def is_sequence_active(creator_id: str, sequence_type: str) -> bool:
    """
    Check if a nurturing sequence is active for a creator.

    Args:
        creator_id: Creator ID
        sequence_type: Sequence type (e.g., 'abandoned', 'interest_cold')

    Returns:
        True if the sequence is active
    """
    config = _load_creator_nurturing_config(creator_id)
    sequences = config.get("sequences", {})

    if sequence_type in sequences:
        is_active = sequences[sequence_type].get("is_active", False)
        logger.info(f"[NURTURING] is_sequence_active({creator_id}, {sequence_type}) = {is_active}")
        return is_active

    # Default: sequences are inactive unless explicitly enabled
    logger.info(
        f"[NURTURING] is_sequence_active({creator_id}, {sequence_type}) = False (not in config)"
    )
    return False


def get_sequence_steps(creator_id: str, sequence_type: str) -> List[tuple]:
    """
    Get the steps for a sequence, using custom config if available.

    Args:
        creator_id: Creator ID
        sequence_type: Sequence type

    Returns:
        List of (delay_hours, message) tuples
    """
    # In TESTING_MODE, always use default delays (bypass custom config)
    if TESTING_MODE:
        logger.info(f"[NURTURING] TESTING_MODE=True: Forcing default delays for '{sequence_type}'")
        return NURTURING_SEQUENCES.get(sequence_type, [])

    # Production: use custom config if available
    config = _load_creator_nurturing_config(creator_id)
    sequences = config.get("sequences", {})

    # Check for custom steps in config
    if sequence_type in sequences:
        custom_steps = sequences[sequence_type].get("steps", [])
        if custom_steps:
            return [(s.get("delay_hours", 24), s.get("message", "")) for s in custom_steps]

    # Fall back to default templates
    return NURTURING_SEQUENCES.get(sequence_type, [])


# Mapeo de intents a secuencias de nurturing
# Solo las 4 secuencias core: abandoned, interest_cold, re_engagement, post_purchase
INTENT_TO_SEQUENCE = {
    # Abandoned cart - leads que muestran interés en comprar
    "question_product": SequenceType.ABANDONED.value,  # Pregunta sobre producto/precio
    "interest_strong": SequenceType.ABANDONED.value,  # Quiere comprar
    "want_to_buy": SequenceType.ABANDONED.value,  # Quiere comprar
    "asking_price": SequenceType.ABANDONED.value,  # Pregunta precio
    "purchase_intent": SequenceType.ABANDONED.value,  # Explicit purchase intent
    # Cold interest - leads con interés débil
    "interest_soft": SequenceType.INTEREST_COLD.value,
    "interest_weak": SequenceType.INTEREST_COLD.value,
    "question_general": SequenceType.INTEREST_COLD.value,
    "greeting": SequenceType.INTEREST_COLD.value,
    "other": SequenceType.INTEREST_COLD.value,
    # Objections (mapped to cold interest for now - simpler flow)
    "objection_price": SequenceType.INTEREST_COLD.value,
    "objection_time": SequenceType.INTEREST_COLD.value,
    "objection_doubt": SequenceType.INTEREST_COLD.value,
    "objection_later": SequenceType.INTEREST_COLD.value,
}


def should_schedule_nurturing(
    intent: str, has_purchased: bool = False, creator_id: str = None
) -> Optional[str]:
    """
    Determinar si se debe programar nurturing basado en el intent.

    Args:
        intent: Intent del mensaje
        has_purchased: Si el usuario ya compró
        creator_id: ID del creador (para verificar si secuencia está activa)

    Returns:
        Tipo de secuencia a programar, o None
    """
    logger.info(
        f"[NURTURING] Checking: intent={intent}, purchased={has_purchased}, creator={creator_id}"
    )

    if has_purchased:
        logger.info("[NURTURING] Skipping - user already purchased")
        return None

    sequence_type = INTENT_TO_SEQUENCE.get(intent)
    logger.info(f"[NURTURING] Mapped intent '{intent}' → sequence '{sequence_type}'")

    if not sequence_type:
        logger.info(f"[NURTURING] No sequence mapping for intent '{intent}'")
        return None

    # Si tenemos creator_id, verificar si la secuencia está activa
    if creator_id:
        active = is_sequence_active(creator_id, sequence_type)
        logger.info(f"[NURTURING] Sequence '{sequence_type}' active for {creator_id}? {active}")
        if not active:
            return None

    logger.info(f"[NURTURING] \u2713 Will schedule '{sequence_type}' for {creator_id}")
    return sequence_type


# =============================================================================
# DEFAULT SEQUENCE ACTIVATION
# =============================================================================

# Sequences to activate by default for new creators
DEFAULT_ACTIVE_SEQUENCES = [
    "interest_cold",  # Follow up on soft interest
    "abandoned",  # Recover abandoned carts
    "booking_reminder",  # Remind about upcoming bookings
    "re_engagement",  # Reactivate ghost leads automatically
]


def activate_default_sequences(creator_id: str) -> Dict[str, bool]:
    """
    Activate default nurturing sequences for a new creator.

    Call this after creating a new creator to ensure basic follow-up
    sequences are enabled.

    Args:
        creator_id: Creator ID

    Returns:
        Dict mapping sequence_type to activation status
    """
    config_path = _BASE_DIR / "data" / "nurturing" / f"{creator_id}_sequences.json"

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config or create new
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {"sequences": {}}
    else:
        config = {"sequences": {}}

    if "sequences" not in config or not isinstance(config["sequences"], dict):
        config["sequences"] = {}

    results = {}
    for seq_type in DEFAULT_ACTIVE_SEQUENCES:
        if seq_type not in config["sequences"]:
            config["sequences"][seq_type] = {}
        config["sequences"][seq_type]["is_active"] = True
        results[seq_type] = True
        logger.info(f"[NURTURING] Activated default sequence '{seq_type}' for {creator_id}")

    # Save config
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(f"[NURTURING] Saved default sequences config for {creator_id}")
    except Exception as e:
        logger.error(f"[NURTURING] Error saving config for {creator_id}: {e}")

    return results
