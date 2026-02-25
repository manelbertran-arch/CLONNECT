"""
Knowledge base operations (FAQs and About Me).
"""

import logging

from api.utils.creator_resolver import resolve_creator_safe
from .session import get_session

logger = logging.getLogger(__name__)


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

        creator = resolve_creator_safe(session, creator_name)
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

        creator = resolve_creator_safe(session, creator_name)
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

        creator = resolve_creator_safe(session, creator_name)
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

        creator = resolve_creator_safe(session, creator_name)
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

        creator = resolve_creator_safe(session, creator_name)
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

        creator = resolve_creator_safe(session, creator_name)
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
