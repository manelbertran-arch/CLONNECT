"""
FeedbackStore — Unified FeedbackCapture facade.

Single entry point for ALL feedback signals:
  - Evaluator scores (human ratings, corrections)
  - Copilot actions (approve, edit, discard, manual, resolved)
  - Historical mining (backfill from old messages)
  - Best-of-N ranking (multi-candidate comparison)

Routes each signal to the correct downstream handler
(evaluator_feedback, preference_pairs, gold_examples).

Feature flag: ENABLE_EVALUATOR_FEEDBACK (default true)
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ENABLE_EVALUATOR_FEEDBACK = os.getenv("ENABLE_EVALUATOR_FEEDBACK", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Quality scores per signal type (BeeS paper heuristic, NeurIPS'25)
# ---------------------------------------------------------------------------
QUALITY_SCORES = {
    "copilot_approve": 0.6,     # Weak positive — bot was good enough
    "copilot_edit": 0.8,        # Strong — creator corrected, both versions available
    "copilot_discard": 0.4,     # Negative signal — bot was bad
    "copilot_manual": 0.8,      # Strong — creator wrote their own
    "copilot_resolved": 0.9,    # Strongest — creator bypassed bot entirely
    "historical_mine": 0.5,     # Medium — real but no A/B comparison
    "best_of_n": 0.7,           # Good — ranked comparison available
    # evaluator_score: dynamic → lo_enviarias / 5.0
}

# Map capture signal_type → preference_pairs action name
_COPILOT_ACTION_MAP = {
    "copilot_approve": "approved",
    "copilot_edit": "edited",
    "copilot_discard": "discarded",
    "copilot_manual": "manual_override",
    "copilot_resolved": "resolved_externally",
}


# ---------------------------------------------------------------------------
# Unified capture() — SINGLE ENTRY POINT for all feedback signals
# ---------------------------------------------------------------------------

async def capture(
    signal_type: str,
    creator_db_id,
    lead_id=None,
    user_message: Optional[str] = None,
    bot_response: Optional[str] = None,
    creator_response: Optional[str] = None,
    conversation_context: Optional[list] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Unified feedback capture — routes to correct handler by signal_type.

    Args:
        signal_type: One of: evaluator_score, copilot_approve, copilot_edit,
            copilot_discard, copilot_manual, copilot_resolved, historical_mine,
            best_of_n
        creator_db_id: Creator UUID (from DB)
        lead_id: Lead UUID (optional, for copilot actions)
        user_message: The user/lead message that triggered the response
        bot_response: The bot's suggested response
        creator_response: What the creator actually wrote (for edits/manual)
        conversation_context: Previous messages for context
        metadata: Signal-specific data (scores, error_tags, intent, etc.)

    Returns:
        Dict with status, quality_score, and handler-specific results.
    """
    meta = metadata or {}
    quality = _compute_quality(signal_type, meta)

    logger.info(
        "[CAPTURE] signal=%s creator=%s quality=%.2f",
        signal_type, creator_db_id, quality,
    )

    # Route: evaluator scores → save_feedback (sync, needs to_thread)
    if signal_type == "evaluator_score":
        result = await asyncio.to_thread(
            save_feedback,
            creator_db_id=creator_db_id,
            evaluator_id=meta.get("evaluator_id", "unknown"),
            user_message=user_message or "",
            bot_response=bot_response or "",
            coherencia=meta.get("coherencia"),
            lo_enviarias=meta.get("lo_enviarias"),
            ideal_response=creator_response,
            error_tags=meta.get("error_tags"),
            error_free_text=meta.get("error_free_text"),
            conversation_id=meta.get("conversation_id"),
            source_message_id=meta.get("source_message_id"),
            conversation_history=conversation_context,
            intent_detected=meta.get("intent"),
            doc_d_version=meta.get("doc_d_version"),
            model_id=meta.get("model_id"),
            system_prompt_hash=meta.get("system_prompt_hash"),
        )
        return {**result, "quality_score": quality, "signal_type": signal_type}

    # Route: copilot actions → preference_pairs_service
    if signal_type in _COPILOT_ACTION_MAP:
        from services.preference_pairs_service import create_pairs_from_action
        action_name = _COPILOT_ACTION_MAP[signal_type]
        pairs_created = await create_pairs_from_action(
            action=action_name,
            creator_db_id=creator_db_id,
            source_message_id=meta.get("source_message_id"),
            lead_id=lead_id,
            suggested_response=bot_response,
            final_response=creator_response,
            user_message=user_message,
            intent=meta.get("intent"),
            lead_stage=meta.get("lead_stage"),
            edit_diff=meta.get("edit_diff"),
            best_of_n_candidates=meta.get("best_of_n_candidates"),
            chosen_confidence=meta.get("chosen_confidence"),
            rejected_confidence=meta.get("rejected_confidence"),
        )
        return {
            "status": "created",
            "signal_type": signal_type,
            "quality_score": quality,
            "pairs_created": pairs_created,
        }

    # Route: best_of_n → preference_pairs (with candidates)
    if signal_type == "best_of_n":
        from services.preference_pairs_service import create_pairs_from_action
        pairs_created = await create_pairs_from_action(
            action="approved",  # base action, candidates do the work
            creator_db_id=creator_db_id,
            source_message_id=meta.get("source_message_id"),
            lead_id=lead_id,
            suggested_response=bot_response,
            user_message=user_message,
            intent=meta.get("intent"),
            lead_stage=meta.get("lead_stage"),
            best_of_n_candidates=meta.get("best_of_n_candidates"),
        )
        return {
            "status": "created",
            "signal_type": signal_type,
            "quality_score": quality,
            "pairs_created": pairs_created,
        }

    # Route: historical mining → mine_historical_pairs
    if signal_type == "historical_mine":
        from services.preference_pairs_service import mine_historical_pairs
        creator_slug = meta.get("creator_slug", "")
        limit = meta.get("limit", 500)
        pairs_created = await mine_historical_pairs(
            creator_slug, creator_db_id, limit=limit,
        )
        return {
            "status": "created",
            "signal_type": signal_type,
            "quality_score": quality,
            "pairs_created": pairs_created,
        }

    logger.warning("[CAPTURE] Unknown signal_type: %s", signal_type)
    return {"status": "error", "message": f"Unknown signal_type: {signal_type}"}


