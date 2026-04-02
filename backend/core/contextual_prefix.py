"""
Universal Contextual Prefix for RAG Chunk Embedding.

Implements the Anthropic "Contextual Retrieval" pattern (+49% retrieval quality):
Prepend a short creator-context summary to each chunk BEFORE embedding so the
vector captures "who + domain + location + language" alongside the content.

The prefix is auto-generated from the creator's DB profile, NOT hardcoded.

Usage:
    from core.contextual_prefix import build_contextual_prefix, generate_embedding_with_context

    # Build prefix for any creator
    prefix = build_contextual_prefix("iris_bertran")
    # → "Iris Bertran es instructora de fitness en Barcelona. Habla castellano/catalán.\n\n"

    # Embed with context (for document embeddings only, NOT search queries)
    embedding = generate_embedding_with_context("Barre costs 5€", "iris_bertran")
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Cache prefix strings per creator to avoid repeated DB lookups + string building.
# Relies on get_creator_data()'s own 5-min cache underneath.
from core.cache import BoundedTTLCache

_prefix_cache: BoundedTTLCache = BoundedTTLCache(max_size=50, ttl_seconds=300)


def build_contextual_prefix(creator_id: str) -> str:
    """Auto-generate a contextual prefix for RAG chunk embedding.

    Loads creator profile from DB and composes a 1-3 sentence summary of:
    - Creator name and handle
    - Domain/specialties
    - Location
    - Language/dialect

    Returns "" if creator not found or data insufficient.
    """
    cached = _prefix_cache.get(creator_id)
    if cached is not None:
        return cached

    prefix = _build_prefix_from_db(creator_id)
    _prefix_cache.set(creator_id, prefix)
    return prefix


def _build_prefix_from_db(creator_id: str) -> str:
    """Build prefix from DB data. Returns "" on any failure.

    Uses multiple fallback sources when knowledge_about is sparse:
    1. knowledge_about.specialties (best source)
    2. knowledge_about.bio first sentence
    3. Product names → inferred domain (universal fallback)
    """
    try:
        from core.creator_data_loader import get_creator_data as _get_creator_data

        data = _get_creator_data(creator_id, use_cache=True)
        if not data or not data.profile or not data.profile.name:
            return ""

        parts = []

        # Part 1: Name + specialties
        name = data.profile.clone_name or data.profile.name
        ka = data.profile.knowledge_about or {}

        # Try to get specialties/domain from knowledge_about
        specialties = ka.get("specialties", [])
        bio = ka.get("bio", "")
        ig_handle = ka.get("instagram_username", "")

        # Fallback: derive specialties from product names when knowledge_about is sparse
        if not specialties and not bio and data.products:
            product_names = [p.name for p in data.products[:5] if p.name]
            if product_names:
                specialties = product_names

        name_part = name
        if ig_handle:
            name_part = f"{name} (@{ig_handle.lstrip('@')})"

        if specialties:
            if isinstance(specialties, list):
                spec_str = ", ".join(specialties[:3])
            else:
                spec_str = str(specialties)
            parts.append(f"{name_part} ofrece {spec_str}")
        elif bio:
            # Use first sentence of bio as fallback
            first_sentence = bio.split(".")[0].strip()
            if first_sentence and len(first_sentence) > 10:
                parts.append(f"{name_part}: {first_sentence}")
            else:
                parts.append(name_part)
        else:
            parts.append(name_part)

        # Part 2: Location
        location = ka.get("location", "")
        if location:
            parts[-1] += f" en {location}"

        # Part 3: Language/dialect
        dialect = data.tone_profile.dialect if data.tone_profile else "neutral"
        if dialect and dialect != "neutral":
            _DIALECT_LABELS = {
                "rioplatense": "español rioplatense",
                "mexican": "español mexicano",
                "catalan": "castellano y catalán",
                "catalan_mixed": "castellano y catalán mezclados",
                "italian": "italiano",
                "english": "inglés",
                "formal_spanish": "español formal",
            }
            lang_label = _DIALECT_LABELS.get(dialect, dialect)
            parts.append(f"Habla {lang_label}")

        # Part 4: Formality/style hint
        formality = data.tone_profile.formality if data.tone_profile else "informal"
        if formality == "formal":
            parts.append("Estilo formal y profesional")
        elif formality == "casual":
            parts.append("Estilo muy informal y cercano")

        # Part 5: FAQ domain hint (when no specialties/bio available)
        if len(parts) == 1 and data.faqs:
            # Only name so far — add FAQ topic hint
            faq_sample = [f.question for f in data.faqs[:3] if f.question]
            if faq_sample:
                topics = "; ".join(faq_sample)
                parts.append(f"Temas frecuentes: {topics}")

        if not parts:
            return ""

        prefix = ". ".join(parts) + ".\n\n"

        # Cap at 500 chars to avoid eating too much embedding capacity
        if len(prefix) > 500:
            prefix = prefix[:497] + ".\n\n"

        logger.info(
            "[CONTEXTUAL-PREFIX] Built prefix for %s: %d chars",
            creator_id, len(prefix),
        )
        return prefix

    except Exception as e:
        logger.warning("[CONTEXTUAL-PREFIX] Failed to build for %s: %s", creator_id, e)
        return ""


def generate_embedding_with_context(
    text: str, creator_id: str,
) -> Optional[List[float]]:
    """Generate embedding with contextual prefix prepended.

    For DOCUMENT embeddings only — search queries must NOT use this.
    The prefix is invisible in stored content but baked into the vector.
    """
    from core.embeddings import generate_embedding

    prefix = build_contextual_prefix(creator_id)
    return generate_embedding(prefix + text)


def generate_embeddings_batch_with_context(
    texts: List[str], creator_id: str,
) -> List[Optional[List[float]]]:
    """Batch variant: generate embeddings with contextual prefix prepended."""
    from core.embeddings import generate_embeddings_batch

    prefix = build_contextual_prefix(creator_id)
    prefixed_texts = [prefix + t for t in texts]
    return generate_embeddings_batch(prefixed_texts)
