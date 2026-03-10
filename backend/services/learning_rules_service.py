"""
Learning Rules Service — CRUD + contextual rule selection for autolearning.

Manages learning rules extracted from creator copilot actions (edits,
discards, manual overrides). Rules are injected into DM prompts to
autocorrect bot behavior.

Functions:
- create_rule(): Store a new rule with deduplication
- get_applicable_rules(): Context-scored rule retrieval (cached)
- update_rule_feedback(): Adjust confidence after rule application
- deactivate_rule(): Soft delete with optional supersession
- get_rules_count() / get_all_active_rules(): For consolidation
"""

import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LEARNING_MAX_RULES_IN_PROMPT = int(os.getenv("LEARNING_MAX_RULES_IN_PROMPT", "5"))

# Simple TTL cache for get_applicable_rules
_rules_cache: Dict[str, Any] = {}
_rules_cache_ts: Dict[str, float] = {}
_RULES_CACHE_TTL = 60  # seconds


def create_rule(
    creator_id,
    rule_text: str,
    pattern: str,
    applies_to_relationship_types: Optional[List[str]] = None,
    applies_to_message_types: Optional[List[str]] = None,
    applies_to_lead_stages: Optional[List[str]] = None,
    example_bad: Optional[str] = None,
    example_good: Optional[str] = None,
    confidence: float = 0.5,
    source_message_id=None,
    source: str = "realtime",
) -> Optional[Dict]:
    """Create a learning rule. Deduplicates: same pattern+text → increment confidence."""
    from api.database import SessionLocal
    from api.models import LearningRule

    session = SessionLocal()
    try:
        # Dedup check: same creator + pattern + similar rule_text
        existing = (
            session.query(LearningRule)
            .filter(
                LearningRule.creator_id == creator_id,
                LearningRule.pattern == pattern,
                LearningRule.rule_text == rule_text,
                LearningRule.is_active.is_(True),
            )
            .first()
        )

        if existing:
            # Increment confidence (cap at 1.0)
            existing.confidence = min(1.0, existing.confidence + 0.05)
            existing.version += 1
            session.commit()
            logger.info(
                f"[AUTOLEARN] Dedup rule {existing.id}: "
                f"confidence={existing.confidence:.2f} version={existing.version}"
            )
            _invalidate_cache(str(creator_id))
            return {"id": str(existing.id), "deduplicated": True, "confidence": existing.confidence}

        rule = LearningRule(
            creator_id=creator_id,
            rule_text=rule_text,
            pattern=pattern,
            applies_to_relationship_types=applies_to_relationship_types or [],
            applies_to_message_types=applies_to_message_types or [],
            applies_to_lead_stages=applies_to_lead_stages or [],
            example_bad=example_bad,
            example_good=example_good,
            confidence=confidence,
            source_message_id=source_message_id,
            source=source,
        )
        session.add(rule)
        session.commit()

        logger.info(
            f"[AUTOLEARN] Created rule {rule.id}: pattern={pattern} "
            f"confidence={confidence}"
        )
        _invalidate_cache(str(creator_id))
        return {"id": str(rule.id), "deduplicated": False, "confidence": confidence}

    except Exception as e:
        logger.error(f"[AUTOLEARN] create_rule error: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def get_applicable_rules(
    creator_db_id,
    intent: Optional[str] = None,
    relationship_type: Optional[str] = None,
    lead_stage: Optional[str] = None,
    max_rules: int = None,
) -> List[Dict]:
    """Get top N applicable rules scored by context match.

    Sync function with 60s TTL cache. Scores:
      +3 intent/pattern match, +2 relationship match, +2 stage match
      Multiplied by confidence, bonus for times_helped ratio.
    """
    if max_rules is None:
        max_rules = LEARNING_MAX_RULES_IN_PROMPT

    cache_key = f"{creator_db_id}:{intent}:{relationship_type}:{lead_stage}"
    now = time.time()
    if cache_key in _rules_cache:
        if now - _rules_cache_ts.get(cache_key, 0) < _RULES_CACHE_TTL:
            return _rules_cache[cache_key]

    from api.database import SessionLocal
    from api.models import LearningRule

    session = SessionLocal()
    try:
        rules = (
            session.query(LearningRule)
            .filter(
                LearningRule.creator_id == creator_db_id,
                LearningRule.is_active.is_(True),
            )
            .limit(100)
            .all()
        )

        if not rules:
            _rules_cache[cache_key] = []
            _rules_cache_ts[cache_key] = now
            return []

        scored = []
        for rule in rules:
            # Base score ensures rules with non-matching context still rank above zero.
            # Without this, context-specific rules (which are almost all rules) score
            # exactly 0 and get filtered by `if _ > 0`, injecting nothing.
            # Context matching raises the score — it's for RANKING, not GATING.
            score = rule.confidence * 0.1

            # Intent/pattern match
            if intent and rule.pattern:
                pattern_lower = rule.pattern.lower()
                intent_lower = intent.lower()
                if pattern_lower == intent_lower:
                    score += 3
                # Check if intent is in applies_to_message_types
                msg_types = rule.applies_to_message_types or []
                if intent_lower in [t.lower() for t in msg_types]:
                    score += 3

            # Relationship type match
            if relationship_type:
                rel_types = rule.applies_to_relationship_types or []
                if relationship_type.lower() in [t.lower() for t in rel_types]:
                    score += 2

            # Lead stage match
            if lead_stage:
                stages = rule.applies_to_lead_stages or []
                if lead_stage.lower() in [s.lower() for s in stages]:
                    score += 2

            # Universal rules (no specific context) get base score
            if not (rule.applies_to_relationship_types or rule.applies_to_message_types or rule.applies_to_lead_stages):
                score += 1

            # Multiply by confidence
            score *= rule.confidence

            # Bonus for helpful rules
            if rule.times_applied > 0:
                help_ratio = rule.times_helped / rule.times_applied
                score += help_ratio * 1.5

            # Bonus for pattern_batch rules (higher quality from LLM judge)
            if getattr(rule, "source", None) == "pattern_batch":
                score += 1.0

            scored.append((score, rule))

        # Sort by score descending, take top N
        scored.sort(key=lambda x: x[0], reverse=True)
        top_rules = scored[:max_rules]

        result = [
            {
                "id": str(r.id),
                "rule_text": r.rule_text,
                "example_bad": r.example_bad,
                "example_good": r.example_good,
                "pattern": r.pattern,
                "confidence": r.confidence,
            }
            for _, r in top_rules
            if _ > 0  # Only rules with positive score
        ]

        _rules_cache[cache_key] = result
        _rules_cache_ts[cache_key] = now
        return result

    except Exception as e:
        logger.error(f"[AUTOLEARN] get_applicable_rules error: {e}")
        return []
    finally:
        session.close()


