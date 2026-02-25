"""
Analytics and dashboard — conversations with counts, metrics, stats.
"""

import logging

from api.services.db_ops.common import get_session
from api.utils.creator_resolver import resolve_creator_safe

logger = logging.getLogger(__name__)


def get_conversations_with_counts(
    creator_name: str,
    limit: int = 50,
    offset: int = 0,
    include_archived: bool = False,
    min_messages: int = 0,
):
    """Get conversations with accurate message counts from PostgreSQL

    Args:
        creator_name: Creator identifier
        limit: Max conversations to return
        offset: Number of conversations to skip (for pagination)
        include_archived: Include archived/spam conversations
        min_messages: Minimum message count to include (default 1, filters out empty conversations)

    Returns:
        dict with 'conversations' list, 'total_count', 'limit', 'offset', 'has_more'
        Each conversation includes last_message_preview and last_message_role for Instagram-like UX
    """
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Lead, Message
        from sqlalchemy import func, not_

        creator = resolve_creator_safe(session, creator_name)
        if not creator:
            return None

        # Query leads with message count using subquery (count ALL messages, not just user)
        msg_count_subq = (
            session.query(Message.lead_id, func.count(Message.id).label("msg_count"))
            .group_by(Message.lead_id)
            .subquery()
        )

        query = (
            session.query(
                Lead, func.coalesce(msg_count_subq.c.msg_count, 0).label("total_messages")
            )
            .outerjoin(msg_count_subq, Lead.id == msg_count_subq.c.lead_id)
            .filter(Lead.creator_id == creator.id)
        )

        # Filter out conversations with fewer than min_messages (default: hide empty conversations)
        if min_messages > 0:
            query = query.filter(func.coalesce(msg_count_subq.c.msg_count, 0) >= min_messages)

        if not include_archived:
            query = query.filter(not_(Lead.status.in_(["archived", "spam"])))

        # Get total count before pagination
        total_count = query.count()

        # Apply pagination
        results = query.order_by(Lead.last_contact_at.desc()).offset(offset).limit(limit).all()

        # Get last message for each lead (batch query for efficiency)
        lead_ids = [lead.id for lead, _ in results]
        last_messages = {}
        if lead_ids:
            # Subquery to get the max created_at for each lead
            pass

            max_date_subq = (
                session.query(Message.lead_id, func.max(Message.created_at).label("max_created_at"))
                .filter(
                    Message.lead_id.in_(lead_ids),
                    Message.status.in_(["sent", "edited"]),
                )
                .group_by(Message.lead_id)
                .subquery()
            )
            # Join to get the actual message
            last_msg_query = session.query(Message).join(
                max_date_subq,
                (Message.lead_id == max_date_subq.c.lead_id)
                & (Message.created_at == max_date_subq.c.max_created_at),
            )
            for msg in last_msg_query.all():
                last_messages[msg.lead_id] = msg

        conversations = []
        for lead, msg_count in results:
            # Get last message preview and role
            last_msg = last_messages.get(lead.id)
            last_message_preview = None
            last_message_role = None
            if last_msg:
                # Truncate to 50 chars for preview
                content = last_msg.content or ""
                last_message_preview = content[:50] + "..." if len(content) > 50 else content
                last_message_role = last_msg.role  # "user" or "assistant"

            # is_unread: true if last message is from user (follower) - awaiting creator response
            is_unread = last_message_role == "user"

            # is_verified: from context JSON (populated by Instagram API)
            context = lead.context or {}
            is_verified = context.get("is_verified", False)

            conversations.append(
                {
                    "id": str(lead.id),
                    "follower_id": lead.platform_user_id,
                    "platform_user_id": lead.platform_user_id,
                    "platform": lead.platform,
                    "username": lead.username or lead.platform_user_id,
                    "name": lead.full_name or lead.username or "",
                    "profile_pic_url": lead.profile_pic_url,
                    "status": lead.status,
                    "purchase_intent_score": lead.purchase_intent or 0.0,
                    "is_lead": lead.status not in ["archived", "spam"],
                    "last_contact": (
                        lead.last_contact_at.isoformat() if lead.last_contact_at else None
                    ),
                    "first_contact": (
                        lead.first_contact_at.isoformat() if lead.first_contact_at else None
                    ),
                    "total_messages": msg_count,
                    "archived": lead.status == "archived",
                    "spam": lead.status == "spam",
                    # Instagram-like UX fields (FIX 2026-02-02)
                    "last_message_preview": last_message_preview,
                    "last_message_role": last_message_role,
                    "is_unread": is_unread,
                    "is_verified": is_verified,
                    # CRM fields from direct columns
                    "email": lead.email,
                    "phone": lead.phone,
                    "notes": lead.notes,
                    "tags": lead.tags,
                    "deal_value": lead.deal_value,
                }
            )

        return {
            "conversations": conversations,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(conversations) < total_count,
        }
    finally:
        session.close()


