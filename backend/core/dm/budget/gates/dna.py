"""DNA gate: wraps relationship DNA context into a MEDIUM Section.

Value is static (0.75) — DNA is always moderately valuable for persona
consistency, not gated on a runtime signal. Cap 300 tokens per design doc
§2.5 note (derived from DNA mean 200-400 chars, ~50-100 tokens typical).
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
        content = inputs.dna_context
        if not content:
            return None
        value = compute_value_score("dna", inputs.cognitive_metadata)
        return Section(
            name="dna",
            content=content,
            priority=Priority.MEDIUM,
            cap_tokens=SECTION_CAPS.get("dna", 300),
            value_score=value,
        )
    except Exception as exc:
        logger.warning("dna gate failed (non-fatal): %s", exc)
        return None
