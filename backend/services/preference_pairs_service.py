"""
Re-export shim — all logic moved to services/feedback_capture.py.
Kept for backward compatibility with existing imports.
"""
from services.feedback_capture import *  # noqa: F401, F403
from services.feedback_capture import (  # noqa: F401
    create_pairs_from_action,
    get_pairs_for_export,
    mark_exported,
    mine_historical_pairs,
    curate_pairs,
    _fetch_context_and_save_sync,
    ENABLE_PREFERENCE_PAIRS,
    _SESSION_GAP_HOURS,
)
