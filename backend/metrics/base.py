"""Base classes for metrics collection."""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class MetricCategory(Enum):
    COGNITIVE = "cognitive"
    QUALITY = "quality"
    REASONING = "reasoning"
    DIALOGUE = "dialogue"
    UX = "user_experience"
    ROBUSTNESS = "robustness"


@dataclass
class MetricResult:
    """Single metric measurement."""

    name: str
    value: float
    category: MetricCategory
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "value": self.value,
            "category": self.category.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class MetricsCollector:
    """Base collector for all metrics."""

    def __init__(self, creator_id: str):
        self.creator_id = creator_id
        self._results: List[MetricResult] = []

    def collect(self, lead_id: str) -> List[MetricResult]:
        """Override in subclasses."""
        raise NotImplementedError

    def add_result(self, result: MetricResult):
        self._results.append(result)
        logger.info("[Metrics] %s: %.2f", result.name, result.value)

    def get_results(self) -> List[MetricResult]:
        return self._results

    def get_summary(self) -> Dict[str, float]:
        """Get average by metric name."""
        sums: Dict[str, List[float]] = defaultdict(list)
        for r in self._results:
            sums[r.name].append(r.value)
        return {k: sum(v) / len(v) for k, v in sums.items()}
