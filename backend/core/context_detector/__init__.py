"""
Context Detector Module — Universal/Multilingual (v2).

Detects contextual signals in messages. Produces factual observations
for the Recalling block — no behavior instructions.
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
    # Models
    "DetectedContext",
    "B2BResult",
    "FrustrationResult",
    "SarcasmResult",
    # Detectors
    "detect_b2b",
    "detect_correction",
    "detect_frustration",
    "detect_interest_level",
    "detect_meta_message",
    "detect_objection_type",
    "detect_sarcasm",
    "extract_user_name",
    # Orchestration
    "detect_all",
    "detect_all_async",
    "format_alerts_for_prompt",
    "get_context_summary",
]
