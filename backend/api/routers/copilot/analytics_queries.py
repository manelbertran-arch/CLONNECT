"""Heavy DB query functions for copilot analytics endpoints."""
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def fetch_notifications(session, creator, since_dt):
    """
    Fetch notification data: new messages, pending responses, hot leads.

    Returns dict ready for HTTP response.
    """
    from api.models import Lead, Message

    # New user messages (increased from 20 to 50)
    new_user_messages = (
        session.query(Message, Lead)
        .join(Lead, Message.lead_id == Lead.id)
        .filter(
            Lead.creator_id == creator.id, Message.role == "user", Message.created_at > since_dt
        )
        .order_by(Message.created_at.desc())
        .limit(50)
        .all()
    )

    new_messages = []
    for msg, lead in new_user_messages:
        new_messages.append(
            {
                "id": str(msg.id),
                "lead_id": str(lead.id),
                "follower_id": lead.platform_user_id,
                "username": lead.username or "",
                "platform": lead.platform,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else "",
            }
        )

    # Pending responses (increased from 20 to 50)
    pending = (
        session.query(Message, Lead)
        .join(Lead, Message.lead_id == Lead.id)
        .filter(
            Lead.creator_id == creator.id,
            Message.status == "pending_approval",
            Message.role == "assistant",
        )
        .order_by(Message.created_at.desc())
        .limit(50)
        .all()
    )

    pending_responses = []
    for msg, lead in pending:
        # Get user message
        user_msg = (
            session.query(Message)
            .filter(Message.lead_id == lead.id, Message.role == "user")
            .order_by(Message.created_at.desc())
            .first()
        )

        pending_responses.append(
            {
                "id": str(msg.id),
                "lead_id": str(lead.id),
                "follower_id": lead.platform_user_id,
                "username": lead.username or "",
                "platform": lead.platform,
                "user_message": user_msg.content if user_msg else "",
                "suggested_response": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else "",
            }
        )

    # Hot leads (increased from 10 to 25)
    hot_leads = (
        session.query(Lead)
        .filter(
            Lead.creator_id == creator.id, Lead.status == "hot", Lead.last_contact_at > since_dt
        )
        .order_by(Lead.last_contact_at.desc())
        .limit(25)
        .all()
    )

    hot_leads_data = [
        {
            "id": str(lead.id),
            "follower_id": lead.platform_user_id,
            "username": lead.username or "",
            "platform": lead.platform,
            "purchase_intent": lead.purchase_intent or 0.0,
            "last_contact": lead.last_contact_at.isoformat() if lead.last_contact_at else "",
        }
        for lead in hot_leads
    ]

    return {
        "new_messages": new_messages,
        "pending_responses": pending_responses,
        "hot_leads": hot_leads_data,
    }


def fetch_pending_for_lead(session, creator, lead_id):
    """
    Fetch pending copilot suggestion for a specific lead with conversation context.

    Returns dict with 'pending' key (None if no pending).
    """
    from api.models import Lead, Message
    from core.copilot_service import get_copilot_service

    # Find the lead
    lead = session.query(Lead).filter_by(id=lead_id, creator_id=creator.id).first()
    if not lead:
        return None  # Signal 404

    # Find pending suggestion for this lead
    pending_msg = (
        session.query(Message)
        .filter(
            Message.lead_id == lead.id,
            Message.role == "assistant",
            Message.status == "pending_approval",
        )
        .order_by(Message.created_at.desc())
        .first()
    )

    if not pending_msg:
        return {"pending": None}

    # Get last user message
    user_msg = (
        session.query(Message)
        .filter(Message.lead_id == lead.id, Message.role == "user")
        .order_by(Message.created_at.desc())
        .first()
    )

    service = get_copilot_service()
    context = service._get_conversation_context(session, lead.id)

    # Extract best_of_n candidates from msg_metadata
    bon = (pending_msg.msg_metadata or {}).get("best_of_n", {})
    candidates_list = None
    if bon.get("candidates"):
        candidates_list = [
            {"content": c["content"], "temperature": c["temperature"],
             "confidence": c.get("confidence", 0), "rank": c.get("rank", 0)}
            for c in bon["candidates"]
        ]

    pending_dict = {
        "id": str(pending_msg.id),
        "lead_id": str(lead.id),
        "follower_id": lead.platform_user_id,
        "platform": lead.platform,
        "username": lead.username or "",
        "full_name": lead.full_name or "",
        "user_message": user_msg.content if user_msg else "",
        "suggested_response": pending_msg.content,
        "intent": pending_msg.intent or "",
        "created_at": pending_msg.created_at.isoformat() if pending_msg.created_at else "",
        "status": pending_msg.status,
        "conversation_context": context,
        "confidence": pending_msg.confidence_score,
    }
    if candidates_list:
        pending_dict["candidates"] = candidates_list

    return {"pending": pending_dict}