def get_dashboard_metrics(creator_name: str):
    """Optimized dashboard metrics - uses aggregated queries instead of N+1"""
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Lead, Message, Product
        from sqlalchemy import Integer, func, not_

        creator = resolve_creator_safe(session, creator_name)
        if not creator:
            return None

        # Get leads (excluding archived and spam) - SINGLE QUERY
        leads = (
            session.query(Lead)
            .filter_by(creator_id=creator.id)
            .filter(not_(Lead.status.in_(["archived", "spam"])))
            .order_by(Lead.last_contact_at.desc())
            .all()
        )
        total_leads = len(leads)

        # Categorize leads by V3 status (in-memory, no extra queries)
        hot_leads = len([l for l in leads if l.status in ("cliente", "caliente")])
        warm_leads = len([l for l in leads if l.status in ("colaborador", "amigo")])
        cold_leads = len([l for l in leads if l.status in ("nuevo", "frío") or l.status is None])
        customers = len([l for l in leads if l.context and l.context.get("is_customer")])

        # Get ALL message counts in SINGLE AGGREGATED QUERY (fixes N+1)
        lead_ids = [l.id for l in leads]
        message_counts = {}
        if lead_ids:
            # Single query with GROUP BY - returns (lead_id, user_count, total_count)
            counts_query = (
                session.query(
                    Message.lead_id,
                    func.sum(func.cast(Message.role == "user", Integer)).label("user_count"),
                    func.count(Message.id).label("total_count"),
                )
                .filter(Message.lead_id.in_(lead_ids))
                .group_by(Message.lead_id)
                .all()
            )

            for row in counts_query:
                message_counts[row.lead_id] = {
                    "user": int(row.user_count or 0),
                    "total": int(row.total_count or 0),
                }

        # Calculate total user messages (sum from aggregated data)
        total_messages = sum(c["user"] for c in message_counts.values())

        # Get products count - SINGLE QUERY
        products_count = session.query(Product).filter_by(creator_id=creator.id).count()

        # Calculate conversion rate
        conversion_rate = (customers / total_leads) if total_leads > 0 else 0.0
        lead_rate = 1.0 if total_leads > 0 else 0.0

        # Build leads array using pre-fetched counts (NO additional queries)
        leads_data = []
        for lead in leads[:50]:
            counts = message_counts.get(lead.id, {"user": 0, "total": 0})
            leads_data.append(
                {
                    "id": str(lead.id),
                    "follower_id": lead.platform_user_id or str(lead.id),
                    "username": lead.username,
                    "name": lead.full_name,
                    "platform": lead.platform or "instagram",
                    "purchase_intent": lead.purchase_intent or 0.0,
                    "purchase_intent_score": lead.purchase_intent or 0.0,
                    "is_lead": True,
                    "is_customer": (
                        lead.context.get("is_customer", False) if lead.context else False
                    ),
                    "last_contact": (
                        lead.last_contact_at.isoformat() if lead.last_contact_at else None
                    ),
                    "total_messages": counts["user"],
                }
            )

        # Build recent conversations using pre-fetched counts (NO additional queries)
        recent_conversations = []
        for lead in leads[:20]:
            counts = message_counts.get(lead.id, {"user": 0, "total": 0})
            recent_conversations.append(
                {
                    "follower_id": lead.platform_user_id or str(lead.id),
                    "username": lead.username,
                    "name": lead.full_name,
                    "platform": lead.platform or "instagram",
                    "total_messages": counts["user"],
                    "purchase_intent": lead.purchase_intent or 0.0,
                    "last_contact": (
                        lead.last_contact_at.isoformat() if lead.last_contact_at else None
                    ),
                }
            )

        logger.info(
            f"[METRICS] {creator_name}: {total_leads} leads, {total_messages} messages (optimized)"
        )

        # Build config
        config = {
            "name": creator.name,
            "clone_name": creator.clone_name or creator.name,
            "clone_tone": creator.clone_tone or "friendly",
            "clone_style": creator.clone_style or "",
            "bot_active": creator.bot_active,
        }

        return {
            "status": "ok",
            "metrics": {
                "total_messages": total_messages,
                "total_conversations": total_leads,
                "total_followers": total_leads,
                "hot_leads": hot_leads,
                "high_intent_followers": hot_leads,
                "warm_leads": warm_leads,
                "cold_leads": cold_leads,
                "total_leads": total_leads,
                "leads": total_leads,
                "customers": customers,
                "conversion_rate": conversion_rate,
                "lead_rate": lead_rate,
            },
            "recent_conversations": recent_conversations,
            "leads": leads_data,
            "config": config,
            "products_count": products_count,
            "bot_active": creator.bot_active,
            "clone_active": creator.bot_active,
            "creator_name": creator.clone_name or creator.name,
        }
    finally:
        session.close()


def get_creator_stats(creator_name: str):
    """Get creator statistics for metrics endpoint"""
    metrics = get_dashboard_metrics(creator_name)
    if metrics:
        return {
            "total_messages": metrics["metrics"]["total_messages"],
            "total_leads": metrics["metrics"]["total_leads"],
            "hot_leads": metrics["metrics"]["hot_leads"],
        }
    return None
