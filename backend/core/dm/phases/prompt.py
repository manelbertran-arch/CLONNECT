"""Phase 3b: Prompt Construction — placeholder (actual build in Phase 4)."""

from typing import Dict

from core.dm.models import ContextBundle, DetectionResult


def phase_prompt_construction(
    agent, message: str, sender_id: str, metadata: Dict,
    context: ContextBundle, detection: DetectionResult,
    cognitive_metadata: Dict,
) -> str:
    """Phase 3b: Strategy, learning rules, gold examples, prompt assembly.

    NOTE: Prompt construction is currently integrated into _phase_llm_generation
    because the learning rules and gold examples require async DB calls.
    This method returns a placeholder; the actual prompt is built in Phase 4.
    """
    return ""  # Actual prompt built in _phase_llm_generation
