"""
Database service for Clonnect - PostgreSQL operations
"""
import os
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)
pg_pool = None  # Not using asyncpg, using SQLAlchemy instead

def get_session():
    if not DATABASE_URL:
        return None
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        engine = create_engine(DATABASE_URL)
        return Session(engine)
    except:
        return None

def get_creator_by_name(name: str):
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator
        creator = session.query(Creator).filter_by(name=name).first()
        if creator:
            return {
                "id": str(creator.id),
                "name": creator.name,
                "email": creator.email,
                "bot_active": creator.bot_active,
                "clone_tone": creator.clone_tone or "friendly",
                "clone_style": creator.clone_style or "",
                "clone_name": creator.clone_name or creator.name,
                "clone_vocabulary": creator.clone_vocabulary or "",
                "welcome_message": creator.welcome_message or "",
            }
        return None
    finally:
        session.close()

def update_creator(name: str, data: dict):
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator
        creator = session.query(Creator).filter_by(name=name).first()
        if creator:
            for key, value in data.items():
                if hasattr(creator, key):
                    setattr(creator, key, value)
            session.commit()
            return True
        return False
    finally:
        session.close()

def toggle_bot(name: str, active: bool = None):
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator
        creator = session.query(Creator).filter_by(name=name).first()
        if creator:
            creator.bot_active = active if active is not None else not creator.bot_active
            session.commit()
            return creator.bot_active
        return None
    finally:
        session.close()

def get_leads(creator_name: str, include_archived: bool = False):
    session = get_session()
    if not session:
        return []
    try:
        from api.models import Creator, Lead
        from sqlalchemy import and_, not_
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return []
        # Filter out archived and spam leads by default
        query = session.query(Lead).filter_by(creator_id=creator.id)
        if not include_archived:
            query = query.filter(not_(Lead.status.in_(["archived", "spam"])))
        leads = query.order_by(Lead.last_contact_at.desc()).all()
        return [{
            "id": str(lead.id),
            "follower_id": str(lead.id),
            "platform_user_id": lead.platform_user_id,
            "platform": lead.platform,
            "username": lead.username,
            "full_name": lead.full_name,
            "status": lead.status,
            "score": lead.score,
            "purchase_intent": lead.purchase_intent,
            "last_contact_at": lead.last_contact_at.isoformat() if lead.last_contact_at else None,
        } for lead in leads]
    finally:
        session.close()

def create_lead(creator_name: str, data: dict):
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Lead
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return None
        lead = Lead(
            creator_id=creator.id,
            platform=data.get("platform", "manual"),
            platform_user_id=data.get("platform_user_id", str(uuid.uuid4())),
            username=data.get("username"),
            full_name=data.get("full_name") or data.get("name"),
            status=data.get("status", "new"),
            score=data.get("score", 0),
            purchase_intent=data.get("purchase_intent", 0.0),
        )
        session.add(lead)
        session.commit()
        return {"id": str(lead.id), "status": "created"}
    finally:
        session.close()

def get_products(creator_name: str):
    session = get_session()
    if not session:
        return []
    try:
        from api.models import Creator, Product
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return []
        products = session.query(Product).filter_by(creator_id=creator.id).all()
        return [{
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "currency": p.currency,
            "is_active": p.is_active,
        } for p in products]
    finally:
        session.close()

def get_dashboard_metrics(creator_name: str):
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Lead, Message, Product
        from sqlalchemy import not_
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return None

        # Get leads (excluding archived and spam)
        leads = session.query(Lead).filter_by(creator_id=creator.id).filter(
            not_(Lead.status.in_(["archived", "spam"]))
        ).order_by(Lead.last_contact_at.desc()).all()
        total_leads = len(leads)

        # Categorize leads by intent (hot >= 0.5, warm 0.25-0.5, cold < 0.25)
        hot_leads = len([l for l in leads if l.purchase_intent and l.purchase_intent >= 0.5])
        warm_leads = len([l for l in leads if l.purchase_intent and 0.25 <= l.purchase_intent < 0.5])
        cold_leads = len([l for l in leads if not l.purchase_intent or l.purchase_intent < 0.25])
        customers = len([l for l in leads if l.context and l.context.get("is_customer")])

        # Get messages count
        lead_ids = [l.id for l in leads]
        total_messages = session.query(Message).filter(Message.lead_id.in_(lead_ids)).count() if lead_ids else 0

        # Get products count
        products_count = session.query(Product).filter_by(creator_id=creator.id).count()

        # Calculate conversion rate
        conversion_rate = (customers / total_leads) if total_leads > 0 else 0.0
        lead_rate = (total_leads / total_leads) if total_leads > 0 else 0.0  # All contacts become leads

        # Build leads array for frontend
        leads_data = []
        for lead in leads[:50]:  # Limit to 50 most recent
            leads_data.append({
                "id": str(lead.id),
                "follower_id": lead.platform_user_id or str(lead.id),
                "username": lead.username,
                "name": lead.full_name,
                "platform": lead.platform or "instagram",
                "purchase_intent": lead.purchase_intent or 0.0,
                "purchase_intent_score": lead.purchase_intent or 0.0,
                "is_lead": True,
                "is_customer": lead.context.get("is_customer", False) if lead.context else False,
                "last_contact": lead.last_contact_at.isoformat() if lead.last_contact_at else None,
                "total_messages": session.query(Message).filter_by(lead_id=lead.id).count(),
            })

        # Build recent conversations (same as leads but with different structure)
        recent_conversations = []
        for lead in leads[:20]:  # Last 20 conversations
            msg_count = session.query(Message).filter_by(lead_id=lead.id).count()
            recent_conversations.append({
                "follower_id": lead.platform_user_id or str(lead.id),
                "username": lead.username,
                "name": lead.full_name,
                "platform": lead.platform or "instagram",
                "total_messages": msg_count,
                "purchase_intent": lead.purchase_intent or 0.0,
                "last_contact": lead.last_contact_at.isoformat() if lead.last_contact_at else None,
            })

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

