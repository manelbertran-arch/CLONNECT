"""
Calibration Loader — loads per-creator calibration data for production DM pipeline.

Calibration JSON contains:
- baseline: median_length, emoji_pct, exclamation_pct, question_frequency_pct
- few_shot_examples: [{context, user_message, response, length}, ...]
- response_pools: {greeting: [...], conversational: [...], ...}
- context_soft_max: {saludo: 22, casual: 25, ...}

Used by:
- core/dm_agent_v2.py (few-shot injection, tone enforcement targets)
- services/tone_enforcer.py (emoji/excl/question rate targets)

Universal: works for any creator_id with a calibration file.
"""

import json
import logging
import os
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# In-memory cache: creator_id -> (calibration_dict, timestamp)
_cache: Dict[str, Tuple[Optional[Dict], float]] = {}
_CACHE_TTL = float(os.getenv("CALIBRATION_CACHE_TTL", "300"))

CALIBRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "calibrations",
)


def load_calibration(creator_id: str) -> Optional[Dict]:
    """Load and cache calibration data for a creator.

    Looks for calibrations/{creator_id}.json.
    Returns None if no calibration exists.
    """
    now = time.time()
    if creator_id in _cache:
        cached_data, cached_ts = _cache[creator_id]
        if (now - cached_ts) < _CACHE_TTL:
            return cached_data

    cal_path = os.path.join(CALIBRATIONS_DIR, f"{creator_id}.json")
    if not os.path.isfile(cal_path):
        _cache[creator_id] = (None, now)
        return None

    try:
        with open(cal_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache[creator_id] = (data, now)
        baseline = data.get("baseline", {})
        n_fse = len(data.get("few_shot_examples", []))
        logger.info(
            "Loaded calibration for %s: median=%s, emoji=%.1f%%, fse=%d",
            creator_id,
            baseline.get("median_length"),
            baseline.get("emoji_pct", 0),
            n_fse,
        )
        return data
    except Exception as e:
        logger.error("Failed to load calibration for %s: %s", creator_id, e)
        _cache[creator_id] = (None, now)
        return None


def get_few_shot_section(calibration: Dict, max_examples: int = 5) -> str:
    """Format few-shot examples from calibration into a prompt section.

    Returns empty string if no examples exist.
    """
    examples: List[Dict] = calibration.get("few_shot_examples", [])
    if not examples:
        return ""

    selected = examples[:max_examples]
    lines = ["=== EJEMPLOS REALES DE CÓMO RESPONDES ==="]
    for ex in selected:
        user_msg = ex.get("user_message", "")
        response = ex.get("response", "")
        if user_msg and response:
            lines.append(f"Follower: {user_msg}")
            lines.append(f"Tú: {response}")
            lines.append("")
    lines.append("Responde de forma breve y natural, como en los ejemplos.")
    lines.append("=== FIN EJEMPLOS ===")
    return "\n".join(lines)


def invalidate_cache(creator_id: Optional[str] = None) -> None:
    """Clear cached calibration data."""
    if creator_id:
        _cache.pop(creator_id, None)
    else:
        _cache.clear()
