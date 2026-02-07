"""
CSAT (Customer Satisfaction) Collector
Post-conversation satisfaction measurement
Paper ref: Customer Satisfaction in Conversational AI (2024)
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

from metrics.base import MetricCategory, MetricResult, MetricsCollector
from sqlalchemy import text

logger = logging.getLogger(__name__)


class CSATRating(Enum):
    VERY_DISSATISFIED = 1
    DISSATISFIED = 2
    NEUTRAL = 3
    SATISFIED = 4
    VERY_SATISFIED = 5


class CSATCollector(MetricsCollector):
    """Collects CSAT scores via multiple methods."""

    def __init__(self, creator_id: str):
        super().__init__(creator_id)

        self.positive_patterns = [
            r"(genial|perfecto|incre[ií]ble|excelente|gracias|awesome)",
            r"(great|perfect|amazing|excellent|thanks)",
            r"(me.*encanta|muy.*[uú]til|super.*bien)",
        ]

        self.negative_patterns = [
            r"(horrible|terrible|p[eé]simo|mal)",
            r"(awful|terrible|bad|useless|waste)",
            r"(no.*sirve|no.*funciona|p[eé]rdida.*tiempo)",
        ]

    def collect(self, lead_id: str) -> List[MetricResult]:
        """Collect implicit CSAT from conversation sentiment."""
        return [self.collect_implicit(lead_id)]

    def collect_explicit(
        self,
        lead_id: str,
        rating: int,
        feedback: Optional[str] = None,
    ) -> MetricResult:
        """Record explicit CSAT rating (1-5)."""
        rating = max(1, min(5, rating))

        result = MetricResult(
            name="csat_explicit",
            value=rating / 5.0,
            category=MetricCategory.UX,
            metadata={
                "lead_id": lead_id,
                "raw_rating": rating,
                "feedback": feedback,
                "method": "explicit",
            },
        )

        self.add_result(result)
        self._store_rating(lead_id, rating, feedback)
        return result

    def collect_implicit(self, lead_id: str) -> MetricResult:
        """Infer CSAT from conversation sentiment."""
        from api.database import get_db_session

        with get_db_session() as db:
            result = db.execute(
                text(
                    """
                    SELECT content
                    FROM messages
                    WHERE lead_id = :lead_id
                    AND role = 'lead'
                    ORDER BY created_at DESC
                    LIMIT 10
                    """
                ),
                {"lead_id": lead_id},
            )
            messages = [row.content or "" for row in result]

        if not messages:
            return MetricResult(
                name="csat_implicit",
                value=0.6,
                category=MetricCategory.UX,
                metadata={"lead_id": lead_id, "method": "implicit"},
            )

        combined = " ".join(messages).lower()

        positive_count = sum(
            1 for p in self.positive_patterns if re.search(p, combined, re.IGNORECASE)
        )
        negative_count = sum(
            1 for p in self.negative_patterns if re.search(p, combined, re.IGNORECASE)
        )

        if positive_count + negative_count == 0:
            score = 0.6
        else:
            score = positive_count / (positive_count + negative_count)
            score = 0.3 + (score * 0.6)  # Scale to 0.3-0.9

        metric = MetricResult(
            name="csat_implicit",
            value=score,
            category=MetricCategory.UX,
            metadata={
                "lead_id": lead_id,
                "positive_signals": positive_count,
                "negative_signals": negative_count,
                "method": "implicit",
            },
        )

        self.add_result(metric)
        return metric

    def _store_rating(
        self,
        lead_id: str,
        rating: int,
        feedback: Optional[str],
    ):
        """Store CSAT rating in database."""
        from api.database import get_db_session

        try:
            with get_db_session() as db:
                db.execute(
                    text(
                        """
                        INSERT INTO csat_ratings
                        (lead_id, creator_id, rating, feedback, created_at)
                        VALUES (:lead_id, :creator_id, :rating, :feedback, :created_at)
                        ON CONFLICT (lead_id) DO UPDATE
                        SET rating = :rating, feedback = :feedback
                        """
                    ),
                    {
                        "lead_id": lead_id,
                        "creator_id": self.creator_id,
                        "rating": rating,
                        "feedback": feedback,
                        "created_at": datetime.now(timezone.utc),
                    },
                )
                db.commit()
        except Exception as e:
            logger.warning("Failed to store CSAT rating: %s", e)

    def get_average_csat(self, days: int = 30) -> Dict[str, float]:
        """Get average CSAT for period."""
        from api.database import get_db_session

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            with get_db_session() as db:
                result = db.execute(
                    text(
                        """
                        SELECT
                            AVG(rating) as avg_rating,
                            COUNT(*) as count
                        FROM csat_ratings
                        WHERE creator_id = :creator_id
                        AND created_at > :cutoff
                        """
                    ),
                    {"creator_id": self.creator_id, "cutoff": cutoff},
                )
                row = result.fetchone()

            avg = float(row.avg_rating) if row and row.avg_rating else 0
            count = int(row.count) if row else 0

            return {
                "average": avg,
                "count": count,
                "normalized": avg / 5.0 if avg else 0,
            }
        except Exception as e:
            logger.warning("Failed to get average CSAT: %s", e)
            return {"average": 0, "count": 0, "normalized": 0}


def generate_csat_prompt() -> str:
    """Generate message to ask for CSAT."""
    return (
        "How would you rate your experience?\n\n"
        "1 - Very dissatisfied\n"
        "2 - Dissatisfied\n"
        "3 - Neutral\n"
        "4 - Satisfied\n"
        "5 - Very satisfied\n\n"
        "(Reply with a number 1-5)"
    )