# ============================================
# CRUD COMPLETO - Phase 11
# ============================================

def create_product(creator_name: str, data: dict):
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Product
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return None
        product = Product(
            creator_id=creator.id,
            name=data.get("name", ""),
            description=data.get("description", ""),
            price=data.get("price", 0),
            currency=data.get("currency", "EUR"),
            is_active=data.get("is_active", True),
        )
        session.add(product)
        session.commit()
        return {"id": str(product.id), "name": product.name, "status": "created"}
    except Exception as e:
        session.rollback()
        return None
    finally:
        session.close()

def update_product(creator_name: str, product_id: str, data: dict):
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator, Product
        import uuid
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return False
        product = session.query(Product).filter_by(creator_id=creator.id, id=uuid.UUID(product_id)).first()
        if product:
            for key, value in data.items():
                if hasattr(product, key):
                    setattr(product, key, value)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        return False
    finally:
        session.close()

def delete_product(creator_name: str, product_id: str):
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator, Product
        import uuid
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return False
        product = session.query(Product).filter_by(creator_id=creator.id, id=uuid.UUID(product_id)).first()
        if product:
            session.delete(product)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        return False
    finally:
        session.close()

def update_lead(creator_name: str, lead_id: str, data: dict):
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator, Lead
        import uuid
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return False
        lead = session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(lead_id)).first()
        if lead:
            for key, value in data.items():
                if hasattr(lead, key):
                    setattr(lead, key, value)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        return False
    finally:
        session.close()

def delete_lead(creator_name: str, lead_id: str):
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator, Lead
        import uuid
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return False
        lead = session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(lead_id)).first()
        if lead:
            session.delete(lead)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        return False
    finally:
        session.close()

def get_lead_by_id(creator_name: str, lead_id: str):
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Lead
        import uuid
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return None
        lead = session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(lead_id)).first()
        if lead:
            return {"id": str(lead.id), "platform_user_id": lead.platform_user_id, "platform": lead.platform, "username": lead.username, "full_name": lead.full_name, "status": lead.status, "score": lead.score, "purchase_intent": lead.purchase_intent, "context": lead.context or {}}
        return None
    finally:
        session.close()

# ============================================================
# ASYNC FUNCTIONS FOR DM_AGENT (using SQLAlchemy)
# ============================================================

async def get_lead_by_platform_id(creator_id: str, platform_id: str) -> dict:
    """Get a lead by their platform-specific ID (e.g., tg_123, ig_456)"""
    if not USE_POSTGRES:
        return None
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Lead
        # First get creator by name (creator_id is the name like "manel")
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            return None
        # Find lead by platform_user_id
        lead = session.query(Lead).filter_by(
            creator_id=creator.id,
            platform_user_id=platform_id
        ).first()
        if lead:
            return {
                "id": str(lead.id),
                "creator_id": str(creator.id),
                "platform_user_id": lead.platform_user_id,
                "platform": lead.platform,
                "username": lead.username,
                "full_name": lead.full_name,
                "status": lead.status
            }
        return None
    except Exception as e:
        logger.error(f"get_lead_by_platform_id error: {e}")
        return None
    finally:
        session.close()


async def create_lead(creator_id: str, data: dict) -> dict:
    """Create a new lead for dm_agent integration"""
    if not USE_POSTGRES:
        return None
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Lead
        # Get creator by name
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            logger.warning(f"Creator not found: {creator_id}")
            return None
        # Create new lead
        lead = Lead(
            creator_id=creator.id,
            platform=data.get("platform", "telegram"),
            platform_user_id=data.get("platform_user_id", str(uuid.uuid4())),
            username=data.get("username", ""),
            full_name=data.get("full_name") or data.get("name", ""),
            status="new",
            score=0,
            purchase_intent=0.0
        )
        session.add(lead)
        session.commit()
        return {"id": str(lead.id), "status": "created"}
    except Exception as e:
        logger.error(f"create_lead error: {e}")
        session.rollback()
        return None
    finally:
        session.close()


