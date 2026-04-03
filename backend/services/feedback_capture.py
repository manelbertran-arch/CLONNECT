"""
FeedbackCapture — Unified feedback capture module.

Single entry point for ALL feedback signals:
  - Evaluator scores (human ratings, corrections)
  - Copilot actions (approve, edit, discard, manual, resolved)
  - Historical mining (backfill from old messages)
  - Best-of-N ranking (multi-candidate comparison)

Merged from:
  - services/feedback_store.py (evaluator feedback + auto-derivatives)
  - services/preference_pairs_service.py (preference pair collection)

Feature flags:
  - ENABLE_EVALUATOR_FEEDBACK (default true)
  - ENABLE_PREFERENCE_PAIRS (default true)
"""

import asyncio
import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ENABLE_EVALUATOR_FEEDBACK = os.getenv("ENABLE_EVALUATOR_FEEDBACK", "true").lower() == "true"
ENABLE_PREFERENCE_PAIRS = os.getenv("ENABLE_PREFERENCE_PAIRS", "true").lower() == "true"

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

# Session boundary: 4h gap (matches ConversationBoundaryDetector GAP_CHECK_SIGNALS_MINUTES=240)
_SESSION_GAP_HOURS = 4


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

    # Route: copilot actions → create_pairs_from_action
    if signal_type in _COPILOT_ACTION_MAP:
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
# Evaluator Feedback
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
# Auto-creation helpers (evaluator → derivatives)
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


# ---------------------------------------------------------------------------
# Preference Pairs — from preference_pairs_service.py
# ---------------------------------------------------------------------------

def _fetch_context_and_save_sync(
    creator_db_id, source_message_id, lead_id, user_message,
    intent, lead_stage, pairs_to_create,
) -> int:
    """Fetch conversation context + save pairs in a single DB session (thread-safe)."""
    from api.database import SessionLocal
    from api.models import Message, PreferencePair

    session = SessionLocal()
    try:
        # --- Fetch session-bounded conversation context ---
        conversation_context = []
        if lead_id:
            anchor_ts = None
            if source_message_id:
                anchor = session.query(Message.created_at).filter_by(id=source_message_id).first()
                if anchor:
                    anchor_ts = anchor[0]
            if not anchor_ts:
                anchor_ts = datetime.now(timezone.utc)

            session_floor = anchor_ts - timedelta(hours=_SESSION_GAP_HOURS)

            rows = (
                session.query(Message.role, Message.content, Message.created_at)
                .filter(
                    Message.lead_id == lead_id,
                    Message.created_at < anchor_ts,
                    Message.created_at >= session_floor,
                    Message.content.isnot(None),
                )
                .order_by(Message.created_at.desc())
                .limit(6)
                .all()
            )

            if rows:
                prev_ts = anchor_ts
                for role, content, ts in rows:
                    if (prev_ts - ts).total_seconds() > _SESSION_GAP_HOURS * 3600:
                        break
                    conversation_context.append({"role": role, "content": content[:500]})
                    prev_ts = ts
                conversation_context.reverse()
                conversation_context = conversation_context[:5]

        # --- Save pairs ---
        count = 0
        for pair_data in pairs_to_create:
            pair = PreferencePair(
                creator_id=creator_db_id,
                source_message_id=source_message_id,
                user_message=user_message,
                intent=intent,
                lead_stage=lead_stage,
                conversation_context=conversation_context,
                chosen=pair_data.get("chosen"),
                rejected=pair_data.get("rejected"),
                action_type=pair_data["action_type"],
                chosen_temperature=pair_data.get("chosen_temperature"),
                rejected_temperature=pair_data.get("rejected_temperature"),
                chosen_confidence=pair_data.get("chosen_confidence"),
                rejected_confidence=pair_data.get("rejected_confidence"),
                confidence_delta=pair_data.get("confidence_delta"),
                edit_diff=pair_data.get("edit_diff"),
            )
            session.add(pair)
            count += 1

        session.commit()
        logger.info(
            "[PREF_PAIRS] Created %d pairs for creator %s",
            count, creator_db_id,
        )
        return count

    except Exception as e:
        logger.error("[PREF_PAIRS] _fetch_context_and_save_sync error: %s", e)
        session.rollback()
        return 0
    finally:
        session.close()


