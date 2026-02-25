"""
DM Debug - Debug/metrics endpoints
(debug_messages, get_dm_metrics)
"""

import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

# Database availability check
try:
    pass

    USE_DB = True
except Exception:
    USE_DB = False
    logger.warning("Database service not available in dm debug router")

router = APIRouter()


@router.get("/debug/{creator_id}")
async def debug_messages(creator_id: str):
    """Debug endpoint to diagnose message count issue"""
    debug_info = {
        "creator_id": creator_id,
        "use_db": USE_DB,
        "creator_found": False,
        "total_leads": 0,
        "total_messages_all": 0,
        "total_messages_user": 0,
        "leads_with_messages": [],
        "sample_messages": [],
    }

    if not USE_DB:
        return {"status": "error", "message": "Database not available", "debug": debug_info}

    try:
        from api.models import Creator, Lead, Message
        from api.services.db_service import get_session

        session = get_session()
        if not session:
            return {"status": "error", "message": "No session", "debug": debug_info}

        try:
            # Check if creator exists
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                debug_info["error"] = f"Creator '{creator_id}' not found"
                # List all creators
                all_creators = session.query(Creator).all()
                debug_info["available_creators"] = [c.name for c in all_creators]
                return {"status": "error", "message": "Creator not found", "debug": debug_info}

            debug_info["creator_found"] = True
            debug_info["creator_uuid"] = str(creator.id)

            # Count leads for this creator
            leads = session.query(Lead).filter_by(creator_id=creator.id).all()
            debug_info["total_leads"] = len(leads)

            # Get lead UUIDs
            lead_ids = [lead.id for lead in leads]
            debug_info["lead_uuids"] = [str(lid) for lid in lead_ids[:5]]  # First 5

            # Count ALL messages for these leads
            if lead_ids:
                all_msg_count = session.query(Message).filter(Message.lead_id.in_(lead_ids)).count()
                debug_info["total_messages_all"] = all_msg_count

                # Count only user messages
                user_msg_count = (
                    session.query(Message)
                    .filter(Message.lead_id.in_(lead_ids), Message.role == "user")
                    .count()
                )
                debug_info["total_messages_user"] = user_msg_count

                # Get message counts per lead
                for lead in leads[:5]:  # First 5 leads
                    lead_all = session.query(Message).filter_by(lead_id=lead.id).count()
                    lead_user = (
                        session.query(Message).filter_by(lead_id=lead.id, role="user").count()
                    )
                    debug_info["leads_with_messages"].append(
                        {
                            "lead_id": str(lead.id),
                            "platform_user_id": lead.platform_user_id,
                            "username": lead.username,
                            "all_messages": lead_all,
                            "user_messages": lead_user,
                        }
                    )

                # Get sample messages
                sample_msgs = (
                    session.query(Message).filter(Message.lead_id.in_(lead_ids)).limit(5).all()
                )
                for msg in sample_msgs:
                    debug_info["sample_messages"].append(
                        {
                            "id": str(msg.id),
                            "lead_id": str(msg.lead_id),
                            "role": msg.role,
                            "content_preview": msg.content[:50] if msg.content else "",
                        }
                    )

                # Check for orphan messages (messages not associated with any of this creator's leads)
                all_msgs_in_db = session.query(Message).count()
                msgs_for_creator = (
                    session.query(Message).filter(Message.lead_id.in_(lead_ids)).count()
                    if lead_ids
                    else 0
                )
                orphan_msgs = all_msgs_in_db - msgs_for_creator
                debug_info["orphan_messages"] = orphan_msgs
                debug_info["all_messages_in_db"] = all_msgs_in_db
                debug_info["messages_for_this_creator"] = msgs_for_creator

                # Get sample orphan messages if any
                if orphan_msgs > 0 and lead_ids:
                    orphan_sample = (
                        session.query(Message).filter(~Message.lead_id.in_(lead_ids)).limit(5).all()
                    )
                    debug_info["orphan_sample"] = [
                        {
                            "id": str(msg.id),
                            "lead_id": str(msg.lead_id),
                            "role": msg.role,
                            "content_preview": msg.content[:50] if msg.content else "",
                        }
                        for msg in orphan_sample
                    ]

            return {"status": "ok", "debug": debug_info}

        finally:
            session.close()

    except Exception as e:
        debug_info["exception"] = str(e)
        logger.error(f"debug_messages error: {e}")
        return {"status": "error", "message": str(e), "debug": debug_info}


@router.get("/metrics/{creator_id}")
async def get_dm_metrics(creator_id: str):
    """Obtener metricas del agent — basic stats from DB."""
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        if not SessionLocal:
            return {"status": "ok", "total_messages": 0, "total_leads": 0, "bot_active": False}

        with SessionLocal() as session:
            # Count messages (messages links via lead_id → leads.creator_id)
            msg_result = session.execute(
                text("""SELECT COUNT(*) FROM messages m
                        JOIN leads l ON m.lead_id = l.id
                        WHERE l.creator_id = :cid"""),
                {"cid": creator_id}
            )
            total_messages = msg_result.scalar() or 0

            # Count leads
            lead_result = session.execute(
                text("SELECT COUNT(*) FROM leads WHERE creator_id = :cid"),
                {"cid": creator_id}
            )
            total_leads = lead_result.scalar() or 0

            # Check bot status
            bot_result = session.execute(
                text("SELECT bot_active FROM creators WHERE name = :cid LIMIT 1"),
                {"cid": creator_id}
            )
            row = bot_result.fetchone()
            bot_active = bool(row[0]) if row else False

        return {
            "status": "ok",
            "total_messages": total_messages,
            "total_leads": total_leads,
            "bot_active": bot_active,
        }
    except Exception as e:
        logger.error(f"DM metrics error: {e}")
        return {"status": "ok", "total_messages": 0, "total_leads": 0, "bot_active": False, "error": str(e)}
