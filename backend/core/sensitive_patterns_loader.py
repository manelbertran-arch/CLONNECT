"""
Multilingual Sensitive Pattern Loader.

Loads regex patterns and crisis resources from JSON files in
data/sensitive_patterns/{lang}.json. Each creator loads patterns for
their configured languages + universal patterns.

Usage:
    from core.sensitive_patterns_loader import load_patterns_for_languages

    # For a bilingual ES/CA creator
    patterns, resources = load_patterns_for_languages(["es", "ca"])
    # patterns = {"self_harm": [...], "eating_disorder": [...], ...}
    # resources = "crisis text for es + ca"

    # For an Italian creator
    patterns, resources = load_patterns_for_languages(["it"])
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

PATTERNS_DIR = Path(__file__).parent.parent / "data" / "sensitive_patterns"

# In-memory cache: frozenset(languages) -> (patterns_dict, resources_str)
_cache: Dict[frozenset, Tuple[Dict[str, List[str]], str]] = {}


def _load_single_language(lang: str) -> Tuple[Dict[str, List[str]], str]:
    """Load patterns from a single language JSON file."""
    path = PATTERNS_DIR / f"{lang}.json"
    if not path.exists():
        logger.debug("No sensitive patterns file for language: %s", lang)
        return {}, ""

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        patterns = data.get("patterns", {})
        resources = data.get("crisis_resources", "")
        logger.debug(
            "Loaded %d pattern categories for %s",
            len(patterns), lang,
        )
        return patterns, resources
    except Exception as e:
        logger.error("Failed to load sensitive patterns for %s: %s", lang, e)
        return {}, ""


def load_patterns_for_languages(
    languages: List[str],
) -> Tuple[Dict[str, List[str]], str]:
    """Load and merge patterns for multiple languages.

    Always includes _universal.json patterns. Deduplicates patterns
    within each category.

    Args:
        languages: List of ISO 639-1 language codes (e.g., ["es", "ca"])

    Returns:
        Tuple of (merged_patterns_dict, combined_crisis_resources)
    """
    cache_key = frozenset(languages)
    if cache_key in _cache:
        return _cache[cache_key]

    merged: Dict[str, List[str]] = {}
    resources_parts: List[str] = []

    # Always load universal patterns first
    langs_to_load = ["_universal"] + list(languages)

    for lang in langs_to_load:
        patterns, resources = _load_single_language(lang)
        for category, regex_list in patterns.items():
            if category not in merged:
                merged[category] = []
            # Deduplicate
            existing = set(merged[category])
            for regex in regex_list:
                if regex not in existing:
                    merged[category].append(regex)
                    existing.add(regex)
        if resources:
            resources_parts.append(resources)

    combined_resources = "\n\n".join(resources_parts)

    # Log summary
    total_patterns = sum(len(v) for v in merged.values())
    logger.info(
        "Loaded sensitive patterns: %d categories, %d total patterns for %s",
        len(merged), total_patterns, "+".join(languages),
    )

    result = (merged, combined_resources)
    _cache[cache_key] = result
    return result


def get_available_languages() -> List[str]:
    """List all available language codes (from files in patterns dir)."""
    if not PATTERNS_DIR.exists():
        return []
    return sorted(
        p.stem for p in PATTERNS_DIR.glob("*.json")
        if not p.stem.startswith("_")
    )


def get_creator_languages(creator_id: str) -> List[str]:
    """Get languages for a creator from calibration/Doc D.

    Falls back to ["es"] if no language info is available.
    """
    # Try calibration first
    try:
        from services.calibration_loader import load_calibration

        cal = load_calibration(creator_id)
        if cal:
            # Check few-shot examples for language distribution
            examples = cal.get("few_shot_examples", [])
            langs = set()
            for ex in examples:
                lang = ex.get("language", "")
                if lang in ("es", "ca", "en", "it", "fr", "pt"):
                    langs.add(lang)
                elif lang == "mixto":
                    langs.add("es")
                    langs.add("ca")
            if langs:
                return sorted(langs)
    except Exception:
        pass

    # Default
    return ["es"]