async def create_pairs_from_action(
    action: str,
    creator_db_id,
    source_message_id=None,
    lead_id=None,
    suggested_response: Optional[str] = None,
    final_response: Optional[str] = None,
    user_message: Optional[str] = None,
    intent: Optional[str] = None,
    lead_stage: Optional[str] = None,
    edit_diff: Optional[dict] = None,
    best_of_n_candidates: Optional[List[dict]] = None,
    chosen_confidence: Optional[float] = None,
    rejected_confidence: Optional[float] = None,
) -> int:
    """Create preference pairs from a copilot action.

    Returns the number of pairs created.
    """
    if not ENABLE_PREFERENCE_PAIRS:
        return 0

    pairs_to_create: List[dict] = []

    # Base pair from the copilot action
    if action == "approved":
        pairs_to_create.append({
            "chosen": suggested_response,
            "rejected": None,
            "action_type": "approved",
            "chosen_confidence": chosen_confidence,
            "rejected_confidence": None,
        })
    elif action == "edited":
        pairs_to_create.append({
            "chosen": final_response,
            "rejected": suggested_response,
            "action_type": "edited",
            "edit_diff": edit_diff,
            "chosen_confidence": chosen_confidence,
            "rejected_confidence": rejected_confidence,
            "confidence_delta": (
                (chosen_confidence - rejected_confidence)
                if chosen_confidence is not None and rejected_confidence is not None
                else None
            ),
        })
    elif action == "discarded":
        pairs_to_create.append({
            "chosen": None,
            "rejected": suggested_response,
            "action_type": "discarded",
            "rejected_confidence": rejected_confidence,
        })
    elif action == "manual_override":
        pairs_to_create.append({
            "chosen": final_response,
            "rejected": suggested_response,
            "action_type": "manual_override",
            "chosen_confidence": chosen_confidence,
            "rejected_confidence": rejected_confidence,
            "confidence_delta": (
                (chosen_confidence - rejected_confidence)
                if chosen_confidence is not None and rejected_confidence is not None
                else None
            ),
        })
    elif action == "resolved_externally":
        # Creator replied directly — strongest divergence signal
        # Skip audio/sticker/media — not meaningful text comparisons
        _non_text = ("[🎤 Audio]", "[🏷️ Sticker]", "[📷", "[🎥", "[📎")
        is_non_text = final_response and any(final_response.startswith(p) for p in _non_text)
        if final_response and suggested_response and not is_non_text:
            pairs_to_create.append({
                "chosen": final_response,
                "rejected": suggested_response,
                "action_type": "divergence",
                "chosen_confidence": chosen_confidence,
                "rejected_confidence": rejected_confidence,
            })

    # Best-of-N ranking pairs: winner vs each loser
    if best_of_n_candidates and len(best_of_n_candidates) > 1:
        # Candidates should be sorted by rank (1=best)
        sorted_cands = sorted(best_of_n_candidates, key=lambda c: c.get("rank", 99))
        winner = sorted_cands[0]
        for loser in sorted_cands[1:]:
            pairs_to_create.append({
                "chosen": winner.get("content"),
                "rejected": loser.get("content"),
                "action_type": "best_of_n_ranking",
                "chosen_temperature": winner.get("temperature"),
                "rejected_temperature": loser.get("temperature"),
                "chosen_confidence": winner.get("confidence"),
                "rejected_confidence": loser.get("confidence"),
                "confidence_delta": (
                    (winner.get("confidence", 0) - loser.get("confidence", 0))
                    if winner.get("confidence") is not None and loser.get("confidence") is not None
                    else None
                ),
            })

    # BUG-6 guard: skip pairs where chosen == rejected (useless for DPO)
    pairs_to_create = [
        p for p in pairs_to_create
        if not (p.get("chosen") and p.get("rejected")
                and p["chosen"].strip() == p["rejected"].strip())
    ]

    if not pairs_to_create:
        return 0

    # BUG-2 + BUG-5: fetch context + save in one thread (single DB session)
    return await asyncio.to_thread(
        _fetch_context_and_save_sync, creator_db_id, source_message_id,
        lead_id, user_message, intent, lead_stage, pairs_to_create,
    )


