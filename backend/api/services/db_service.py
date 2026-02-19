"""
Database service for Clonnect - PostgreSQL operations
"""

import logging
import os
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)
pg_pool = None  # Not using asyncpg, using SQLAlchemy instead


def get_session():
    if not DATABASE_URL:
        return None
    try:
        from api.database import SessionLocal
        if SessionLocal is None:
            logger.error("SessionLocal not initialized")
            return None
        return SessionLocal()
    except Exception as e:
        logger.error("Failed to create database session: %s", e)
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
                "knowledge_about": creator.knowledge_about or {},
            }
        return None
    finally:
        session.close()


# =============================================================================
# PROTECTED BLOCK: Instagram Token Access
# Modified: 2026-01-16
# Reason: Centralized function for Instagram credentials to prevent lookup bugs
# Do not modify without considering all usages across the codebase
# =============================================================================
def get_instagram_credentials(creator_id: str):
    """
    Centralized function to get Instagram credentials for a creator.

    IMPORTANT: This is the ONLY function that should be used to get Instagram tokens.
    It handles:
    - Lookup by name or UUID
    - Clear error messages when token is missing
    - All Instagram fields in one place

    Args:
        creator_id: Creator name (e.g., 'fitpack_global') or UUID

    Returns:
        Dict with:
            - success: bool
            - token: str or None
            - page_id: str or None
            - user_id: str or None
            - expires_at: datetime or None
            - creator_name: str
            - creator_uuid: str
            - error: str (if success=False)
    """
    session = get_session()
    if not session:
        return {
            "success": False,
            "error": "Database not available",
            "token": None,
            "page_id": None,
            "user_id": None,
        }

    try:
        from api.models import Creator
        from sqlalchemy import text

        # Try by name first
        creator = session.query(Creator).filter_by(name=creator_id).first()

        # If not found by name, try by UUID
        if not creator:
            try:
                creator = (
                    session.query(Creator)
                    .filter(text("id::text = :cid"))
                    .params(cid=creator_id)
                    .first()
                )
            except Exception as e:
                logger.warning("Failed to query creator by UUID %s: %s", creator_id, e)

        if not creator:
            return {
                "success": False,
                "error": f"Creator '{creator_id}' not found in database",
                "token": None,
                "page_id": None,
                "user_id": None,
            }

        # Creator found - check if token exists
        if not creator.instagram_token:
            return {
                "success": False,
                "error": f"Creator '{creator.name}' has no Instagram token configured. "
                "Please connect Instagram via OAuth at /connect/instagram",
                "creator_name": creator.name,
                "creator_uuid": str(creator.id),
                "token": None,
                "page_id": creator.instagram_page_id,
                "user_id": creator.instagram_user_id,
            }

        # Success - return all credentials
        # Use getattr for expires_at as it may not exist in all DB schemas
        expires_at = getattr(creator, "instagram_token_expires_at", None)

        return {
            "success": True,
            "token": creator.instagram_token,
            "page_id": creator.instagram_page_id,
            "user_id": creator.instagram_user_id,
            "expires_at": expires_at,
            "creator_name": creator.name,
            "creator_uuid": str(creator.id),
            "error": None,
        }

    except Exception as e:
        logger.error(f"get_instagram_credentials error for {creator_id}: {e}")
        return {"success": False, "error": str(e), "token": None, "page_id": None, "user_id": None}
    finally:
        session.close()


def get_or_create_creator(name: str):
    """Get creator by name, or create if doesn't exist"""
    session = get_session()
    if not session:
        logger.error("get_or_create_creator: no session available")
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
        except AttributeError:
            result["other_payment_methods"] = {}
        try:
            result["knowledge_about"] = getattr(creator, "knowledge_about", None) or {}
        except AttributeError:
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

        logger.info("=== UPDATE_CREATOR DEBUG ===")
        logger.info(f"Creator: {name}, Data keys: {list(data.keys())}")
        if "other_payment_methods" in data:
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