async def save_message(lead_id: str, role: str, content: str, intent: str = None) -> dict:
    """Save a message to the database for dm_agent integration"""
    if not USE_POSTGRES:
        return None
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Message
        from datetime import timezone
        # Create new message
        message = Message(
            lead_id=lead_id,
            role=role,  # 'user' or 'assistant'
            content=content,
            intent=intent,
            created_at=datetime.now(timezone.utc)
        )
        session.add(message)
        session.commit()
        return {"id": str(message.id), "status": "saved"}
    except Exception as e:
        logger.error(f"save_message error: {e}")
        session.rollback()
        return None
    finally:
        session.close()


async def get_messages(creator_id: str, follower_id: str = None, limit: int = 50) -> list:
    """Get messages for a creator"""
    if not USE_POSTGRES:
        return []
    session = get_session()
    if not session:
        return []
    try:
        from api.models import Creator, Lead, Message
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            return []
        query = session.query(Message).join(Lead).filter(Lead.creator_id == creator.id)
        if follower_id:
            query = query.filter(Lead.platform_user_id == follower_id)
        messages = query.order_by(Message.created_at.desc()).limit(limit).all()
        return [{"id": str(m.id), "role": m.role, "content": m.content, "intent": m.intent, "created_at": str(m.created_at)} for m in messages]
    except Exception as e:
        logger.error(f"get_messages error: {e}")
        return []
    finally:
        session.close()


async def get_message_count(creator_id: str) -> int:
    """Get total message count for a creator"""
    if not USE_POSTGRES:
        return 0
    session = get_session()
    if not session:
        return 0
    try:
        from api.models import Creator, Lead, Message
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            return 0
        count = session.query(Message).join(Lead).filter(Lead.creator_id == creator.id).count()
        return count
    except Exception as e:
        logger.error(f"get_message_count error: {e}")
        return 0
    finally:
        session.close()


# ============================================================
# CONVERSATION ACTIONS (Archive, Spam, Delete)
# ============================================================

def archive_conversation(creator_name: str, conversation_id: str) -> bool:
    """Archive a conversation by setting lead.status = 'archived'"""
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator, Lead
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return False
        # Find lead by platform_user_id or id
        lead = session.query(Lead).filter_by(creator_id=creator.id, platform_user_id=conversation_id).first()
        if not lead:
            try:
                import uuid
                lead = session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(conversation_id)).first()
            except:
                pass
        if lead:
            lead.status = "archived"
            session.commit()
            # Sync to JSON
            try:
                from api.services.data_sync import sync_archive_to_json
                sync_archive_to_json(creator_name, lead.platform_user_id or conversation_id)
            except Exception as sync_err:
                logger.warning(f"JSON sync failed: {sync_err}")
            logger.info(f"Archived conversation {conversation_id} for {creator_name}")
            return True
        return False
    except Exception as e:
        logger.error(f"archive_conversation error: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def mark_conversation_spam(creator_name: str, conversation_id: str) -> bool:
    """Mark a conversation as spam by setting lead.status = 'spam'"""
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator, Lead
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return False
        # Find lead by platform_user_id or id
        lead = session.query(Lead).filter_by(creator_id=creator.id, platform_user_id=conversation_id).first()
        if not lead:
            try:
                import uuid
                lead = session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(conversation_id)).first()
            except:
                pass
        if lead:
            lead.status = "spam"
            session.commit()
            # Sync to JSON
            try:
                from api.services.data_sync import sync_spam_to_json
                sync_spam_to_json(creator_name, lead.platform_user_id or conversation_id)
            except Exception as sync_err:
                logger.warning(f"JSON sync failed: {sync_err}")
            logger.info(f"Marked conversation {conversation_id} as spam for {creator_name}")
            return True
        return False
    except Exception as e:
        logger.error(f"mark_conversation_spam error: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def delete_conversation(creator_name: str, conversation_id: str) -> bool:
    """Delete a conversation and all its messages permanently"""
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator, Lead, Message
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return False
        # Find lead by platform_user_id or id
        lead = session.query(Lead).filter_by(creator_id=creator.id, platform_user_id=conversation_id).first()
        platform_user_id = None
        if not lead:
            try:
                import uuid
                lead = session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(conversation_id)).first()
            except:
                pass
        if lead:
            platform_user_id = lead.platform_user_id
            # Delete all messages first (foreign key constraint)
            session.query(Message).filter_by(lead_id=lead.id).delete()
            # Delete the lead
            session.delete(lead)
            session.commit()
            # Sync: delete JSON file too
            try:
                from api.services.data_sync import sync_delete_json
                sync_delete_json(creator_name, platform_user_id or conversation_id)
            except Exception as sync_err:
                logger.warning(f"JSON sync failed: {sync_err}")
            logger.info(f"Deleted conversation {conversation_id} for {creator_name}")
            return True
        return False
    except Exception as e:
        logger.error(f"delete_conversation error: {e}")
        session.rollback()
        return False
    finally:
        session.close()
