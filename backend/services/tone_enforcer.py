"""
Tone Enforcer — probabilistic per-response enforcement of tone markers.

Reads targets from calibration baseline and uses hash-based probability
to decide whether each response should have emoji, exclamation, or question.

Converges to target rates over many responses by law of large numbers.

Universal: all targets come from calibration, no hardcoded creator data.
"""

import hashlib
import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_EMOJI_PAT = re.compile(r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\ufe00-\ufe0f]")

# Light emojis to inject when needed (neutral, positive)
_INJECT_EMOJIS = ["😊", "💙", "💪", "🙌", "🔥"]

# Natural questions to inject when needed
_INJECT_QUESTIONS = [
    " Todo bien?",
    " Cómo vas?",
    " Cómo estás?",
    " En serio?",
    " Sí?",
]


def enforce_tone(
    response: str,
    calibration: Optional[Dict],
    sender_id: str = "",
    message: str = "",
) -> str:
    """Apply probabilistic tone enforcement to a single response.

    Uses hash of (sender_id + message) for deterministic, reproducible decisions.
    Each marker (emoji, exclamation, question) is enforced independently.

    Args:
        response: The LLM response to enforce
        calibration: Calibration dict with baseline targets
        sender_id: For deterministic hashing
        message: Current user message for hashing

    Returns:
        Enforced response string
    """
    if not calibration or not response:
        return response

    baseline = calibration.get("baseline", {})
    if not baseline:
        return response

    target_emoji = baseline.get("emoji_pct", 0) / 100
    target_excl = baseline.get("exclamation_pct", 0) / 100
    target_q = baseline.get("question_frequency_pct", 0) / 100

    # Deterministic hash base
    h_base = hashlib.md5(f"tone_{sender_id}_{message[:30]}".encode()).hexdigest()

    # --- Emoji enforcement ---
    h_emoji = int(h_base[:8], 16) % 1000
    has_emoji = bool(_EMOJI_PAT.search(response))
    should_have_emoji = h_emoji < (target_emoji * 1000)

    if has_emoji and not should_have_emoji:
        response = _EMOJI_PAT.sub("", response).strip()
    elif not has_emoji and should_have_emoji:
        emoji = _INJECT_EMOJIS[int(h_base[8:10], 16) % len(_INJECT_EMOJIS)]
        response = response.rstrip() + " " + emoji

    # --- Exclamation enforcement ---
    h_excl = int(h_base[8:16], 16) % 1000
    has_excl = "!" in response
    should_have_excl = h_excl < (target_excl * 1000)

    if has_excl and not should_have_excl:
        response = response.replace("!", "", 1)
    elif not has_excl and should_have_excl:
        response = response.rstrip() + "!"

    # --- Question enforcement ---
    h_q = int(h_base[16:24], 16) % 1000
    has_q = "?" in response
    should_have_q = h_q < (target_q * 1000)

    if has_q and not should_have_q:
        response = response.replace("?", "", 1)
    elif not has_q and should_have_q:
        q = _INJECT_QUESTIONS[int(h_base[24:26], 16) % len(_INJECT_QUESTIONS)]
        response = response.rstrip() + q

    return response
