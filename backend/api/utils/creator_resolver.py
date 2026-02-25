"""Shared creator resolution logic — replaces 20+ duplicated lookup patterns."""
import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def resolve_creator(session: Session, creator_id: str):
    """
    Resolve a creator by name (slug) or UUID string.

    Args:
        session: SQLAlchemy session
        creator_id: Creator name or UUID

    Returns:
        Creator instance

    Raises:
        HTTPException(404) if not found
    """
    from api.models import Creator

    # Try by name first (most common path)
    creator = session.query(Creator).filter_by(name=creator_id).first()

    # Fallback: try by UUID
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
        raise HTTPException(status_code=404, detail=f"Creator '{creator_id}' not found")

    return creator


def resolve_creator_safe(session: Session, creator_id: str):
    """
    Like resolve_creator but returns None instead of raising.
    Use in services that return dicts instead of raising HTTPException.
    """
    from api.models import Creator

    creator = session.query(Creator).filter_by(name=creator_id).first()
    if not creator:
        try:
            creator = (
                session.query(Creator)
                .filter(text("id::text = :cid"))
                .params(cid=creator_id)
                .first()
            )
        except Exception:
            pass
    return creator
