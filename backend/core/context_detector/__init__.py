"""
Context Detector Module

Detects contextual signals in messages for LLM prompt injection.
Detectors only INFORM, they do NOT respond. The LLM decides what to do.

Part of refactor/context-injection-v2
"""

from .detectors import (
    detect_b2b,
    detect_correction,
    detect_frustration,
    detect_interest_level,
    detect_meta_message,
    detect_objection_type,
    detect_sarcasm,
    extract_user_name,
)
from .models import B2BResult, DetectedContext, FrustrationResult, SarcasmResult
from .orchestration import (
    detect_all,
    detect_all_async,
    format_alerts_for_prompt,
    get_context_summary,
)

__all__ = [
    # Models / Dataclasses
    "FrustrationResult",
    "SarcasmResult",
    "B2BResult",
    "DetectedContext",
    # Individual detectors
    "detect_frustration",
    "detect_sarcasm",
    "extract_user_name",
    "detect_b2b",
    "detect_interest_level",
    "detect_meta_message",
    "detect_correction",
    "detect_objection_type",
    # Orchestration
    "detect_all",
    "detect_all_async",
    "format_alerts_for_prompt",
    "get_context_summary",
]
