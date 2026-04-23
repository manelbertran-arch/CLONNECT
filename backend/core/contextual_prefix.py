"""
Universal Contextual Prefix for RAG Chunk Embedding.

Implements the Anthropic "Contextual Retrieval" pattern (reported +35-49% recall@20
on Anthropic's internal corpora): prepend a short creator-context summary to each
chunk BEFORE embedding so the vector captures "who + domain + location + language"
alongside the content. The prefix is auto-generated from the creator's DB profile.

Asymmetry — IMPORTANT:
    The prefix is prepended to DOCUMENT embeddings only. Search QUERIES must NOT
    be prefixed, or the query space gets biased toward the creator context and
    cosine similarity becomes distorted. SemanticRAG._semantic_search obeys this
    invariant (verified by tests/test_contextual_prefix.py).

Configuration (env vars, see core/config/contextual_prefix_config.py):
    ENABLE_CONTEXTUAL_PREFIX_EMBED=true    master switch (ablation requires reindex)
    CONTEXTUAL_PREFIX_CACHE_SIZE=50
    CONTEXTUAL_PREFIX_CACHE_TTL=300
    CONTEXTUAL_PREFIX_CAP_CHARS=500
    CONTEXTUAL_PREFIX_MAX_SPECIALTIES=3
    CONTEXTUAL_PREFIX_MAX_PRODUCTS=5
    CONTEXTUAL_PREFIX_MAX_FAQS=3
    CONTEXTUAL_PREFIX_MIN_BIO_LEN=10

Observability (Prometheus, via core.observability.metrics.emit_metric):
    contextual_prefix_builds_total{creator_id, source, has_prefix}
    contextual_prefix_cache_hits_total{creator_id}
    contextual_prefix_cache_misses_total{creator_id}
    contextual_prefix_errors_total{creator_id, error_class}
    contextual_prefix_length_chars{creator_id} (histogram)
    contextual_prefix_truncations_total{creator_id}

Usage:
    from core.contextual_prefix import build_contextual_prefix, generate_embedding_with_context

    prefix = build_contextual_prefix("iris_bertran")
    # -> "Iris (@iraais5) ofrece ... en Barcelona. Habla castellano y catalán.\n\n"

    embedding = generate_embedding_with_context("Barre costs 5€", "iris_bertran")
"""

from __future__ import annotations

import logging
from typing import List, Optional

from core.cache import BoundedTTLCache
from core.config import contextual_prefix_config as _cfg

logger = logging.getLogger(__name__)


_prefix_cache: BoundedTTLCache = BoundedTTLCache(
    max_size=_cfg.CACHE_SIZE,
    ttl_seconds=_cfg.CACHE_TTL_SECONDS,
)


def _emit(metric: str, value: float = 1, **labels) -> None:
    """Fire-and-forget metric emission. Never raises — observability must not break indexing."""
    try:
        from core.observability.metrics import emit_metric
        emit_metric(metric, value, **labels)
    except Exception:  # pragma: no cover
        pass


def _truncate_at_word_boundary(text: str, cap_chars: int) -> str:
    """Truncate to <= cap_chars, preferring last space to avoid mid-word cuts.

    Always appends ".\n\n". Leaves room (3 chars) for the terminator.
    """
    budget = cap_chars - 3
    if len(text) <= budget:
        return text + ".\n\n"
    truncated = text[:budget]
    last_space = truncated.rfind(" ")
    if last_space >= int(budget * 0.6):
        truncated = truncated[:last_space]
    return truncated + ".\n\n"


def build_contextual_prefix(creator_id: str) -> str:
    """Auto-generate a contextual prefix for RAG chunk embedding.

    Loads creator profile from DB and composes 1-3 sentences about:
    name + handle, domain/specialties, location, language/dialect, formality.

    Returns "" if disabled by flag, creator not found, or any build error.
    """
    if not _cfg.ENABLE_CONTEXTUAL_PREFIX_EMBED:
        return ""

    cached = _prefix_cache.get(creator_id)
    if cached is not None:
        _emit("contextual_prefix_cache_hits_total", creator_id=creator_id)
        return cached

    _emit("contextual_prefix_cache_misses_total", creator_id=creator_id)
    prefix, source = _build_prefix_from_db(creator_id)
    _prefix_cache.set(creator_id, prefix)

    _emit(
        "contextual_prefix_builds_total",
        creator_id=creator_id,
        source=source,
        has_prefix=str(bool(prefix)).lower(),
    )
    if prefix:
        _emit("contextual_prefix_length_chars", value=len(prefix), creator_id=creator_id)
    return prefix


def invalidate_cache(creator_id: Optional[str] = None) -> int:
    """Invalidate prefix cache for a single creator or all.

    Returns number of entries removed. Safe to call from admin endpoints after
    editing `knowledge_about` so the next build picks up fresh data within the
    next TTL window (does NOT reindex existing vectors — that requires a
    separate content_refresh job).
    """
    if creator_id is None:
        size = len(_prefix_cache)
        _prefix_cache.clear()
        return size
    if creator_id in _prefix_cache:
        _prefix_cache.pop(creator_id)
        return 1
    return 0