def update_rule_feedback(rule_id, was_helpful: bool) -> bool:
    """Update times_applied/times_helped and adjust confidence."""
    from api.database import SessionLocal
    from api.models import LearningRule

    session = SessionLocal()
    try:
        rule = session.query(LearningRule).filter_by(id=rule_id).first()
        if not rule:
            return False

        rule.times_applied += 1
        if was_helpful:
            rule.times_helped += 1
            rule.confidence = min(1.0, rule.confidence + 0.05)
        else:
            rule.confidence = max(0.1, rule.confidence - 0.05)

        session.commit()
        _invalidate_cache(str(rule.creator_id))
        return True

    except Exception as e:
        logger.error(f"[AUTOLEARN] update_rule_feedback error: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def deactivate_rule(rule_id, superseded_by=None) -> bool:
    """Soft delete a rule, optionally setting superseded_by."""
    from api.database import SessionLocal
    from api.models import LearningRule

    session = SessionLocal()
    try:
        rule = session.query(LearningRule).filter_by(id=rule_id).first()
        if not rule:
            return False

        rule.is_active = False
        if superseded_by:
            rule.superseded_by = superseded_by

        session.commit()
        _invalidate_cache(str(rule.creator_id))
        return True

    except Exception as e:
        logger.error(f"[AUTOLEARN] deactivate_rule error: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_rules_count(creator_db_id) -> int:
    """Count active rules for a creator."""
    from api.database import SessionLocal
    from api.models import LearningRule

    session = SessionLocal()
    try:
        return (
            session.query(LearningRule)
            .filter(
                LearningRule.creator_id == creator_db_id,
                LearningRule.is_active.is_(True),
            )
            .count()
        )
    except Exception as e:
        logger.error(f"[AUTOLEARN] get_rules_count error: {e}")
        return 0
    finally:
        session.close()


def get_all_active_rules(creator_db_id) -> List[Dict]:
    """Get all active rules for consolidation."""
    from api.database import SessionLocal
    from api.models import LearningRule

    session = SessionLocal()
    try:
        rules = (
            session.query(LearningRule)
            .filter(
                LearningRule.creator_id == creator_db_id,
                LearningRule.is_active.is_(True),
            )
            .order_by(LearningRule.created_at)
            .limit(100)
            .all()
        )

        return [
            {
                "id": str(r.id),
                "rule_text": r.rule_text,
                "pattern": r.pattern,
                "confidence": r.confidence,
                "times_applied": r.times_applied,
                "times_helped": r.times_helped,
                "example_bad": r.example_bad,
                "example_good": r.example_good,
                "applies_to_relationship_types": r.applies_to_relationship_types or [],
                "applies_to_message_types": r.applies_to_message_types or [],
                "applies_to_lead_stages": r.applies_to_lead_stages or [],
            }
            for r in rules
        ]
    except Exception as e:
        logger.error(f"[AUTOLEARN] get_all_active_rules error: {e}")
        return []
    finally:
        session.close()


def _invalidate_cache(creator_id_str: str):
    """Invalidate all cached rules for a creator."""
    keys_to_remove = [k for k in _rules_cache if k.startswith(creator_id_str)]
    for k in keys_to_remove:
        _rules_cache.pop(k, None)
        _rules_cache_ts.pop(k, None)
