"""
Knowledge Retention Score
Measures: Bot's ability to remember facts from earlier in conversation
Paper ref: Memory in Conversational Agents (2024)
"""

import logging
import re
from typing import Any, Dict, List

from metrics.base import MetricCategory, MetricResult, MetricsCollector
from sqlalchemy import text

logger = logging.getLogger(__name__)


class KnowledgeRetentionCollector(MetricsCollector):
    """Measures knowledge retention across conversation."""

    def __init__(self, creator_id: str):
        super().__init__(creator_id)

        self.fact_patterns = {
            "name": r"(?:me llamo|soy|my name is)\s+([A-Z][a-z\u00e1\u00e9\u00ed\u00f3\u00fa]+)",
            "location": r"(?:vivo en|soy de|from|live in)\s+([A-Z][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\s]+)",
            "interest": r"(?:me interesa|quiero|interested in)\s+(.+?)(?:\.|$)",
            "budget": r"(?:presupuesto|budget).*?(\d+[\u20ac$]|\d+\s*euros?)",
            "goal": r"(?:objetivo|quiero lograr|goal|want to)\s+(.+?)(?:\.|$)",
        }

    def collect(self, lead_id: str) -> List[MetricResult]:
        """Analyze knowledge retention in conversation."""
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

        if len(messages) < 4:
            return []

        user_facts = self._extract_facts(messages)
        if not user_facts:
            return []

        retention_score = self._calculate_retention(messages, user_facts)

        metric = MetricResult(
            name="knowledge_retention",
            value=retention_score,
            category=MetricCategory.COGNITIVE,
            metadata={
                "lead_id": lead_id,
                "facts_extracted": len(user_facts),
                "facts_retained": int(retention_score * len(user_facts)),
                "fact_types": list(user_facts.keys()),
            },
        )

        self.add_result(metric)
        return [metric]

    def _extract_facts(self, messages: List[Dict[str, Any]]) -> Dict[str, str]:
        """Extract facts from user messages."""
        facts: Dict[str, str] = {}

        for msg in messages:
            if msg["role"] != "lead":
                continue

            content = msg["content"] or ""

            for fact_type, pattern in self.fact_patterns.items():
                match = re.search(pattern, content, re.IGNORECASE)
                if match and fact_type not in facts:
                    facts[fact_type] = match.group(1).strip()

        return facts

    def _calculate_retention(
        self,
        messages: List[Dict[str, Any]],
        facts: Dict[str, str],
    ) -> float:
        """Calculate how many facts were retained/referenced."""
        if not facts:
            return 1.0

        mid_point = len(messages) // 2
        later_bot_messages = [
            m["content"] or "" for m in messages[mid_point:] if m["role"] != "lead"
        ]

        combined_bot = " ".join(later_bot_messages).lower()

        retained = 0
        for fact_type, fact_value in facts.items():
            if fact_value.lower() in combined_bot:
                retained += 1
            elif fact_type == "name" and any(
                ref in combined_bot
                for ref in ["tu nombre", "your name", fact_value.split()[0].lower()]
            ):
                retained += 1

        return retained / len(facts)
