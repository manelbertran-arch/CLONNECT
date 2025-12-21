"""
Database service for Clonnect - PostgreSQL operations
"""
import os
from datetime import datetime
import uuid

DATABASE_URL = os.getenv("DATABASE_URL", "")

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

def get_leads(creator_name: str):
    session = get_session()
    if not session:
        return []
    try:
        from api.models import Creator, Lead
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return []
        leads = session.query(Lead).filter_by(creator_id=creator.id).all()
        return [{
            "id": str(lead.id),
            "follower_id": str(lead.id),
            "platform": lead.platform,
            "username": lead.username,
            "full_name": lead.full_name,
            "status": lead.status,
            "score": lead.score,
            "purchase_intent": lead.purchase_intent,
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
        from api.models import Creator, Lead, Message
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return None
        leads = session.query(Lead).filter_by(creator_id=creator.id).all()
        total_leads = len(leads)
        hot_leads = len([l for l in leads if l.purchase_intent and l.purchase_intent >= 0.7])
        warm_leads = len([l for l in leads if l.purchase_intent and 0.4 <= l.purchase_intent < 0.7])
        customers = len([l for l in leads if l.context and l.context.get("is_customer")])
        lead_ids = [l.id for l in leads]
        total_messages = session.query(Message).filter(Message.lead_id.in_(lead_ids)).count() if lead_ids else 0
        return {
            "status": "ok",
            "metrics": {
                "total_messages": total_messages,
                "total_conversations": total_leads,
                "total_followers": total_leads,
                "hot_leads": hot_leads,
                "high_intent_followers": hot_leads,
                "warm_leads": warm_leads,
                "total_leads": total_leads,
                "leads": total_leads,
                "customers": customers,
                "conversion_rate": 0.0,
            },
            "bot_active": creator.bot_active,
            "clone_active": creator.bot_active,
            "creator_name": creator.clone_name or creator.name,
        }
    finally:
        session.close()

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
