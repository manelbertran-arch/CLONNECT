"""
Preference Pairs Service — collect (chosen, rejected) training data from copilot actions.

Generates preference pairs from:
- approve: (suggested, None)
- edit: (edited_text, suggested)
- discard: (None, suggested)
- manual_override: (manual_text, suggested)
- best_of_n_ranking: winner vs each loser → N-1 pairs

Feature flag: ENABLE_PREFERENCE_PAIRS (default false)
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ENABLE_PREFERENCE_PAIRS = os.getenv("ENABLE_PREFERENCE_PAIRS", "false").lower() == "true"


async def create_pairs_from_action(
    action: str,
    creator_db_id,
    source_message_id=None,
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

    from api.database import SessionLocal
    from api.models import PreferencePair

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

    if not pairs_to_create:
        return 0

    session = SessionLocal()
    try:
        count = 0
        for pair_data in pairs_to_create:
            pair = PreferencePair(
                creator_id=creator_db_id,
                source_message_id=source_message_id,
                user_message=user_message,
                intent=intent,
                lead_stage=lead_stage,
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
            "[PREF_PAIRS] Created %d pairs from %s for creator %s",
            count, action, creator_db_id,
        )
        return count

    except Exception as e:
        logger.error("[PREF_PAIRS] create_pairs_from_action error: %s", e)
        session.rollback()
        return 0
    finally:
        session.close()


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