def fetch_comparisons(session, creator, offset, limit):
    """
    Fetch side-by-side comparisons of bot suggestions vs creator responses.

    Returns dict with comparisons, count, has_more.
    """
    from sqlalchemy import text

    rows = session.execute(text("""
        WITH
        -- Source 1: Copilot-era edits (bot suggested -> creator edited)
        copilot_edits AS (
            SELECT
                m.id, m.lead_id, m.suggested_response as bot_suggestion, m.content as creator_response,
                m.copilot_action as action, m.edit_diff, m.confidence_score,
                m.response_time_ms, m.created_at,
                COALESCE(l.full_name, l.username, l.platform_user_id) as lead_name,
                l.platform, l.platform_user_id,
                (m.suggested_response = m.content) as is_identical,
                'copilot' as source,
                NULL::json as creator_responses_json
            FROM messages m
            JOIN leads l ON m.lead_id = l.id
            WHERE l.creator_id = :creator_id
            AND m.role = 'assistant'
            AND m.copilot_action IN ('edited', 'manual_override', 'approved', 'resolved_externally')
            AND m.suggested_response IS NOT NULL
        ),
        -- Source 2: Legacy -- bot auto-sent paired with ALL creator manual responses
        bot_auto AS (
            SELECT m.id, m.lead_id, m.content as bot_suggestion,
                   m.created_at, m.intent, m.confidence_score,
                   COALESCE(l.full_name, l.username, l.platform_user_id) as lead_name,
                   l.platform, l.platform_user_id
            FROM messages m
            JOIN leads l ON m.lead_id = l.id
            WHERE l.creator_id = :creator_id
            AND m.role = 'assistant'
            AND m.copilot_action IS NULL
            AND (m.approved_by IS NULL OR m.approved_by = 'auto')
            AND m.status = 'sent'
            AND m.content NOT IN ('Mentioned you in their story', 'Shared content')
        ),
        legacy_pairs AS (
            SELECT
                ba.id, ba.lead_id, ba.bot_suggestion, cr.first_response as creator_response,
                'legacy_comparison' as action,
                NULL::json as edit_diff, ba.confidence_score,
                NULL::integer as response_time_ms,
                ba.created_at,
                ba.lead_name, ba.platform, ba.platform_user_id,
                (ba.bot_suggestion = cr.first_response) as is_identical,
                'legacy' as source,
                cr.all_responses as creator_responses_json
            FROM bot_auto ba
            CROSS JOIN LATERAL (
                SELECT
                    (SELECT content FROM messages
                     WHERE lead_id = ba.lead_id AND role = 'assistant'
                     AND approved_by = 'creator_manual'
                     AND created_at BETWEEN ba.created_at - INTERVAL '4 hours'
                                         AND ba.created_at + INTERVAL '24 hours'
                     ORDER BY created_at ASC LIMIT 1
                    ) as first_response,
                    (SELECT json_agg(json_build_object(
                        'content', content,
                        'timestamp', created_at::text
                     ) ORDER BY created_at ASC)
                     FROM messages
                     WHERE lead_id = ba.lead_id AND role = 'assistant'
                     AND approved_by = 'creator_manual'
                     AND created_at BETWEEN ba.created_at - INTERVAL '4 hours'
                                         AND ba.created_at + INTERVAL '24 hours'
                    ) as all_responses
            ) cr
            WHERE cr.first_response IS NOT NULL
        ),
        -- Combine both sources
        all_comparisons AS (
            SELECT * FROM copilot_edits
            UNION ALL
            SELECT * FROM legacy_pairs
        )
        SELECT * FROM all_comparisons
        ORDER BY created_at DESC
        OFFSET :offset
        LIMIT :limit_plus_one
    """), {
        "creator_id": str(creator.id),
        "offset": offset,
        "limit_plus_one": limit + 1,
    }).fetchall()

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    # Collect conversation context per unique lead
    from core.copilot_service import get_copilot_service

    copilot_svc = get_copilot_service()
    lead_context_cache: dict = {}

    comparisons = []
    for row in rows:
        # Build creator_responses array
        creator_responses = None
        if row.creator_responses_json:
            creator_responses = row.creator_responses_json

        # Get conversation context (cached per lead)
        lead_id = row.lead_id
        if lead_id not in lead_context_cache:
            try:
                before_ts = row.created_at if row.created_at else None
                lead_context_cache[lead_id] = copilot_svc._get_conversation_context(
                    session, lead_id, max_messages=5, before_timestamp=before_ts
                )
            except Exception:
                lead_context_cache[lead_id] = []

        comparisons.append({
            "message_id": str(row.id),
            "bot_original": row.bot_suggestion or "",
            "creator_final": row.creator_response or "",
            "action": row.action,
            "edit_diff": row.edit_diff,
            "confidence": row.confidence_score,
            "response_time_ms": row.response_time_ms,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "username": row.lead_name or "",
            "platform": row.platform,
            "is_identical": row.is_identical,
            "source": row.source,
            "creator_responses": creator_responses,
            "conversation_context": lead_context_cache.get(lead_id, []),
        })

    return {
        "comparisons": comparisons,
        "count": len(comparisons),
        "has_more": has_more,
    }


