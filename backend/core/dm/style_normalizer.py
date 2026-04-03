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
_eval_profile_cache: dict = {}


def _load_eval_profile_emoji_rate(creator_id: str) -> Optional[float]:
    """Load emoji_rate from evaluation_profiles/{creator_id}_style.json.

    This file is produced by CCEE (the style-profile worker). When it
    exists its value takes precedence over baseline_metrics because it
    is derived from a larger, more recent sample.

    Returns the rate as a fraction 0-1, or None if the file doesn't exist
    or lacks the field.
    """
    if creator_id in _eval_profile_cache:
        return _eval_profile_cache[creator_id]

    # Resolve relative to this file's location (backend root → evaluation_profiles/)
    _backend_root = Path(__file__).parent.parent.parent
    profile_path = _backend_root / "evaluation_profiles" / f"{creator_id}_style.json"
    try:
        import json
        with open(profile_path) as f:
            data = json.load(f)
        # Field may be stored as 0-1 fraction or 0-100 percentage;
        # normalise to 0-1.
        raw = data.get("emoji_rate")
        if raw is None:
            _eval_profile_cache[creator_id] = None
            return None
        rate = float(raw)
        if rate > 1.0:      # percentage → fraction
            rate = rate / 100.0
        rate = max(0.0, min(1.0, rate))
        _eval_profile_cache[creator_id] = rate
        logger.debug("[STYLE-NORM] eval_profile emoji_rate=%.3f for %s", rate, creator_id)
        return rate
    except FileNotFoundError:
        # File not yet created by CCEE worker — silent degradation to baseline/fallback
        _eval_profile_cache[creator_id] = None
        return None
    except Exception as e:
        logger.debug("[STYLE-NORM] eval_profile load failed for %s: %s", creator_id, e)
        _eval_profile_cache[creator_id] = None
        return None


def _get_creator_emoji_rate(creator_id: str) -> Optional[float]:
    """Resolve creator emoji rate as a 0-1 fraction.

    Priority:
      1. evaluation_profiles/{creator_id}_style.json  → "emoji_rate"
      2. DB / local baseline_metrics               → emoji.emoji_rate_pct / 100
      3. None  (caller will use 0.50 fallback)
    """
    # 1. CCEE evaluation profile (highest priority — most recent & accurate)
    rate = _load_eval_profile_emoji_rate(creator_id)
    if rate is not None:
        return rate

    # 2. Existing baseline (DB → local file)
    baseline = _load_baseline(creator_id)
    if baseline:
        pct = baseline.get("emoji", {}).get("emoji_rate_pct")
        if pct is not None:
            return float(pct) / 100.0

    return None


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

    result = response

    # ── 1. Exclamation normalization ─────────────────────────────────────────
    # Per-message probabilistic decision: keep_prob = creator_rate / bot_natural_rate.
    # Requires baseline; skipped gracefully when no profile exists.
    if "!" in result:
        baseline = _load_baseline(creator_id)
        if baseline:
            punct = baseline.get("punctuation", {})
            excl_rate = punct.get("has_exclamation_msg_pct", punct.get("exclamation_rate_pct", 50))
            bot_rates = _load_bot_natural_rates(creator_id)
            if bot_rates and bot_rates.get("excl_rate") is not None:
                model_excl_rate = float(bot_rates["excl_rate"])
                logger.debug("[STYLE-NORM] excl natural rate from DB: %.1f%% for %s", model_excl_rate, creator_id)
            else:
                model_excl_rate = float(os.getenv("STYLE_NORM_MODEL_EXCL_RATE", "86"))
                logger.debug("[STYLE-NORM] excl natural rate FALLBACK: %.1f%% for %s", model_excl_rate, creator_id)
            if model_excl_rate > 0 and excl_rate < model_excl_rate:
                keep_prob = min(1.0, excl_rate / model_excl_rate)
                if random.random() > keep_prob:
                    result = re.sub(r"!+", ".", result)
                    if "¡" in result:
                        result = result.replace("¡", "")
                    result = re.sub(r"\.{2,}", ".", result)

    # ── 2. Emoji normalization ───────────────────────────────────────────────
    # Direct-rate formula: keep_prob = creator_emoji_rate (0-1 fraction).
    # For each response: if random() > keep_prob → strip all emojis.
    # This guarantees output distribution matches creator rate without
    # needing bot-natural-rate measurements.
    #
    # Source priority for keep_prob:
    #   1. evaluation_profiles/{creator_id}_style.json  → "emoji_rate"
    #   2. DB / local baseline_metrics               → emoji.emoji_rate_pct / 100
    #   3. Fallback 0.50  (conservative: keep emoji in half of responses)
    if _has_emoji(result):
        keep_prob = _get_creator_emoji_rate(creator_id)
        if keep_prob is None:
            keep_prob = 0.50   # conservative fallback
            logger.debug("[STYLE-NORM] emoji keep_prob FALLBACK=0.50 for %s", creator_id)
        else:
            logger.debug("[STYLE-NORM] emoji keep_prob=%.3f for %s", keep_prob, creator_id)

        if random.random() > keep_prob:
            # Strip all emojis from this message
            stripped = _strip_emojis(result, keep_n=0)
            if len(stripped.strip()) >= 2:
                result = stripped
        else:
            # Keeping emojis — trim count to creator's per-emoji-message average.
            # avg_emoji_count is the unconditional mean (across all messages);
            # divide by keep_prob to get the conditional mean (only emoji-bearing
            # messages). Clamped to [1, 5] to prevent explosion for very low rates.
            baseline = _load_baseline(creator_id)
            avg_emoji_count = (baseline or {}).get("emoji", {}).get("avg_emoji_count")
            if avg_emoji_count is not None and keep_prob > 0:
                per_emoji_msg = avg_emoji_count / keep_prob
                target_n = max(1, min(5, round(per_emoji_msg)))
                trimmed = _strip_emojis(result, keep_n=target_n)
                if len(trimmed.strip()) >= 2:
                    result = trimmed

    return result.strip()
