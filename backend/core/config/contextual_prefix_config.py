"""
Configuration for core/contextual_prefix.py — Universal Contextual Prefix.

All tunables previously hardcoded live here, driven by env vars so they can be
tuned per-environment without code changes.

IMPORTANT: this module contains ZERO hardcoded linguistic content. Dialect and
formality human-readable labels are read from the creator's own
tone_profile.profile_data fields (dialect_label, formality_label). If absent,
the raw dialect/formality literal is emitted — the creator is responsible for
populating these per their own language/variety. No translation dictionary
lives in code.

Env vars (all optional, all have production defaults):
  - ENABLE_CONTEXTUAL_PREFIX_EMBED   (bool, default true)
  - CONTEXTUAL_PREFIX_CACHE_SIZE      (int,  default 50)
  - CONTEXTUAL_PREFIX_CACHE_TTL       (int,  default 300)
  - CONTEXTUAL_PREFIX_CAP_CHARS       (int,  default 500)
  - CONTEXTUAL_PREFIX_MAX_SPECIALTIES (int,  default 3)
  - CONTEXTUAL_PREFIX_MAX_PRODUCTS    (int,  default 5)
  - CONTEXTUAL_PREFIX_MAX_FAQS        (int,  default 3)
  - CONTEXTUAL_PREFIX_MIN_BIO_LEN     (int,  default 10)
"""

from __future__ import annotations

import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 0, maximum: int = 10_000_000) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except (ValueError, AttributeError):
        logger.warning("[contextual_prefix_config] %s=%r is not int, using default %d", name, raw, default)
        return default
    if value < minimum or value > maximum:
        logger.warning("[contextual_prefix_config] %s=%d out of [%d,%d], using default %d",
                       name, value, minimum, maximum, default)
        return default
    return value


ENABLE_CONTEXTUAL_PREFIX_EMBED: bool = _env_bool("ENABLE_CONTEXTUAL_PREFIX_EMBED", True)

CACHE_SIZE: int = _env_int("CONTEXTUAL_PREFIX_CACHE_SIZE", 50, minimum=1, maximum=10_000)
CACHE_TTL_SECONDS: int = _env_int("CONTEXTUAL_PREFIX_CACHE_TTL", 300, minimum=1, maximum=86_400)
CAP_CHARS: int = _env_int("CONTEXTUAL_PREFIX_CAP_CHARS", 500, minimum=50, maximum=8_000)
MAX_SPECIALTIES: int = _env_int("CONTEXTUAL_PREFIX_MAX_SPECIALTIES", 3, minimum=1, maximum=20)
MAX_PRODUCTS: int = _env_int("CONTEXTUAL_PREFIX_MAX_PRODUCTS", 5, minimum=1, maximum=20)
MAX_FAQS: int = _env_int("CONTEXTUAL_PREFIX_MAX_FAQS", 3, minimum=1, maximum=20)
MIN_BIO_LEN: int = _env_int("CONTEXTUAL_PREFIX_MIN_BIO_LEN", 10, minimum=0, maximum=200)


PREFIX_SOURCE_SPECIALTIES = "specialties"
PREFIX_SOURCE_BIO = "bio"
PREFIX_SOURCE_PRODUCTS = "products_fallback"
PREFIX_SOURCE_FAQ = "faq_fallback"
PREFIX_SOURCE_NAME_ONLY = "name_only"
PREFIX_SOURCE_EMPTY = "empty"


def snapshot() -> Dict[str, object]:
    return {
        "ENABLE_CONTEXTUAL_PREFIX_EMBED": ENABLE_CONTEXTUAL_PREFIX_EMBED,
        "CACHE_SIZE": CACHE_SIZE,
        "CACHE_TTL_SECONDS": CACHE_TTL_SECONDS,
        "CAP_CHARS": CAP_CHARS,
        "MAX_SPECIALTIES": MAX_SPECIALTIES,
        "MAX_PRODUCTS": MAX_PRODUCTS,
        "MAX_FAQS": MAX_FAQS,
        "MIN_BIO_LEN": MIN_BIO_LEN,
        "label_source": "tone_profile.dialect_label / tone_profile.formality_label (DB-driven, no hardcoded dict)",
    }
