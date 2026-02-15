"""Message storage compatible with SQLAlchemy models"""
import uuid
import logging

logger = logging.getLogger(__name__)

# Import database utilities
try:
    from api.services.db_service import USE_POSTGRES, pg_pool, get_session
except ImportError:
    USE_POSTGRES = False
    pg_pool = None
    get_session = lambda: None


def save_message_sync(lead_id: str, role: str, content: str, intent: str = None) -> dict:
    """Save message using SQLAlchemy (sync) - matches Message model"""
    session = get_session()
    if not session:
        return {"error": "no session"}
    
    try:
        from api.models import Message
        msg = Message(
            id=uuid.uuid4(),
            lead_id=uuid.UUID(lead_id) if isinstance(lead_id, str) else lead_id,
            role=role,
            content=content,
            intent=intent
        )
        session.add(msg)
        session.commit()
        return {"id": str(msg.id), "status": "saved"}
    except Exception as e:
        session.rollback()
        logger.warning(f"Failed to save message: {e}")
        return {"error": str(e)}
    finally:
        session.close()


def get_or_create_lead_sync(creator_id: str, platform_id: str, platform: str = "instagram",
                            username: str = "", name: str = "") -> dict:
    """Get or create lead using SQLAlchemy (sync).

    FIX: Previously loaded ALL leads for a creator and iterated in Python.
    Now uses a targeted WHERE clause on platform_user_id for O(1) lookup.
    Falls back to JSON context search only if direct lookup fails.
    """
    session = get_session()
    if not session:
        return None

    try:
        from api.models import Creator, Lead

        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            logger.warning(f"Creator {creator_id} not found")
            return None

        # OPTIMIZED: Direct lookup by platform_user_id (indexed column)
        lead = (
            session.query(Lead)
            .filter_by(creator_id=creator.id, platform_user_id=platform_id)
            .first()
        )
        if lead:
            return {"id": str(lead.id), "creator_id": str(creator.id)}

        # Fallback: Check context JSON for legacy leads that stored platform_id in context
        # Uses PostgreSQL JSON operator for targeted query instead of loading all leads
        try:
            from sqlalchemy import text
            lead = (
                session.query(Lead)
                .filter(
                    Lead.creator_id == creator.id,
                    text("context->>'platform_id' = :pid")
                )
                .params(pid=platform_id)
                .first()
            )
            if lead:
                return {"id": str(lead.id), "creator_id": str(creator.id)}
        except Exception:
            # If JSON query fails (e.g., SQLite in tests), skip fallback
            pass

        # Create new lead
        lead = Lead(
            id=uuid.uuid4(),
            creator_id=creator.id,
            platform_user_id=platform_id,
            username=username or name or platform_id,
            full_name=name or username or "",
            platform=platform,
            status="new",
            context={"platform_id": platform_id, "username": username}
        )
        session.add(lead)
        session.commit()
        return {"id": str(lead.id), "creator_id": str(creator.id)}
    except Exception as e:
        session.rollback()
        logger.warning(f"Failed to get/create lead: {e}")
        return None
    finally:
        session.close()
