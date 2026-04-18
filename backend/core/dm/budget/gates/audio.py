"""Audio gate: wraps audio_context into a HIGH Section.

Value is conditional on the `audio_intel` cognitive signal (0.70 when present,
0.0 otherwise). When value is 0 the gate returns None — audio without a
recognised intel signal does not consume budget in the orchestrator path.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from core.dm.budget.section import SECTION_CAPS, Priority, Section, compute_value_score

if TYPE_CHECKING:
    from core.dm.phases.context import _ContextAssemblyInputs

logger = logging.getLogger(__name__)


async def build(inputs: "_ContextAssemblyInputs") -> Optional[Section]:
    try:
        content = inputs.audio_context
        if not content:
            return None
        value = compute_value_score("audio", inputs.cognitive_metadata)
        if value <= 0.0:
            return None
        return Section(
            name="audio",
            content=content,
            priority=Priority.HIGH,
            cap_tokens=SECTION_CAPS.get("audio", 250),
            value_score=value,
        )
    except Exception as exc:
        logger.warning("audio gate failed (non-fatal): %s", exc)
        return None
