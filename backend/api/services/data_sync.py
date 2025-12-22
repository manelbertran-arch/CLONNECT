"""
Data Synchronization Service for CLONNECT
Provides bidirectional sync between PostgreSQL and JSON files
"""
import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)
STORAGE_PATH = "data/followers"


def _get_json_path(creator_id: str, follower_id: str) -> str:
    """Get the JSON file path for a follower"""
    creator_dir = os.path.join(STORAGE_PATH, creator_id)
    os.makedirs(creator_dir, exist_ok=True)
    return os.path.join(creator_dir, f"{follower_id}.json")


def _load_json(creator_id: str, follower_id: str) -> Optional[Dict]:
    """Load follower data from JSON file"""
    file_path = _get_json_path(creator_id, follower_id)
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading JSON {file_path}: {e}")
    return None


def _save_json(creator_id: str, follower_id: str, data: Dict):
    """Save follower data to JSON file"""
    file_path = _get_json_path(creator_id, follower_id)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug(f"Saved JSON: {file_path}")
    except Exception as e:
        logger.error(f"Error saving JSON {file_path}: {e}")


def sync_lead_to_json(creator_name: str, lead_data: Dict):
    """
    Sync a PostgreSQL Lead to JSON file.
    Called after any Lead update in PostgreSQL.
    """
    try:
        platform_user_id = lead_data.get("platform_user_id", "")
        if not platform_user_id:
            return

        # Load existing JSON or create new
        existing = _load_json(creator_name, platform_user_id)

        now = datetime.now(timezone.utc).isoformat()

        if existing:
            # Update existing JSON with PostgreSQL data
            existing["username"] = lead_data.get("username") or existing.get("username", "")
            existing["name"] = lead_data.get("full_name") or existing.get("name", "")
            existing["purchase_intent_score"] = lead_data.get("purchase_intent", 0.0)
            existing["is_lead"] = lead_data.get("status") not in ["archived", "spam"]
            existing["is_customer"] = lead_data.get("context", {}).get("is_customer", False) if lead_data.get("context") else existing.get("is_customer", False)
            existing["last_contact"] = lead_data.get("last_contact_at") or existing.get("last_contact", now)
            _save_json(creator_name, platform_user_id, existing)
        else:
            # Create new JSON from PostgreSQL data
            new_data = {
                "follower_id": platform_user_id,
                "creator_id": creator_name,
                "username": lead_data.get("username", ""),
                "name": lead_data.get("full_name", ""),
                "first_contact": lead_data.get("first_contact_at") or now,
                "last_contact": lead_data.get("last_contact_at") or now,
                "total_messages": 0,
                "interests": [],
                "products_discussed": [],
                "objections_raised": [],
                "purchase_intent_score": lead_data.get("purchase_intent", 0.0),
                "engagement_score": 0.0,
                "is_lead": lead_data.get("status") not in ["archived", "spam"],
                "is_customer": lead_data.get("context", {}).get("is_customer", False) if lead_data.get("context") else False,
                "needs_followup": False,
                "preferred_language": "es",
                "conversation_summary": "",
                "last_messages": []
            }
            _save_json(creator_name, platform_user_id, new_data)

        logger.info(f"Synced Lead to JSON: {creator_name}/{platform_user_id}")
    except Exception as e:
        logger.error(f"sync_lead_to_json error: {e}")


