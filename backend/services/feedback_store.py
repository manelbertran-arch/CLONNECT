"""
Re-export shim — all logic moved to services/feedback_capture.py.
Kept for backward compatibility with existing imports.
"""
from services.feedback_capture import *  # noqa: F401, F403
from services.feedback_capture import (  # noqa: F401
    capture,
    save_feedback,
    get_feedback,
    get_feedback_stats,
    QUALITY_SCORES,
    _COPILOT_ACTION_MAP,
    _compute_quality,
    _auto_create_preference_pair,
    _auto_create_gold_example,
    ENABLE_EVALUATOR_FEEDBACK,
)
