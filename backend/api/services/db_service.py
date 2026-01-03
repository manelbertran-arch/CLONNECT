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
                "other_payment_methods": creator.other_payment_methods or {},
            }
        return None
    finally:
        session.close()


def get_or_create_creator(name: str):
    """Get creator by name, or create if doesn't exist"""
    session = get_session()
    if not session:
        logger.error(f"get_or_create_creator: no session available")
        return None
    try:
        from api.models import Creator
        logger.info(f"get_or_create_creator: looking for creator '{name}'")
        creator = session.query(Creator).filter_by(name=name).first()
        if not creator:
            logger.info(f"Creator '{name}' not found, auto-creating...")
            creator = Creator(name=name, bot_active=True, clone_tone="friendly")
            session.add(creator)
            session.commit()
            logger.info(f"Created creator '{name}' with id {creator.id}")

        # Build response dict, handling potentially missing columns gracefully
        result = {
            "id": str(creator.id),
            "name": creator.name,
            "email": creator.email,
            "bot_active": creator.bot_active if creator.bot_active is not None else True,
            "clone_tone": creator.clone_tone or "friendly",
            "clone_style": creator.clone_style or "",
            "clone_name": creator.clone_name or creator.name,
            "clone_vocabulary": creator.clone_vocabulary or "",
            "welcome_message": creator.welcome_message or "",
        }

        # These columns might not exist in older DB schemas
        try:
            result["other_payment_methods"] = creator.other_payment_methods or {}
        except:
            result["other_payment_methods"] = {}
        try:
            result["knowledge_about"] = getattr(creator, 'knowledge_about', None) or {}
        except:
            result["knowledge_about"] = {}

        logger.info(f"get_or_create_creator: returning config for '{name}'")
        return result
    except Exception as e:
        logger.error(f"get_or_create_creator error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        session.rollback()
        return None
    finally:
        session.close()

def update_creator(name: str, data: dict):
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator
        logger.info(f"=== UPDATE_CREATOR DEBUG ===")
        logger.info(f"Creator: {name}, Data keys: {list(data.keys())}")
        if 'other_payment_methods' in data:
            logger.info(f"other_payment_methods value: {data['other_payment_methods']}")

        creator = session.query(Creator).filter_by(name=name).first()
        if creator:
            for key, value in data.items():
                if hasattr(creator, key):
                    old_value = getattr(creator, key, None)
                    setattr(creator, key, value)
                    logger.info(f"Set {key}: {old_value} -> {value}")
                else:
                    logger.warning(f"Creator has no attribute '{key}' - skipping")
            session.commit()
            logger.info(f"Committed changes for {name}")
            # Verify the save
            session.refresh(creator)
            logger.info(f"After save, other_payment_methods = {creator.other_payment_methods}")
            return True
        else:
            logger.warning(f"Creator '{name}' not found")
        return False
    except Exception as e:
        logger.error(f"Error updating creator: {e}")
        session.rollback()
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
        result = []
        for lead in leads:
            ctx = lead.context or {}
            result.append({
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
                "email": ctx.get("email"),
                "phone": ctx.get("phone"),
                "notes": ctx.get("notes"),
            })
        return result
    finally:
        session.close()


def get_conversations_with_counts(creator_name: str, limit: int = 50, include_archived: bool = False):
    """Get conversations with accurate message counts from PostgreSQL"""
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Lead, Message
        from sqlalchemy import func, not_

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return None

        # Query leads with message count using subquery (only count user messages, not bot responses)
        msg_count_subq = session.query(
            Message.lead_id,
            func.count(Message.id).label('msg_count')
        ).filter(Message.role == 'user').group_by(Message.lead_id).subquery()

        query = session.query(Lead, func.coalesce(msg_count_subq.c.msg_count, 0).label('total_messages'))\
            .outerjoin(msg_count_subq, Lead.id == msg_count_subq.c.lead_id)\
            .filter(Lead.creator_id == creator.id)

        if not include_archived:
            query = query.filter(not_(Lead.status.in_(["archived", "spam"])))

        results = query.order_by(Lead.last_contact_at.desc()).limit(limit).all()

        conversations = []
        for lead, msg_count in results:
            conversations.append({
                "id": str(lead.id),
                "follower_id": lead.platform_user_id,
                "platform_user_id": lead.platform_user_id,
                "platform": lead.platform,
                "username": lead.username or lead.platform_user_id,
                "name": lead.full_name or lead.username or "",
                "status": lead.status,
                "purchase_intent_score": lead.purchase_intent or 0.0,
                "is_lead": lead.status not in ["archived", "spam"],
                "last_contact": lead.last_contact_at.isoformat() if lead.last_contact_at else None,
                "total_messages": msg_count,
                "archived": lead.status == "archived",
                "spam": lead.status == "spam",
            })

        return conversations
    finally:
        session.close()


def create_lead(creator_name: str, data: dict):
    session = get_session()
    if not session:
        logger.warning("create_lead: no database session available")
        return None
    try:
        from api.models import Creator, Lead
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            logger.warning(f"create_lead: creator '{creator_name}' not found, creating it")
            # Auto-create creator if not exists
            creator = Creator(name=creator_name)
            session.add(creator)
            session.commit()

        # Build context with optional fields (email, phone, notes stored in JSON)
        context = {}
        if data.get("email"):
            context["email"] = data.get("email")
        if data.get("phone"):
            context["phone"] = data.get("phone")
        if data.get("notes"):
            context["notes"] = data.get("notes")

        # Use "name" field for both username and full_name if specific fields not provided
        name_value = data.get("name", "")
        lead = Lead(
            creator_id=creator.id,
            platform=data.get("platform", "manual"),
            platform_user_id=data.get("platform_user_id") or str(uuid.uuid4()),
            username=data.get("username") or name_value,
            full_name=data.get("full_name") or name_value,
            status=data.get("status", "new"),
            score=data.get("score", 0),
            purchase_intent=data.get("purchase_intent", 0.0),
            context=context,
        )
        session.add(lead)
        session.commit()
        logger.info(f"create_lead: created lead {lead.id} for creator {creator_name}")
        return {
            "id": str(lead.id),
            "platform_user_id": lead.platform_user_id,
            "username": lead.username,
            "full_name": lead.full_name,
            "platform": lead.platform,
            "status": lead.status,
            "score": lead.score,
            "purchase_intent": lead.purchase_intent,
            "email": context.get("email"),
            "phone": context.get("phone"),
            "notes": context.get("notes"),
        }
    except Exception as e:
        logger.error(f"create_lead error: {e}")
        session.rollback()
        return None
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
            "payment_link": getattr(p, 'payment_link', '') or "",
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
        logger.info(f"[METRICS] creator_name={creator_name}, found={creator is not None}")
        if not creator:
            return None

        logger.info(f"[METRICS] creator.id={creator.id}")

        # Get leads (excluding archived and spam)
        leads = session.query(Lead).filter_by(creator_id=creator.id).filter(
            not_(Lead.status.in_(["archived", "spam"]))
        ).order_by(Lead.last_contact_at.desc()).all()
        total_leads = len(leads)
        logger.info(f"[METRICS] total_leads={total_leads}")

        # Categorize leads by intent (hot >= 0.5, warm 0.25-0.5, cold < 0.25)
        hot_leads = len([l for l in leads if l.purchase_intent and l.purchase_intent >= 0.5])
        warm_leads = len([l for l in leads if l.purchase_intent and 0.25 <= l.purchase_intent < 0.5])
        cold_leads = len([l for l in leads if not l.purchase_intent or l.purchase_intent < 0.25])
        customers = len([l for l in leads if l.context and l.context.get("is_customer")])

        # Get messages count (only user messages, not bot responses)
        lead_ids = [l.id for l in leads]
        total_messages = session.query(Message).filter(Message.lead_id.in_(lead_ids), Message.role == 'user').count() if lead_ids else 0
        # Debug: also count all messages (regardless of role)
        all_messages = session.query(Message).filter(Message.lead_id.in_(lead_ids)).count() if lead_ids else 0
        # Debug: count all messages in table
        all_messages_total = session.query(Message).count()
        logger.info(f"[METRICS] user_messages={total_messages}, all_messages_for_leads={all_messages}, all_messages_in_table={all_messages_total}")

        # If PostgreSQL has 0 messages, count from JSON files as fallback
        if total_messages == 0:
            json_total = 0
            for lead in leads:
                if lead.platform_user_id:
                    try:
                        from api.services.data_sync import _load_json
                        json_data = _load_json(creator_name, lead.platform_user_id)
                        if json_data:
                            last_messages = json_data.get("last_messages", [])
                            json_total += len([m for m in last_messages if m.get("role") == "user"])
                    except:
                        pass
            if json_total > 0:
                logger.info(f"[METRICS] Fallback to JSON: total_messages={json_total}")
                total_messages = json_total

        # Get products count
        products_count = session.query(Product).filter_by(creator_id=creator.id).count()

        # Calculate conversion rate
        conversion_rate = (customers / total_leads) if total_leads > 0 else 0.0
        lead_rate = (total_leads / total_leads) if total_leads > 0 else 0.0  # All contacts become leads

        # Build leads array for frontend
        leads_data = []
        for lead in leads[:50]:  # Limit to 50 most recent
            user_count = session.query(Message).filter_by(lead_id=lead.id, role='user').count()
            all_count = session.query(Message).filter_by(lead_id=lead.id).count()

            # Fallback to JSON if PostgreSQL has 0
            final_count = user_count
            if user_count == 0 and lead.platform_user_id:
                try:
                    from api.services.data_sync import _load_json
                    json_data = _load_json(creator_name, lead.platform_user_id)
                    if json_data:
                        last_messages = json_data.get("last_messages", [])
                        final_count = len([m for m in last_messages if m.get("role") == "user"])
                except:
                    pass

            if all_count > 0 or final_count > 0:  # Log leads with messages
                logger.info(f"[METRICS] Lead {lead.platform_user_id}: pg_user={user_count}, pg_all={all_count}, final={final_count}")
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
                "total_messages": final_count,
            })

        # Build recent conversations (same as leads but with different structure)
        recent_conversations = []
        for lead in leads[:20]:  # Last 20 conversations
            msg_count = session.query(Message).filter_by(lead_id=lead.id, role='user').count()

            # Fallback to JSON if PostgreSQL has 0
            final_msg_count = msg_count
            if msg_count == 0 and lead.platform_user_id:
                try:
                    from api.services.data_sync import _load_json
                    json_data = _load_json(creator_name, lead.platform_user_id)
                    if json_data:
                        last_messages = json_data.get("last_messages", [])
                        final_msg_count = len([m for m in last_messages if m.get("role") == "user"])
                except:
                    pass

            recent_conversations.append({
                "follower_id": lead.platform_user_id or str(lead.id),
                "username": lead.username,
                "name": lead.full_name,
                "platform": lead.platform or "instagram",
                "total_messages": final_msg_count,
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
        logger.error("update_product: No session available")
        return False
    try:
        from api.models import Creator, Product
        import uuid
        logger.info(f"update_product: creator={creator_name}, product_id={product_id}")
        logger.info(f"update_product: data received = {data}")

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            logger.error(f"update_product: Creator '{creator_name}' not found")
            return False

        product = session.query(Product).filter_by(creator_id=creator.id, id=uuid.UUID(product_id)).first()
        if product:
            logger.info(f"update_product: Found product '{product.name}', current payment_link='{product.payment_link}'")
            for key, value in data.items():
                if hasattr(product, key):
                    old_value = getattr(product, key, None)
                    setattr(product, key, value)
                    logger.info(f"update_product: Set {key}: '{old_value}' -> '{value}'")
                else:
                    logger.warning(f"update_product: Product has no attribute '{key}'")
            session.commit()
            logger.info(f"update_product: Committed. payment_link is now '{product.payment_link}'")
            return True
        else:
            logger.error(f"update_product: Product {product_id} not found for creator {creator.id}")
        return False
    except Exception as e:
        logger.error(f"update_product: Exception: {e}", exc_info=True)
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
            logger.warning(f"update_lead: creator '{creator_name}' not found")
            return False

        # Try to find lead by UUID first, then by platform_user_id
        lead = None
        try:
            lead = session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(lead_id)).first()
        except (ValueError, AttributeError):
            pass  # Not a valid UUID, try platform_user_id

        if not lead:
            lead = session.query(Lead).filter_by(creator_id=creator.id, platform_user_id=lead_id).first()

        if lead:
            from sqlalchemy.orm.attributes import flag_modified

            # Handle special fields that go into context JSON
            # IMPORTANT: Create a NEW dict to ensure SQLAlchemy detects the change
            context_fields = ['email', 'phone', 'notes']
            old_context = lead.context
            new_context = dict(old_context) if old_context else {}

            logger.info(f"update_lead: lead {lead_id} found. old_context={old_context}, type={type(old_context)}")

            for key, value in data.items():
                if key in context_fields:
                    new_context[key] = value
                    logger.info(f"update_lead: setting context[{key}] = {value}")
                elif hasattr(lead, key):
                    setattr(lead, key, value)

            # Also update name fields if provided
            if 'name' in data:
                lead.full_name = data['name']
                if not lead.username:
                    lead.username = data['name']

            # Assign the new context dict AND flag as modified (belt and suspenders)
            lead.context = new_context
            flag_modified(lead, 'context')
            logger.info(f"update_lead: assigned new context={new_context}, flagged as modified")

            session.commit()
            logger.info(f"update_lead: committed lead {lead_id}")
            return {
                "id": str(lead.id),
                "platform_user_id": lead.platform_user_id,
                "username": lead.username,
                "full_name": lead.full_name,
                "platform": lead.platform,
                "status": lead.status,
                "score": lead.score,
                "purchase_intent": lead.purchase_intent,
                "email": new_context.get("email"),
                "phone": new_context.get("phone"),
                "notes": new_context.get("notes"),
            }
        logger.warning(f"update_lead: lead '{lead_id}' not found")
        return None
    except Exception as e:
        logger.error(f"update_lead error: {e}")
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
            logger.warning(f"delete_lead: creator '{creator_name}' not found")
            return False

        # Try to find lead by UUID first, then by platform_user_id
        lead = None
        try:
            lead = session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(lead_id)).first()
        except (ValueError, AttributeError):
            pass  # Not a valid UUID, try platform_user_id

        if not lead:
            lead = session.query(Lead).filter_by(creator_id=creator.id, platform_user_id=lead_id).first()

        if lead:
            session.delete(lead)
            session.commit()
            logger.info(f"delete_lead: deleted lead {lead_id}")
            return True
        logger.warning(f"delete_lead: lead '{lead_id}' not found")
        return False
    except Exception as e:
        logger.error(f"delete_lead error: {e}")
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

        # Try to find lead by UUID first, then by platform_user_id
        lead = None
        try:
            lead = session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(lead_id)).first()
        except (ValueError, AttributeError):
            pass  # Not a valid UUID, try platform_user_id

        if not lead:
            lead = session.query(Lead).filter_by(creator_id=creator.id, platform_user_id=lead_id).first()

        if lead:
            ctx = lead.context or {}
            return {
                "id": str(lead.id),
                "platform_user_id": lead.platform_user_id,
                "platform": lead.platform,
                "username": lead.username,
                "full_name": lead.full_name,
                "status": lead.status,
                "score": lead.score,
                "purchase_intent": lead.purchase_intent,
                "email": ctx.get("email"),
                "phone": ctx.get("phone"),
                "notes": ctx.get("notes"),
                "context": ctx
            }
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


