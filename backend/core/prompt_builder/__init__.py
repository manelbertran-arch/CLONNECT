"""
Prompt Builder Package

Builds the complete system prompt for LLM by combining:
- Creator data (products, booking, payment methods, FAQs)
- User context (preferences, history, lead info)
- Detected context (frustration, B2B, intent, alerts)

Part of refactor/context-injection-v2
"""

from core.prompt_builder.calibration import (
    build_length_hint,
    build_question_hint,
    build_vocabulary_hint,
    get_calibration_soft_max,
)
from core.prompt_builder.orchestration import (
    build_prompt_from_ids,
    build_system_prompt,
    get_prompt_summary,
    validate_prompt,
)
from core.prompt_builder.sections import (
    COHERENCE_INSTRUCTION,
    CONVERSION_INSTRUCTION,
    NO_REPETITION_INSTRUCTION,
    PROACTIVE_CLOSE_INSTRUCTION,
    build_actions_section,
    build_alerts_section,
    build_b2b_section,
    build_data_section,
    build_frustration_section,
    build_identity_section,
    build_rules_section,
    build_user_section,
)

__all__ = [
    # Instruction constants
    "PROACTIVE_CLOSE_INSTRUCTION",
    "NO_REPETITION_INSTRUCTION",
    "COHERENCE_INSTRUCTION",
    "CONVERSION_INSTRUCTION",
    # Section builders
    "build_identity_section",
    "build_data_section",
    "build_user_section",
    "build_alerts_section",
    "build_rules_section",
    "build_actions_section",
    "build_b2b_section",
    "build_frustration_section",
    # Orchestration
    "build_system_prompt",
    "build_prompt_from_ids",
    "get_prompt_summary",
    "validate_prompt",
    # Calibration
    "get_calibration_soft_max",
    "build_length_hint",
    "build_vocabulary_hint",
    "build_question_hint",
]