def get_pairs_for_export(
    creator_db_id,
    limit: int = 100,
    offset: int = 0,
    action_type: Optional[str] = None,
    unexported_only: bool = False,
) -> List[Dict]:
    """Retrieve preference pairs for export/viewing."""
    from api.database import SessionLocal
    from api.models import PreferencePair

    session = SessionLocal()
    try:
        query = session.query(PreferencePair).filter(
            PreferencePair.creator_id == creator_db_id,
        )
        if action_type:
            query = query.filter(PreferencePair.action_type == action_type)
        if unexported_only:
            query = query.filter(PreferencePair.exported_at.is_(None))

        query = query.order_by(PreferencePair.created_at.desc())
        pairs = query.offset(offset).limit(limit).all()

        return [
            {
                "id": str(p.id),
                "chosen": p.chosen,
                "rejected": p.rejected,
                "user_message": p.user_message,
                "intent": p.intent,
                "lead_stage": p.lead_stage,
                "action_type": p.action_type,
                "chosen_temperature": p.chosen_temperature,
                "rejected_temperature": p.rejected_temperature,
                "chosen_confidence": p.chosen_confidence,
                "rejected_confidence": p.rejected_confidence,
                "confidence_delta": p.confidence_delta,
                "edit_diff": p.edit_diff,
                "conversation_context": p.conversation_context,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "exported_at": p.exported_at.isoformat() if p.exported_at else None,
                "batch_analyzed_at": p.batch_analyzed_at.isoformat() if p.batch_analyzed_at else None,
            }
            for p in pairs
        ]

    except Exception as e:
        logger.error("[PREF_PAIRS] get_pairs_for_export error: %s", e)
        return []
    finally:
        session.close()


def mark_exported(pair_ids: List[str]) -> int:
    """Mark pairs as exported. Returns count of updated rows."""
    if not pair_ids:
        return 0

    from api.database import SessionLocal
    from api.models import PreferencePair

    session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        uuids = [uuid.UUID(pid) for pid in pair_ids]
        count = (
            session.query(PreferencePair)
            .filter(PreferencePair.id.in_(uuids))
            .update({"exported_at": now}, synchronize_session=False)
        )
        session.commit()
        logger.info("[PREF_PAIRS] Marked %d pairs as exported", count)
        return count

    except Exception as e:
        logger.error("[PREF_PAIRS] mark_exported error: %s", e)
        session.rollback()
        return 0
    finally:
        session.close()


