"""History gate: wraps the recalling block (history aggregation) into a HIGH Section."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from core.dm.budget.section import Priority, Section, SECTION_CAPS, compute_value_score

if TYPE_CHECKING:
    from core.dm.phases.context import _ContextAssemblyInputs


async def build(inputs: "_ContextAssemblyInputs") -> Optional[Section]:
    content = inputs.recalling
    if not content:
        return None
    value = compute_value_score("recalling", inputs.cognitive_metadata)
    return Section(
        name="recalling",
        content=content,
        priority=Priority.HIGH,
        cap_tokens=SECTION_CAPS.get("recalling", 400),
        value_score=value,
    )