def _compute_quality(signal_type: str, metadata: dict) -> float:
    """Compute quality score for a feedback signal."""
    if signal_type == "evaluator_score":
        lo = metadata.get("lo_enviarias")
        return lo / 5.0 if lo is not None else 0.5
    return QUALITY_SCORES.get(signal_type, 0.5)


# ---------------------------------------------------------------------------
# Evaluator Feedback — NEW (the missing piece)
# ---------------------------------------------------------------------------

def save_feedback(
    creator_db_id,
    evaluator_id: str,
    user_message: str,
    bot_response: str,
    coherencia: Optional[int] = None,
    lo_enviarias: Optional[int] = None,
    ideal_response: Optional[str] = None,
    error_tags: Optional[list] = None,
    error_free_text: Optional[str] = None,
    conversation_id=None,
    source_message_id=None,
    conversation_history: Optional[list] = None,
    intent_detected: Optional[str] = None,
    doc_d_version: Optional[str] = None,
    model_id: Optional[str] = None,
    system_prompt_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Save structured evaluator feedback. Auto-creates derivative records.

    When ideal_response is provided (non-empty):
      - Auto-creates a PreferencePair (chosen=ideal, rejected=bot)
      - Auto-creates a GoldExample if lo_enviarias >= 4

    Returns dict with status + feedback_id and derivative record counts.
    Returns {"status": "disabled"} if feature flag is off.
    Returns {"status": "error", "message": ...} on failure.
    """
    if not ENABLE_EVALUATOR_FEEDBACK:
        return {"status": "disabled"}

    from api.database import SessionLocal
    from api.models import EvaluatorFeedback

    session = SessionLocal()
    try:
        # FIX FB-02: Dedup — if source_message_id provided, check for existing
        if source_message_id:
            existing = session.query(EvaluatorFeedback).filter(
                EvaluatorFeedback.creator_id == creator_db_id,
                EvaluatorFeedback.source_message_id == source_message_id,
                EvaluatorFeedback.evaluator_id == evaluator_id,
            ).first()
            if existing:
                # Update existing record instead of creating duplicate
                existing.coherencia = coherencia if coherencia is not None else existing.coherencia
                existing.lo_enviarias = lo_enviarias if lo_enviarias is not None else existing.lo_enviarias
                existing.ideal_response = ideal_response if ideal_response else existing.ideal_response
                existing.error_tags = error_tags if error_tags is not None else existing.error_tags
                existing.error_free_text = error_free_text if error_free_text else existing.error_free_text
                session.commit()
                logger.info(
                    "[FEEDBACK] Updated existing feedback %s for source_message %s",
                    existing.id, source_message_id,
                )
                return {
                    "status": "updated",
                    "feedback_id": str(existing.id),
                    "pair_created": False,
                    "gold_created": False,
                }

        feedback = EvaluatorFeedback(
            creator_id=creator_db_id,
            evaluator_id=evaluator_id,
            user_message=user_message,
            bot_response=bot_response,
            coherencia=coherencia,
            lo_enviarias=lo_enviarias,
            ideal_response=ideal_response,
            error_tags=error_tags,
            error_free_text=error_free_text,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            conversation_history=conversation_history,
            intent_detected=intent_detected,
            doc_d_version=doc_d_version,
            model_id=model_id,
            system_prompt_hash=system_prompt_hash,
        )
        session.add(feedback)

        logger.info(
            "[FEEDBACK] Saving evaluator feedback from %s for creator %s "
            "(coherencia=%s, lo_enviarias=%s, has_ideal=%s)",
            evaluator_id, creator_db_id,
            coherencia, lo_enviarias, ideal_response is not None,
        )

        # Auto-create derivative records in the SAME transaction
        pair_created = False
        gold_created = False

        # FIX FB-03: Check non-empty ideal_response (not just truthy)
        has_ideal = bool(ideal_response and ideal_response.strip())

        if has_ideal:
            pair_created = _auto_create_preference_pair(
                session=session,
                creator_db_id=creator_db_id,
                user_message=user_message,
                bot_response=bot_response,
                ideal_response=ideal_response,
                intent=intent_detected,
                source_message_id=source_message_id,
            )

            if lo_enviarias is not None and lo_enviarias >= 4:
                gold_created = _auto_create_gold_example(
                    session=session,
                    creator_db_id=creator_db_id,
                    user_message=user_message,
                    ideal_response=ideal_response,
                    intent=intent_detected,
                    source_message_id=source_message_id,
                )

        # FIX FB-01: Single commit for feedback + all derivatives
        session.commit()
        feedback_id = str(feedback.id)

        return {
            "status": "created",
            "feedback_id": feedback_id,
            "pair_created": pair_created,
            "gold_created": gold_created,
        }

    except Exception as e:
        logger.error("[FEEDBACK] save_feedback error: %s", e)
        session.rollback()
        # FIX FB-07: Distinguish error from disabled
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


def get_feedback(
    creator_db_id,
    evaluator_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    min_coherencia: Optional[int] = None,
    min_lo_enviarias: Optional[int] = None,
    with_ideal_only: bool = False,
) -> List[Dict]:
    """Retrieve evaluator feedback with optional filters."""
    from api.database import SessionLocal
    from api.models import EvaluatorFeedback

    session = SessionLocal()
    try:
        query = session.query(EvaluatorFeedback).filter(
            EvaluatorFeedback.creator_id == creator_db_id,
        )
        if evaluator_id:
            query = query.filter(EvaluatorFeedback.evaluator_id == evaluator_id)
        if min_coherencia is not None:
            query = query.filter(EvaluatorFeedback.coherencia >= min_coherencia)
        if min_lo_enviarias is not None:
            query = query.filter(EvaluatorFeedback.lo_enviarias >= min_lo_enviarias)
        if with_ideal_only:
            query = query.filter(EvaluatorFeedback.ideal_response.isnot(None))

        query = query.order_by(EvaluatorFeedback.created_at.desc())
        rows = query.offset(offset).limit(limit).all()

        return [
            {
                "id": str(r.id),
                "evaluator_id": r.evaluator_id,
                "user_message": r.user_message,
                "bot_response": r.bot_response,
                "coherencia": r.coherencia,
                "lo_enviarias": r.lo_enviarias,
                "ideal_response": r.ideal_response,
                "error_tags": r.error_tags,
                "error_free_text": r.error_free_text,
                "intent_detected": r.intent_detected,
                "model_id": r.model_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    except Exception as e:
        logger.error("[FEEDBACK] get_feedback error: %s", e)
        return []
    finally:
        session.close()


def get_feedback_stats(creator_db_id) -> Dict[str, Any]:
    """Aggregate stats across all feedback types for a creator.

    Returns dict with stats or {"status": "error"} on failure.
    """
    from sqlalchemy import func as sqlfunc
    from api.database import SessionLocal
    from api.models import EvaluatorFeedback, GoldExample, LearningRule, PreferencePair

    session = SessionLocal()
    try:
        # Evaluator feedback stats
        ef_total = session.query(sqlfunc.count(EvaluatorFeedback.id)).filter(
            EvaluatorFeedback.creator_id == creator_db_id
        ).scalar() or 0
        ef_with_ideal = session.query(sqlfunc.count(EvaluatorFeedback.id)).filter(
            EvaluatorFeedback.creator_id == creator_db_id,
            EvaluatorFeedback.ideal_response.isnot(None),
        ).scalar() or 0
        ef_avg_coherencia = session.query(sqlfunc.avg(EvaluatorFeedback.coherencia)).filter(
            EvaluatorFeedback.creator_id == creator_db_id,
            EvaluatorFeedback.coherencia.isnot(None),
        ).scalar()
        ef_avg_lo_enviarias = session.query(sqlfunc.avg(EvaluatorFeedback.lo_enviarias)).filter(
            EvaluatorFeedback.creator_id == creator_db_id,
            EvaluatorFeedback.lo_enviarias.isnot(None),
        ).scalar()

        # Other feedback counts
        pp_total = session.query(sqlfunc.count(PreferencePair.id)).filter(
            PreferencePair.creator_id == creator_db_id
        ).scalar() or 0
        lr_active = session.query(sqlfunc.count(LearningRule.id)).filter(
            LearningRule.creator_id == creator_db_id,
            LearningRule.is_active.is_(True),
        ).scalar() or 0
        ge_active = session.query(sqlfunc.count(GoldExample.id)).filter(
            GoldExample.creator_id == creator_db_id,
            GoldExample.is_active.is_(True),
        ).scalar() or 0

        return {
            "evaluator_feedback": {
                "total": ef_total,
                "with_ideal_response": ef_with_ideal,
                "avg_coherencia": round(ef_avg_coherencia, 2) if ef_avg_coherencia else None,
                "avg_lo_enviarias": round(ef_avg_lo_enviarias, 2) if ef_avg_lo_enviarias else None,
            },
            "preference_pairs": {"total": pp_total},
            "learning_rules": {"active": lr_active},
            "gold_examples": {"active": ge_active},
        }

    except Exception as e:
        logger.error("[FEEDBACK] get_feedback_stats error: %s", e)
        # FIX FB-08: Return error status instead of empty dict
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Auto-creation helpers
# ---------------------------------------------------------------------------

def _auto_create_preference_pair(
    session,
    creator_db_id,
    user_message: str,
    bot_response: str,
    ideal_response: str,
    intent: Optional[str] = None,
    source_message_id=None,
) -> bool:
    """Create a preference pair from evaluator correction. Uses caller's session."""
    from api.models import PreferencePair

    try:
        pair = PreferencePair(
            creator_id=creator_db_id,
            source_message_id=source_message_id,
            user_message=user_message,
            chosen=ideal_response,
            rejected=bot_response,
            action_type="evaluator_correction",
            intent=intent,
        )
        session.add(pair)
        logger.info("[FEEDBACK] Auto-created preference pair from evaluator correction")
        return True
    except Exception as e:
        logger.error("[FEEDBACK] _auto_create_preference_pair error: %s", e)
        return False


def _auto_create_gold_example(
    session,
    creator_db_id,
    user_message: str,
    ideal_response: str,
    intent: Optional[str] = None,
    source_message_id=None,
) -> bool:
    """Create a gold example from high-quality evaluator correction. Uses caller's session."""
    from api.models import GoldExample

    try:
        # Dedup: check for existing active example with same user_message
        if source_message_id:
            existing = (
                session.query(GoldExample)
                .filter(
                    GoldExample.creator_id == creator_db_id,
                    GoldExample.is_active.is_(True),
                    GoldExample.source_message_id == source_message_id,
                )
                .first()
            )
        else:
            existing = (
                session.query(GoldExample)
                .filter(
                    GoldExample.creator_id == creator_db_id,
                    GoldExample.is_active.is_(True),
                    GoldExample.user_message == user_message,
                )
                .first()
            )
        if existing:
            # Update if quality is higher (evaluator_correction = 0.9)
            if 0.9 > existing.quality_score:
                existing.creator_response = ideal_response
                existing.quality_score = 0.9
                existing.source = "evaluator_correction"
            return True

        example = GoldExample(
            creator_id=creator_db_id,
            user_message=user_message,
            creator_response=ideal_response,
            intent=intent,
            source="evaluator_correction",
            source_message_id=source_message_id,
            quality_score=0.9,  # Evaluator-approved = high quality
            is_active=True,
        )
        session.add(example)
        logger.info("[FEEDBACK] Auto-created gold example from evaluator correction")
        return True
    except Exception as e:
        logger.error("[FEEDBACK] _auto_create_gold_example error: %s", e)
        return False