async def mine_historical_pairs(creator_id: str, creator_db_id, limit: int = 500) -> int:
    """Mine historical creator messages (copilot_action IS NULL) for preference pairs.

    For creators onboarded with years of historical IG data, this extracts
    (user_msg → creator_response) as 'historical' action_type pairs for ML training.
    These are high-quality approved-style pairs: the creator actually sent them.

    Quality filters:
    - Creator response: 15–250 chars (concise DM-style, not walls of text)
    - User message: > 5 chars
    - At most 5 pairs per lead (to avoid one conversation dominating)
    - Skip if a pair from this source_message_id already exists (dedup)

    Returns number of pairs created.
    """
    from sqlalchemy import func as sqlfunc
    from api.database import SessionLocal
    from api.models import Lead, Message, PreferencePair

    session = SessionLocal()
    created = 0
    try:
        rows = (
            session.query(Message, Lead)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator_db_id,
                Message.role == "assistant",
                Message.copilot_action.is_(None),
                sqlfunc.length(Message.content) >= 15,
                sqlfunc.length(Message.content) <= 250,
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )

        # Pre-fetch already-mined source_message_ids to avoid per-row queries
        source_ids = [msg.id for msg, _ in rows]
        already_mined = set()
        if source_ids:
            existing = (
                session.query(PreferencePair.source_message_id)
                .filter(PreferencePair.source_message_id.in_(source_ids))
                .all()
            )
            already_mined = {str(row[0]) for row in existing}

        # Filter candidates (dedup + per-lead cap)
        pairs_per_lead: Dict[str, int] = {}
        filtered_rows = []
        for msg, lead in rows:
            if str(msg.id) in already_mined:
                continue
            lead_key = str(msg.lead_id)
            if pairs_per_lead.get(lead_key, 0) >= 5:
                continue
            filtered_rows.append((msg, lead))
            pairs_per_lead[lead_key] = pairs_per_lead.get(lead_key, 0) + 1

        if not filtered_rows:
            return 0

        # BUG-4: Batch-fetch messages for candidate leads (eliminates N+1)
        candidate_lead_ids = list({msg.lead_id for msg, _ in filtered_rows})
        earliest_ts = min(msg.created_at for msg, _ in filtered_rows) - timedelta(hours=_SESSION_GAP_HOURS)

        # User messages only (for pairing: find which user msg triggered the response)
        user_msgs_raw = (
            session.query(Message)
            .filter(
                Message.lead_id.in_(candidate_lead_ids),
                Message.role == "user",
                Message.created_at >= earliest_ts,
                sqlfunc.length(Message.content) > 5,
            )
            .order_by(Message.lead_id, Message.created_at.desc())
            .all()
        )
        user_msgs_by_lead: Dict[str, list] = defaultdict(list)
        for um in user_msgs_raw:
            user_msgs_by_lead[str(um.lead_id)].append(um)

        # All messages (for conversation context: both user + assistant turns)
        all_msgs_raw = (
            session.query(Message)
            .filter(
                Message.lead_id.in_(candidate_lead_ids),
                Message.created_at >= earliest_ts,
                Message.content.isnot(None),
            )
            .order_by(Message.lead_id, Message.created_at.desc())
            .all()
        )
        all_msgs_by_lead: Dict[str, list] = defaultdict(list)
        for am in all_msgs_raw:
            all_msgs_by_lead[str(am.lead_id)].append(am)

        for msg, lead in filtered_rows:
            lead_key = str(msg.lead_id)
            # BUG-3: 4h session boundary for user message matching
            session_floor = msg.created_at - timedelta(hours=_SESSION_GAP_HOURS)

            user_msg = None
            for um in user_msgs_by_lead.get(lead_key, []):
                if um.created_at < msg.created_at and um.created_at >= session_floor:
                    user_msg = um
                    break  # sorted desc, first match is nearest

            if not user_msg or not user_msg.content:
                continue

            # Build conversation context from ALL messages (user + assistant turns)
            context_msgs = []
            prev_ts = msg.created_at
            for am in all_msgs_by_lead.get(lead_key, []):
                if am.created_at < msg.created_at and am.created_at >= session_floor:
                    if (prev_ts - am.created_at).total_seconds() > _SESSION_GAP_HOURS * 3600:
                        break
                    context_msgs.append({"role": am.role, "content": am.content[:500]})
                    prev_ts = am.created_at
                    if len(context_msgs) >= 5:
                        break
            context_msgs.reverse()

            pair = PreferencePair(
                creator_id=creator_db_id,
                source_message_id=msg.id,
                user_message=user_msg.content,
                intent=msg.intent,
                lead_stage=lead.status,
                chosen=msg.content,
                rejected=None,
                action_type="historical",
                conversation_context=context_msgs,
            )
            session.add(pair)
            created += 1

        session.commit()
        logger.info(
            "[PREF_PAIRS] mine_historical_pairs %s: created=%d from %d candidates",
            creator_id, created, len(rows),
        )
        return created

    except Exception as e:
        logger.error("[PREF_PAIRS] mine_historical_pairs error for %s: %s", creator_id, e)
        session.rollback()
        return 0
    finally:
        session.close()


async def curate_pairs(creator_id: str, creator_db_id) -> Dict[str, Any]:
    """Background: mine historical pairs when the library is thin (< 10 pairs).

    Mirrors gold_examples_service.curate_examples() — called by JOB 20 scheduler
    to backfill training data for newly onboarded creators with historical IG data.
    """
    from api.database import SessionLocal
    from api.models import PreferencePair

    session = SessionLocal()
    try:
        total = (
            session.query(PreferencePair)
            .filter(PreferencePair.creator_id == creator_db_id)
            .count()
        )
    finally:
        session.close()

    historical_created = 0
    if total < 10:
        historical_created = await mine_historical_pairs(creator_id, creator_db_id, limit=500)

    logger.info(
        "[PREF_PAIRS] curate_pairs %s: total_before=%d historical_created=%d",
        creator_id, total, historical_created,
    )
    return {
        "status": "done",
        "total_before": total,
        "historical_created": historical_created,
    }