async def create_lead_async(creator_id: str, data: dict) -> dict:
    """Create a new lead for dm_agent integration (async version)"""
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
        import uuid as uuid_module
        # Convert lead_id string to UUID
        lead_uuid = uuid_module.UUID(lead_id) if isinstance(lead_id, str) else lead_id
        # Create new message
        message = Message(
            lead_id=lead_uuid,
            role=role,  # 'user' or 'assistant'
            content=content,
            intent=intent,
            created_at=datetime.now(timezone.utc)
        )
        session.add(message)
        session.commit()
        logger.info(f"Saved message for lead {lead_id}: role={role}")
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
    """Get total message count for a creator (only user messages, not bot responses)"""
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
        count = session.query(Message).join(Lead).filter(Lead.creator_id == creator.id, Message.role == 'user').count()
        return count
    except Exception as e:
        logger.error(f"get_message_count error: {e}")
        return 0
    finally:
        session.close()


def get_messages_by_lead_id(lead_id: str, limit: int = 50) -> list:
    """Get messages for a specific lead by UUID (sync version for /dm/conversations)"""
    if not USE_POSTGRES:
        return []
    session = get_session()
    if not session:
        return []
    try:
        from api.models import Message
        import uuid as uuid_module
        lead_uuid = uuid_module.UUID(lead_id) if isinstance(lead_id, str) else lead_id
        messages = session.query(Message).filter(
            Message.lead_id == lead_uuid
        ).order_by(Message.created_at.desc()).limit(limit).all()
        return [
            {"role": m.role, "content": m.content, "timestamp": str(m.created_at)}
            for m in reversed(messages)  # Return in chronological order
        ]
    except Exception as e:
        logger.error(f"get_messages_by_lead_id error: {e}")
        return []
    finally:
        session.close()


