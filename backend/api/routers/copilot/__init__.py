"""Copilot endpoints — decomposed into actions and analytics."""
from fastapi import APIRouter

from api.auth import require_creator_access  # noqa: F401 — re-exported for patch targets in tests
from .actions import router as actions_router
from .analytics import router as analytics_router

router = APIRouter(prefix="/copilot", tags=["copilot"])
router.include_router(actions_router)
router.include_router(analytics_router)

# Re-export symbols for backward compatibility with existing imports
# (e.g. tests that do `from api.routers.copilot import ApproveRequest`)
from .actions import (  # noqa: E402, F401
    ApproveRequest,
    DiscardRequest,
    ManualResponseRequest,
    MarkExportedRequest,
    SuggestRequest,
    ToggleRequest,
    approve_all_pending,
    approve_response,
    discard_all_pending,
    discard_response,
    get_pending_responses,
    mark_pairs_exported,
    suggest_response,
    toggle_copilot_mode,
    track_manual_response,
)
from .analytics import (  # noqa: E402, F401
    PATTERN_UI_MAP,
    _compute_tip,
    get_copilot_comparisons,
    get_copilot_history,
    get_copilot_stats,
    get_copilot_status,
    get_historical_rates,
    get_learning_progress,
    get_notifications,
    get_pending_for_lead,
    get_preference_pairs,
)
