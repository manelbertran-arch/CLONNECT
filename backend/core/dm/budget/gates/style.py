"""Style gate: wraps agent.style_prompt into a CRITICAL Section.

S4-proximity fix (A1.4): appends the last 200 chars of the lead's message as
a <RECENT_LEAD_MESSAGE> anchor. This ensures the LLM always sees the raw
proximity signal when adapting tone — resolves the S4 regression observed in
A1.3 (style consuming 40% budget crowded out adaptation signals).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from core.dm.budget.section import SECTION_CAPS, Priority, Section

if TYPE_CHECKING:
    from core.dm.phases.context import _ContextAssemblyInputs

_RECENT_MSG_CHARS = 200  # immutable anchor; never truncated by compressor


async def build(inputs: "_ContextAssemblyInputs") -> Optional[Section]:
    content = inputs.style_prompt
    if not content:
        return None
    if inputs.message:
        recent = inputs.message[-_RECENT_MSG_CHARS:].strip()
        if recent:
            content = content + f"\n<RECENT_LEAD_MESSAGE>{recent}</RECENT_LEAD_MESSAGE>"
    return Section(
        name="style",
        content=content,
        priority=Priority.CRITICAL,
        cap_tokens=SECTION_CAPS.get("style", 800),
        value_score=1.0,
    )
