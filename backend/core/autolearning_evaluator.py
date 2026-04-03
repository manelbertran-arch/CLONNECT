"""
Autolearning Evaluator — RE-EXPORT SHIM.

All functions moved to services/persona_compiler.py (System B consolidation).
This file kept for backward compatibility.
"""

# Re-export all public functions from persona_compiler
from services.persona_compiler import (  # noqa: F401
    run_daily_evaluation,
    _detect_daily_patterns,
    run_weekly_recalibration,
    _generate_weekly_recommendations,
)

__all__ = [
    "run_daily_evaluation",
    "run_weekly_recalibration",
]
