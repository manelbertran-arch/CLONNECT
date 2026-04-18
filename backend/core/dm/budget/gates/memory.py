"""Memory gate: wraps hier_memory_context into a HIGH or LOW Section.

Priority and value are dynamic based on whether memory/episodic was actually
recalled this turn. When recalled: HIGH priority, value=0.80. Otherwise: LOW,
value=0.40 (deprioritised but not dropped).
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
        content = inputs.hier_memory_context
        if not content:
            return None
        cog = inputs.cognitive_metadata
        recalled = cog.get("memory_recalled") or cog.get("episodic_recalled")
        priority = Priority.HIGH if recalled else Priority.LOW
        value = compute_value_score("memory", cog)
        return Section(
            name="memory",
            content=content,
            priority=priority,
            cap_tokens=SECTION_CAPS.get("memory", 400),
            value_score=value,
        )
    except Exception as exc:
        logger.warning("memory gate failed (non-fatal): %s", exc)
        return None
