"""
Dashboard metrics and creator stats.
"""

import logging

from api.utils.creator_resolver import resolve_creator_safe
from .session import get_session

logger = logging.getLogger(__name__)


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
            .limit(50)
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
                .limit(50)
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
