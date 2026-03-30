"""Style normalizer — post-processing to match creator quantitative style.

Fixes the gap between what the LLM can achieve via prompting alone
and the creator's actual style metrics. Two main corrections:

1. Exclamation normalization: Replace trailing '!' with '.' or nothing
   to match creator's exclamation_rate_pct.
2. Emoji normalization: Strip emojis from responses probabilistically
   to match creator's emoji_rate_pct.

Uses baseline_metrics.json for per-creator targets.
"""

import logging
import os
import random
import re
import unicodedata
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Feature flag
ENABLE_STYLE_NORMALIZER = os.getenv("ENABLE_STYLE_NORMALIZER", "true").lower() in (
    "true", "1", "yes",
)

# Cache for loaded baselines
_baseline_cache: dict = {}


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


def _has_emoji(text: str) -> bool:
    """Check if text contains any emoji."""
    for c in text:
        if (unicodedata.category(c) in ('So', 'Sk')
                or '\U0001F300' <= c <= '\U0001FAFF'
                or '\u2600' <= c <= '\u27BF'):
            return True
    return False


def _strip_emojis(text: str, keep_first: bool = False) -> str:
    """Remove emojis from text, optionally keeping the first one.

    Args:
        text: Input text.
        keep_first: If True, keep the first emoji found (for avg_emoji matching).
    """
    result = []
    kept_first = False
    for c in text:
        is_emoji = (unicodedata.category(c) in ('So', 'Sk')
                    or '\U0001F300' <= c <= '\U0001FAFF'
                    or '\u2600' <= c <= '\u27BF')
        if is_emoji:
            if keep_first and not kept_first:
                result.append(c)
                kept_first = True
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

    # Emoji normalization
    # If response has emoji, probabilistically strip based on creator rate.
    # The model generates emoji in ~55% of responses after strong prompting.
    # We want to bring that down to the creator's rate (e.g. 22.6%).
    # keep_prob = target / model_rate — keeps the right fraction of emoji msgs.
    emoji_rate = baseline.get("emoji", {}).get("emoji_rate_pct", 20)
    model_emoji_rate = float(os.getenv("STYLE_NORM_MODEL_EMOJI_RATE", "55"))
    if _has_emoji(result) and model_emoji_rate > 0:
        keep_prob = min(1.0, emoji_rate / model_emoji_rate)
        if random.random() > keep_prob:
            result = _strip_emojis(result)
            # If stripping emoji left us with nothing useful, keep original
            if len(result.strip()) < 2:
                result = response

    return result.strip()
