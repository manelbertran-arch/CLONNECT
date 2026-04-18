"""Commitments gate: wraps commitment_text into a MEDIUM Section.

Only activates when `commitments_pending` flag is set in cognitive_metadata
(value=0.60). Without the flag the gate returns None — no budget consumed.
Cap is tight (150 tokens) per design doc §2.5.
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
        content = inputs.commitment_text
        if not content:
            return None
        value = compute_value_score("commitments", inputs.cognitive_metadata)
        if value <= 0.0:
            return None
        return Section(
            name="commitments",
            content=content,
            priority=Priority.MEDIUM,
            cap_tokens=SECTION_CAPS.get("commitments", 150),
            value_score=value,
        )
    except Exception as exc:
        logger.warning("commitments gate failed (non-fatal): %s", exc)
        return None