def _build_prefix_from_db(creator_id: str) -> tuple[str, str]:
    """Build prefix + winning source tag. Returns ("", PREFIX_SOURCE_EMPTY) on failure."""
    try:
        from core.creator_data_loader import get_creator_data as _get_creator_data

        data = _get_creator_data(creator_id, use_cache=True)
        if not data or not data.profile.name:
            return "", _cfg.PREFIX_SOURCE_EMPTY

        parts: List[str] = []
        source = _cfg.PREFIX_SOURCE_NAME_ONLY

        name = data.profile.clone_name or data.profile.name
        ka = data.profile.knowledge_about or {}

        specialties = ka.get("specialties") or []
        if not isinstance(specialties, list):
            specialties = [str(specialties)]
        bio = ka.get("bio") or ""
        ig_handle = ka.get("instagram_username") or ""

        # Fallback: derive domain from product names when knowledge_about is sparse
        used_products_fallback = False
        if not specialties and not bio and data.products:
            product_names = [p.name for p in data.products[: _cfg.MAX_PRODUCTS] if p.name]
            if product_names:
                specialties = product_names
                used_products_fallback = True

        name_part = name
        if ig_handle:
            name_part = f"{name} (@{ig_handle.lstrip('@')})"

        if specialties:
            spec_str = ", ".join(str(s) for s in specialties[: _cfg.MAX_SPECIALTIES])
            parts.append(f"{name_part} ofrece {spec_str}")
            source = _cfg.PREFIX_SOURCE_PRODUCTS if used_products_fallback else _cfg.PREFIX_SOURCE_SPECIALTIES
        elif bio:
            first_sentence = bio.split(".")[0].strip()
            if first_sentence and len(first_sentence) > _cfg.MIN_BIO_LEN:
                parts.append(f"{name_part}: {first_sentence}")
                source = _cfg.PREFIX_SOURCE_BIO
            else:
                parts.append(name_part)
        else:
            parts.append(name_part)

        location = ka.get("location") or ""
        if location:
            parts[-1] += f" en {location}"

        # Language/dialect: prefer the creator-provided human-readable label
        # (tone_profile.dialect_label) over the raw enum tag. If the creator
        # has not populated the label, we fall back to the raw dialect literal —
        # no hardcoded translation dict lives in code.
        tp = data.tone_profile
        dialect = tp.dialect if tp else "neutral"
        dialect_label = (tp.dialect_label if tp else "") or ""
        if dialect_label:
            parts.append(f"Habla {dialect_label}")
        elif dialect and dialect != "neutral":
            parts.append(f"Habla {dialect}")

        # Formality: same DB-first pattern. Raw formality tag is an internal
        # enum ('informal'/'formal'/'mixed'/'casual') — only emit if the
        # creator has provided a human-readable formality_label.
        formality_label = (tp.formality_label if tp else "") or ""
        if formality_label:
            parts.append(formality_label)

        if source == _cfg.PREFIX_SOURCE_NAME_ONLY and data.faqs:
            faq_sample = [f.question for f in data.faqs[: _cfg.MAX_FAQS] if f.question]
            if faq_sample:
                topics = "; ".join(faq_sample)
                parts.append(f"Temas frecuentes: {topics}")
                source = _cfg.PREFIX_SOURCE_FAQ

        if not parts:
            return "", _cfg.PREFIX_SOURCE_EMPTY

        raw = ". ".join(parts)
        prefix = _truncate_at_word_boundary(raw, _cfg.CAP_CHARS)
        if len(raw) + 3 > _cfg.CAP_CHARS:
            _emit("contextual_prefix_truncations_total", creator_id=creator_id)

        logger.info(
            "[CONTEXTUAL-PREFIX] built creator=%s source=%s len=%d",
            creator_id, source, len(prefix),
        )
        return prefix, source

    except Exception as e:
        err_class = type(e).__name__
        logger.warning(
            "[CONTEXTUAL-PREFIX] failed creator=%s error_class=%s msg=%s",
            creator_id, err_class, e,
        )
        _emit("contextual_prefix_errors_total", creator_id=creator_id, error_class=err_class)
        return "", _cfg.PREFIX_SOURCE_EMPTY


def generate_embedding_with_context(
    text: str, creator_id: str,
) -> Optional[List[float]]:
    """Generate embedding with contextual prefix prepended.

    For DOCUMENT embeddings only — search queries must NOT use this.
    The prefix is invisible in stored content but baked into the vector.
    """
    from core.embeddings import generate_embedding

    prefix = build_contextual_prefix(creator_id)
    return generate_embedding(prefix + text if prefix else text)


def generate_embeddings_batch_with_context(
    texts: List[str], creator_id: str,
) -> List[Optional[List[float]]]:
    """Batch variant: generate embeddings with contextual prefix prepended."""
    from core.embeddings import generate_embeddings_batch

    prefix = build_contextual_prefix(creator_id)
    if prefix:
        prefixed = [prefix + t for t in texts]
    else:
        prefixed = list(texts)
    return generate_embeddings_batch(prefixed)
