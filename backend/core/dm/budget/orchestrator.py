"""
BudgetOrchestrator — greedy token-budget packing for DM context sections.
Design: docs/sprint5_planning/ARC1_token_aware_budget.md §2.3

Algorithm: CRITICAL sections are always included (compressed if over cap).
Remaining sections compete greedily by value_score / cost ratio.
Justification: greedy is near-optimal for ≤15 sections at <2ms latency.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Optional

from core.dm.budget.section import AssembledContext, Priority, Section
from core.dm.budget.tokenizer import TokenCounter
from core.observability.metrics import emit_metric

logger = logging.getLogger(__name__)


class BudgetOrchestrator:
    def __init__(
        self,
        tokenizer: TokenCounter,
        budget_tokens: int,
        session_cap_tokens: Optional[int] = None,
    ) -> None:
        self.tokenizer = tokenizer
        self.budget = budget_tokens
        self.session_cap = session_cap_tokens

    def pack(self, sections: list[Section]) -> AssembledContext:
        """
        Selects the subset of sections that maximises sum(value_score * included)
        subject to: sum(min(tokens(s), s.cap_tokens) for s in included) <= budget

        CRITICAL sections are always attempted (compressed/truncated if needed).
        Non-critical compete greedily by value_score / cost ratio.
        """
        tokenized: list[tuple[Section, int]] = [
            (s, self.tokenizer.count(s.content)) for s in sections
        ]

        result: list[Section] = []
        dropped: list[Section] = []
        compressed: list[tuple[Section, int]] = []
        remaining = self.budget

        # Pass 1 — CRITICAL: always include, compress if over cap
        for section, tok in sorted(tokenized, key=lambda p: -p[0].priority):
            if section.priority != Priority.CRITICAL:
                break
            section, effective_tok = self._fit(
                section, tok, remaining, compressed, force=True
            )
            result.append(section)
            remaining -= effective_tok

        # Pass 2 — non-CRITICAL: greedy by value/cost
        rest = [(s, tok) for s, tok in tokenized if s.priority != Priority.CRITICAL]
        rest.sort(key=lambda p: -(p[0].value_score / max(p[1], 1)))

        for section, tok in rest:
            effective_tok = min(tok, section.cap_tokens)
            if effective_tok <= remaining:
                section, effective_tok = self._fit(
                    section, tok, remaining, compressed, force=False
                )
                result.append(section)
                remaining -= effective_tok
            else:
                dropped.append(section)

        total_used = self.budget - remaining
        combined = "\n\n".join(s.content for s in result if s.content)
        return AssembledContext(
            combined=combined,
            sections_selected=result,
            sections_dropped=dropped,
            sections_compressed=compressed,
            total_tokens=total_used,
            budget_tokens=self.budget,
            utilization=total_used / self.budget if self.budget > 0 else 0.0,
        )

    def _fit(
        self,
        section: Section,
        tok: int,
        remaining: int,
        compressed: list[tuple[Section, int]],
        force: bool,
    ) -> tuple[Section, int]:
        """Return (possibly compressed/truncated section, effective_tokens)."""
        effective_tok = min(tok, section.cap_tokens)

        if tok > section.cap_tokens and section.compressor is not None:
            new_content = section.compressor(section.content, section.cap_tokens)
            new_tok = self.tokenizer.count(new_content)
            section = _replace(section, content=new_content)
            effective_tok = new_tok
            compressed.append((section, new_tok))

        elif tok > section.cap_tokens and not force:
            # Non-CRITICAL, no compressor: content exceeded cap — truncate to cap so
            # the concatenated prompt matches the token budget accounting (ARC1-TRUNCATION fix).
            truncated = self.tokenizer.truncate(section.content, section.cap_tokens)
            section = _replace(section, content=truncated)
            effective_tok = section.cap_tokens
            compressed.append((section, effective_tok))
            logger.debug(
                "[BUDGET] truncated non-critical %s: %d→%d tokens (cap=%d, overflow=%d)",
                section.name, tok, effective_tok, section.cap_tokens, tok - section.cap_tokens,
            )
            emit_metric("budget_section_truncation_total", section_name=section.name)

        if force and effective_tok > remaining:
            # CRITICAL does not fit even compressed — hard-truncate to remaining
            truncated = self.tokenizer.truncate(section.content, remaining)
            section = _replace(section, content=truncated)
            effective_tok = remaining
            compressed.append((section, effective_tok))

        return section, effective_tok


def _replace(section: Section, **kwargs: object) -> Section:
    """Return a new Section with overridden fields (frozen dataclass helper)."""
    d = {k: v for k, v in asdict(section).items() if k != "compressor"}
    d.update(kwargs)
    return Section(
        name=d["name"],
        content=str(d["content"]),
        priority=Priority(d["priority"]),
        cap_tokens=int(d["cap_tokens"]),
        value_score=float(d["value_score"]),
        compressor=section.compressor,
        metadata=d.get("metadata", {}),
    )
