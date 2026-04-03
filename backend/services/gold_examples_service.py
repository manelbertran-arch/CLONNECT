"""
Re-export shim — all logic moved to services/style_retriever.py.
Kept for backward compatibility with existing imports.
"""
from services.style_retriever import *  # noqa: F401, F403
from services.style_retriever import (  # noqa: F401
    create_gold_example,
    get_matching_examples,
    detect_language,
    _is_non_text,
    _SOURCE_QUALITY,
    mine_historical_examples,
    curate_examples,
    _invalidate_examples_cache,
    retrieve,
    ensure_embeddings,
)