def count_user_messages_by_lead_id(lead_id: str) -> int:
    """Count user messages for a specific lead by UUID (sync version)"""
    if not USE_POSTGRES:
        return 0
    session = get_session()
    if not session:
        return 0
    try:
        from api.models import Message
        import uuid as uuid_module
        lead_uuid = uuid_module.UUID(lead_id) if isinstance(lead_id, str) else lead_id
        count = session.query(Message).filter(
            Message.lead_id == lead_uuid,
            Message.role == 'user'
        ).count()
        return count
    except Exception as e:
        logger.error(f"count_user_messages_by_lead_id error: {e}")
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


def reset_conversation_status(creator_name: str, conversation_id: str = None) -> int:
    """Reset status of conversation(s) from archived/spam back to 'new'
    If conversation_id is None, resets ALL conversations for the creator.
    Returns number of conversations reset.
    """
    session = get_session()
    if not session:
        return 0
    try:
        from api.models import Creator, Lead
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return 0

        if conversation_id:
            # Reset specific conversation
            lead = session.query(Lead).filter_by(creator_id=creator.id, platform_user_id=conversation_id).first()
            if not lead:
                try:
                    import uuid
                    lead = session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(conversation_id)).first()
                except:
                    pass
            if lead and lead.status in ["archived", "spam"]:
                lead.status = "new"
                session.commit()
                logger.info(f"Reset conversation {conversation_id} to 'new'")
                return 1
            return 0
        else:
            # Reset ALL archived/spam conversations
            count = session.query(Lead).filter_by(creator_id=creator.id).filter(
                Lead.status.in_(["archived", "spam"])
            ).update({"status": "new"}, synchronize_session=False)
            session.commit()
            logger.info(f"Reset {count} conversations to 'new' for {creator_name}")
            return count
    except Exception as e:
        logger.error(f"reset_conversation_status error: {e}")
        session.rollback()
        return 0
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