def get_leads(creator_name: str, include_archived: bool = False, limit: int = 100):
    """Get leads for a creator with pagination.

    Args:
        creator_name: Creator's name
        include_archived: Include archived/spam leads
        limit: Maximum leads to return (default 100 for performance)
    """
    session = get_session()
    if not session:
        return []
    try:
        from api.models import Creator, Lead, Message
        from sqlalchemy import not_

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return []
        # Filter out archived and spam leads by default
        query = session.query(Lead).filter_by(creator_id=creator.id)
        if not include_archived:
            query = query.filter(not_(Lead.status.in_(["archived", "spam"])))
        # Add limit for performance (was loading ALL leads before)
        leads = query.order_by(Lead.last_contact_at.desc()).limit(limit).all()

        # Get last message for each lead using DISTINCT ON (PostgreSQL optimization)
        lead_ids = [lead.id for lead in leads]
        last_messages = {}
        if lead_ids:
            from sqlalchemy import desc

            # DISTINCT ON is much faster than subquery + JOIN
            # It gets the first row for each lead_id when ordered by created_at DESC
            # Only include sent/edited messages (exclude pending_approval copilot drafts)
            last_msg_query = (
                session.query(Message)
                .filter(
                    Message.lead_id.in_(lead_ids),
                    Message.status.in_(["sent", "edited"]),
                )
                .distinct(Message.lead_id)
                .order_by(Message.lead_id, desc(Message.created_at))
            )
            for msg in last_msg_query.all():
                last_messages[msg.lead_id] = msg

        result = []
        for lead in leads:
            # Get last message preview and role
            last_msg = last_messages.get(lead.id)
            last_message_preview = None
            last_message_role = None
            if last_msg:
                content = last_msg.content or ""
                last_message_preview = content[:50] + "..." if len(content) > 50 else content
                last_message_role = last_msg.role

            # is_unread: true if last message is from user (follower) - awaiting creator response
            is_unread = last_message_role == "user"

            # is_verified: from context JSON (populated by Instagram API)
            context = lead.context or {}
            is_verified = context.get("is_verified", False)

            result.append(
                {
                    "id": str(lead.id),
                    "follower_id": str(lead.id),
                    "platform_user_id": lead.platform_user_id,
                    "platform": lead.platform,
                    "username": lead.username,
                    "full_name": lead.full_name,
                    "profile_pic_url": lead.profile_pic_url,
                    "status": lead.status,
                    "score": lead.score,
                    "purchase_intent": lead.purchase_intent,
                    "relationship_type": lead.relationship_type or "nuevo",
                    "last_contact_at": (
                        lead.last_contact_at.isoformat() if lead.last_contact_at else None
                    ),
                    # Instagram-like UX fields (FIX 2026-02-02)
                    "last_message_preview": last_message_preview,
                    "last_message_role": last_message_role,
                    "is_unread": is_unread,
                    "is_verified": is_verified,
                    # CRM fields from direct columns (not context JSON)
                    "email": lead.email,
                    "phone": lead.phone,
                    "notes": lead.notes,
                    "tags": lead.tags,
                    "deal_value": lead.deal_value,
                }
            )
        return result
    finally:
        session.close()


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

        creator = session.query(Creator).filter_by(name=creator_name).first()
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


def create_lead(creator_name: str, data: dict):
    import time
    start = time.time()
    session = get_session()
    if not session:
        logger.warning("create_lead: no database session available")
        return None
    try:
        from api.models import Creator, Lead

        t1 = time.time()
        creator = session.query(Creator).filter_by(name=creator_name).first()
        logger.info(f"⏱️ create_lead: query creator took {time.time()-t1:.2f}s")

        if not creator:
            logger.warning(f"create_lead: creator '{creator_name}' not found, creating it")
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
            source=data.get("source", f"{data.get('platform', 'manual')}_dm"),
            status=data.get("status", "new"),
            score=data.get("score", 0),
            purchase_intent=data.get("purchase_intent", 0.0),
            context=context,
        )
        session.add(lead)
        t2 = time.time()
        session.commit()
        logger.info(f"⏱️ create_lead: commit took {time.time()-t2:.2f}s")
        logger.info(f"⏱️ create_lead: TOTAL {time.time()-start:.2f}s for {creator_name}")
        return {
            "id": str(lead.id),
            "platform_user_id": lead.platform_user_id,
            "username": lead.username,
            "full_name": lead.full_name,
            "platform": lead.platform,
            "status": lead.status,
            "score": lead.score,
            "purchase_intent": lead.purchase_intent,
            "relationship_type": lead.relationship_type or "nuevo",
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
        logger.warning(f"get_products: no session for {creator_name}")
        return []
    try:
        from api.models import Creator, Product

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            logger.warning(f"get_products: creator '{creator_name}' not found")
            return []
        products = session.query(Product).filter_by(creator_id=creator.id).all()
        logger.info(f"get_products: found {len(products)} products for {creator_name}")
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "short_description": getattr(p, "short_description", "") or "",
                "category": getattr(p, "category", "product") or "product",
                "product_type": getattr(p, "product_type", "otro") or "otro",
                "is_free": getattr(p, "is_free", False) or False,
                "price": p.price,
                "currency": p.currency,
                "payment_link": getattr(p, "payment_link", "") or "",
                "source_url": getattr(p, "source_url", "") or "",
                "is_active": p.is_active,
            }
            for p in products
        ]
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

        creator = session.query(Creator).filter_by(name=creator_name).first()
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


