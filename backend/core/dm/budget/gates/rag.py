"""RAG gate: wraps rag_context into a HIGH-priority Section."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from core.dm.budget.section import Priority, Section, SECTION_CAPS, compute_value_score

if TYPE_CHECKING:
    from core.dm.phases.context import _ContextAssemblyInputs


async def build(inputs: "_ContextAssemblyInputs") -> Optional[Section]:
    content = inputs.rag_context
    if not content:
        return None
    value = compute_value_score("rag", inputs.cognitive_metadata)
    return Section(
        name="rag",
        content=content,
        priority=Priority.HIGH,
        cap_tokens=SECTION_CAPS.get("rag", 350),
        value_score=value,
    )
