"""Style normalizer — post-processing to match creator quantitative style.

Fixes the gap between what the LLM can achieve via prompting alone
and the creator's actual style metrics:

1. Exclamation normalization: per-mark probabilistic '!' → '.' replacement.
   keep_prob derived from creator baseline / measured bot natural rate.
2. Emoji normalization: probabilistic strip based on creator emoji_rate_pct.

Bot natural rates (measured from Level 1 runs) are stored in
creator_profiles(profile_type='bot_natural_rates') and read at runtime.
When unavailable, env-var fallbacks are used and logged.
"""

import logging
import os
import random
import re
import unicodedata
from pathlib import Path

from typing import Optional

from core.emoji_utils import is_emoji_char

logger = logging.getLogger(__name__)

# Feature flag
ENABLE_STYLE_NORMALIZER = os.getenv("ENABLE_STYLE_NORMALIZER", "true").lower() in (
    "true", "1", "yes",
)

# Cache for loaded baselines and bot natural rates
_baseline_cache: dict = {}
_natural_rates_cache: dict = {}


def _load_baseline(creator_id: str) -> Optional[dict]:
    """Load baseline metrics for creator, cached.
    Priority: DB → local file → None."""
    if creator_id in _baseline_cache:
        return _baseline_cache[creator_id]

    # 1. Try DB
    try:
        from services.creator_profile_service import get_baseline
        db_data = get_baseline(creator_id)
        if db_data:
            _baseline_cache[creator_id] = db_data.get("metrics", db_data)
            return _baseline_cache[creator_id]
    except Exception:
        pass

    # 2. Fallback: local file
    path = Path("tests/cpe_data") / creator_id / "baseline_metrics.json"
    try:
        import json
        with open(path) as f:
            data = json.load(f)
        _baseline_cache[creator_id] = data.get("metrics", {})
        return _baseline_cache[creator_id]
    except (FileNotFoundError, Exception) as e:
        logger.debug("No baseline for %s: %s", creator_id, e)
        _baseline_cache[creator_id] = None
        return None


def _load_bot_natural_rates(creator_id: str) -> Optional[dict]:
    """Load measured bot natural rates from DB, cached.

    Populated by Level 1 runs or auto-provisioning.
    Returns dict with keys like 'excl_rate', 'question_rate', etc.
    Returns None if no measurements exist yet.
    """
    if creator_id in _natural_rates_cache:
        return _natural_rates_cache[creator_id]

    try:
        from services.creator_profile_service import get_profile
        data = get_profile(creator_id, "bot_natural_rates")
        _natural_rates_cache[creator_id] = data
        return data
    except Exception:
        _natural_rates_cache[creator_id] = None
        return None


def _has_emoji(text: str) -> bool:
    """Check if text contains any emoji."""
    return any(is_emoji_char(c) for c in text)


def _strip_emojis(text: str, keep_n: int = 0) -> str:
    """Remove emojis from text, optionally keeping the first N.

    Args:
        text: Input text.
        keep_n: Number of emojis to keep (0 = remove all).
    """
    result = []
    kept = 0
    for c in text:
        if is_emoji_char(c):
            if kept < keep_n:
                result.append(c)
                kept += 1
                continue
            continue
        result.append(c)
    cleaned = "".join(result)
    cleaned = re.sub(r"  +", " ", cleaned).strip()
    return cleaned


def normalize_style(
    response: str,
    creator_id: str,
) -> str:
    """Apply post-processing style normalization to match creator metrics.

    Args:
        response: Generated LLM response.
        creator_id: Creator slug for loading baseline.

    Returns:
        Normalized response string.
    """
    if not ENABLE_STYLE_NORMALIZER:
        return response

    baseline = _load_baseline(creator_id)
    if not baseline:
        return response

    result = response

    # 1. Exclamation normalization
    # Per-message decision: keep_prob = creator_rate / bot_natural_rate.
    # Uses has_exclamation_msg_pct (message-level, WhatsApp-calibrated) when available,
    # falling back to exclamation_rate_pct. Bot natural rate from DB or env fallback.
    punct = baseline.get("punctuation", {})
    excl_rate = punct.get("has_exclamation_msg_pct", punct.get("exclamation_rate_pct", 50))
    bot_rates = _load_bot_natural_rates(creator_id)
    if bot_rates and bot_rates.get("excl_rate") is not None:
        model_excl_rate = float(bot_rates["excl_rate"])
        logger.debug("[STYLE-NORM] excl natural rate from DB: %.1f%% for %s", model_excl_rate, creator_id)
    else:
        model_excl_rate = float(os.getenv("STYLE_NORM_MODEL_EXCL_RATE", "86"))
        logger.debug("[STYLE-NORM] excl natural rate FALLBACK: %.1f%% for %s", model_excl_rate, creator_id)
    if "!" in result and model_excl_rate > 0 and excl_rate < model_excl_rate:
        # Per-message keep probability: creator_rate / bot_natural_rate
        keep_prob = min(1.0, excl_rate / model_excl_rate)
        if random.random() > keep_prob:
            result = re.sub(r"!+", ".", result)
            # Clean up orphaned '¡' (no matching '!')
            if "¡" in result:
                result = result.replace("¡", "")
            # Remove double periods
            result = re.sub(r"\.{2,}", ".", result)

    # 2. Emoji normalization
    # Two-level control:
    #   a) Message-level: probabilistically strip ALL emojis (controls has_emoji %).
    #      keep_prob = creator_emoji_rate_pct / bot_natural_emoji_rate.
    #   b) Count-level: when keeping emojis, trim to creator's avg_emoji_count
    #      (controls emoji_count per message).
    emoji_rate = baseline.get("emoji", {}).get("emoji_rate_pct", 20)
    avg_emoji_count = baseline.get("emoji", {}).get("avg_emoji_count")
    if bot_rates and bot_rates.get("emoji_rate") is not None:
        model_emoji_rate = float(bot_rates["emoji_rate"])
    else:
        model_emoji_rate = float(os.getenv("STYLE_NORM_MODEL_EMOJI_RATE", "55"))
    if _has_emoji(result) and model_emoji_rate > 0:
        keep_prob = min(1.0, emoji_rate / model_emoji_rate)
        if random.random() > keep_prob:
            # Strip all emojis from this message
            result = _strip_emojis(result, keep_n=0)
            if len(result.strip()) < 2:
                result = response
        elif avg_emoji_count is not None:
            # Keep emojis but trim to creator's per-emoji-message average.
            # avg_emoji_count is across ALL messages; divide by emoji_rate to
            # get the count conditioned on the message having emoji at all.
            emoji_frac = max(0.01, emoji_rate / 100)
            per_emoji_msg = avg_emoji_count / emoji_frac
            target_n = max(1, round(per_emoji_msg))
            result = _strip_emojis(result, keep_n=target_n)
            if len(result.strip()) < 2:
                result = response

    return result.strip()
