"""
Lead Management Service.

Extracted from dm_agent.py as part of REFACTOR-PHASE2.
Provides lead scoring, stage management, and funnel analytics.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LeadStage(str, Enum):
    """Lead funnel stages."""

    NUEVO = "NUEVO"
    INTERESADO = "INTERESADO"
    CALIENTE = "CALIENTE"
    CLIENTE = "CLIENTE"
    FANTASMA = "FANTASMA"


@dataclass
class LeadScore:
    """
    Lead scoring result.

    Attributes:
        score: Numeric score 0-100
        stage: Current funnel stage
        factors: Breakdown of scoring factors
    """

    score: int
    stage: LeadStage
    factors: Dict[str, int] = field(default_factory=dict)
    calculated_at: datetime = field(default_factory=datetime.utcnow)


class LeadService:
    """
    Service for lead scoring and stage management.

    Provides:
    - Score calculation based on engagement metrics
    - Stage determination based on score and activity
    - Stage transition recommendations
    """

    # Score thresholds for each stage
    STAGE_THRESHOLDS = {
        LeadStage.CALIENTE: 70,
        LeadStage.INTERESADO: 40,
        LeadStage.NUEVO: 0,
    }

    # Days without contact to become FANTASMA
    FANTASMA_THRESHOLD_DAYS = 14

    # Scoring weights
    WEIGHTS = {
        "messages": 3,  # Points per message
        "messages_max": 30,  # Max points for messages
        "response_rate": 30,  # Max points for response rate
        "purchase_intent": 25,  # Points for purchase intent
        "links": 5,  # Points per link clicked
        "links_max": 15,  # Max points for links
    }

    def __init__(self) -> None:
        """Initialize lead service."""
        logger.info("[LeadService] Initialized")

    def calculate_score(
        self,
        messages_count: int = 0,
        response_rate: float = 0.0,
        purchase_intent: bool = False,
        opened_links: int = 0,
        **kwargs,
    ) -> int:
        """
        Calculate lead score based on engagement metrics.

        Args:
            messages_count: Number of messages exchanged
            response_rate: Response rate 0.0-1.0
            purchase_intent: Whether purchase intent detected
            opened_links: Number of links clicked

        Returns:
            Score between 0 and 100
        """
        score = 0

        # Message engagement (max 30 points)
        message_score = min(
            self.WEIGHTS["messages_max"],
            messages_count * self.WEIGHTS["messages"],
        )
        score += message_score

        # Response rate (max 30 points)
        response_score = int(response_rate * self.WEIGHTS["response_rate"])
        score += response_score

        # Purchase intent (25 points)
        if purchase_intent:
            score += self.WEIGHTS["purchase_intent"]

        # Link engagement (max 15 points)
        link_score = min(
            self.WEIGHTS["links_max"],
            opened_links * self.WEIGHTS["links"],
        )
        score += link_score

        # Cap at 100
        final_score = min(100, score)

        logger.debug(
            f"[LeadService] Score calculated: {final_score} "
            f"(msgs={message_score}, resp={response_score}, "
            f"intent={purchase_intent}, links={link_score})"
        )

        return final_score

    def determine_stage(
        self,
        score: int,
        days_since_contact: int = 0,
        is_customer: bool = False,
    ) -> LeadStage:
        """
        Determine lead stage based on score and activity.

        Args:
            score: Lead score 0-100
            days_since_contact: Days since last contact
            is_customer: Whether already a customer

        Returns:
            Appropriate LeadStage
        """
        # Customers stay as CLIENTE
        if is_customer:
            return LeadStage.CLIENTE

        # Check for inactivity (FANTASMA)
        if days_since_contact >= self.FANTASMA_THRESHOLD_DAYS:
            return LeadStage.FANTASMA

        # Determine stage by score threshold
        for stage, threshold in self.STAGE_THRESHOLDS.items():
            if score >= threshold:
                return stage

        return LeadStage.NUEVO

    def get_full_score(
        self,
        messages_count: int = 0,
        response_rate: float = 0.0,
        purchase_intent: bool = False,
        opened_links: int = 0,
        days_since_contact: int = 0,
        is_customer: bool = False,
    ) -> LeadScore:
        """
        Calculate full lead score with stage.

        Returns:
            LeadScore with score, stage, and factor breakdown
        """
        score = self.calculate_score(
            messages_count=messages_count,
            response_rate=response_rate,
            purchase_intent=purchase_intent,
            opened_links=opened_links,
        )

        stage = self.determine_stage(
            score=score,
            days_since_contact=days_since_contact,
            is_customer=is_customer,
        )

        factors = {
            "messages": min(
                self.WEIGHTS["messages_max"],
                messages_count * self.WEIGHTS["messages"],
            ),
            "response_rate": int(response_rate * self.WEIGHTS["response_rate"]),
            "purchase_intent": (
                self.WEIGHTS["purchase_intent"] if purchase_intent else 0
            ),
            "links": min(
                self.WEIGHTS["links_max"],
                opened_links * self.WEIGHTS["links"],
            ),
        }

        return LeadScore(score=score, stage=stage, factors=factors)

    def get_stage_recommendations(self, stage: LeadStage) -> Dict[str, Any]:
        """
        Get recommended actions for a lead stage.

        Args:
            stage: Current lead stage

        Returns:
            Dict with action, priority, and message_type
        """
        recommendations = {
            LeadStage.NUEVO: {
                "action": "introduce",
                "priority": "medium",
                "message_type": "welcome",
                "description": "New lead - introduce products",
            },
            LeadStage.INTERESADO: {
                "action": "nurture",
                "priority": "high",
                "message_type": "value_proposition",
                "description": "Interested - provide value and build trust",
            },
            LeadStage.CALIENTE: {
                "action": "close",
                "priority": "urgent",
                "message_type": "offer",
                "description": "Hot lead - present offer and close",
            },
            LeadStage.CLIENTE: {
                "action": "retain",
                "priority": "medium",
                "message_type": "support",
                "description": "Customer - provide support and upsell",
            },
            LeadStage.FANTASMA: {
                "action": "reactivate",
                "priority": "low",
                "message_type": "win_back",
                "description": "Inactive - attempt reactivation",
            },
        }
        return recommendations.get(stage, {})

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "stage_thresholds": {
                stage.value: threshold
                for stage, threshold in self.STAGE_THRESHOLDS.items()
            },
            "fantasma_threshold_days": self.FANTASMA_THRESHOLD_DAYS,
            "weights": self.WEIGHTS,
        }
