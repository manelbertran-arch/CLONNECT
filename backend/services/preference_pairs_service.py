"""
Preference Pairs Service — collect (chosen, rejected) training data from copilot actions.

Generates preference pairs from:
- approve: (suggested, None)
- edit: (edited_text, suggested)
- discard: (None, suggested)
- manual_override: (manual_text, suggested)
- best_of_n_ranking: winner vs each loser → N-1 pairs
- historical: (creator_response, None) mined from historical IG messages

Feature flag: ENABLE_PREFERENCE_PAIRS (default true)
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ENABLE_PREFERENCE_PAIRS = os.getenv("ENABLE_PREFERENCE_PAIRS", "true").lower() == "true"

# Session boundary: 4h gap (matches ConversationBoundaryDetector GAP_CHECK_SIGNALS_MINUTES=240)
_SESSION_GAP_HOURS = 4


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
    from collections import defaultdict

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
