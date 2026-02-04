"""PostContext repository - CRUD operations for post_contexts table.

Provides database operations for storing and retrieving
analyzed context from creator's Instagram posts.

Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_session():
    """Get database session."""
    try:
        from api.services.db_service import get_session as db_get_session

        return db_get_session()
    except ImportError:
        logger.warning("Database service not available")
        return None


def get_post_context(creator_id: str) -> Optional[Dict[str, Any]]:
    """Get PostContext for a creator.

    Args:
        creator_id: Creator identifier

    Returns:
        Dict with context data or None if not found
    """
    session = get_session()
    if not session:
        return None

    try:
        from api.models import PostContextModel

        row = session.query(PostContextModel).filter_by(creator_id=creator_id).first()

        if not row:
            return None

        return _model_to_dict(row)

    except Exception as e:
        logger.error(f"Error getting post context for {creator_id}: {e}")
        return None
    finally:
        session.close()


def create_post_context(context_data: Dict[str, Any]) -> bool:
    """Create new PostContext in database.

    Args:
        context_data: Dict with context fields

    Returns:
        True if successful
    """
    session = get_session()
    if not session:
        return False

    try:
        from api.models import PostContextModel

        model = PostContextModel(
            creator_id=context_data["creator_id"],
            active_promotion=context_data.get("active_promotion"),
            promotion_deadline=context_data.get("promotion_deadline"),
            promotion_urgency=context_data.get("promotion_urgency"),
            recent_topics=context_data.get("recent_topics", []),
            recent_products=context_data.get("recent_products", []),
            availability_hint=context_data.get("availability_hint"),
            context_instructions=context_data["context_instructions"],
            posts_analyzed=context_data.get("posts_analyzed", 0),
            analyzed_at=context_data.get("analyzed_at", datetime.now(timezone.utc)),
            expires_at=context_data["expires_at"],
            source_posts=context_data.get("source_posts", []),
        )

        session.add(model)
        session.commit()

        logger.info(f"Created post context for {context_data['creator_id']}")
        return True

    except Exception as e:
        logger.error(f"Error creating post context: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def update_post_context(creator_id: str, update_data: Dict[str, Any]) -> bool:
    """Update existing PostContext.

    Args:
        creator_id: Creator identifier
        update_data: Dict with fields to update

    Returns:
        True if successful
    """
    session = get_session()
    if not session:
        return False

    try:
        from api.models import PostContextModel

        row = session.query(PostContextModel).filter_by(creator_id=creator_id).first()

        if not row:
            logger.warning(f"Post context not found for {creator_id}")
            return False

        # Update fields
        for key, value in update_data.items():
            if hasattr(row, key):
                setattr(row, key, value)

        session.commit()

        logger.info(f"Updated post context for {creator_id}")
        return True

    except Exception as e:
        logger.error(f"Error updating post context for {creator_id}: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def delete_post_context(creator_id: str) -> bool:
    """Delete PostContext from database.

    Args:
        creator_id: Creator identifier

    Returns:
        True if successful
    """
    session = get_session()
    if not session:
        return False

    try:
        from api.models import PostContextModel

        row = session.query(PostContextModel).filter_by(creator_id=creator_id).first()

        if not row:
            logger.warning(f"Post context not found for {creator_id}")
            return False

        session.delete(row)
        session.commit()

        logger.info(f"Deleted post context for {creator_id}")
        return True

    except Exception as e:
        logger.error(f"Error deleting post context for {creator_id}: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_or_create_post_context(
    creator_id: str, default_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Get existing PostContext or create new one.

    Args:
        creator_id: Creator identifier
        default_data: Default data if creating new

    Returns:
        Dict with context data
    """
    session = get_session()
    if not session:
        return None

    try:
        from api.models import PostContextModel

        row = session.query(PostContextModel).filter_by(creator_id=creator_id).first()

        if row:
            return _model_to_dict(row)

        # Create new
        model = PostContextModel(
            creator_id=creator_id,
            active_promotion=default_data.get("active_promotion"),
            promotion_deadline=default_data.get("promotion_deadline"),
            promotion_urgency=default_data.get("promotion_urgency"),
            recent_topics=default_data.get("recent_topics", []),
            recent_products=default_data.get("recent_products", []),
            availability_hint=default_data.get("availability_hint"),
            context_instructions=default_data.get(
                "context_instructions", "Sin contexto especial"
            ),
            posts_analyzed=default_data.get("posts_analyzed", 0),
            analyzed_at=default_data.get("analyzed_at", datetime.now(timezone.utc)),
            expires_at=default_data["expires_at"],
            source_posts=default_data.get("source_posts", []),
        )

        session.add(model)
        session.commit()

        logger.info(f"Created new post context for {creator_id}")
        return _model_to_dict(model)

    except Exception as e:
        logger.error(f"Error in get_or_create for {creator_id}: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def get_expired_contexts() -> List[Dict[str, Any]]:
    """Get all expired PostContexts that need refresh.

    Returns:
        List of expired context dicts
    """
    session = get_session()
    if not session:
        return []

    try:
        from api.models import PostContextModel

        now = datetime.now(timezone.utc)
        rows = session.query(PostContextModel).filter(
            PostContextModel.expires_at < now
        ).all()

        return [_model_to_dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Error getting expired contexts: {e}")
        return []
    finally:
        session.close()


def _model_to_dict(row) -> Dict[str, Any]:
    """Convert SQLAlchemy model to dictionary.

    Args:
        row: PostContextModel instance

    Returns:
        Dict with context data
    """
    return {
        "id": str(row.id) if row.id else None,
        "creator_id": row.creator_id,
        "active_promotion": row.active_promotion,
        "promotion_deadline": row.promotion_deadline,
        "promotion_urgency": row.promotion_urgency,
        "recent_topics": row.recent_topics or [],
        "recent_products": row.recent_products or [],
        "availability_hint": row.availability_hint,
        "context_instructions": row.context_instructions,
        "posts_analyzed": row.posts_analyzed,
        "analyzed_at": row.analyzed_at,
        "expires_at": row.expires_at,
        "source_posts": row.source_posts or [],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _context_to_model(ctx):
    """Convert PostContext dataclass to SQLAlchemy model.

    Args:
        ctx: PostContext instance

    Returns:
        PostContextModel instance
    """
    from api.models import PostContextModel

    return PostContextModel(
        creator_id=ctx.creator_id,
        active_promotion=ctx.active_promotion,
        promotion_deadline=ctx.promotion_deadline,
        promotion_urgency=ctx.promotion_urgency,
        recent_topics=ctx.recent_topics,
        recent_products=ctx.recent_products,
        availability_hint=ctx.availability_hint,
        context_instructions=ctx.context_instructions,
        posts_analyzed=ctx.posts_analyzed,
        analyzed_at=ctx.analyzed_at,
        expires_at=ctx.expires_at,
        source_posts=ctx.source_posts,
    )
