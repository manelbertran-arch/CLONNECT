"""
Learning Consolidator — RE-EXPORT SHIM.

All functions moved to services/persona_compiler.py (System B consolidation).
This file kept for backward compatibility.
"""

# Re-export compile_persona as consolidate_rules_for_creator for backward compat
from services.persona_compiler import compile_persona as consolidate_rules_for_creator  # noqa: F401

__all__ = [
    "consolidate_rules_for_creator",
]
