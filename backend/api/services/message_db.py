"""Message storage compatible with SQLAlchemy models"""
import uuid
import logging
from datetime import datetime, timezone

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
    """Get or create lead using SQLAlchemy (sync)"""
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
        
        # Find existing lead by platform_id in context
        leads = session.query(Lead).filter_by(creator_id=creator.id).all()
        for lead in leads:
            ctx = lead.context or {}
            if ctx.get("platform_id") == platform_id:
                return {"id": str(lead.id), "creator_id": str(creator.id)}
        
        # Create new lead
        lead = Lead(
            id=uuid.uuid4(),
            creator_id=creator.id,
            name=name or username or platform_id,
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
