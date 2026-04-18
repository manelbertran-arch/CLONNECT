"""
Section dataclass + Priority enum for the token-aware budget orchestrator.
Design: docs/sprint5_planning/ARC1_token_aware_budget.md §2.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Optional


class Priority(IntEnum):
    CRITICAL = 4  # style, few_shots, system hardcoded rules
    HIGH = 3      # rag, audio, memory_engine facts
    MEDIUM = 2    # dna, commitments, frustration_note
    LOW = 1       # hier_memory, advanced_section
    FINAL = 0     # citations, output_style_note, kb


@dataclass(frozen=True)
class Section:
    name: str
    content: str
    priority: Priority
    cap_tokens: int
    value_score: float
    compressor: Optional[Callable[[str, int], str]] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AssembledContext:
    combined: str
    sections_selected: list[Section]
    sections_dropped: list[Section]
    sections_compressed: list[tuple[Section, int]]
    total_tokens: int
    budget_tokens: int
    utilization: float


# Cap table per section — derived from W3 measurements + W6 §5.3 + W5 §2.1
SECTION_CAPS: dict[str, int] = {
    "style":       800,
    "few_shots":   350,
    "recalling":   400,
    "audio":       250,
    "rag":         350,
    "history":     500,
    "commitments": 150,
    "hier_memory": 200,
    "kb":          100,
    "citations":   50,
    "friend_context": 0,
}


def compute_value_score(section_name: str, cognitive_metadata: dict) -> float:
    """Value-score heuristic per section. Design: ARC1 §2.6."""
    base: dict[str, float] = {
        "style":       1.00,
        "few_shots":   0.95,
        "recalling":   0.80,
        "audio":       0.70 if cognitive_metadata.get("audio_intel") else 0.0,
        "rag":         0.75 if cognitive_metadata.get("rag_signal") else 0.30,
        "history":     0.50,
        "commitments": 0.60 if cognitive_metadata.get("commitments_pending") else 0.0,
        "hier_memory": 0.40,
        "kb":          0.10,
        "citations":   0.20,
    }
    score = base.get(section_name, 0.5)

    intent = cognitive_metadata.get("intent_category")
    if intent == "purchase_intent" and section_name == "rag":
        score *= 1.2
    if intent == "casual" and section_name == "rag":
        score *= 0.5

    return min(score, 1.0)