def fetch_history(session, creator, offset, limit):
    """
    Fetch full copilot action history with aggregate stats.

    Returns dict with items, stats, count, has_more.
    """
    from sqlalchemy import func

    from api.models import Lead, Message

    # Query messages with copilot_action, join with Lead
    query = (
        session.query(
            Message.id,
            Message.lead_id,
            Message.status,
            Message.copilot_action,
            Message.suggested_response,
            Message.content,
            Message.intent,
            Message.confidence_score,
            Message.response_time_ms,
            Message.created_at,
            Message.approved_at,
            Message.msg_metadata,
            Lead.username,
            Lead.platform,
            Lead.platform_user_id,
        )
        .join(Lead, Message.lead_id == Lead.id)
        .filter(
            Lead.creator_id == creator.id,
            Message.role == "assistant",
            Message.copilot_action.isnot(None),
        )
        .order_by(Message.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )

    rows = query.all()
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    # Build items
    items = []
    for row in rows:
        meta = row.msg_metadata or {}
        similarity = meta.get("similarity_score") if row.copilot_action == "resolved_externally" else None

        items.append({
            "id": str(row.id),
            "lead_name": row.username or row.platform_user_id or "",
            "platform": row.platform,
            "status": row.status,
            "copilot_action": row.copilot_action,
            "bot_suggestion": row.suggested_response or "",
            "creator_actual": row.content or "",
            "similarity_score": similarity,
            "confidence": row.confidence_score,
            "intent": row.intent or "",
            "response_time_ms": row.response_time_ms,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "resolved_at": row.approved_at.isoformat() if row.approved_at else "",
        })

    # Aggregate stats
    stats_query = (
        session.query(
            Message.copilot_action,
            func.count().label("cnt"),
        )
        .join(Lead, Message.lead_id == Lead.id)
        .filter(
            Lead.creator_id == creator.id,
            Message.role == "assistant",
            Message.copilot_action.isnot(None),
        )
        .group_by(Message.copilot_action)
        .limit(100)
        .all()
    )

    action_counts = {action: cnt for action, cnt in stats_query}
    total_all = sum(action_counts.values())

    # Average similarity for resolved_externally
    avg_sim = None
    resolved_ext_count = action_counts.get("resolved_externally", 0)
    if resolved_ext_count > 0:
        from sqlalchemy import text as sa_text

        avg_sim_result = session.execute(sa_text("""
            SELECT AVG((msg_metadata->>'similarity_score')::float)
            FROM messages m
            JOIN leads l ON m.lead_id = l.id
            WHERE l.creator_id = :cid
            AND m.copilot_action = 'resolved_externally'
            AND m.msg_metadata->>'similarity_score' IS NOT NULL
        """), {"cid": str(creator.id)}).scalar()
        if avg_sim_result is not None:
            avg_sim = round(float(avg_sim_result), 2)

    stats = {
        "total": total_all,
        "approved": action_counts.get("approved", 0),
        "edited": action_counts.get("edited", 0),
        "discarded": action_counts.get("discarded", 0),
        "manual_override": action_counts.get("manual_override", 0),
        "resolved_externally": resolved_ext_count,
        "avg_similarity": avg_sim,
    }

    return {
        "items": items,
        "stats": stats,
        "count": len(items),
        "has_more": has_more,
    }