def sync_json_to_postgres(creator_name: str, follower_id: str) -> Optional[str]:
    """
    Sync a JSON follower to PostgreSQL Lead.
    Called when JSON exists but PostgreSQL doesn't.
    Returns the lead_id if created/found.
    """
    if not USE_POSTGRES:
        return None

    try:
        json_data = _load_json(creator_name, follower_id)
        if not json_data:
            return None

        from api.services.db_service import get_session
        from api.models import Creator, Lead

        session = get_session()
        if not session:
            return None

        try:
            # Get creator
            creator = session.query(Creator).filter_by(name=creator_name).first()
            if not creator:
                logger.warning(f"Creator not found: {creator_name}")
                return None

            # Check if lead exists
            lead = session.query(Lead).filter_by(
                creator_id=creator.id,
                platform_user_id=follower_id
            ).first()

            if lead:
                # Update existing lead with JSON data if JSON is newer
                json_last_contact = json_data.get("last_contact")
                if json_last_contact:
                    try:
                        json_dt = datetime.fromisoformat(json_last_contact.replace('Z', '+00:00'))
                        if not lead.last_contact_at or json_dt > lead.last_contact_at:
                            lead.purchase_intent = json_data.get("purchase_intent_score", lead.purchase_intent or 0.0)
                            lead.username = json_data.get("username") or lead.username
                            lead.full_name = json_data.get("name") or lead.full_name
                            lead.last_contact_at = json_dt
                            # Sync status from JSON (only upgrade, never downgrade)
                            json_status = json_data.get("status", "new")
                            status_order = {"new": 0, "active": 1, "hot": 2, "customer": 3}
                            if status_order.get(json_status, 0) > status_order.get(lead.status, 0):
                                lead.status = json_status
                                logger.info(f"Synced status {lead.status} → {json_status} for {follower_id}")
                            session.commit()
                    except:
                        pass
                return str(lead.id)
            else:
                # Create new lead from JSON
                # Detect platform from follower_id
                platform = "instagram"
                if follower_id.startswith("tg_"):
                    platform = "telegram"
                elif follower_id.startswith("wa_"):
                    platform = "whatsapp"

                # Use status from JSON if available, otherwise derive from is_customer/is_lead
                json_status = json_data.get("status")
                if not json_status:
                    if json_data.get("is_customer", False):
                        json_status = "customer"
                    elif json_data.get("is_lead", True):
                        json_status = "new"
                    else:
                        json_status = "new"

                lead = Lead(
                    creator_id=creator.id,
                    platform=platform,
                    platform_user_id=follower_id,
                    username=json_data.get("username", ""),
                    full_name=json_data.get("name", ""),
                    status=json_status,
                    purchase_intent=json_data.get("purchase_intent_score", 0.0),
                    context={"is_customer": json_data.get("is_customer", False)}
                )
                session.add(lead)
                session.commit()
                logger.info(f"Created Lead from JSON: {creator_name}/{follower_id}")
                return str(lead.id)
        finally:
            session.close()
    except Exception as e:
        logger.error(f"sync_json_to_postgres error: {e}")
        return None


