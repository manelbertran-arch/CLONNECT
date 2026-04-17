"""Cache Boundary — prompt prefix optimization for DeepInfra prefix caching.

DeepInfra (OpenAI-compatible API) automatically caches KV states for
byte-identical request prefixes: $0.02/1M cached vs $0.13/1M input (85% off).

This module provides utilities to:
- Compute a hash of the static prefix (for stability verification)
- Measure prefix vs total prompt size
- Log structured cache metrics

Based on Claude Code patterns:
- P1: SYSTEM_PROMPT_DYNAMIC_BOUNDARY (prompts.ts:114)
- P10: recordPromptState() (promptCacheBreakDetection.ts:247)
- P12: Cache break vector tracking (promptCacheBreakDetection.ts:71)
"""

import hashlib
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# DeepInfra pricing (defaults, overridable via env)
_CACHED_PRICE = float(os.getenv("DEEPINFRA_CACHED_PRICE_PER_M", "0.02"))
_INPUT_PRICE = float(os.getenv("DEEPINFRA_INPUT_PRICE_PER_M", "0.13"))

# Approximate chars-per-token ratio for Gemma4 tokenizer
_CHARS_PER_TOKEN = int(os.getenv("CACHE_BOUNDARY_CHARS_PER_TOKEN", "4"))

# Previous prefix hash per creator (in-process tracking for cache break detection).
# Bounded by creator count (currently <100). If scaling beyond, add LRU eviction.
_previous_hashes: Dict[str, str] = {}


def compute_prefix_hash(prefix_text: str) -> str:
    """SHA-256 hash of the static prefix text.

    Used to verify byte-identical prefixes across requests.
    If the hash changes for the same creator, the cache is busted.
    """
    return hashlib.sha256(prefix_text.encode("utf-8")).hexdigest()[:16]


def measure_cache_boundary(
    static_prefix_chars: int,
    total_prompt_chars: int,
) -> Dict:
    """Compute cache boundary metrics.

    Args:
        static_prefix_chars: Character count of the cacheable static prefix.
        total_prompt_chars: Character count of the full system prompt.

    Returns:
        Dict with prefix/total sizes, ratio, and estimated savings.
    """
    prefix_tokens = static_prefix_chars // _CHARS_PER_TOKEN
    total_tokens = total_prompt_chars // _CHARS_PER_TOKEN
    dynamic_tokens = total_tokens - prefix_tokens

    ratio = static_prefix_chars / total_prompt_chars if total_prompt_chars > 0 else 0.0

    # Savings estimate: cached prefix at $0.02 vs $0.13, dynamic at full price
    cost_without_cache = total_tokens * _INPUT_PRICE / 1_000_000
    cost_with_cache = (
        prefix_tokens * _CACHED_PRICE / 1_000_000
        + dynamic_tokens * _INPUT_PRICE / 1_000_000
    )
    savings_pct = (
        (1 - cost_with_cache / cost_without_cache) * 100
        if cost_without_cache > 0
        else 0.0
    )

    return {
        "prefix_chars": static_prefix_chars,
        "prefix_tokens": prefix_tokens,
        "total_chars": total_prompt_chars,
        "total_tokens": total_tokens,
        "cache_ratio": round(ratio, 3),
        "savings_pct": round(savings_pct, 1),
    }


def check_cache_break(creator_id: str, current_hash: str) -> Optional[str]:
    """Detect if the static prefix changed for a creator.

    Returns None if no break (or first call), or the previous hash if changed.
    CC pattern: P10 recordPromptState() + checkResponseForCacheBreak().
    """
    prev = _previous_hashes.get(creator_id)
    _previous_hashes[creator_id] = current_hash

    if prev is None:
        return None  # First call for this creator — no baseline
    if prev == current_hash:
        return None  # Stable prefix — no break
    return prev  # Break detected — return old hash for logging


def log_cache_metrics(
    metrics: Dict,
    creator_id: str,
    prefix_hash: str,
    cache_break: Optional[str] = None,
) -> None:
    """Emit structured cache boundary log.

    Args:
        metrics: Output from measure_cache_boundary().
        creator_id: Creator slug.
        prefix_hash: Current prefix hash.
        cache_break: Previous hash if a break was detected, else None.
    """
    if cache_break:
        logger.warning(
            "[CacheBoundary] BREAK creator=%s prev_hash=%s new_hash=%s "
            "prefix=%d/%d chars (%d%% cacheable)",
            creator_id,
            cache_break,
            prefix_hash,
            metrics["prefix_chars"],
            metrics["total_chars"],
            int(metrics["cache_ratio"] * 100),
        )
    else:
        logger.info(
            "[CacheBoundary] creator=%s hash=%s prefix=%d/%d chars "
            "(%d%% cacheable, ~%.1f%% savings)",
            creator_id,
            prefix_hash,
            metrics["prefix_chars"],
            metrics["total_chars"],
            int(metrics["cache_ratio"] * 100),
            metrics["savings_pct"],
        )
