"""
Abandonment Rate Collector
Measures: % of conversations abandoned before resolution
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from metrics.base import MetricCategory, MetricResult, MetricsCollector
from sqlalchemy import text

logger = logging.getLogger(__name__)


class AbandonmentCollector(MetricsCollector):
    """Tracks conversation abandonment."""

    def __init__(self, creator_id: str):
        super().__init__(creator_id)
        self.abandonment_threshold_minutes = 30
        self.min_messages_for_completion = 4

    def collect(self, lead_id: str) -> List[MetricResult]:
        """Analyze if conversation was abandoned."""
        from api.database import get_db_session

        with get_db_session() as db:
            result = db.execute(
                text(
                    """
                    SELECT role, created_at
                    FROM messages
                    WHERE lead_id = :lead_id
                    ORDER BY created_at ASC
                    """
                ),
                {"lead_id": lead_id},
            )
            messages = [{"role": row.role, "created_at": row.created_at} for row in result]

        if not messages:
            return []

        is_abandoned, reason = self._check_abandonment(messages)

        metric = MetricResult(
            name="abandonment_rate",
            value=1.0 if is_abandoned else 0.0,
            category=MetricCategory.UX,
            metadata={
                "lead_id": lead_id,
                "abandoned": is_abandoned,
                "reason": reason,
                "message_count": len(messages),
                "last_sender": messages[-1]["role"] if messages else None,
            },
        )

        self.add_result(metric)
        return [metric]

    def _check_abandonment(self, messages: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """Determine if conversation was abandoned and why."""
        if len(messages) < self.min_messages_for_completion:
            if messages[-1]["role"] != "lead":
                return True, "user_no_response_short"
            return False, "too_few_messages"

        last_msg = messages[-1]

        # If bot responded and user never came back
        if last_msg["role"] != "lead":
            time_since_last = (
                datetime.now(timezone.utc) - last_msg["created_at"].replace(tzinfo=timezone.utc)
            ).total_seconds() / 60
            if time_since_last > self.abandonment_threshold_minutes:
                return True, "user_no_response_timeout"

        # Check if conversation ended abruptly (user's last message)
        if last_msg["role"] == "lead":
            time_since = (
                datetime.now(timezone.utc) - last_msg["created_at"].replace(tzinfo=timezone.utc)
            ).total_seconds() / 60
            if time_since > self.abandonment_threshold_minutes * 2:
                return True, "conversation_stalled"

        return False, "active"

    def get_abandonment_rate(self, days: int = 30) -> Dict[str, Any]:
        """Get overall abandonment rate."""
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
            return {"rate": 0, "total": 0, "abandoned": 0, "reasons": {}}

        abandoned_count = 0
        reasons: Dict[str, int] = {}

        for lid in lead_ids:
            results = self.collect(lid)
            if results and results[0].value == 1.0:
                abandoned_count += 1
                reason = results[0].metadata.get("reason", "unknown")
                reasons[reason] = reasons.get(reason, 0) + 1

        return {
            "rate": abandoned_count / len(lead_ids),
            "total": len(lead_ids),
            "abandoned": abandoned_count,
            "reasons": reasons,
        }
