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
import random
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# In-memory cache: creator_id -> (calibration_dict, timestamp)
_cache: Dict[str, Tuple[Optional[Dict], float]] = {}
_CACHE_TTL = float(os.getenv("CALIBRATION_CACHE_TTL", "300"))

# Cache for pre-computed example embeddings: content_hash -> List[Optional[List[float]]]
_example_embeddings_cache: Dict[int, List] = {}

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

    # Prefer unified pool (larger, higher retrieval quality) over base calibration
    cal_path = os.path.join(CALIBRATIONS_DIR, f"{creator_id}_unified.json")
    if not os.path.isfile(cal_path):
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


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors using numpy."""
    import numpy as np
    va, vb = np.array(a, dtype=float), np.array(b, dtype=float)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


def _select_examples_by_similarity(
    examples: List[Dict],
    current_message: str,
    n_semantic: int,
    n_random: int,
) -> List[Dict]:
    """Return n_semantic examples closest to current_message + n_random from the rest.

    Falls back to pure random.sample() if embeddings are unavailable.
    """
    try:
        from core.embeddings import generate_embedding, generate_embeddings_batch

        # Cache example embeddings by content hash (stable across calls)
        cache_key = hash(tuple(ex.get("user_message", "") for ex in examples))
        if cache_key not in _example_embeddings_cache:
            texts = [ex.get("user_message", "") for ex in examples]
            _example_embeddings_cache[cache_key] = generate_embeddings_batch(texts)
            logger.debug(
                "Computed embeddings for %d few-shot examples (cache key %d)",
                len(texts), cache_key,
            )

        example_embeddings = _example_embeddings_cache[cache_key]
        msg_embedding = generate_embedding(current_message)

        if not msg_embedding:
            raise ValueError("Empty message embedding")

        # Rank examples by cosine similarity to current_message
        scored = [
            (_cosine_similarity(msg_embedding, emb), i)
            for i, emb in enumerate(example_embeddings)
            if emb is not None
        ]
        scored.sort(reverse=True)

        top_indices = {i for _, i in scored[:n_semantic]}
        semantic_examples = [examples[i] for _, i in scored[:n_semantic]]
        remaining = [ex for i, ex in enumerate(examples) if i not in top_indices]
        random_examples = random.sample(remaining, min(n_random, len(remaining)))

        logger.debug(
            "Few-shot: %d semantic (top sim=%.2f) + %d random",
            len(semantic_examples),
            scored[0][0] if scored else 0,
            len(random_examples),
        )
        return semantic_examples + random_examples

    except Exception as e:
        logger.debug("Semantic few-shot selection failed, using random: %s", e)
        k = min(n_semantic + n_random, len(examples))
        return random.sample(examples, k)


def detect_message_language(text: str) -> Optional[str]:
    """Detect the language of a message, including ca-es code-switching.

    Returns 'ca', 'es', 'ca-es' (code-switching), other ISO 639-1 codes, or None.

    Barcelona-style code-switching (ca-es) is detected when a message contains
    markers from BOTH Catalan and Spanish. This is common for bilingual speakers
    who mix mid-sentence: "Tinc la veu molt malament pero bueno es lo que hay".

    When 'ca-es' is returned, the few-shot pool should NOT be filtered by language,
    so the LLM sees examples in both languages and learns to mix naturally.
    """
    import re

    stripped = text.strip()
    if len(stripped) < 10:
        return None

    lower = stripped.lower()

    # Catalan-only markers (words that don't exist in Spanish)
    ca_only = re.findall(
        r"\b(tinc|estic|però|molt|doncs|també|perquè|aquí|això|tinc|vull|"
        r"puc|fes|mira|clar|setmana|dimarts|dijous|dissabte|diumenge|"
        r"què|què tal|gracies|gràcies|bona nit|bona tarda|bon dia|"
        r"nosaltres|ells|elles|puguis|vulguis|necessites|"
        r"xk|pq|xfi|na mais)\b",
        lower,
    )
    # Spanish-only markers (words that don't exist in Catalan)
    es_only = re.findall(
        r"\b(tengo|estoy|pero|mucho|entonces|también|porque|aquí|quiero|"
        r"puedo|necesito|bueno|gracias|vale|claro|genial|"
        r"miércoles|jueves|sábado|domingo|semana|"
        r"nosotros|ellos|ellas|puedes|quieres|necesitas)\b",
        lower,
    )

    if ca_only and es_only:
        logger.debug(
            "Code-switching detected: ca_markers=%d (%s) es_markers=%d (%s)",
            len(ca_only), ca_only[:3], len(es_only), es_only[:3],
        )
        return "ca-es"

    try:
        from langdetect import detect
        return detect(stripped)
    except Exception:
        return None


def get_few_shot_section(
    calibration: Dict,
    max_examples: int = 5,
    current_message: Optional[str] = None,
    lead_language: Optional[str] = None,
) -> str:
    """Format few-shot examples from calibration into a prompt section.

    When current_message is provided, selects half by semantic similarity to
    the message and half randomly for variety. Falls back to random if
    embeddings are unavailable.

    When lead_language is 'ca' or 'es', pre-filters the pool to prefer examples
    in that language + 'mixto' examples. Falls back to full pool if the filtered
    pool is too small.

    Returns empty string if no examples exist.
    """
    examples: List[Dict] = calibration.get("few_shot_examples", [])
    if not examples:
        return ""

    # Language-aware pool filtering: prefer same-language + mixto examples.
    # For code-switching (ca-es): use FULL pool so LLM sees both languages.
    pool = examples
    if lead_language and lead_language != "ca-es":
        filtered = [
            ex for ex in examples
            if ex.get("language") in (lead_language, "mixto")
        ]
        # Only use the filtered pool if it has enough variety (≥ max_examples)
        if len(filtered) >= max_examples:
            pool = filtered
            logger.debug(
                "Few-shot: language filter=%s reduced pool %d→%d",
                lead_language, len(examples), len(pool),
            )
    elif lead_language == "ca-es":
        logger.debug("Few-shot: code-switching detected, using full pool (%d examples)", len(pool))

    if current_message and len(pool) > max_examples:
        n_semantic = max_examples // 2          # e.g. 5 of 10
        n_random = max_examples - n_semantic    # e.g. 5 of 10
        selected = _select_examples_by_similarity(
            pool, current_message, n_semantic, n_random
        )
    else:
        k = min(max_examples, len(pool))
        selected = random.sample(pool, k)

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