# ============================================
# CRUD COMPLETO - Phase 11
# ============================================


# =============================================================================
# PROTECTED BLOCK: Product Creation with Taxonomy
# Modified: 2026-01-16
# Reason: Guarda todos los campos de taxonomía (category, product_type, is_free)
# Do not remove taxonomy fields - required for frontend forms and bot responses
# =============================================================================
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
            short_description=data.get("short_description", ""),
            # Taxonomy fields
            category=data.get("category", "product"),
            product_type=data.get("product_type", "otro"),
            is_free=data.get("is_free", False),
            # Pricing
            price=data.get("price", 0),
            currency=data.get("currency", "EUR"),
            # Links
            payment_link=data.get("payment_link", ""),
            # Status
            is_active=data.get("is_active", True),
        )
        session.add(product)
        session.commit()
        return {"id": str(product.id), "name": product.name, "status": "created"}
    except Exception as _e:
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
        import uuid

        from api.models import Creator, Product

        logger.info(f"update_product: creator={creator_name}, product_id={product_id}")
        logger.info(f"update_product: data received = {data}")

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            logger.error(f"update_product: Creator '{creator_name}' not found")
            return False

        product = (
            session.query(Product)
            .filter_by(creator_id=creator.id, id=uuid.UUID(product_id))
            .first()
        )
        if product:
            logger.info(
                f"update_product: Found product '{product.name}', current payment_link='{product.payment_link}'"
            )
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
        import uuid

        from api.models import Creator, Product

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return False
        product = (
            session.query(Product)
            .filter_by(creator_id=creator.id, id=uuid.UUID(product_id))
            .first()
        )
        if product:
            session.delete(product)
            session.commit()
            return True
        return False
    except Exception as _e:
        session.rollback()
        return False
    finally:
        session.close()