# ============================================================
# KNOWLEDGE BASE FUNCTIONS
# ============================================================

def get_knowledge_items(creator_name: str) -> list:
    """Get all FAQ items from knowledge_base table"""
    session = get_session()
    if not session:
        return []
    try:
        from api.models import Creator, KnowledgeBase
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return []
        items = session.query(KnowledgeBase).filter_by(creator_id=creator.id).order_by(KnowledgeBase.created_at.desc()).all()
        return [{
            "id": str(item.id),
            "question": item.question,
            "answer": item.answer,
            "created_at": item.created_at.isoformat() if item.created_at else None
        } for item in items]
    except Exception as e:
        logger.error(f"get_knowledge_items error: {e}")
        return []
    finally:
        session.close()


def add_knowledge_item(creator_name: str, question: str, answer: str) -> dict:
    """Add a FAQ item to knowledge_base table"""
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, KnowledgeBase
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            # Auto-create creator if doesn't exist
            logger.info(f"Creator '{creator_name}' not found, auto-creating for knowledge item")
            creator = Creator(name=creator_name, bot_active=True, clone_tone="friendly")
            session.add(creator)
            session.commit()
        item = KnowledgeBase(
            creator_id=creator.id,
            question=question,
            answer=answer
        )
        session.add(item)
        session.commit()
        return {
            "id": str(item.id),
            "question": item.question,
            "answer": item.answer,
            "created_at": item.created_at.isoformat() if item.created_at else None
        }
    except Exception as e:
        logger.error(f"add_knowledge_item error: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def delete_knowledge_item(creator_name: str, item_id: str) -> bool:
    """Delete a FAQ item from knowledge_base table"""
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator, KnowledgeBase
        import uuid as uuid_module
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return False
        item = session.query(KnowledgeBase).filter_by(
            creator_id=creator.id,
            id=uuid_module.UUID(item_id)
        ).first()
        if item:
            session.delete(item)
            session.commit()
            return True
        return False
    except Exception as e:
        logger.error(f"delete_knowledge_item error: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_knowledge_about(creator_name: str) -> dict:
    """Get About Me/Business info from creator.knowledge_about"""
    session = get_session()
    if not session:
        return {}
    try:
        from api.models import Creator
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if creator:
            return creator.knowledge_about or {}
        return {}
    except Exception as e:
        logger.error(f"get_knowledge_about error: {e}")
        return {}
    finally:
        session.close()


def update_knowledge_about(creator_name: str, data: dict) -> bool:
    """Update About Me/Business info in creator.knowledge_about"""
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator
        from sqlalchemy.orm.attributes import flag_modified
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            # Auto-create creator if doesn't exist
            logger.info(f"Creator '{creator_name}' not found, auto-creating for knowledge about")
            creator = Creator(name=creator_name, bot_active=True, clone_tone="friendly")
            session.add(creator)
            session.commit()
        creator.knowledge_about = data
        flag_modified(creator, 'knowledge_about')
        session.commit()
        return True
    except Exception as e:
        logger.error(f"update_knowledge_about error: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_full_knowledge(creator_name: str) -> dict:
    """Get complete knowledge base: FAQs + About Me"""
    faqs = get_knowledge_items(creator_name)
    about = get_knowledge_about(creator_name)
    return {
        "faqs": faqs,
        "about": about
    }
