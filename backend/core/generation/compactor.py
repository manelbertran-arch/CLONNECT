"""ARC3 Phase 2 — PromptSliceCompactor.

Decides how to truncate prompt sections to fit within a character budget.
In Phase 2 (shadow mode) this runs in parallel and logs decisions without
altering any actual prompt. Phase 3 will activate live compaction via
USE_COMPACTION=true.

Algorithm: §2.3.4 of docs/sprint5_planning/ARC3_compaction.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants — §2.3.2
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_RATIOS: Dict[str, float] = {
    "style_prompt":    0.35,
    "lead_facts":      0.15,
    "lead_memories":   0.20,
    "rag_hits":        0.15,
    "message_history": 0.10,
    "few_shots":       0.05,
}

# Sections that must never be truncated — §2.3.3
PROMPT_WHITELIST = frozenset({
    "system_instructions",
    "guardrails",
    "persona_identity",
    "current_user_msg",
    "tone_directive",
})


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SectionSpec:
    name: str
    content: str
    priority: int          # 1 = highest, 10 = lowest
    is_whitelist: bool
    ratio_cap: Optional[float] = None  # 0.0-1.0 relative to non-whitelist budget


@dataclass
class PackResult:
    packed: Dict[str, str]
    status: str             # "OK" | "CIRCUIT_BREAK"
    compaction_applied: bool = False
    reason: str = "OK"
    sections_truncated: List[str] = field(default_factory=list)
    distill_applied: bool = False
    final_chars: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def truncate_preserving_structure(text: str, max_chars: int) -> str:
    """Truncate at paragraph/sentence/word boundary, not mid-word.

    Falls back to hard cut only when no clean boundary is found in the
    acceptable region (>80% of max_chars for paragraphs, >85% for sentences,
    >90% for words).
    """
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]

    last_paragraph = truncated.rfind("\n\n")
    if last_paragraph > max_chars * 0.8:
        return truncated[:last_paragraph]

    last_period = truncated.rfind(". ")
    if last_period > max_chars * 0.85:
        return truncated[:last_period + 1]

    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.9:
        return truncated[:last_space]

    return truncated


# ─────────────────────────────────────────────────────────────────────────────
# Main compactor
# ─────────────────────────────────────────────────────────────────────────────

class PromptSliceCompactor:
    """Pack prompt sections into a character budget.

    Phase 2 (shadow): call pack() to get decisions without applying them.
    Phase 3 (live): use PackResult.packed to replace original sections.
    """

    def __init__(
        self,
        budget_chars: int,
        ratios: Optional[Dict[str, float]] = None,
        distill_service: Optional[object] = None,
    ) -> None:
        self.budget = budget_chars
        self.ratios = ratios or DEFAULT_RATIOS
        self.distill_service = distill_service

    async def pack(
        self,
        sections: List[SectionSpec],
        creator_id: Optional[UUID] = None,
    ) -> PackResult:
        """Pack sections into budget, returning what would have happened.

        Steps follow §2.3.4 literally:
          1. Compute whitelist cost
          2. Compute remaining budget
          3. Try as-is (no compaction)
          4. Apply StyleDistillCache if style_prompt is too large
          5. Apply ratio caps
          6. Aggressive truncation by reverse priority
          7. Assemble
        """
        import copy
        # Work on copies so original SectionSpec objects are never mutated
        sections = [copy.copy(s) for s in sections]

        # Step 1: whitelist cost
        whitelist_cost = sum(len(s.content) for s in sections if s.is_whitelist)

        if whitelist_cost > self.budget:
            logger.warning(
                "[ARC3-COMPACTOR] whitelist_overflow: whitelist=%d budget=%d creator=%s",
                whitelist_cost, self.budget, creator_id,
            )
            return PackResult(
                packed={},
                status="CIRCUIT_BREAK",
                reason="CIRCUIT_BREAK",
            )

        # Step 2: budget for non-whitelist sections
        remaining = self.budget - whitelist_cost

        # Step 3: try as-is
        non_wl = [s for s in sections if not s.is_whitelist]
        current_cost = sum(len(s.content) for s in non_wl)

        if current_cost <= remaining:
            return PackResult(
                packed={s.name: s.content for s in sections},
                status="OK",
                compaction_applied=False,
                reason="OK",
                final_chars=whitelist_cost + current_cost,
            )

        sections_truncated: List[str] = []
        distill_applied = False

        # Step 4: StyleDistillCache if style_prompt is the bottleneck
        style_section = next((s for s in non_wl if s.name == "style_prompt"), None)
        if style_section and len(style_section.content) > remaining * 0.4:
            distilled: Optional[str] = None
            if self.distill_service is not None:
                try:
                    distilled = await self.distill_service.get_or_generate(
                        creator_id=creator_id,
                        doc_d=style_section.content,
                    )
                except Exception as _e:
                    logger.debug("[ARC3-COMPACTOR] distill_service failed: %s", _e)

            if distilled:
                style_section.content = distilled
                distill_applied = True
                current_cost = sum(len(s.content) for s in non_wl)
                logger.debug(
                    "[ARC3-COMPACTOR] distill applied: style_prompt %d → %d chars",
                    len(style_section.content), len(distilled),
                )

        # Step 5: apply ratio caps if still over budget
        if current_cost > remaining:
            for s in non_wl:
                ratio = self.ratios.get(s.name)
                if ratio is None:
                    continue
                cap_chars = int(ratio * remaining)
                if len(s.content) > cap_chars and cap_chars > 0:
                    s.content = truncate_preserving_structure(s.content, cap_chars)
                    sections_truncated.append(s.name)

            current_cost = sum(len(s.content) for s in non_wl)

        # Step 6: aggressive truncation by reverse priority (lowest priority first)
        if current_cost > remaining:
            for s in sorted(non_wl, key=lambda x: -x.priority):
                if current_cost <= remaining:
                    break
                needed_reduction = current_cost - remaining
                new_len = max(0, len(s.content) - needed_reduction)
                s.content = s.content[:new_len]
                if s.name not in sections_truncated:
                    sections_truncated.append(s.name)
                current_cost = sum(len(x.content) for x in non_wl)

        # Step 7: assemble
        wl_map = {s.name: s.content for s in sections if s.is_whitelist}
        non_wl_map = {s.name: s.content for s in non_wl}

        reason = "OK"
        if distill_applied:
            reason = "DISTILL_APPLIED"
        elif sections_truncated:
            # Differentiate ratio-cap vs aggressive truncation
            all_have_ratios = all(s in self.ratios for s in sections_truncated)
            reason = "RATIO_CAPS" if all_have_ratios else "AGGRESSIVE_TRUNC"

        return PackResult(
            packed={**wl_map, **non_wl_map},
            status="OK",
            compaction_applied=True,
            reason=reason,
            sections_truncated=sections_truncated,
            distill_applied=distill_applied,
            final_chars=whitelist_cost + current_cost,
        )
