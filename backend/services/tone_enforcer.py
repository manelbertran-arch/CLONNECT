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

# Default emojis (fallback for creators without calibration)
_DEFAULT_INJECT_EMOJIS = ["😊", "💙", "💪", "🙌", "🔥"]


def _get_creator_emojis(calibration: Optional[Dict]) -> list:
    """Get creator-specific emojis from calibration, or defaults."""
    if not calibration:
        return _DEFAULT_INJECT_EMOJIS
    creator_emojis = calibration.get("inject_emojis")
    if creator_emojis and isinstance(creator_emojis, list):
        return creator_emojis
    # Fallback: extract from notes or baseline
    notes = calibration.get("notes", {})
    if isinstance(notes, dict) and "emoji_clusters" in str(notes):
        # Try to find common emojis in few_shot examples
        examples = calibration.get("few_shot_examples", [])
        emoji_counter = {}
        for ex in examples:
            resp = ex.get("response", "")
            for ch in resp:
                if _EMOJI_PAT.match(ch):
                    emoji_counter[ch] = emoji_counter.get(ch, 0) + 1
        if emoji_counter:
            top = sorted(emoji_counter, key=emoji_counter.get, reverse=True)[:6]
            return top
    return _DEFAULT_INJECT_EMOJIS


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

    # --- Emoji enforcement (creator-specific emojis) ---
    creator_emojis = _get_creator_emojis(calibration)
    if has_emoji and not should_have_emoji:
        response = _EMOJI_PAT.sub("", response).strip()
    elif not has_emoji and should_have_emoji:
        emoji = creator_emojis[int(h_base[8:10], 16) % len(creator_emojis)]
        response = response.rstrip() + emoji

    # --- Exclamation enforcement ---
    h_excl = int(h_base[8:16], 16) % 1000
    has_excl = "!" in response
    should_have_excl = h_excl < (target_excl * 1000)

    if has_excl and not should_have_excl:
        response = response.replace("!", "", 1)
    elif not has_excl and should_have_excl:
        response = response.rstrip() + "!"

    # Question enforcement removed — injecting generic questions
    # ("Todo bien?", "Cómo vas?") made the bot sound like customer service.
    # Question generation is better handled by the LLM itself.

    return response
