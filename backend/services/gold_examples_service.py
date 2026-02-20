"""
Gold Examples Service — curate and retrieve creator response examples for few-shot injection.

Scans recent approved/edited/manual messages to build a library of high-quality
examples that can be injected into DM prompts as concrete references.

Feature flag: ENABLE_GOLD_EXAMPLES (default false)
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GOLD_MAX_EXAMPLES_IN_PROMPT = int(os.getenv("GOLD_MAX_EXAMPLES_IN_PROMPT", "3"))
GOLD_MAX_CHARS_PER_EXAMPLE = int(os.getenv("GOLD_MAX_CHARS_PER_EXAMPLE", "500"))
GOLD_MAX_EXAMPLES_PER_CREATOR = 100
GOLD_EXPIRY_DAYS = 90

# Simple TTL cache for get_matching_examples
_examples_cache: Dict[str, Any] = {}
_examples_cache_ts: Dict[str, float] = {}
_EXAMPLES_CACHE_TTL = 120  # seconds

# Quality scores by source
_SOURCE_QUALITY = {
    "manual_override": 0.9,
    "approved": 0.8,
    "minor_edit": 0.7,
}


def create_gold_example(
    creator_db_id,
    user_message: str,
    creator_response: str,
    intent: Optional[str] = None,
    lead_stage: Optional[str] = None,
    relationship_type: Optional[str] = None,
    source: str = "approved",
    source_message_id=None,
) -> Optional[Dict]:
    """Create a gold example with deduplication."""
    from api.database import SessionLocal
    from api.models import GoldExample

    if not user_message or not creator_response:
        return None

    # Truncate long responses
    creator_response = creator_response[:GOLD_MAX_CHARS_PER_EXAMPLE]

    session = SessionLocal()
    try:
        # Dedup: same creator + similar user_message (first 100 chars)
        user_prefix = user_message[:100]
        existing = (
            session.query(GoldExample)
            .filter(
                GoldExample.creator_id == creator_db_id,
                GoldExample.is_active.is_(True),
                GoldExample.user_message.startswith(user_prefix),
            )
            .first()
        )
        if existing:
            # Update with newer response if quality is higher
            new_quality = _SOURCE_QUALITY.get(source, 0.5)
            if new_quality > existing.quality_score:
                existing.creator_response = creator_response
                existing.quality_score = new_quality
                existing.source = source
                session.commit()
                _invalidate_examples_cache(str(creator_db_id))
                return {"id": str(existing.id), "updated": True}
            return {"id": str(existing.id), "skipped": True}

        quality = _SOURCE_QUALITY.get(source, 0.5)
        example = GoldExample(
            creator_id=creator_db_id,
            user_message=user_message,
            creator_response=creator_response,
            intent=intent,
            lead_stage=lead_stage,
            relationship_type=relationship_type,
            source=source,
            source_message_id=source_message_id,
            quality_score=quality,
        )
        session.add(example)
        session.commit()

        _invalidate_examples_cache(str(creator_db_id))
        return {"id": str(example.id), "created": True, "quality": quality}

    except Exception as e:
        logger.error("[GOLD] create_gold_example error: %s", e)
        session.rollback()
        return None
    finally:
        session.close()


def get_matching_examples(
    creator_db_id,
    intent: Optional[str] = None,
    lead_stage: Optional[str] = None,
    relationship_type: Optional[str] = None,
) -> List[Dict]:
    """Get context-scored examples for prompt injection.

    Scoring: +3 intent, +2 stage, +1 relationship × quality_score.
    Returns top N examples, max GOLD_MAX_CHARS_PER_EXAMPLE chars each.
    """
    cache_key = f"{creator_db_id}:{intent}:{lead_stage}:{relationship_type}"
    now = time.time()
    if cache_key in _examples_cache:
        if now - _examples_cache_ts.get(cache_key, 0) < _EXAMPLES_CACHE_TTL:
            return _examples_cache[cache_key]

    from api.database import SessionLocal
    from api.models import GoldExample

    session = SessionLocal()
    try:
        examples = (
            session.query(GoldExample)
            .filter(
                GoldExample.creator_id == creator_db_id,
                GoldExample.is_active.is_(True),
            )
            .all()
        )

        if not examples:
            _examples_cache[cache_key] = []
            _examples_cache_ts[cache_key] = now
            return []

        scored = []
        for ex in examples:
            score = 0.0

            # Intent match
            if intent and ex.intent and ex.intent.lower() == intent.lower():
                score += 3

            # Lead stage match
            if lead_stage and ex.lead_stage and ex.lead_stage.lower() == lead_stage.lower():
                score += 2

            # Relationship type match
            if relationship_type and ex.relationship_type:
                if ex.relationship_type.lower() == relationship_type.lower():
                    score += 1

            # Universal examples (no context) get base score
            if not (ex.intent or ex.lead_stage or ex.relationship_type):
                score += 0.5

            # Multiply by quality
            score *= ex.quality_score

            scored.append((score, ex))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:GOLD_MAX_EXAMPLES_IN_PROMPT]

        result = [
            {
                "user_message": ex.user_message[:GOLD_MAX_CHARS_PER_EXAMPLE],
                "creator_response": ex.creator_response[:GOLD_MAX_CHARS_PER_EXAMPLE],
                "intent": ex.intent,
                "quality_score": ex.quality_score,
            }
            for _, ex in top
            if _ > 0
        ]

        _examples_cache[cache_key] = result
        _examples_cache_ts[cache_key] = now
        return result

    except Exception as e:
        logger.error("[GOLD] get_matching_examples error: %s", e)
        return []
    finally:
        session.close()


async def curate_examples(creator_id: str, creator_db_id) -> Dict[str, Any]:
    """Background: scan recent copilot messages and create gold examples.

    Also expires old low-usage examples and caps per-creator count.
    """
    from api.database import SessionLocal
    from api.models import GoldExample, Lead, Message

    session = SessionLocal()
    try:
        # Find recent approved/edited/manual messages (last 7 days)
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        messages = (
            session.query(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator_db_id,
                Message.role == "assistant",
                Message.copilot_action.in_(["approved", "edited", "manual_override"]),
                Message.created_at >= seven_days_ago,
            )
            .order_by(Message.created_at.desc())
            .limit(50)
            .all()
        )

        created = 0
        for msg in messages:
            # Get the preceding user message for this lead
            user_msg = (
                session.query(Message)
                .filter(
                    Message.lead_id == msg.lead_id,
                    Message.role == "user",
                    Message.created_at < msg.created_at,
                )
                .order_by(Message.created_at.desc())
                .first()
            )
            if not user_msg or not user_msg.content:
                continue

            # Determine source
            source = msg.copilot_action or "approved"
            if source == "edited":
                # Check edit severity — minor edits are good examples
                diff = msg.edit_diff or {}
                if diff.get("similarity_ratio", 1.0) >= 0.8:
                    source = "minor_edit"
                else:
                    continue  # Skip heavy edits — not good examples

            result = create_gold_example(
                creator_db_id=creator_db_id,
                user_message=user_msg.content,
                creator_response=msg.content,
                intent=msg.intent,
                source=source,
                source_message_id=msg.id,
            )
            if result and result.get("created"):
                created += 1

        # Expire old low-usage examples (>90 days, times_used < 3)
        expiry_cutoff = datetime.now(timezone.utc) - timedelta(days=GOLD_EXPIRY_DAYS)
        expired = (
            session.query(GoldExample)
            .filter(
                GoldExample.creator_id == creator_db_id,
                GoldExample.is_active.is_(True),
                GoldExample.created_at < expiry_cutoff,
                GoldExample.times_used < 3,
            )
            .update({"is_active": False}, synchronize_session=False)
        )

        # Cap at max per creator — deactivate lowest quality
        total_active = (
            session.query(GoldExample)
            .filter(
                GoldExample.creator_id == creator_db_id,
                GoldExample.is_active.is_(True),
            )
            .count()
        )
        over_cap = 0
        if total_active > GOLD_MAX_EXAMPLES_PER_CREATOR:
            # Deactivate lowest quality examples
            excess = (
                session.query(GoldExample)
                .filter(
                    GoldExample.creator_id == creator_db_id,
                    GoldExample.is_active.is_(True),
                )
                .order_by(GoldExample.quality_score.asc())
                .limit(total_active - GOLD_MAX_EXAMPLES_PER_CREATOR)
                .all()
            )
            for ex in excess:
                ex.is_active = False
                over_cap += 1

        session.commit()
        _invalidate_examples_cache(str(creator_db_id))

        logger.info(
            "[GOLD] %s: created=%d expired=%d capped=%d",
            creator_id, created, expired, over_cap,
        )
        return {
            "status": "done",
            "created": created,
            "expired": expired,
            "capped": over_cap,
        }

    except Exception as e:
        logger.error("[GOLD] curate_examples error for %s: %s", creator_id, e)
        session.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        session.close()


def _invalidate_examples_cache(creator_db_id_str: str):
    """Remove all cache entries for a creator."""
    keys_to_remove = [k for k in _examples_cache if k.startswith(creator_db_id_str)]
    for k in keys_to_remove:
        _examples_cache.pop(k, None)
        _examples_cache_ts.pop(k, None)
