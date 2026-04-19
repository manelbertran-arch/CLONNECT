"""Fewshots gate: wraps few_shot_section into a CRITICAL Section."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from core.dm.budget.section import Priority, Section, SECTION_CAPS

if TYPE_CHECKING:
    from core.dm.phases.context import _ContextAssemblyInputs


async def build(inputs: "_ContextAssemblyInputs") -> Optional[Section]:
    content = inputs.few_shot_section
    if not content:
        return None
    return Section(
        name="few_shots",
        content=content,
        priority=Priority.CRITICAL,
        cap_tokens=SECTION_CAPS.get("few_shots", 350),
        value_score=0.95,
    )
