"""
LLM-as-Judge Consistency Checker
Uses LLM to detect contradictions in bot responses
Paper ref: LLM-as-a-Judge (2024)
"""

import json
import logging
from typing import List

from metrics.base import MetricCategory, MetricResult, MetricsCollector
from sqlalchemy import text

logger = logging.getLogger(__name__)

JUDGE_PROMPT = """
Analyze the following bot responses in a conversation and detect contradictions.

BOT RESPONSES:
{responses}

QUESTION: Did the bot contradict itself at any point?

Reply in JSON:
{{
    "has_contradiction": true/false,
    "contradictions": ["description of contradiction 1", ...],
    "consistency_score": 0.0-1.0
}}

Only JSON, no additional explanation.
"""


class ConsistencyJudgeCollector(MetricsCollector):
    """Uses LLM to judge response consistency."""

    def __init__(self, creator_id: str):
        super().__init__(creator_id)

    def collect(self, lead_id: str) -> List[MetricResult]:
        """Analyze consistency using LLM judge."""
        from api.database import get_db_session

        with get_db_session() as db:
            result = db.execute(
                text(
                    """
                    SELECT content
                    FROM messages
                    WHERE lead_id = :lead_id
                    AND role != 'lead'
                    ORDER BY created_at ASC
                    """
                ),
                {"lead_id": lead_id},
            )
            messages = [row.content for row in result]

        if len(messages) < 3:
            return []

        responses = "\n".join([f"{i + 1}. {m}" for i, m in enumerate(messages)])
        prompt = JUDGE_PROMPT.format(responses=responses)

        try:
            from services.llm_service import LLMService

            llm = LLMService()
            llm_response = llm.generate_sync(
                prompt=prompt,
                system_prompt="You are a consistency evaluator. Reply only in JSON.",
                max_tokens=500,
                temperature=0,
            )

            if llm_response and hasattr(llm_response, "content"):
                judgment = json.loads(llm_response.content)
            else:
                judgment = {"consistency_score": 0.5, "error": "no_response"}

            score = judgment.get("consistency_score", 0.5)

        except Exception as e:
            logger.error("LLM judge failed: %s", e)
            score = 0.5
            judgment = {"error": str(e)}

        metric = MetricResult(
            name="consistency_llm_judge",
            value=score,
            category=MetricCategory.QUALITY,
            metadata={
                "lead_id": lead_id,
                "judgment": judgment,
                "response_count": len(messages),
            },
        )

        self.add_result(metric)
        return [metric]
