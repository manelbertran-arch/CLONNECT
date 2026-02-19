"""LearningRule domain model for autolearning feedback loop.

Dataclass representation used by services and the DM pipeline.
The SQLAlchemy model lives in api/models.py (LearningRule).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class LearningRuleData:
    """In-memory representation of a learning rule.

    Used when passing rules between services (analyzer, consolidator,
    dm_agent) without coupling to SQLAlchemy.
    """

    id: str
    creator_id: str
    rule_text: str
    pattern: str
    confidence: float = 0.5
    times_applied: int = 0
    times_helped: int = 0
    example_bad: Optional[str] = None
    example_good: Optional[str] = None
    applies_to_relationship_types: List[str] = field(default_factory=list)
    applies_to_message_types: List[str] = field(default_factory=list)
    applies_to_lead_stages: List[str] = field(default_factory=list)
    is_active: bool = True
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    superseded_by: Optional[str] = None

    @property
    def help_ratio(self) -> float:
        """Ratio of times the rule helped vs times applied."""
        if self.times_applied == 0:
            return 0.0
        return self.times_helped / self.times_applied

    @property
    def is_effective(self) -> bool:
        """Rule is considered effective if help ratio > 50% with enough data."""
        return self.times_applied >= 3 and self.help_ratio > 0.5

    def to_prompt_line(self) -> str:
        """Format rule for injection into DM prompt."""
        line = f"- {self.rule_text}"
        if self.example_bad:
            line += f'\n  NO: "{self.example_bad}"'
        if self.example_good:
            line += f'\n  SI: "{self.example_good}"'
        return line
