"""
Conversation actions — archive, spam, reset, delete.
"""

import logging

from api.services.db_ops.common import get_session
from api.utils.creator_resolver import resolve_creator_safe

logger = logging.getLogger(__name__)


def archive_conversation(creator_name: str, conversation_id: str) -> bool:
    """Archive a conversation by setting lead.status = 'archived'"""
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator, Lead

        creator = resolve_creator_safe(session, creator_name)
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

        creator = resolve_creator_safe(session, creator_name)
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

        creator = resolve_creator_safe(session, creator_name)
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

        creator = resolve_creator_safe(session, creator_name)
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
            from api.models import CSATRating, LeadActivity, LeadTask

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
