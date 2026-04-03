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
- sanitize_rule_text(): Defense-in-depth sanitization before prompt injection
- filter_contradictions(): Remove contradictory rules, keep highest confidence
"""

import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LEARNING_MAX_RULES_IN_PROMPT = int(os.getenv("LEARNING_MAX_RULES_IN_PROMPT", "5"))
_MAX_RULE_TEXT_LENGTH = 500

# Simple TTL cache for get_applicable_rules
_rules_cache: Dict[str, Any] = {}
_rules_cache_ts: Dict[str, float] = {}
_RULES_CACHE_TTL = 60  # seconds
_RULES_CACHE_MAX_SIZE = 200  # max entries before eviction

# Prompt injection patterns to strip from rule_text
_INJECTION_PATTERNS = re.compile(
    r"(?i)"
    r"(ignore\s+(all\s+)?previous\s+instructions?"
    r"|you\s+are\s+now"
    r"|system\s*:"
    r"|assistant\s*:"
    r"|<\s*/?\s*(?:system|instructions?|prompt|role)\s*>)",
)

# Contradiction keyword pairs: (positive_keywords, negative_keywords)
# If one rule contains a positive and another contains a negative for the same
# topic, they contradict. We keep the one with higher confidence.
_CONTRADICTION_PAIRS = [
    (["usa ", "incluye", "incluir", "añade", "añadir", "utiliza", "usar"],
     ["no uses", "no incluyas", "no incluir", "evita", "evitar", "no utilices", "no usar", "elimina"]),
    (["breve", "corto", "corta", "conciso"],
     ["largo", "detallado", "extenso", "explica bien", "elabora"]),
    (["emoji", "emojis", "emoticono"],
     ["sin emoji", "no emoji", "evita emoji", "no uses emoji"]),
    (["formal", "usted"],
     ["informal", "coloquial", "casual", "tú"]),
    (["pregunta", "pregunta abierta"],
     ["no preguntes", "sin pregunta", "evita preguntar"]),
]


def sanitize_rule_text(text: str) -> str:
    """Strip prompt injection patterns and enforce max length."""
    if not text:
        return ""
    cleaned = _INJECTION_PATTERNS.sub("", text).strip()
    if len(cleaned) > _MAX_RULE_TEXT_LENGTH:
        cleaned = cleaned[:_MAX_RULE_TEXT_LENGTH].rsplit(" ", 1)[0]
    return cleaned


def filter_contradictions(rules: List[Dict]) -> List[Dict]:
    """Remove contradictory rules — keep the one with higher confidence."""
    if len(rules) <= 1:
        return rules

    to_remove = set()
    for i, r1 in enumerate(rules):
        if i in to_remove:
            continue
        t1 = r1["rule_text"].lower()
        for j, r2 in enumerate(rules):
            if j <= i or j in to_remove:
                continue
            t2 = r2["rule_text"].lower()
            for positives, negatives in _CONTRADICTION_PAIRS:
                r1_pos = any(kw in t1 for kw in positives)
                r1_neg = any(kw in t1 for kw in negatives)
                r2_pos = any(kw in t2 for kw in positives)
                r2_neg = any(kw in t2 for kw in negatives)
                if (r1_pos and r2_neg) or (r1_neg and r2_pos):
                    loser = j if r1["confidence"] >= r2["confidence"] else i
                    to_remove.add(loser)
                    logger.info(
                        f"[AUTOLEARN] Contradiction filtered: "
                        f"kept={'r1' if loser == j else 'r2'} "
                        f"({rules[loser]['rule_text'][:60]}...)"
                    )
                    break

    return [r for idx, r in enumerate(rules) if idx not in to_remove]


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
    if not rule_text or not rule_text.strip():
        logger.warning("[AUTOLEARN] Rejected rule with empty rule_text")
        return None
    confidence = max(0.0, min(1.0, confidence))
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

    # Evict stale entries if cache is too large
    if len(_rules_cache) > _RULES_CACHE_MAX_SIZE:
        expired = [k for k, ts in _rules_cache_ts.items() if now - ts > _RULES_CACHE_TTL]
        for k in expired:
            _rules_cache.pop(k, None)
            _rules_cache_ts.pop(k, None)

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
            .order_by(LearningRule.confidence.desc(), LearningRule.times_helped.desc())
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
            # NOTE: confidence is applied ONCE at line 185 (`score *= confidence`).
            score = 0.1

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

        result = []
        for score_val, r in top_rules:
            if score_val <= 0:
                continue
            cleaned_text = sanitize_rule_text(r.rule_text)
            if not cleaned_text:
                continue
            result.append({
                "id": str(r.id),
                "rule_text": cleaned_text,
                "example_bad": r.example_bad,
                "example_good": r.example_good,
                "pattern": r.pattern,
                "confidence": r.confidence,
            })

        result = filter_contradictions(result)

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
