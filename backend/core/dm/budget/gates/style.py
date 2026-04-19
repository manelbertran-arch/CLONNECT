"""Style gate: wraps agent.style_prompt into a CRITICAL Section."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from core.dm.budget.section import Priority, Section, SECTION_CAPS

if TYPE_CHECKING:
    from core.dm.phases.context import _ContextAssemblyInputs


async def build(inputs: "_ContextAssemblyInputs") -> Optional[Section]:
    content = inputs.style_prompt
    if not content:
        return None
    return Section(
        name="style",
        content=content,
        priority=Priority.CRITICAL,
        cap_tokens=SECTION_CAPS.get("style", 800),
        value_score=1.0,
    )
