"""
Pattern Analyzer — RE-EXPORT SHIM.

All functions moved to services/persona_compiler.py (System B consolidation).
This file kept for backward compatibility.
"""

# Re-export all public functions from persona_compiler
from services.persona_compiler import (  # noqa: F401
    _format_pair,
    _call_judge,
    _persist_run_sync,
    _persist_run,
    compile_persona_all as run_pattern_analysis_all,
    compile_persona as run_pattern_analysis,
)

__all__ = [
    "run_pattern_analysis",
    "run_pattern_analysis_all",
]
