"""Auto-calibrate LLM generation parameters from creator message analysis.

Computes temperature, max_tokens, and soft_max_chars from real creator messages.
Universal: works for any creator with sufficient message history.

Temperature formula:
    temp = 0.5 + (emoji_rate * 0.15) + (length_cv_norm * 0.15) + (informal_score * 0.2)
    clamped to [0.5, 0.9]

Signals:
    - emoji_rate: fraction of messages containing emojis (expressiveness)
    - length_cv_norm: coefficient of variation of message length (inconsistency)
    - informal_score: density of informal markers per message (casualness)

Usage:
    from core.personality_extraction.auto_calibrator import auto_calibrate
    result = auto_calibrate(messages)
    # {"temperature": 0.78, "max_tokens": 83, "soft_max_chars": 95, "signals": {...}}
"""

import re
import statistics
from typing import Dict, List

# Broad emoji pattern covering most Unicode emoji ranges
_EMOJI_RE = re.compile(
    r"[\U0001f000-\U0001ffff"       # emoticons, symbols, dingbats, etc.
    r"\u2600-\u27bf"                # misc symbols
    r"\u2764\ufe0f"                 # heart
    r"\U0001fa70-\U0001faff"        # symbols & pictographs extended-A
    r"]"
)

# Informal markers — multilingual (ES, CA, PT, EN)
_INFORMAL_MARKERS = [
    # Laughter
    "jaja", "jeje", "jiij", "haha", "lol",
    # Exclamations (ES/CA)
    "ostia", "hostia", "buah", "buaah", "uff", "buf", "wow", "uala",
    # Affectionate address (ES/CA)
    "tia", "nena", "cuca", "bro", "reina", "amor", "cari",
    "guapa", "flor", "baby", "mami", "papi",
    # Fillers / slang
    "mola", "pues", "bua", "esque", "esq", "tio", "piba",
    # Abbreviations
    "tb", "tmb", "xq", "pq", "xfa", "dw", "np",
]

# Default values when insufficient data
_DEFAULTS = {
    "temperature": 0.7,
    "max_tokens": 100,
    "soft_max_chars": 60,
}

# Minimum messages needed for reliable calibration
MIN_MESSAGES = 30


def auto_calibrate(messages: List[str]) -> Dict:
    """Compute LLM generation parameters from creator message samples.

    Args:
        messages: List of creator (assistant) message strings.

    Returns:
        Dict with keys: temperature, max_tokens, soft_max_chars, signals.
        Falls back to safe defaults if insufficient data.
    """
    # Filter out non-text messages (stickers, photos, etc.)
    texts = [
        m for m in messages
        if m and len(m) > 1 and not m.startswith("[")
    ]

    if len(texts) < MIN_MESSAGES:
        return {**_DEFAULTS, "signals": {"status": "insufficient_data", "n": len(texts)}}

    # ── Signal 1: Emoji rate ──
    emoji_msgs = sum(1 for t in texts if _EMOJI_RE.search(t))
    emoji_rate = emoji_msgs / len(texts)

    # ── Signal 2: Length variance (coefficient of variation) ──
    lengths = [len(t) for t in texts]
    mean_len = statistics.mean(lengths)
    if mean_len > 0 and len(lengths) > 1:
        length_cv = statistics.stdev(lengths) / mean_len
    else:
        length_cv = 0.0
    # Normalize: CV of 2.0+ is max variability
    length_cv_norm = min(length_cv / 2.0, 1.0)

    # ── Signal 3: Informal marker density ──
    all_text_lower = " ".join(texts).lower()
    informal_count = sum(all_text_lower.count(w) for w in _INFORMAL_MARKERS)
    informal_score = min(informal_count / len(texts), 1.0)

    # ── Temperature ──
    temperature = (
        0.5
        + (emoji_rate * 0.15)
        + (length_cv_norm * 0.15)
        + (informal_score * 0.2)
    )
    temperature = round(max(0.5, min(0.9, temperature)), 2)

    # ── Max tokens: allow up to 2× the p95 message length in tokens ──
    # Generous: max_tokens is a ceiling, not a target. SBS/length enforcement
    # controls actual output length. We just need enough headroom.
    # ~3.5 chars/token for ES/CA text.
    sorted_lengths = sorted(lengths)
    p95_idx = min(int(len(sorted_lengths) * 0.95), len(sorted_lengths) - 1)
    p95 = sorted_lengths[p95_idx]
    max_tokens = max(80, min(300, int(p95 / 3.5) * 2))

    # ── Soft max chars (90th percentile) ──
    p90_idx = min(int(len(sorted_lengths) * 0.90), len(sorted_lengths) - 1)
    soft_max_chars = sorted_lengths[p90_idx]

    return {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "soft_max_chars": soft_max_chars,
        "signals": {
            "n": len(texts),
            "emoji_rate": round(emoji_rate, 3),
            "length_cv": round(length_cv, 2),
            "length_cv_norm": round(length_cv_norm, 2),
            "informal_score": round(informal_score, 3),
            "mean_length": round(mean_len, 1),
            "median_length": int(statistics.median(lengths)),
            "p90_chars": soft_max_chars,
            "p95_chars": p95,
        },
    }
