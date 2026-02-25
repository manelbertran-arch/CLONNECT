"""
Autolearning API package — endpoints for viewing and managing learning rules.

Provides visibility into the autolearning feedback loop:
- List active rules for a creator
- View rule stats and effectiveness
- Manually deactivate/reactivate rules
- Trigger consolidation on demand
- Gamified dashboard with XP, levels, skills, achievements
"""

from fastapi import APIRouter

from api.routers.autolearning.analysis import router as _analysis_router
from api.routers.autolearning.dashboard import router as _dashboard_router
from api.routers.autolearning.rules import router as _rules_router

# Re-export all public symbols from sub-modules
from api.routers.autolearning.rules import list_rules, deactivate_rule, reactivate_rule  # noqa: F401
from api.routers.autolearning.analysis import (  # noqa: F401
    trigger_consolidation,
    analyze_patterns,
    get_pattern_analysis,
)
from api.routers.autolearning.dashboard import (  # noqa: F401
    get_dashboard,
    rule_stats,
    get_gold_examples,
    get_preference_profile,
    curate_gold_examples,
    LEVELS,
    INTENT_LABELS,
    PATTERN_LABELS,
    ACHIEVEMENTS,
    _get_level,
    _compute_streak,
    _edit_severity,
    _autopilot_status,
)

router = APIRouter(prefix="/autolearning", tags=["autolearning"])
router.include_router(_rules_router)
router.include_router(_analysis_router)
router.include_router(_dashboard_router)