def sync_message_to_json(creator_name: str, follower_id: str, role: str, content: str):
    """
    Sync a message to the JSON last_messages array.
    Called after saving a message to PostgreSQL.
    """
    try:
        json_data = _load_json(creator_name, follower_id)
        if not json_data:
            # Create basic JSON if doesn't exist
            json_data = {
                "follower_id": follower_id,
                "creator_id": creator_name,
                "username": "",
                "name": "",
                "first_contact": datetime.now(timezone.utc).isoformat(),
                "last_contact": datetime.now(timezone.utc).isoformat(),
                "total_messages": 0,
                "interests": [],
                "products_discussed": [],
                "objections_raised": [],
                "purchase_intent_score": 0.0,
                "engagement_score": 0.0,
                "is_lead": True,
                "is_customer": False,
                "needs_followup": False,
                "preferred_language": "es",
                "conversation_summary": "",
                "last_messages": []
            }

        # Add message
        json_data["last_messages"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Keep last 20 messages
        json_data["last_messages"] = json_data["last_messages"][-20:]

        # Update counters
        json_data["total_messages"] = json_data.get("total_messages", 0) + 1
        json_data["last_contact"] = datetime.now(timezone.utc).isoformat()

        _save_json(creator_name, follower_id, json_data)
        logger.debug(f"Synced message to JSON: {creator_name}/{follower_id}")
    except Exception as e:
        logger.error(f"sync_message_to_json error: {e}")


def sync_archive_to_json(creator_name: str, follower_id: str):
    """Mark a conversation as archived in JSON"""
    try:
        json_data = _load_json(creator_name, follower_id)
        if json_data:
            json_data["is_lead"] = False
            json_data["archived"] = True
            _save_json(creator_name, follower_id, json_data)
            logger.info(f"Archived in JSON: {creator_name}/{follower_id}")
    except Exception as e:
        logger.error(f"sync_archive_to_json error: {e}")


def sync_spam_to_json(creator_name: str, follower_id: str):
    """Mark a conversation as spam in JSON"""
    try:
        json_data = _load_json(creator_name, follower_id)
        if json_data:
            json_data["is_lead"] = False
            json_data["spam"] = True
            _save_json(creator_name, follower_id, json_data)
            logger.info(f"Marked spam in JSON: {creator_name}/{follower_id}")
    except Exception as e:
        logger.error(f"sync_spam_to_json error: {e}")


def sync_delete_json(creator_name: str, follower_id: str):
    """Delete the JSON file for a conversation"""
    try:
        file_path = _get_json_path(creator_name, follower_id)
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted JSON: {creator_name}/{follower_id}")
    except Exception as e:
        logger.error(f"sync_delete_json error: {e}")


def ensure_lead_in_postgres(creator_name: str, follower_id: str) -> Optional[str]:
    """
    Ensure a lead exists in PostgreSQL (sync from JSON if needed).
    Returns the lead_id.
    """
    if not USE_POSTGRES:
        return None

    try:
        from api.services.db_service import get_session
        from api.models import Creator, Lead

        session = get_session()
        if not session:
            return None

        try:
            creator = session.query(Creator).filter_by(name=creator_name).first()
            if not creator:
                return None

            lead = session.query(Lead).filter_by(
                creator_id=creator.id,
                platform_user_id=follower_id
            ).first()

            if lead:
                return str(lead.id)

            # Lead doesn't exist in PostgreSQL, try to sync from JSON
            return sync_json_to_postgres(creator_name, follower_id)
        finally:
            session.close()
    except Exception as e:
        logger.error(f"ensure_lead_in_postgres error: {e}")
        return None


def full_sync_creator(creator_name: str) -> Dict[str, int]:
    """
    Full sync for a creator: sync all JSON files to PostgreSQL.
    Returns stats about the sync.
    """
    stats = {"synced": 0, "errors": 0, "skipped": 0}

    if not USE_POSTGRES:
        return stats

    creator_dir = os.path.join(STORAGE_PATH, creator_name)
    if not os.path.exists(creator_dir):
        return stats

    try:
        for filename in os.listdir(creator_dir):
            if filename.endswith('.json'):
                follower_id = filename[:-5]
                try:
                    result = sync_json_to_postgres(creator_name, follower_id)
                    if result:
                        stats["synced"] += 1
                    else:
                        stats["skipped"] += 1
                except Exception as e:
                    logger.error(f"Error syncing {follower_id}: {e}")
                    stats["errors"] += 1
    except Exception as e:
        logger.error(f"full_sync_creator error: {e}")

    logger.info(f"Full sync for {creator_name}: {stats}")
    return stats


def sync_messages_from_json(creator_name: str) -> Dict[str, int]:
    """
    Sync all messages from JSON files to PostgreSQL for a creator.
    This is a one-time migration function.
    Returns stats about the sync.
    """
    stats = {"messages_synced": 0, "leads_processed": 0, "errors": 0}

    if not USE_POSTGRES:
        return stats

    creator_dir = os.path.join(STORAGE_PATH, creator_name)
    if not os.path.exists(creator_dir):
        return stats

    try:
        from api.services.db_service import get_session
        from api.models import Creator, Lead, Message
        import uuid

        session = get_session()
        if not session:
            return stats

        try:
            creator = session.query(Creator).filter_by(name=creator_name).first()
            if not creator:
                logger.warning(f"Creator not found: {creator_name}")
                return stats

            for filename in os.listdir(creator_dir):
                if filename.endswith('.json'):
                    follower_id = filename[:-5]
                    try:
                        json_data = _load_json(creator_name, follower_id)
                        if not json_data:
                            continue

                        # Get or create lead
                        lead = session.query(Lead).filter_by(
                            creator_id=creator.id,
                            platform_user_id=follower_id
                        ).first()

                        if not lead:
                            # Create lead first
                            platform = "instagram"
                            if follower_id.startswith("tg_"):
                                platform = "telegram"
                            elif follower_id.startswith("wa_"):
                                platform = "whatsapp"

                            lead = Lead(
                                creator_id=creator.id,
                                platform=platform,
                                platform_user_id=follower_id,
                                username=json_data.get("username", ""),
                                full_name=json_data.get("name", ""),
                                status="new",
                                purchase_intent=json_data.get("purchase_intent_score", 0.0)
                            )
                            session.add(lead)
                            session.commit()

                        # Check existing messages count for this lead
                        existing_count = session.query(Message).filter_by(lead_id=lead.id).count()

                        # Sync messages from JSON
                        last_messages = json_data.get("last_messages", [])
                        messages_added = 0

                        for msg in last_messages:
                            role = msg.get("role", "user")
                            content = msg.get("content", "")
                            timestamp_str = msg.get("timestamp")

                            if not content:
                                continue

                            # Parse timestamp
                            created_at = None
                            if timestamp_str:
                                try:
                                    created_at = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                except:
                                    created_at = datetime.now(timezone.utc)
                            else:
                                created_at = datetime.now(timezone.utc)

                            # Check if message already exists (by content and timestamp)
                            existing = session.query(Message).filter_by(
                                lead_id=lead.id,
                                role=role,
                                content=content
                            ).first()

                            if not existing:
                                message = Message(
                                    lead_id=lead.id,
                                    role=role,
                                    content=content,
                                    created_at=created_at
                                )
                                session.add(message)
                                messages_added += 1

                        session.commit()
                        stats["messages_synced"] += messages_added
                        stats["leads_processed"] += 1
                        logger.info(f"Synced {messages_added} messages for {follower_id}")

                    except Exception as e:
                        logger.error(f"Error syncing messages for {follower_id}: {e}")
                        stats["errors"] += 1
                        session.rollback()

        finally:
            session.close()

    except Exception as e:
        logger.error(f"sync_messages_from_json error: {e}")

    logger.info(f"Message sync for {creator_name}: {stats}")
    return stats
