"""
Task Completion Rate Collector
Measures: % of conversations where user achieved their goal
Paper ref: Conversation Success Metrics (2024)
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List

from metrics.base import MetricCategory, MetricResult, MetricsCollector
from sqlalchemy import text

logger = logging.getLogger(__name__)


class TaskType(Enum):
    PURCHASE = "purchase"
    INFO_REQUEST = "info_request"
    SUPPORT = "support"
    BOOKING = "booking"
    LEAD_QUALIFIED = "lead_qualified"
    UNKNOWN = "unknown"


class TaskOutcome(Enum):
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    ESCALATED = "escalated"
    PENDING = "pending"


class TaskCompletionCollector(MetricsCollector):
    """Collects task completion metrics."""

    def __init__(self, creator_id: str):
        super().__init__(creator_id)

        self.completion_patterns: Dict[TaskType, List[str]] = {
            TaskType.PURCHASE: [
                r"(gracias.*compra|pedido.*confirmado|pago.*recibido)",
                r"(thanks.*purchase|order.*confirmed|payment.*received)",
                r"(ya.*pagu[eé]|transferencia.*hecha)",
            ],
            TaskType.INFO_REQUEST: [
                r"(perfecto.*entendido|gracias.*info|me.*queda.*claro)",
                r"(perfect.*understood|thanks.*info|clear.*now)",
                r"(vale.*gracias|ok.*entiendo)",
            ],
            TaskType.BOOKING: [
                r"(cita.*confirmada|reserva.*hecha|agenda.*)",
                r"(appointment.*confirmed|booking.*made)",
                r"(nos.*vemos|quedamos.*entonces)",
            ],
            TaskType.LEAD_QUALIFIED: [
                r"(me.*interesa.*m[aá]s|quiero.*saber.*precio)",
                r"(cu[aá]nto.*cuesta|precio|tarifas)",
                r"(c[oó]mo.*empiezo|siguiente.*paso)",
            ],
        }

        self.abandonment_patterns = [
            r"(no.*gracias|no.*interesa|demasiado.*caro)",
            r"(bye|adi[oó]s|hasta.*luego)(?!.*gracias)",
            r"(lo.*pienso|ya.*ver[eé]|otro.*momento)",
        ]

        self.escalation_patterns = [
            r"(hablar.*humano|persona.*real|agente)",
            r"(no.*entiendes|eres.*bot|m[aá]quina)",
            r"(quiero.*hablar.*con)",
        ]

    def collect(self, lead_id: str) -> List[MetricResult]:
        """Analyze conversation for task completion."""
        from api.database import get_db_session

        with get_db_session() as db:
            result = db.execute(
                text(
                    """
                    SELECT content, role, created_at
                    FROM messages
                    WHERE lead_id = :lead_id
                    ORDER BY created_at ASC
                    """
                ),
                {"lead_id": lead_id},
            )
            messages = [
                {"content": row.content, "role": row.role, "created_at": row.created_at}
                for row in result
            ]

        if not messages:
            return []

        task_type = self._detect_task_type(messages)
        outcome = self._detect_outcome(messages)
        is_completed = outcome == TaskOutcome.COMPLETED

        metric = MetricResult(
            name="task_completion_rate",
            value=1.0 if is_completed else 0.0,
            category=MetricCategory.UX,
            metadata={
                "lead_id": lead_id,
                "task_type": task_type.value,
                "outcome": outcome.value,
                "message_count": len(messages),
            },
        )

        self.add_result(metric)
        return [metric]

    def _detect_task_type(self, messages: List[Dict[str, Any]]) -> TaskType:
        """Detect what the user was trying to accomplish."""
        user_messages = [m["content"] for m in messages if m["role"] == "lead"][:3]
        combined = " ".join(user_messages).lower()

        for task_type, patterns in self.completion_patterns.items():
            for pattern in patterns:
                if re.search(pattern, combined, re.IGNORECASE):
                    return task_type

        return TaskType.UNKNOWN

    def _detect_outcome(self, messages: List[Dict[str, Any]]) -> TaskOutcome:
        """Detect conversation outcome from last messages."""
        last_messages = messages[-5:]
        combined = " ".join(m["content"] or "" for m in last_messages).lower()

        for patterns in self.completion_patterns.values():
            for pattern in patterns:
                if re.search(pattern, combined, re.IGNORECASE):
                    return TaskOutcome.COMPLETED

        for pattern in self.escalation_patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                return TaskOutcome.ESCALATED

        for pattern in self.abandonment_patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                return TaskOutcome.ABANDONED

        return TaskOutcome.PENDING

    def get_aggregate_rate(self, days: int = 30) -> float:
        """Get overall task completion rate for period."""
        from api.database import get_db_session

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        with get_db_session() as db:
            result = db.execute(
                text(
                    """
                    SELECT DISTINCT lead_id
                    FROM messages
                    WHERE lead_id IN (
                        SELECT id FROM leads WHERE creator_id = :creator_id
                    )
                    AND created_at > :cutoff
                    """
                ),
                {"creator_id": self.creator_id, "cutoff": cutoff},
            )
            lead_ids = [str(row.lead_id) for row in result]

        if not lead_ids:
            return 0.0

        completed = 0
        for lid in lead_ids:
            results = self.collect(lid)
            if results and results[0].value == 1.0:
                completed += 1

        return completed / len(lead_ids)