def update_lead(creator_name: str, lead_id: str, data: dict):
    session = get_session()
    if not session:
        return False
    try:
        import uuid

        from api.models import Creator, Lead

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            logger.warning(f"update_lead: creator '{creator_name}' not found")
            return False

        # Try to find lead by UUID first, then by platform_user_id
        lead = None
        try:
            lead = (
                session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(lead_id)).first()
            )
        except (ValueError, AttributeError):
            pass  # Not a valid UUID, try platform_user_id

        if not lead:
            lead = (
                session.query(Lead)
                .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                .first()
            )

        if lead:
            logger.info(f"update_lead: lead {lead_id} found")

            # CRM fields are now direct columns on Lead model
            _crm_fields = ["email", "phone", "notes", "tags", "deal_value", "source", "assigned_to"]

            for key, value in data.items():
                if hasattr(lead, key):
                    setattr(lead, key, value)
                    logger.info(f"update_lead: setting {key} = {value}")

            # Also update name fields if provided
            if "name" in data:
                lead.full_name = data["name"]
                if not lead.username:
                    lead.username = data["name"]

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
                "relationship_type": lead.relationship_type or "nuevo",
                "email": lead.email,
                "phone": lead.phone,
                "notes": lead.notes,
                "tags": lead.tags,
                "deal_value": lead.deal_value,
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
    """
    Delete a lead using raw SQL for speed.
    ORM cascade is slow with many messages - this uses bulk DELETE.
    """
    session = get_session()
    if not session:
        return False
    try:
        import uuid

        from api.models import Creator, Lead
        from sqlalchemy import text

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            logger.warning(f"delete_lead: creator '{creator_name}' not found")
            return False

        # Try to find lead by UUID first, then by platform_user_id
        lead_uuid = None
        try:
            lead_uuid = uuid.UUID(lead_id)
            lead = session.query(Lead).filter_by(creator_id=creator.id, id=lead_uuid).first()
        except (ValueError, AttributeError):
            lead = (
                session.query(Lead)
                .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                .first()
            )

        if not lead:
            logger.warning(f"delete_lead: lead '{lead_id}' not found")
            return False

        lead_uuid = lead.id
        platform_user_id = lead.platform_user_id

        # FAST: Use raw SQL bulk DELETE (not ORM cascade which is slow)
        # Delete related records first (FK constraints)
        session.execute(
            text("DELETE FROM lead_activities WHERE lead_id = :lid"), {"lid": lead_uuid}
        )
        session.execute(text("DELETE FROM lead_tasks WHERE lead_id = :lid"), {"lid": lead_uuid})
        session.execute(text("DELETE FROM csat_ratings WHERE lead_id = :lid"), {"lid": lead_uuid})
        session.execute(text("DELETE FROM messages WHERE lead_id = :lid"), {"lid": lead_uuid})

        # Add to dismissed_leads blocklist so it doesn't reappear on sync
        session.execute(
            text(
                """
            INSERT INTO dismissed_leads (creator_id, platform_user_id, dismissed_at)
            VALUES (:cid, :puid, NOW())
            ON CONFLICT (creator_id, platform_user_id) DO NOTHING
        """
            ),
            {"cid": creator.id, "puid": platform_user_id},
        )

        # Now delete the lead itself
        session.execute(text("DELETE FROM leads WHERE id = :lid"), {"lid": lead_uuid})

        session.commit()
        logger.info(f"delete_lead: deleted lead {lead_id} (fast SQL)")
        return True
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
        import uuid

        from api.models import Creator, Lead

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return None

        # Try to find lead by UUID first, then by platform_user_id
        lead = None
        try:
            lead = (
                session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(lead_id)).first()
            )
        except (ValueError, AttributeError):
            pass  # Not a valid UUID, try platform_user_id

        if not lead:
            lead = (
                session.query(Lead)
                .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                .first()
            )

        if lead:
            return {
                "id": str(lead.id),
                "platform_user_id": lead.platform_user_id,
                "platform": lead.platform,
                "username": lead.username,
                "full_name": lead.full_name,
                "status": lead.status,
                "score": lead.score,
                "purchase_intent": lead.purchase_intent,
                "relationship_type": lead.relationship_type or "nuevo",
                # CRM fields from direct columns
                "email": lead.email,
                "phone": lead.phone,
                "notes": lead.notes,
                "tags": lead.tags,
                "deal_value": lead.deal_value,
                "context": lead.context or {},
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
        lead = (
            session.query(Lead)
            .filter_by(creator_id=creator.id, platform_user_id=platform_id)
            .first()
        )
        if lead:
            return {
                "id": str(lead.id),
                "creator_id": str(creator.id),
                "platform_user_id": lead.platform_user_id,
                "platform": lead.platform,
                "username": lead.username,
                "full_name": lead.full_name,
                "status": lead.status,
            }
        return None
    except Exception as e:
        logger.error(f"get_lead_by_platform_id error: {e}")
        return None
    finally:
        session.close()


async def create_lead_async(creator_id: str, data: dict) -> dict:
    """Create a new lead for dm_agent integration (async version).

    FIX: Added duplicate check to prevent race conditions from creating duplicate leads.
    """
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

        platform_user_id = data.get("platform_user_id", str(uuid.uuid4()))

        # DUPLICATE CHECK: Prevent race condition duplicates
        existing = (
            session.query(Lead)
            .filter_by(creator_id=creator.id, platform_user_id=platform_user_id)
            .first()
        )
        if existing:
            logger.info(f"Lead already exists for {platform_user_id}, returning existing")
            return {"id": str(existing.id), "status": "existing"}

        # Create new lead
        lead = Lead(
            creator_id=creator.id,
            platform=data.get("platform", "telegram"),
            platform_user_id=platform_user_id,
            username=data.get("username", ""),
            full_name=data.get("full_name") or data.get("name", ""),
            status="new",
            score=0,
            purchase_intent=0.0,
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


def get_or_create_lead(
    creator_name: str,
    platform_user_id: str,
    platform: str = "instagram",
    username: str = None,
    full_name: str = None,
    profile_pic_url: str = None,
) -> dict:
    """
    Get existing lead or create new one. Used by Instagram webhook handlers.

    This is the primary function for ensuring a lead exists when processing
    incoming messages or interactions.

    Args:
        creator_name: Creator name (e.g., 'fitpack_global')
        platform_user_id: Platform-specific user ID (e.g., 'ig_123456')
        platform: Platform name ('instagram', 'telegram')
        username: Optional @username
        full_name: Optional display name
        profile_pic_url: Optional profile picture URL

    Returns:
        Dict with lead info: {id, creator_id, platform_user_id, username, status}
        or None if failed
    """
    session = get_session()
    if not session:
        logger.warning("get_or_create_lead: no database session available")
        return None

    try:
        from datetime import timezone

        from api.models import Creator, DismissedLead, Lead

        # Get creator by name
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            logger.warning(f"get_or_create_lead: creator '{creator_name}' not found")
            return None

        # Check if lead already exists - check both with and without ig_ prefix
        # to prevent duplicates from different sources
        raw_id = (
            platform_user_id.replace("ig_", "")
            if platform_user_id.startswith("ig_")
            else platform_user_id
        )
        possible_ids = [platform_user_id, f"ig_{raw_id}", raw_id]
        # Remove duplicates while preserving order
        possible_ids = list(dict.fromkeys(possible_ids))

        lead = (
            session.query(Lead)
            .filter(Lead.creator_id == creator.id, Lead.platform_user_id.in_(possible_ids))
            .first()
        )

        if lead:
            # Update profile info if provided and changed
            if username and lead.username != username:
                lead.username = username
            if full_name and lead.full_name != full_name:
                lead.full_name = full_name
            if profile_pic_url and lead.profile_pic_url != profile_pic_url:
                lead.profile_pic_url = profile_pic_url

            # Always update last_contact_at
            lead.last_contact_at = datetime.now(timezone.utc)
            session.commit()

            return {
                "id": str(lead.id),
                "creator_id": str(creator.id),
                "platform_user_id": lead.platform_user_id,
                "username": lead.username,
                "full_name": lead.full_name,
                "status": lead.status,
            }

        # Check if this lead was dismissed (deleted by creator)
        # Must check all possible ID formats in the blocklist
        is_dismissed = (
            session.query(DismissedLead)
            .filter(
                DismissedLead.creator_id == creator.id,
                DismissedLead.platform_user_id.in_(possible_ids),
            )
            .first()
        )
        if is_dismissed:
            logger.info(
                f"get_or_create_lead: BLOCKED dismissed lead {platform_user_id} "
                f"(dismissed as {is_dismissed.platform_user_id})"
            )
            return None

        # Create new lead
        now = datetime.now(timezone.utc)
        lead = Lead(
            creator_id=creator.id,
            platform=platform,
            platform_user_id=platform_user_id,
            username=username or platform_user_id,
            full_name=full_name or username or "",
            profile_pic_url=profile_pic_url,
            source=f"{platform}_dm",
            status="new",
            score=0,
            purchase_intent=0.0,
            first_contact_at=now,
            last_contact_at=now,
        )
        session.add(lead)
        session.commit()

        logger.info(f"get_or_create_lead: created new lead {lead.id} for {platform_user_id}")

        return {
            "id": str(lead.id),
            "creator_id": str(creator.id),
            "platform_user_id": lead.platform_user_id,
            "username": lead.username,
            "full_name": lead.full_name,
            "status": lead.status,
        }

    except Exception as e:
        logger.error(f"get_or_create_lead error: {e}")
        session.rollback()
        return None
    finally:
        session.close()


async def save_message(
    lead_id: str,
    role: str,
    content: str,
    intent: str = None,
    platform_message_id: str = None,
    metadata: dict = None,
) -> dict:
    """Save a message to the database for dm_agent integration.

    FIX: Added duplicate detection to prevent webhook message duplication.
    Checks for existing message with same content+lead within last 5 minutes.

    NOTE: Link preview extraction is done asynchronously via background job,
    not during save_message, to avoid blocking the webhook.

    Args:
        lead_id: UUID of the lead
        role: 'user' or 'assistant'
        content: Message text
        intent: Optional intent classification
        platform_message_id: Optional platform-specific message ID
        metadata: Optional dict with type, url, emoji, link_preview, etc.
    """
    if not USE_POSTGRES:
        return None
    session = get_session()
    if not session:
        return None
    try:
        import uuid as uuid_module
        from datetime import timedelta, timezone

        from api.models import Message

        # Convert lead_id string to UUID
        lead_uuid = uuid_module.UUID(lead_id) if isinstance(lead_id, str) else lead_id

        # DUPLICATE CHECK: Check if same message exists for this lead in last 5 minutes
        # This prevents webhook retries from creating duplicate messages
        five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        existing = (
            session.query(Message)
            .filter(
                Message.lead_id == lead_uuid,
                Message.role == role,
                Message.content == content,
                Message.created_at >= five_minutes_ago,
            )
            .first()
        )

        if existing:
            logger.info(f"Duplicate message detected for lead {lead_id}, skipping (role={role})")
            return {"id": str(existing.id), "status": "duplicate_skipped"}

        # Also check by platform_message_id if provided
        if platform_message_id:
            existing_by_id = (
                session.query(Message)
                .filter(Message.platform_message_id == platform_message_id)
                .first()
            )
            if existing_by_id:
                logger.info(f"Duplicate message by platform_message_id: {platform_message_id}")
                return {"id": str(existing_by_id.id), "status": "duplicate_skipped"}

        # Build metadata (link preview extraction moved to background job)
        msg_metadata = metadata.copy() if metadata else {}

        # Create new message
        message = Message(
            lead_id=lead_uuid,
            role=role,  # 'user' or 'assistant'
            content=content,
            intent=intent,
            platform_message_id=platform_message_id,
            msg_metadata=msg_metadata if msg_metadata else None,
            created_at=datetime.now(timezone.utc),
        )
        session.add(message)
        session.commit()
        message_id = str(message.id)
        logger.info(f"Saved message for lead {lead_id}: role={role}")

        # Schedule background link preview extraction (fire-and-forget)
        if content and "http" in content.lower():
            try:
                from core.link_preview import schedule_link_preview_extraction

                schedule_link_preview_extraction(message_id, content)
            except Exception as e:
                logger.debug(f"Could not schedule link preview: {e}")

        return {"id": message_id, "status": "saved"}
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
        return [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "intent": m.intent,
                "created_at": str(m.created_at),
            }
            for m in messages
        ]
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
        count = (
            session.query(Message)
            .join(Lead)
            .filter(Lead.creator_id == creator.id, Message.role == "user")
            .count()
        )
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
        import uuid as uuid_module

        from api.models import Message

        lead_uuid = uuid_module.UUID(lead_id) if isinstance(lead_id, str) else lead_id
        messages = (
            session.query(Message)
            .filter(Message.lead_id == lead_uuid)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {"role": m.role, "content": m.content, "timestamp": str(m.created_at)}
            for m in reversed(messages)  # Return in chronological order
        ]
    except Exception as e:
        logger.error(f"get_messages_by_lead_id error: {e}")
        return []
    finally:
        session.close()


def get_recent_messages(creator_id: str, follower_id: str, limit: int = 4) -> list:
    """Get recent messages for a follower (sync version for thanks detection)"""
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

        lead = (
            session.query(Lead)
            .filter(Lead.creator_id == creator.id, Lead.platform_user_id == follower_id)
            .first()
        )
        if not lead:
            return []

        messages = (
            session.query(Message)
            .filter(Message.lead_id == lead.id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {"role": m.role, "content": m.content, "timestamp": str(m.created_at)}
            for m in messages  # Most recent first
        ]
    except Exception as e:
        logger.error(f"get_recent_messages error: {e}")
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
        import uuid as uuid_module

        from api.models import Message

        lead_uuid = uuid_module.UUID(lead_id) if isinstance(lead_id, str) else lead_id
        count = (
            session.query(Message)
            .filter(Message.lead_id == lead_uuid, Message.role == "user")
            .count()
        )
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
        lead = (
            session.query(Lead)
            .filter_by(creator_id=creator.id, platform_user_id=conversation_id)
            .first()
        )
        if not lead:
            try:
                import uuid

                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, id=uuid.UUID(conversation_id))
                    .first()
                )
            except (ValueError, AttributeError) as e:
                logger.warning("Failed to parse conversation UUID %s: %s", conversation_id, e)
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
        lead = (
            session.query(Lead)
            .filter_by(creator_id=creator.id, platform_user_id=conversation_id)
            .first()
        )
        if not lead:
            try:
                import uuid

                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, id=uuid.UUID(conversation_id))
                    .first()
                )
            except (ValueError, AttributeError) as e:
                logger.warning("Failed to parse conversation UUID %s: %s", conversation_id, e)
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
            lead = (
                session.query(Lead)
                .filter_by(creator_id=creator.id, platform_user_id=conversation_id)
                .first()
            )
            if not lead:
                try:
                    import uuid

                    lead = (
                        session.query(Lead)
                        .filter_by(creator_id=creator.id, id=uuid.UUID(conversation_id))
                        .first()
                    )
                except (ValueError, AttributeError) as e:
                    logger.warning("Failed to parse conversation UUID %s: %s", conversation_id, e)
            if lead and lead.status in ["archived", "spam"]:
                lead.status = "new"
                session.commit()
                logger.info(f"Reset conversation {conversation_id} to 'new'")
                return 1
            return 0
        else:
            # Reset ALL archived/spam conversations
            count = (
                session.query(Lead)
                .filter_by(creator_id=creator.id)
                .filter(Lead.status.in_(["archived", "spam"]))
                .update({"status": "new"}, synchronize_session=False)
            )
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
        lead = (
            session.query(Lead)
            .filter_by(creator_id=creator.id, platform_user_id=conversation_id)
            .first()
        )
        platform_user_id = None
        if not lead:
            try:
                import uuid

                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, id=uuid.UUID(conversation_id))
                    .first()
                )
            except (ValueError, AttributeError) as e:
                logger.warning("Failed to parse conversation UUID %s: %s", conversation_id, e)
        if lead:
            platform_user_id = lead.platform_user_id
            lead_username = lead.username

            # Add to dismissed_leads blocklist BEFORE deleting
            # This prevents sync from re-importing the conversation
            try:
                from api.models import DismissedLead

                existing_dismissed = (
                    session.query(DismissedLead)
                    .filter_by(creator_id=creator.id, platform_user_id=platform_user_id)
                    .first()
                )
                if not existing_dismissed:
                    dismissed = DismissedLead(
                        creator_id=creator.id,
                        platform_user_id=platform_user_id,
                        username=lead_username,
                        reason="manual_delete",
                    )
                    session.add(dismissed)
                    logger.info(
                        f"Added {platform_user_id} ({lead_username}) to dismissed_leads blocklist"
                    )
            except Exception as blocklist_err:
                logger.warning(f"Failed to add to blocklist: {blocklist_err}")

            # Delete all dependent records first (foreign key constraints)
            from api.models import LeadActivity, LeadTask, CSATRating

            session.query(LeadActivity).filter_by(lead_id=lead.id).delete()
            session.query(LeadTask).filter_by(lead_id=lead.id).delete()
            session.query(CSATRating).filter_by(lead_id=lead.id).delete()
            session.query(Message).filter_by(lead_id=lead.id).delete()
            # Also clean up nurturing followups (no FK but stale data)
            try:
                from core.nurturing_db import NurturingFollowupDB

                session.query(NurturingFollowupDB).filter_by(
                    follower_id=platform_user_id
                ).delete()
            except Exception:
                pass  # Table may not exist
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
        items = (
            session.query(KnowledgeBase)
            .filter_by(creator_id=creator.id)
            .order_by(KnowledgeBase.created_at.desc())
            .all()
        )
        return [
            {
                "id": str(item.id),
                "question": item.question,
                "answer": item.answer,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ]
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
        item = KnowledgeBase(creator_id=creator.id, question=question, answer=answer)
        session.add(item)
        session.commit()
        return {
            "id": str(item.id),
            "question": item.question,
            "answer": item.answer,
            "created_at": item.created_at.isoformat() if item.created_at else None,
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
        import uuid as uuid_module

        from api.models import Creator, KnowledgeBase

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return False
        item = (
            session.query(KnowledgeBase)
            .filter_by(creator_id=creator.id, id=uuid_module.UUID(item_id))
            .first()
        )
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


def update_knowledge_item(creator_name: str, item_id: str, question: str, answer: str) -> dict:
    """Update a FAQ item in knowledge_base table"""
    session = get_session()
    if not session:
        return None
    try:
        import uuid as uuid_module

        from api.models import Creator, KnowledgeBase

        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            return None
        item = (
            session.query(KnowledgeBase)
            .filter_by(creator_id=creator.id, id=uuid_module.UUID(item_id))
            .first()
        )
        if item:
            item.question = question
            item.answer = answer
            session.commit()
            return {
                "id": str(item.id),
                "question": item.question,
                "answer": item.answer,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
        return None
    except Exception as e:
        logger.error(f"update_knowledge_item error: {e}")
        session.rollback()
        return None
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
        flag_modified(creator, "knowledge_about")
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
    return {"faqs": faqs, "about": about}
